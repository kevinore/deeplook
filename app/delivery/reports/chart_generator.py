"""
Generate charts as base64-encoded PNG images for embedding in HTML reports.

Design principles (DeepLook Report Design Guide):
- Every chart title IS the insight, not a category label
- Traffic-light colors: teal (#1D9E75), amber (#EF9F27), coral (#D85A30)
- Spanish throughout
- Flat 2D only — no 3D, no radar/spider charts
- Horizontal bars for category data; vertical bars for time-based data
- Value labels at end of every bar
- Remove top and right spines; keep only needed gridlines
- All charts share the same canvas size (_W × _H) for visual consistency
"""
from app.models.schemas import ConversationAnalysisResult
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import base64
import io
from collections import Counter

import matplotlib
from matplotlib.ticker import MaxNLocator
matplotlib.use("Agg")


# ── Color palette ─────────────────────────────────────────────────────────────
TEAL = "#16a34a"
TEAL_DARK = "#15803d"
TEAL_LIGHT = "#86efac"
AMBER = "#EF9F27"
CORAL = "#D85A30"
GRAY = "#6B7280"
LIGHT_GRAY = "#F5F5F4"

# ── Standard canvas — every chart uses this size so they appear uniform ───────
_W: float = 6.5   # width  (inches)
_H: float = 2.5   # height (inches)

# ── LATAM response-time thresholds (seconds) ──────────────────────────────────
_RT_EXCELLENT = 300    # < 5 min  → teal
_RT_ACCEPTABLE = 1800   # < 30 min → amber
# ≥ 30 min → coral

# ── Shared rcParams applied via plt.rc_context() in every function ────────────
_CHART_STYLE: dict = {
    "font.family":      "sans-serif",
    "font.size":        9.5,
    "axes.titlesize":   9.5,      # chart titles same weight as body text in PDF
    "axes.titleweight": "bold",
    "axes.labelsize":   9.0,
    "xtick.labelsize":  8.5,
    "ytick.labelsize":  8.5,
    "figure.facecolor": "white",
    "axes.facecolor":   "white",
    "axes.edgecolor":   "#CCCCCC",
    "axes.linewidth":   0.7,
    "xtick.major.size": 0,
    "ytick.major.size": 2,
    "axes.axisbelow":   True,
}

_GRID_X = dict(axis="x", color="#EBEBEB", linewidth=0.55, zorder=0)
_GRID_Y = dict(axis="y", color="#EBEBEB", linewidth=0.55, zorder=0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _traffic_light_color(value_seconds: float) -> str:
    if value_seconds <= _RT_EXCELLENT:
        return TEAL
    if value_seconds <= _RT_ACCEPTABLE:
        return AMBER
    return CORAL


def _hour_label(h: int) -> str:
    """Compact 12-hour AM/PM label."""
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180,
                bbox_inches="tight", facecolor="white")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


# ── Chart functions ───────────────────────────────────────────────────────────

def sentiment_donut_chart(results: list[ConversationAnalysisResult]) -> str:
    """
    Centered donut with sentiment breakdown below.
    Donut occupies the upper portion of the canvas, horizontally centered.
    Title above donut; below: ● Label + percentage for each sentiment, evenly spaced.
    """
    sentiments = [
        r.sentiment.value if r.sentiment else "neutral" for r in results]
    counter = Counter(sentiments)
    total = len(results) or 1

    color_map = {"positive": TEAL, "neutral": GRAY, "negative": CORAL}
    label_map = {"positive": "Positivo", "neutral": "Neutral", "negative": "Negativo"}

    rows = [
        (key, label_map[key], counter.get(key, 0))
        for key in ("positive", "neutral", "negative")
        if counter.get(key, 0) > 0
    ]

    sizes, colors = [], []
    for key in ("positive", "neutral", "negative"):
        count = counter.get(key, 0)
        if count > 0:
            sizes.append(count)
            colors.append(color_map[key])

    if not sizes:
        sizes, colors = [1], [LIGHT_GRAY]
        rows = []

    dominant_key = max(("positive", "neutral", "negative"),
                       key=lambda k: counter.get(k, 0))
    dom_pct = counter.get(dominant_key, 0) / total * 100
    dom_label = label_map.get(dominant_key, "")
    dom_color = color_map.get(dominant_key, GRAY)

    _DONUT_H: float = 3.0   # compact height — enough room for the donut without excess whitespace

    with plt.rc_context(_CHART_STYLE):
        fig = plt.figure(figsize=(_W, _DONUT_H), facecolor="white")

        fig.suptitle("Distribución de Sentimiento",
                     fontsize=9.5, fontweight="bold", ha="left", x=0.01, y=0.98)

        # Full-width invisible axes — anchors bbox_inches="tight" to the complete
        # canvas so this chart saves at the correct pixel width as all others.
        ax_bg = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax_bg.axis("off")

        # Centered square donut axes — fraction calculated against _DONUT_H
        donut_h_frac = 0.78                            # 0.78 × 4.0 = 3.12 in
        donut_w_frac = donut_h_frac * _DONUT_H / _W   # keeps axes square
        left = (1.0 - donut_w_frac) / 2
        ax_d = fig.add_axes([left, 0.14, donut_w_frac, donut_h_frac])
        ax_d.pie(
            sizes,
            colors=colors,
            startangle=90,
            wedgeprops={"width": 0.52, "linewidth": 2.5, "edgecolor": "white"},
        )
        # Center hole: dominant % + label
        ax_d.text(0,  0.12, f"{dom_pct:.0f}%",
                  ha="center", va="center", fontsize=11,
                  fontweight="bold", color=dom_color)
        ax_d.text(0, -0.22, dom_label,
                  ha="center", va="center", fontsize=9.0, color=dom_color)

        # ── Bottom row: compact, centered below the donut ─────────────────────
        if rows:
            n = len(rows)
            spacing = 0.13   # figure-fraction spacing between items
            xs = [0.5 + (i - (n - 1) / 2) * spacing for i in range(n)]
            for (key, label, count), x in zip(rows, xs):
                pct = count / total * 100
                color = color_map[key]
                ax_bg.text(x, 0.09, f"● {label}",
                           transform=ax_bg.transAxes,
                           fontsize=9.5, fontweight="600", color=color,
                           ha="center", va="center")
                ax_bg.text(x, 0.03, f"{pct:.0f}%",
                           transform=ax_bg.transAxes,
                           fontsize=9.5, fontweight="bold", color=color,
                           ha="center", va="center")

        return _fig_to_base64(fig)


# Backwards-compat alias
sentiment_pie_chart = sentiment_donut_chart


def response_time_by_hour_chart(by_hour: dict[int, float]) -> str:
    """
    Vertical bar chart of median response time by hour (Colombia local time).

    Design decisions:
    - Symlog Y-axis (linear 0–60 min, log above): keeps fast bars (5 min) and
      slow bars (72 h) visible on the same chart without distortion.
    - Y-axis ticks in human-readable format (5m, 15m, 1h, 4h, 24h…) instead of
      raw minutes — consistent with the value labels on each bar.
    - Bar value labels always shown in h/m adaptive format.
    """
    if not by_hour:
        with plt.rc_context(_CHART_STYLE):
            fig, ax = plt.subplots(figsize=(_W, _H), constrained_layout=True)
            ax.text(0.5, 0.5, "Sin datos de tiempo de respuesta por hora",
                    ha="center", va="center", transform=ax.transAxes,
                    color=GRAY, fontsize=10)
            ax.axis("off")
            return _fig_to_base64(fig)

    SEGMENTS = [
        ("Mañana",  range(6, 12)),
        ("Tarde",   range(12, 18)),
        ("Noche",   range(18, 24)),
        ("Madrugada", range(0, 6)),
    ]

    positions: list[float] = []
    values_min: list[float] = []
    bar_colors: list[str] = []
    tick_labels: list[str] = []
    segment_centers: list[tuple[float, str]] = []
    segment_edges: list[float] = []

    cursor = 0.0
    SEG_PADDING = 1.2
    BAR_WIDTH = 0.85
    for seg_name, seg_hours in SEGMENTS:
        present = [h for h in seg_hours if h in by_hour]
        if not present:
            continue
        seg_start = cursor
        for h in present:
            v_sec = by_hour[h]
            v_min = v_sec / 60.0
            positions.append(cursor)
            values_min.append(v_min)
            bar_colors.append(_traffic_light_color(v_sec))
            tick_labels.append(_hour_label(h))
            cursor += 1
        seg_end = cursor - 1
        segment_centers.append(((seg_start + seg_end) / 2, seg_name))
        segment_edges.append(cursor - 0.5)
        cursor += SEG_PADDING

    if not positions:
        with plt.rc_context(_CHART_STYLE):
            fig, ax = plt.subplots(figsize=(_W, _H), constrained_layout=True)
            ax.text(0.5, 0.5, "Sin datos de tiempo de respuesta por hora",
                    ha="center", va="center", transform=ax.transAxes, color=GRAY)
            ax.axis("off")
            return _fig_to_base64(fig)

    max_val_min = max(values_min)
    n_bars = len(positions)
    fig_w = max(_W, 0.55 * n_bars + 1.5)

    # Symlog threshold: linear scale up to 60 min (1 h), log above.
    # This makes 5m bars and 72h bars both clearly visible.
    LINTHRESH = 60.0

    # Human-readable Y-axis tick marks (in minutes).
    _YTICK_MIN  = [5, 15, 30, 60, 240, 480, 1440, 4320]  # 5m 15m 30m 1h 4h 8h 24h 72h
    _YTICK_LBL  = ["5m", "15m", "30m", "1h", "4h", "8h", "24h", "72h"]
    yticks = [v for v in _YTICK_MIN if v <= max_val_min * 1.5]
    ylabels = [_YTICK_LBL[i] for i, v in enumerate(_YTICK_MIN) if v <= max_val_min * 1.5]
    # Always include at least the first tick and one above the max bar
    if not yticks:
        yticks, ylabels = [_YTICK_MIN[0]], [_YTICK_LBL[0]]

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(fig_w, 3.2))

        ax.bar(positions, values_min, width=BAR_WIDTH,
               color=bar_colors, edgecolor="white", linewidth=0.8, zorder=2)

        # Symlog scale keeps tiny and huge bars both visible.
        ax.set_yscale("symlog", linthresh=LINTHRESH, linscale=0.5)
        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels, fontsize=8)

        # Value labels above each bar — adaptive h/m format.
        for x, val in zip(positions, values_min):
            lbl = f"{val:.0f}m" if val < 60 else f"{val / 60:.1f}h"
            # Place label just above the bar; on symlog axis use a small
            # multiplicative offset so it stays above at any scale.
            y_label = val * 1.25 if val >= LINTHRESH else val + LINTHRESH * 0.12
            ax.text(x, y_label, lbl,
                    ha="center", va="bottom",
                    fontsize=7.5, fontweight="600", color="#333")

        # Subtle horizontal reference line at 5 min (Excelente threshold).
        ax.axhline(y=5, color=TEAL, linewidth=0.7, linestyle=":", alpha=0.6, zorder=1)
        ax.axhline(y=30, color=AMBER, linewidth=0.7, linestyle=":", alpha=0.5, zorder=1)

        # Vertical segment separators.
        for edge in segment_edges[:-1]:
            ax.axvline(x=edge + SEG_PADDING / 2, color="#DDDDDD",
                       linewidth=1.0, linestyle="--", zorder=1)

        # Segment titles — use a blended transform: data X, axes-fraction Y.
        # This avoids symlog coordinate distortion and always places the label
        # at a fixed height (88% up the axes) regardless of the Y scale range.
        import matplotlib.transforms as _transforms
        _blended = _transforms.blended_transform_factory(ax.transData, ax.transAxes)
        for center, name in segment_centers:
            ax.text(center, 0.88, name,
                    ha="center", va="top",
                    fontsize=9, fontweight="700", color="#0e0749",
                    transform=_blended)

        ax.set_xticks(positions)
        ax.set_xticklabels(tick_labels, fontsize=8, rotation=45, ha="right")
        ax.set_ylabel("Tiempo de respuesta", fontsize=9, labelpad=4)
        ax.set_ylim(bottom=0)
        ax.set_xlim(min(positions) - 0.8, max(positions) + 0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#EBEBEB", linewidth=0.55, zorder=0)

        legend_handles = [
            mpatches.Patch(facecolor=TEAL,  label="< 5 min — Excelente"),
            mpatches.Patch(facecolor=AMBER, label="5–30 min — Regular"),
            mpatches.Patch(facecolor=CORAL, label="> 30 min — Crítico"),
        ]
        ax.legend(handles=legend_handles,
                  loc="lower center",
                  bbox_to_anchor=(0.5, 1.0),
                  ncol=3, fontsize=7.5, frameon=False,
                  columnspacing=1.0, handlelength=1.0)

        fig.suptitle("¿A qué hora respondes más lento?",
                     fontsize=9.5, fontweight="bold", ha="left", x=0.01, y=1.0)
        fig.tight_layout(rect=[0, 0, 1, 0.88])
        return _fig_to_base64(fig)


def topics_bar_chart(results: list[ConversationAnalysisResult], top_n: int = 8) -> str:
    """
    Horizontal bar chart of top conversation topics, sorted descending.
    Top bar highlighted in deep teal. Labels truncated at 28 chars.
    Fixed canvas (_W × _H).
    """
    topics = [r.primary_topic for r in results if r.primary_topic]
    counter = Counter(topics)
    # Stable sort: count DESC, topic text ASC — deterministic when counts are tied
    most_common = sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:top_n]

    if not most_common:
        with plt.rc_context(_CHART_STYLE):
            fig, ax = plt.subplots(figsize=(_W, _H), constrained_layout=True)
            ax.text(0.5, 0.5, "Sin datos de temas",
                    ha="center", va="center", transform=ax.transAxes,
                    color=GRAY, fontsize=10)
            ax.axis("off")
            return _fig_to_base64(fig)

    MAX_LBL = 35

    def _truncate_label(text: str, max_len: int = MAX_LBL) -> str:
        if len(text) <= max_len:
            return text
        # Truncate at word boundary
        truncated = text[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            truncated = truncated[:last_space]
        return truncated + "…"

    labels = [_truncate_label(t).title() for t, _ in most_common][::-1]
    values = [v for _, v in most_common][::-1]
    total = len(results) or 1
    max_val = max(values) if values else 1

    # Highest bar gets the deep-teal highlight
    bar_colors = [TEAL_DARK if i == len(labels) - 1 else TEAL
                  for i in range(len(labels))]

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(_W, _H))

        bars = ax.barh(labels, values,
                       color=bar_colors, edgecolor="white", linewidth=0.8, height=0.5)

        for bar, val in zip(bars, values):
            pct = val / total * 100
            ax.text(
                bar.get_width() + max_val * 0.025,
                bar.get_y() + bar.get_height() / 2,
                f"{pct:.0f}% ({val})",
                va="center", ha="left", fontsize=8.5, color="#333333",
            )

        fig.suptitle("¿Sobre qué preguntan tus clientes?",
                     fontsize=9.5, fontweight="bold", ha="left", x=0.01)
        ax.set_xlabel("Conversaciones", fontsize=9, labelpad=4)
        ax.set_xlim(0, max_val * 1.32)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(left=False)
        ax.grid(**_GRID_X)
        fig.tight_layout(rect=[0, 0, 1, 0.90])
        return _fig_to_base64(fig)


def quality_bars_chart(
    results: list[ConversationAnalysisResult],
    unanswered_excluded: int = 0,
) -> str:
    """
    Horizontal bar chart of 3 quality dimensions (0–10).

    `results` should be the answered-only subset so the bars reflect real
    communication quality without being dragged down by the 0/0/0 scores
    that unanswered conversations receive by the AI rule.

    `unanswered_excluded`: how many conversations were excluded (shown as a
    subtitle note when > 0 so the reader understands the scope).
    """
    dims = ["helpfulness", "tone", "completeness"]
    dim_labels = ["Utilidad", "Tono", "Completitud"]

    avgs: list[float] = []
    for dim in dims:
        scores = [getattr(r.quality_breakdown, dim)
                  for r in results if r.quality_breakdown]
        avgs.append(sum(scores) / len(scores) if scores else 0.0)

    bar_colors = [TEAL if v >= 7 else (
        AMBER if v >= 5 else CORAL) for v in avgs]

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(_W, 2.0))

        # Subtle background zone shading
        ax.axvspan(0,  5, alpha=0.045, color=CORAL, zorder=0)
        ax.axvspan(5,  7, alpha=0.045, color=AMBER, zorder=0)
        ax.axvspan(7, 10, alpha=0.045, color=TEAL,  zorder=0)

        bars = ax.barh(dim_labels, avgs,
                       color=bar_colors, edgecolor="white",
                       linewidth=0.8, zorder=2)

        # Title — adds scope note when unanswered conversations were excluded
        title = "Desglose de Calidad de Atención"
        if unanswered_excluded > 0:
            noun = "conversación" if unanswered_excluded == 1 else "conversaciones"
            subtitle = (
                f"Solo conversaciones respondidas  ·  "
                f"{unanswered_excluded} {noun} sin respuesta excluida{'s' if unanswered_excluded > 1 else ''} "
                f"(calidad 0/10 — ver Cobertura de Respuestas)"
            )
        else:
            subtitle = None

        fig.suptitle(title, fontsize=9.5, fontweight="bold", ha="left", x=0.01)
        if subtitle:
            fig.text(0.01, 0.92, subtitle,
                     fontsize=7.0, color="#888888", ha="left", va="top",
                     transform=fig.transFigure)

        ax.set_xlim(0, 10)
        ax.set_xlabel("Puntaje promedio (0–10)", fontsize=9, labelpad=4)

        # Benchmark dashed line at 7.0
        ax.axvline(x=7.0, color="#AAAAAA", linewidth=1.3,
                   linestyle="--", zorder=3)
        ax.text(7.1, len(dim_labels) - 0.5, "Objetivo\n7.0",
                fontsize=7.0, color="#999999", va="top", ha="left", zorder=4)

        for bar, val in zip(bars, avgs):
            if 5.8 <= val <= 7.5:
                ax.text(
                    max(val - 0.2, 0.15),
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}",
                    va="center", ha="right",
                    fontsize=9, fontweight="600",
                    color="#333333" if val < 7.0 else "white",
                    zorder=5,
                )
            else:
                ax.text(
                    min(val + 0.18, 9.55),
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}",
                    va="center", ha="left",
                    fontsize=9, fontweight="600", color="#222222", zorder=5,
                )

        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(left=False)
        ax.grid(**_GRID_X)
        top_margin = 0.82 if subtitle else 0.88
        fig.tight_layout(rect=[0, 0, 1, top_margin])
        return _fig_to_base64(fig)


def volume_by_hour_chart(by_hour: dict[int, int]) -> str:
    """
    Vertical bar chart of message volume by hour of day.
    Business hours (8–18 h) in teal, after-hours in gray.
    X-axis labels every 3 hours to avoid crowding.
    Fixed canvas (_W × _H).
    """
    hours = list(range(24))
    values = [by_hour.get(h, 0) for h in hours]
    colors = [TEAL if 8 <= h <= 18 else GRAY for h in hours]

    xtick_labels = [
        (_hour_label(h).replace(" ", "\n") if h % 3 == 0 else "")
        for h in hours
    ]

    with plt.rc_context(_CHART_STYLE):
        fig, ax = plt.subplots(figsize=(_W, _H))
        ax.bar(hours, values, color=colors, edgecolor="white",
               linewidth=0.5, width=0.78)

        fig.suptitle("¿Cuándo te escriben tus clientes?",
                     fontsize=9.5, fontweight="bold", ha="left", x=0.01)
        ax.set_xlabel("Hora del día", fontsize=9, labelpad=4)
        ax.set_ylabel("Mensajes", fontsize=9, labelpad=4)
        ax.set_xticks(hours)
        ax.set_xticklabels(xtick_labels, fontsize=7.5, linespacing=1.1)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(**_GRID_Y)

        legend_handles = [
            mpatches.Patch(facecolor=TEAL, label="Horario laboral (8h–18h)"),
            mpatches.Patch(facecolor=GRAY, label="Fuera de horario"),
        ]
        ax.legend(handles=legend_handles, loc="upper right",
                  fontsize=7.5, framealpha=0.95, edgecolor="#DDDDDD")
        fig.tight_layout(rect=[0, 0, 1, 0.90])
        return _fig_to_base64(fig)


def messages_per_day_chart(results: list[ConversationAnalysisResult]) -> str | None:
    """Placeholder — only meaningful with multi-day time-series data."""
    return None
