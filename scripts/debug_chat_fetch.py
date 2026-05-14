"""
Debug script: trace exactly what happens during a WAHA sync for a given session.

Shows the full funnel:
  Total chats from WAHA
  → After removing groups
  → After removing archived
  → After applying plan cap
  → After fetching messages (with since_ts filter)
  → After min_messages filter
  → Final conversations analyzed

Usage:
    python scripts/debug_chat_fetch.py [session_name] [plan]

Defaults: session_name=test, plan=basic
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.integrations.waha.client import WahaClient
from app.integrations.waha.models import WahaChatOverview

SESSION   = sys.argv[1] if len(sys.argv) > 1 else "test"
PLAN      = sys.argv[2] if len(sys.argv) > 2 else "basic"

_LOOKBACK_BY_PLAN = {"basic": 32, "plus": 92, "enterprise": 182, "free": 32}
_MAX_CHATS_BY_PLAN = {"basic": 130, "plus": 380, "enterprise": 1200, "free": 130}
_CONV_LIMIT_BY_PLAN = {"basic": 100, "plus": 300, "enterprise": 1000, "free": 100}

LOOKBACK_DAYS = _LOOKBACK_BY_PLAN.get(PLAN, 30)
MAX_CHATS     = _MAX_CHATS_BY_PLAN.get(PLAN, 130)
CONV_LIMIT    = _CONV_LIMIT_BY_PLAN.get(PLAN, 100)

SEP = "─" * 70


async def run():
    from app.config import settings
    client = WahaClient(base_url=settings.waha_base_url, api_key=settings.waha_api_key)

    now   = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=LOOKBACK_DAYS)
    since_ts = int(since.timestamp())

    print(SEP)
    print(f"  DEBUG CHAT FETCH  |  session={SESSION}  plan={PLAN}")
    print(f"  Lookback: {LOOKBACK_DAYS} days  ({since.date()} → {now.date()})")
    print(f"  Plan cap: {CONV_LIMIT} conversations  (fetch buffer: {MAX_CHATS} chats)")
    print(SEP)

    # ── STEP 1: Raw list_chats ────────────────────────────────────────────────
    print("\n[STEP 1] Fetching all chats from WAHA...")
    all_chats: list[WahaChatOverview] = await client.list_chats(SESSION, limit=2000)
    print(f"  Total chats returned by WAHA:          {len(all_chats)}")

    type_counts: dict[str, int] = {}
    for c in all_chats:
        key = "group (@g.us)" if c.id.endswith("@g.us") else \
              "broadcast (@broadcast)" if c.id.endswith("@broadcast") else \
              "DM (@c.us / @lid)"
        type_counts[key] = type_counts.get(key, 0) + 1
    for k, v in sorted(type_counts.items()):
        print(f"    {k}: {v}")

    # ── STEP 2: Group detection — DOUBLE validation ───────────────────────────
    from app.config import settings as app_settings
    include_groups = getattr(app_settings, "waha_include_groups", False)

    def _is_group(chat) -> bool:
        return chat.isGroup or chat.id.endswith("@g.us")

    groups_by_flag   = [c for c in all_chats if c.isGroup]
    groups_by_suffix = [c for c in all_chats if c.id.endswith("@g.us")]
    groups_both      = [c for c in all_chats if c.isGroup and c.id.endswith("@g.us")]
    groups_only_flag = [c for c in all_chats if c.isGroup and not c.id.endswith("@g.us")]
    groups_only_sfx  = [c for c in all_chats if not c.isGroup and c.id.endswith("@g.us")]
    total_groups     = [c for c in all_chats if _is_group(c)]

    print(f"\n[STEP 2] Group detection — WAHA_INCLUDE_GROUPS={str(include_groups).lower()}:")
    print(f"  Detected by isGroup=True:              {len(groups_by_flag)}")
    print(f"  Detected by @g.us suffix:              {len(groups_by_suffix)}")
    print(f"  Detected by BOTH (fully confirmed):    {len(groups_both)}")
    if groups_only_flag:
        print(f"  ⚠️  isGroup=True but NOT @g.us:         {len(groups_only_flag)}  ← caught by double-check!")
        for c in groups_only_flag:
            print(f"       • {c.name or c.id}")
    if groups_only_sfx:
        print(f"  ⚠️  @g.us suffix but isGroup=False:     {len(groups_only_sfx)}  ← caught by double-check!")
    print(f"  Total groups excluded (either check):  {len(total_groups)}")

    if include_groups:
        dm_chats = all_chats
    else:
        dm_chats = [c for c in all_chats if not _is_group(c)]
    groups_removed = len(all_chats) - len(dm_chats)
    print(f"  {'All chats kept' if include_groups else 'DM chats remaining'}:             {len(dm_chats)}")

    # ── STEP 3: Remove archived ───────────────────────────────────────────────
    non_archived = [c for c in dm_chats if not c.archived]
    muted        = [c for c in non_archived if c.isMuted]
    archived_removed = len(dm_chats) - len(non_archived)
    print(f"\n[STEP 3] After removing archived chats:")
    print(f"  Archived removed:                      {archived_removed}")
    print(f"  Muted (kept, just flagged):             {len(muted)}")
    print(f"  Visible DM chats:                      {len(non_archived)}")

    # ── STEP 4: Apply plan cap ────────────────────────────────────────────────
    capped = non_archived[:MAX_CHATS]
    cap_removed = len(non_archived) - len(capped)
    print(f"\n[STEP 4] After applying plan cap ({MAX_CHATS}):")
    print(f"  Chats cut by plan cap:                 {cap_removed}")
    print(f"  Chats to fetch messages for:           {len(capped)}")

    # ── STEP 4b: Pre-filter by chat.timestamp ─────────────────────────────────
    chats_to_fetch = []
    pre_skipped = 0
    for chat in capped:
        last_ts = chat.timestamp or 0
        if last_ts > 0 and last_ts < since_ts:
            pre_skipped += 1
        else:
            chats_to_fetch.append(chat)
    print(f"\n[STEP 4b] Pre-filter by chat.timestamp (NEW OPTIMIZATION):")
    print(f"  Chats skipped — last activity BEFORE {since.date()}: {pre_skipped}")
    print(f"  Chats to actually fetch messages for:              {len(chats_to_fetch)}")
    print(f"  API calls saved vs old flow:                       {pre_skipped}")

    # ── STEP 5: Fetch messages per chat ──────────────────────────────────────
    print(f"\n[STEP 5] Fetching messages (since {since.date()})...")
    print(f"  This may take a moment ({len(chats_to_fetch)} chats × up to 500 msgs/page)...")

    results = []
    no_msgs_in_window   = 0
    only_1_msg          = 0
    has_2plus_msgs      = 0
    fetch_errors        = 0

    for i, chat in enumerate(chats_to_fetch, 1):
        phone = chat.id.split("@")[0]
        try:
            msgs = await client.get_chat_messages(SESSION, chat.id, limit=500, since_ts=since_ts)
            n = len(msgs)
            inbound  = sum(1 for m in msgs if not m.fromMe)
            outbound = sum(1 for m in msgs if m.fromMe)
            last_from_me = chat.lastMessage.fromMe if chat.lastMessage else None

            results.append({
                "phone": phone,
                "name": chat.name or "(sin nombre)",
                "total_msgs_in_window": n,
                "inbound": inbound,
                "outbound": outbound,
                "unread": chat.unreadCount,
                "muted": chat.isMuted,
                "last_from_me": last_from_me,
            })

            if n == 0:
                no_msgs_in_window += 1
            elif n == 1:
                only_1_msg += 1
            else:
                has_2plus_msgs += 1

        except Exception as exc:
            fetch_errors += 1
            results.append({"phone": phone, "name": chat.name or "?", "error": str(exc)})

        if i % 10 == 0:
            print(f"    Progress: {i}/{len(capped)} chats processed...")

    print(f"\n  Message fetch results:")
    print(f"    0 msgs in window (would be DROPPED):  {no_msgs_in_window}")
    print(f"    1 msg  in window (kept with new rule): {only_1_msg}")
    print(f"    2+ msgs in window:                    {has_2plus_msgs}")
    print(f"    Fetch errors (skipped):               {fetch_errors}")

    # ── STEP 6: Apply min_messages filter ─────────────────────────────────────
    kept_old = [r for r in results if r.get("total_msgs_in_window", 0) >= 2]
    kept_new = [r for r in results if r.get("total_msgs_in_window", 0) >= 1]
    dropped_by_min = len(results) - len(kept_new)

    print(f"\n[STEP 6] After min_messages filter:")
    print(f"  Old rule (≥2): would keep              {len(kept_old)} conversations")
    print(f"  New rule (≥1): keeps                   {len(kept_new)} conversations")
    print(f"  Gained by lowering threshold:          {len(kept_new) - len(kept_old)}")

    # ── STEP 7: Apply plan conv_limit ─────────────────────────────────────────
    final = kept_new[:CONV_LIMIT]
    print(f"\n[STEP 7] After plan conversation cap ({CONV_LIMIT}):")
    print(f"  FINAL conversations analyzed:          {len(final)}")

    # ── STEP 8: Unanswered breakdown ─────────────────────────────────────────
    unanswered_by_last_msg   = [r for r in final if r.get("last_from_me") is False]
    unanswered_by_unread     = [r for r in final if (r.get("unread") or 0) > 0]
    unanswered_no_outbound   = [r for r in final if r.get("outbound", 1) == 0]

    print(f"\n[STEP 8] Unanswered analysis (of {len(final)} final conversations):")
    print(f"  wa_last_message_from_me=False:         {len(unanswered_by_last_msg)}  ← our 'sin responder'")
    print(f"  unread_count > 0:                      {len(unanswered_by_unread)}  ← WhatsApp 'no leídos'")
    print(f"  0 outbound messages (never replied):   {len(unanswered_no_outbound)}")

    # ── FUNNEL SUMMARY ────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print(f"  FUNNEL SUMMARY")
    print(f"{SEP}")
    print(f"  WAHA total chats:          {len(all_chats):>5}")
    print(f"  − groups:                  {groups_removed:>5}")
    print(f"  − archived:                {archived_removed:>5}")
    print(f"  = visible DMs:             {len(non_archived):>5}")
    print(f"  − plan cap (>{MAX_CHATS}): {cap_removed:>5}")
    print(f"  = chats fetched:           {len(capped):>5}")
    print(f"  − 0 msgs in window:        {no_msgs_in_window:>5}")
    print(f"  − fetch errors:            {fetch_errors:>5}")
    print(f"  = with ≥1 msg:             {len(kept_new):>5}")
    print(f"  − plan conv cap (>{CONV_LIMIT}): {max(0, len(kept_new)-CONV_LIMIT):>4}")
    print(f"  = FINAL analyzed:          {len(final):>5}")
    print(SEP)

    # ── SECTION A: UNANSWERED CHATS (details) ────────────────────────────────
    unanswered_detail = [r for r in final if r.get("last_from_me") is False]
    print(f"\n{'═'*70}")
    print(f"  SECCIÓN A — CLIENTES ESPERANDO RESPUESTA ({len(unanswered_detail)} chats)")
    print(f"  (wa_last_message_from_me = False → cliente escribió último)")
    print(f"{'═'*70}")
    print(f"  {'#':<3} {'Nombre / Número':<35} {'Msgs':>4} {'In':>4} {'Out':>4} {'Unread':>7}")
    print(f"  {'─'*65}")
    for i, r in enumerate(sorted(unanswered_detail, key=lambda x: -(x.get("unread") or 0)), 1):
        unread_flag = " ★ NO LEÍDO" if (r.get("unread") or 0) > 0 else ""
        no_reply_flag = " ✗ NUNCA RESPONDIDO" if r.get("outbound", 1) == 0 else ""
        label = r["name"] if r["name"] != r["phone"] else r["phone"]
        print(f"  {i:<3} {label[:35]:<35} {r['total_msgs_in_window']:>4} "
              f"{r['inbound']:>4} {r['outbound']:>4} {(r.get('unread') or 0):>7}"
              f"{unread_flag}{no_reply_flag}")

    # ── SECTION B: EXCLUDED CHATS (with reason) ──────────────────────────────
    print(f"\n{'═'*70}")
    print(f"  SECCIÓN B — CHATS EXCLUIDOS Y POR QUÉ")
    print(f"{'═'*70}")

    # B1 — Groups
    groups = [c for c in all_chats if c.id.endswith("@g.us")]
    print(f"\n  B1. GRUPOS ({len(groups)}) — la cuenta ES MIEMBRO de estos grupos:")
    print(f"      (No son conversaciones con clientes → siempre excluidos)")
    for g in groups[:20]:
        print(f"      • {g.name or g.id}")
    if len(groups) > 20:
        print(f"      ... y {len(groups)-20} más")

    # B2 — Archived
    archived_list = [c for c in dm_chats if c.archived]
    if archived_list:
        print(f"\n  B2. ARCHIVADOS ({len(archived_list)}) — el negocio los archivó en WhatsApp:")
        for c in archived_list:
            label = c.name or c.id.split("@")[0]
            print(f"      • {label}")
    else:
        print(f"\n  B2. ARCHIVADOS: ninguno")

    # B3 — Cut by plan cap
    cut_chats = non_archived[MAX_CHATS:]
    print(f"\n  B3. CORTADOS POR CUPO DEL PLAN ({len(cut_chats)}) — más allá del límite {MAX_CHATS}:")
    if cut_chats:
        print(f"      (Son los {len(cut_chats)} contactos menos recientes — podrían tener mensajes este mes)")
        for c in cut_chats[:15]:
            label = c.name or c.id.split("@")[0]
            last_ts = datetime.fromtimestamp(c.timestamp, tz=timezone.utc).strftime("%d/%m/%Y") if c.timestamp else "?"
            print(f"      • {label:<35} último mensaje: {last_ts}")
        if len(cut_chats) > 15:
            print(f"      ... y {len(cut_chats)-15} más")
    else:
        print(f"      ninguno")

    # B4 — No messages in window
    no_msg_chats = [r for r in results if r.get("total_msgs_in_window", 0) == 0]
    print(f"\n  B4. SIN MENSAJES EN LOS ÚLTIMOS {LOOKBACK_DAYS} DÍAS ({len(no_msg_chats)}):")
    print(f"      (Contactos que no escribieron ni recibieron mensajes este mes)")
    for r in no_msg_chats[:15]:
        label = r["name"] if r["name"] != r["phone"] else r["phone"]
        unread_note = f" [UNREAD:{r.get('unread')}]" if (r.get("unread") or 0) > 0 else ""
        print(f"      • {label}{unread_note}")
    if len(no_msg_chats) > 15:
        print(f"      ... y {len(no_msg_chats)-15} más")

    # ── SECTION C: FINAL INCLUDED CHATS ──────────────────────────────────────
    print(f"\n{'═'*70}")
    print(f"  SECCIÓN C — CHATS ANALIZADOS EN EL REPORTE ({len(final)})")
    print(f"{'═'*70}")
    print(f"  {'#':<3} {'Nombre / Número':<35} {'Msgs':>4} {'In':>4} {'Out':>4} {'Estado'}")
    print(f"  {'─'*70}")
    for i, r in enumerate(sorted(final, key=lambda x: -x.get("total_msgs_in_window", 0)), 1):
        if r.get("last_from_me") is False:
            status = "⚠ SIN RESPONDER"
        elif r.get("last_from_me") is True:
            status = "✓ Respondido"
        else:
            status = "? Desconocido"
        if (r.get("unread") or 0) > 0:
            status += " [NO LEÍDO]"
        label = r["name"] if r["name"] != r["phone"] else r["phone"]
        print(f"  {i:<3} {label[:35]:<35} {r['total_msgs_in_window']:>4} "
              f"{r['inbound']:>4} {r['outbound']:>4}  {status}")

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(run())
