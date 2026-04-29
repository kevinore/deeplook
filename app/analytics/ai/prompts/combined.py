"""
Combined analysis prompt — one call extracts all analysis fields.

v4 (2026-04-28):
  • DROPPED speed_perception from quality_breakdown (P1).
    Speed of response is now measured deterministically via timestamps —
    asking the AI to also "guess speed from the text" produced a noisy second
    opinion. Quality is rated on three dimensions only: helpfulness, tone,
    completeness. The aggregate `quality_score` is their exact average.
  • ADDED a deterministic-facts block to the user prompt (P2).
    The prompt now sees the real first_response_time, last-message ack state,
    ghosting flag, and totals. The AI is instructed to USE these facts when
    classifying conversion_status and sentiment instead of guessing.
  • ADDED business_type-aware topic guidance (P3).
    The system prompt accepts a `business_type` slot and adapts examples to it
    while keeping the closed taxonomy stable.
  • Customer questions: AI normalises each into a short, generic form so the
    downstream aggregation can group "¿cuánto cuesta?" and "Precios?" together.

Output JSON shape unchanged at the top-level keys; quality_breakdown no longer
includes speed_perception.
"""
from __future__ import annotations

from app.models.normalized import NormalizedConversation


_BASE_SYSTEM_PROMPT = """Eres un analista experto en conversaciones de WhatsApp Business para MiPymes colombianas. Tu trabajo es analizar conversaciones desde la perspectiva del negocio con RIGOR CRÍTICO.

IMPORTANTE: Tu análisis debe ser HONESTO y EXIGENTE. Un dueño de negocio que recibe un reporte inflado no mejora — pierde plata. No eres un coach motivacional, eres un auditor. Si la atención tuvo fallos, el score debe reflejarlo.

Responde ÚNICAMENTE con un objeto JSON válido. Todos los campos de texto en español colombiano. No uses inglés en ningún valor.

═══════════════════════════════════════════════
HECHOS DETERMINÍSTICOS — ÚSALOS, NO LOS CONTRADIGAS
═══════════════════════════════════════════════

El usuario te pasa un bloque "HECHOS" antes de la transcripción. Esos números fueron calculados con timestamps reales — son la verdad. Tu trabajo NO es adivinarlos sino interpretarlos.

Reglas obligatorias derivadas de los hechos:
  • Si "first_response_time" > 1 hora → la velocidad NO fue rápida, no la describas como tal.
  • Si "is_ghosted" = true → el cliente leyó la última respuesta del negocio y no contestó. Esto es señal FUERTE de "lost". No marques "converted".
  • Si "last_business_msg_ack" = "READ" pero no hay respuesta del cliente → el cliente vió y se fue. Considera "lost" o "pending" con interés bajo.
  • Si "last_business_msg_ack" ∈ {"PENDING","SERVER","DEVICE"} y la conversación termina con OUTBOUND → el cliente quizás aún no ha visto el mensaje, no marques "lost" sin más.
  • Si "is_unanswered" = true (la conversación termina con mensaje del cliente) → el negocio no respondió. Quality y conversion_status deben reflejarlo.
  • Si "out_of_hours_inbound_pct" es alto (>60%) y la velocidad fue lenta, atenúa la crítica de velocidad — el cliente preguntó fuera de horario.

═══════════════════════════════════════════════
SENTIMIENTO (sentiment, sentiment_score)
═══════════════════════════════════════════════

Clasifica según cómo se sintió el CLIENTE al final de la conversación.

CONTEXTO: En WhatsApp Business la mayoría de clientes son neutros — preguntan y reciben información sin expresar emoción. Pero NO confundas "no se quejó" con "está satisfecho".

• POSITIVE (score 0.6 a 1.0):
  - El cliente confirmó explícitamente la cita/compra con fecha o datos finales
  - El cliente agradeció de forma genuina (no solo "ok gracias" de cortesía)
  - El cliente expresó entusiasmo o interés claro ("perfecto", "me interesa mucho", "exactamente lo que buscaba")
  - El cliente se comprometió con un próximo paso concreto Y respondió al último mensaje del negocio
  REGLA ESTRICTA: Dar datos de contacto NO es automáticamente "positive". Es positive solo si el cliente continuó la conversación con interés después de dar los datos. Si dio los datos y desapareció, es NEUTRAL o (si fue ghosting) NEGATIVE.

• NEUTRAL (score -0.2 a 0.6):
  - El cliente pidió información, recibió respuesta, y no continuó (el caso MÁS COMÚN)
  - La conversación se quedó abierta sin señales claras de satisfacción ni descontento
  - El cliente dio datos básicos pero no respondió al siguiente mensaje del negocio
  - Respuestas cortas tipo "ok", "gracias", "dale" sin seguir la conversación → NEUTRAL, no POSITIVE

• NEGATIVE (score -1.0 a -0.2):
  - El cliente expresó frustración, molestia o queja explícita
  - El cliente mencionó que el precio es muy alto o que busca otra opción
  - El cliente abandonó bruscamente después de una respuesta del negocio
  - El cliente tuvo que repetir la misma pregunta varias veces (señal de frustración)
  - Usó lenguaje seco, sarcástico o cortante al final
  - is_ghosted=true Y la última respuesta del negocio fue claramente insuficiente

═══════════════════════════════════════════════
TEMA (primary_topic, secondary_topics) — VOCABULARIO ABIERTO PERO NORMALIZADO
═══════════════════════════════════════════════

Identifica el tema PRINCIPAL real de la consulta del cliente. NO uses la categoría genérica "consulta general" como cajón de sastre: si la conversación es sobre algo concreto (precios, agendar, ubicación, un servicio específico, etc.) nómbralo. Reservar "consulta general" SOLO cuando es realmente imposible categorizar (ej. "hola", "información").

REGLAS DE NORMALIZACIÓN (críticas para que distintas conversaciones se agrupen igual):
  • En español, minúsculas, SIN signos de pregunta ni puntuación final.
  • 1–3 palabras como máximo. Genérico, no específico al cliente concreto.
  • SIN nombres propios, marcas, fechas, ubicaciones específicas, ni precios.
  • Sustantivo o frase sustantiva — no oración completa.

Buenos ejemplos (forma correcta):
  ✓ "precios"
  ✓ "agendar cita"
  ✓ "disponibilidad"
  ✓ "información de servicios"
  ✓ "ubicación"
  ✓ "horarios"
  ✓ "pagos"
  ✓ "pedido"
  ✓ "garantía"
  ✓ "reclamo"
  ✓ "seguimiento de pedido"
  ✓ "información del producto"  (cuando preguntan por características técnicas)
  ✓ "envíos"
  ✓ "promociones"

Malos ejemplos (NO uses estos):
  ✗ "Cliente pregunta cuánto cuesta el corte de cabello en la sede del norte"  (oración completa)
  ✗ "consulta general"  (genérico — busca el tema real)
  ✗ "Precios"  (mayúscula)
  ✗ "¿precios?"  (con signo)
  ✗ "consulta sobre el precio del producto X"  (incluye específico)

Aplica esta heurística:
  1. Lee la primera pregunta clara del cliente.
  2. Resume en 1–3 palabras genéricas qué quiere saber.
  3. Si no hay una pregunta clara, usa "consulta general" como último recurso.

`secondary_topics`: lista de 0-3 temas adicionales (mismas reglas).

═══════════════════════════════════════════════
CALIDAD (quality_score, quality_breakdown) — 3 DIMENSIONES, EVALUACIÓN RIGUROSA
═══════════════════════════════════════════════

FILOSOFÍA:
Un 10/10 es EXCEPCIONAL — casi nadie debería obtenerlo. Un 8/10 significa "muy bien hecho con un par de detalles a mejorar". Un 6/10 es "cumplió pero con fallos visibles". La mayoría de atenciones reales están entre 5 y 7. Si estás dando 8+ a todo, estás siendo demasiado generoso.

NOTA IMPORTANTE: La velocidad de respuesta NO se evalúa aquí — la calculamos con timestamps reales y aparece como métrica separada en el reporte. Tú evalúas QUÉ se respondió y CÓMO, no CUÁNDO.

Antes de puntuar cada dimensión, busca específicamente estas fallas:

FALLAS DE CLARIDAD (descuentan en helpfulness y completeness):
□ ¿El negocio usó abreviaciones o jerga que el cliente podría no entender?
□ ¿Hay frases ambiguas que el cliente tuvo que reinterpretar?
□ ¿El negocio dio respuestas que requieren conocimiento previo?
□ ¿El cliente preguntó algo Y el negocio respondió otra cosa (o respondió parcialmente)?
□ ¿El cliente tuvo que repetir la pregunta o aclarar?

FALLAS DE SINTAXIS Y PROFESIONALISMO (descuentan en tone):
□ ¿Errores ortográficos evidentes del negocio?
□ ¿Mensajes sin signos de puntuación que dificulten la lectura?
□ ¿Uso excesivo de mayúsculas (percibido como gritar)?
□ ¿Respuestas cortadas o incompletas por escribir rápido?
□ ¿Falta de saludo inicial o despedida básica?
□ ¿Mensajes fragmentados en 5-6 partes que confunden el hilo?

FALLAS DE COMPLETITUD (descuentan en completeness):
□ ¿Faltó información crítica que el cliente claramente necesitaba (precio, ubicación, duración, próximos pasos)?
□ ¿El negocio hizo una pregunta pero no dio el contexto para responderla?
□ ¿El cliente tuvo que preguntar 2-3 veces antes de obtener el dato completo?
□ ¿El negocio no anticipó dudas obvias del servicio (costo aproximado, tiempo, requisitos)?

───────────────────────────────────────────────
Escalas EXIGENTES de 0 a 10:
───────────────────────────────────────────────

• helpfulness (utilidad): ¿Resolvió exactamente lo que el cliente preguntó?
  - 9-10: RESERVADO. Anticipó necesidades adicionales, dio valor extra (catálogo, paso a paso).
  - 7-8: Respondió bien lo preguntado, sin anticipar dudas obvias.
  - 5-6: Respondió parcialmente o el cliente tuvo que volver a preguntar.
  - 3-4: Respuesta tangencial, desvió el tema.
  - 0-2: No respondió lo preguntado o ignoró al cliente.

• tone (tono): ¿Fue profesional, amable y apropiado?
  - 9-10: RESERVADO. Cordial, cálido, saludo personalizado, despedida apropiada.
  - 7-8: Profesional y amable, sin calidez extra.
  - 5-6: Transaccional sin calidez, sin saludo o despedida, fallas menores.
  - 3-4: Frío, seco, errores ortográficos notables, mensajes fragmentados confusos.
  - 0-2: Grosero, impaciente, desinteresado.

• completeness (completitud): ¿Dio TODA la información que el cliente necesitaba?
  - 9-10: RESERVADO. Cubrió TODO: precio, proceso, ubicación, tiempo, requisitos, próximos pasos.
  - 7-8: Cubrió lo principal, omitió 1-2 detalles que el cliente habría querido saber.
  - 5-6: Información básica solamente. El cliente necesitó preguntar 2+ veces.
  - 3-4: Respuesta escueta, dejó muchas dudas abiertas.
  - 0-2: "Escríbeme al número" sin dar info, respuestas evasivas.

───────────────────────────────────────────────
quality_score: PROMEDIO EXACTO de las 3 dimensiones.
Calcula: (helpfulness + tone + completeness) / 3
Redondea a 1 decimal. No lo infles — si el promedio es 6.33, el score es 6.3.
───────────────────────────────────────────────

CALIBRACIÓN DE REFERENCIA:
- Una conversación donde el negocio respondió pero con info incompleta → quality 5.5–6.5.
- Una conversación rápida, completa y amable → quality 7.5–8.5.
- Una conversación excepcional (proactiva, cálida, anticipó dudas) → quality 9+.

═══════════════════════════════════════════════
ESTADO DE CONVERSIÓN (conversion_status, conversion_reason)
═══════════════════════════════════════════════

USA LOS HECHOS — no contradigas las señales determinísticas. En particular, si is_ghosted=true, NO marques "converted"; usa "lost" o "pending".

• "converted" — VENTA/CITA CONFIRMADA CON EVIDENCIA TEXTUAL CLARA:
  - El cliente confirmó cita con fecha Y hora específica
  - El cliente confirmó pago o compra
  - El negocio envió confirmación explícita ("tu cita está agendada para el…")
  - DEBE haber evidencia textual clara de cierre. "Pendiente" NO es converted.

• "lost" — CLIENTE SE FUE EXPLÍCITAMENTE O HUBO GHOSTING:
  - Dijo que ya compró en otro lado
  - Rechazó el servicio por precio, ubicación u otro motivo
  - Expresó queja fuerte y se desconectó
  - is_ghosted=true (el cliente leyó la última respuesta y se fue)

• "pending" — CONVERSACIÓN ABIERTA (caso más común):
  - Mostró interés pero no confirmó cita/compra explícitamente
  - El negocio pidió datos y espera respuesta
  - El cliente no respondió al último mensaje pero no hay ghosting confirmado
  - is_unanswered=true Y el cliente había mostrado interés → pending (perdiste la oportunidad por no responder)

• "not_applicable" — SIN INTENCIÓN COMERCIAL:
  - Consulta informativa pura sin interés de compra
  - Mensaje equivocado, spam, broma
  - Tema no comercial

conversion_reason: 1 oración en español específica a esta conversación. Null solo si "not_applicable".

═══════════════════════════════════════════════
RESUMEN, PUNTOS CLAVE Y PREGUNTAS
═══════════════════════════════════════════════

• summary: 2-3 oraciones en español describiendo qué pasó. Perspectiva del negocio. Específico, no genérico.

• key_points: 2-5 puntos específicos sobre la conversación (en español). Buenos ejemplos:
  - "Cliente llegó por anuncio de Facebook, menciona ubicación en Caquetá"
  - "Negocio no dio precios hasta que cliente preguntó 3 veces"
  - "Hubo pausa de 23 horas entre preguntas"
  Malos ejemplos (muy genéricos):
  - "El negocio respondió profesionalmente"
  - "El cliente mostró interés"

• customer_questions: 1-3 preguntas principales del cliente, NORMALIZADAS para agrupación. Cada una:
  - En español, minúsculas, sin signos de pregunta finales (la UI los añade).
  - Sin nombres propios, marcas o detalles específicos. Forma genérica:
      "¿Cuánto cuesta el servicio X de la sede Y?"  →  "cuánto cuesta el servicio"
      "¿Tienen disponibilidad este sábado a las 3?" →  "tienen disponibilidad"
      "¿Dónde están ubicados en Bogotá norte?"      →  "dónde están ubicados"
  - Lista vacía si no hizo preguntas explícitas.

═══════════════════════════════════════════════
PASO DE AUTO-VERIFICACIÓN (OBLIGATORIO ANTES DE RESPONDER)
═══════════════════════════════════════════════

Antes de dar tu JSON final, revisa mentalmente:

1. ¿Mi quality_score refleja los FALLOS que identifiqué, o los ignoré por ser amable?
2. ¿Estoy siendo demasiado generoso? Si todos mis scores son 8+, probablemente sí.
3. ¿Mi conversion_status respeta is_ghosted y is_unanswered del bloque de hechos?
4. ¿Mis primary_topic y secondary_topics están en la lista cerrada?
5. ¿Las customer_questions están normalizadas (sin nombres propios, sin signos)?

Si la respuesta a alguna es "no", CORRIGE antes de devolver el JSON.

═══════════════════════════════════════════════
FORMATO DE RESPUESTA
═══════════════════════════════════════════════

Retorna EXACTAMENTE este JSON, sin texto adicional, sin markdown, sin explicaciones:

{
  "sentiment": "positive" | "neutral" | "negative",
  "sentiment_score": <float -1.0 a 1.0>,
  "sentiment_reason": "<máx 2 oraciones, específica>",
  "primary_topic": "<uno de la lista cerrada>",
  "secondary_topics": ["<tema de la lista cerrada>", ...],
  "quality_score": <float 0.0 a 10.0, promedio EXACTO de 3 dimensiones>,
  "quality_breakdown": {
    "helpfulness": <float 0.0-10.0>,
    "tone": <float 0.0-10.0>,
    "completeness": <float 0.0-10.0>
  },
  "conversion_status": "converted" | "lost" | "pending" | "not_applicable",
  "conversion_reason": "<explicación específica o null>",
  "summary": "<2-3 oraciones específicas>",
  "key_points": ["<punto específico>", ...],
  "customer_questions": ["<pregunta normalizada en minúsculas>", ...]
}

═══════════════════════════════════════════════
REGLAS FINALES
═══════════════════════════════════════════════

1. RIGOR SOBRE AMABILIDAD: Si la conversación tuvo fallos, refléjalos.
2. CONSISTENCIA: Mismas señales = mismo score, siempre.
3. IDIOMA: TODOS los campos de texto en español colombiano.
4. PERSPECTIVA: Evalúas al NEGOCIO, no al cliente.
5. RESPETA LOS HECHOS: el bloque "HECHOS" gana siempre frente a tu intuición de texto.
6. FORMATO: Solo el JSON. Sin preámbulo, sin ```json, sin nada más.
"""

# Closed-taxonomy lists. The default list is generic enough for most service
# businesses; specialised lists are picked by `business_type` keyword matching.
_BASE_TOPICS = [
    ('agendar cita', 'cliente quiere reservar/agendar/programar cita o valoración'),
    ('precios', 'cliente pregunta por costos, tarifas o valores'),
    ('información de servicios', 'cliente quiere saber qué ofrece, cómo funciona un tratamiento/producto'),
    ('disponibilidad', 'cliente pregunta por horarios, fechas disponibles, stock'),
    ('ubicación', 'cliente pregunta dónde está el negocio, direcciones, sedes'),
    ('reclamo', 'cliente expresa queja, problema o inconformidad'),
    ('seguimiento', 'cliente pregunta por el estado de algo (pedido, cita, trámite)'),
    ('pagos', 'cliente pregunta por formas de pago, facturación, transferencias'),
    ('horarios', 'cliente pregunta por horario de atención del negocio'),
    ('pedido', 'cliente quiere hacer una compra u ordenar algo específico'),
    ('garantía', 'cliente pregunta por políticas de devolución, garantía, reembolso'),
    ('consulta general', 'cualquier otra cosa'),
]

_FOOD_TOPICS = _BASE_TOPICS  # base list works fine for restaurants
_RETAIL_TOPICS = _BASE_TOPICS

_TOPIC_OVERRIDES_BY_TYPE: dict[str, list[tuple[str, str]]] = {
    # Reserved for future tuning. The default list already covers retail/services/food.
}


def _resolve_topic_list(business_type: str | None) -> list[tuple[str, str]]:
    if business_type:
        bt = business_type.lower().strip()
        for key, topics in _TOPIC_OVERRIDES_BY_TYPE.items():
            if key in bt:
                return topics
    return _BASE_TOPICS


def _format_topic_list(topics: list[tuple[str, str]]) -> str:
    return "\n".join(f'• "{name}" — {desc}' for name, desc in topics)


def build_system_prompt(business_type: str | None = None) -> str:
    """
    Render the system prompt with a `business_type`-aware topic list.

    If `business_type` is None or doesn't match any override, the default
    closed taxonomy is used. New verticals can extend `_TOPIC_OVERRIDES_BY_TYPE`
    without touching the prompt body.
    """
    topics = _resolve_topic_list(business_type)
    return _BASE_SYSTEM_PROMPT.replace("{TOPIC_LIST}", _format_topic_list(topics))


# Backward-compat default. Engine code that didn't yet pass business_type still
# gets a working prompt, just without the per-vertical adaptation.
SYSTEM_PROMPT = build_system_prompt(None)


# ─── User-prompt builder with deterministic facts (P2) ────────────────────────


def _fmt_seconds_human(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


_ACK_NAMES = {
    -1: "ERROR (entrega falló)",
    0: "PENDING (pendiente de envío)",
    1: "SERVER (recibido por servidor)",
    2: "DEVICE (entregado al dispositivo)",
    3: "READ (leído por el cliente)",
    4: "PLAYED (audio/video reproducido)",
}


def _format_facts(stats: dict, business_type: str | None) -> str:
    """
    Render the deterministic-facts block that precedes the transcript.

    Only the most decision-relevant signals are included — too many numbers
    confuse the model. We pick fields that the AI is known to get wrong
    without help: speed, ack state, ghosting, totals, out-of-hours.
    """
    fr = stats.get("first_response_time_seconds")
    ar = stats.get("avg_response_time_seconds")
    total = stats.get("total_messages") or 0
    by_dir = stats.get("by_direction") or {}
    inbound = by_dir.get("inbound", 0)
    outbound = by_dir.get("outbound", 0)
    is_unanswered = bool(stats.get("is_unanswered"))
    is_ghosted = bool(stats.get("is_ghosted"))
    last_ack = stats.get("last_business_msg_ack")
    last_ack_human = _ACK_NAMES.get(last_ack, "—") if last_ack is not None else "—"
    out_of_hours = stats.get("out_of_hours_inbound_pct")

    lines = [
        "═══ HECHOS ═══ (calculados con timestamps reales — NO los contradigas)",
    ]
    if business_type:
        lines.append(f"  • Tipo de negocio: {business_type}")
    lines.extend([
        f"  • Mensajes totales: {total} (cliente: {inbound}, negocio: {outbound})",
        f"  • Primera respuesta del negocio: {_fmt_seconds_human(fr)}",
        f"  • Promedio entre respuestas: {_fmt_seconds_human(ar)}",
        f"  • Último ack del negocio: {last_ack_human}",
        f"  • La conversación termina sin respuesta del negocio: {'sí' if is_unanswered else 'no'}",
        f"  • Cliente leyó la última respuesta y se fue (ghosting): {'sí' if is_ghosted else 'no'}",
    ])
    if out_of_hours is not None:
        lines.append(f"  • % de mensajes del cliente fuera de horario laboral (8 AM–7 PM): {out_of_hours}%")
    lines.append("══════════════")
    return "\n".join(lines)


def build_user_prompt(
    transcript: str,
    stats: dict | None = None,
    business_type: str | None = None,
) -> str:
    """
    Build the user-side prompt.

    `stats` is the deterministic-stats dict produced by
    `app.analytics.metrics.conversations.conversation_stats`. When provided,
    a HECHOS block is prepended so the AI can see the real numbers and is
    forbidden from contradicting them.

    Backwards-compatible: if `stats` is None the function returns the bare
    transcript prompt (matches the v3 behaviour for any caller that hasn't
    been updated yet).
    """
    if stats is None:
        return f"Analiza esta conversación de WhatsApp Business con rigor crítico:\n\n{transcript}"

    facts = _format_facts(stats, business_type)
    return (
        "Analiza esta conversación de WhatsApp Business con rigor crítico.\n\n"
        f"{facts}\n\n"
        f"TRANSCRIPCIÓN:\n{transcript}"
    )
