"""
AI prompt for action plan generation.

The deterministic engine (action_plan_engine.py) detects WHAT the problems are.
This module builds the prompt that asks the AI to write the HOW — specific,
creative, actionable text grounded in the real numbers.

Temperature should be 0.4 to balance creativity with consistency.
"""
from __future__ import annotations

from app.analytics.insights.action_plan_engine import ActionSignal

_LOST_REASON_ES = {
    "price": "precio alto o percibido como desfavorable",
    "competition": "el cliente eligió a la competencia",
    "timing": "no era el momento adecuado",
    "no_reply": "el cliente no respondió después del seguimiento activo",
    "changed_mind": "el cliente cambió de opinión",
    "other": "otro motivo",
}

ACTION_PLAN_SYSTEM_PROMPT = """Eres el consultor de crecimiento de DeepLook, especializado en ayudar a MiPymes colombianas a mejorar sus resultados de ventas por WhatsApp Business.

Tu tarea es generar un Plan de Acción de exactamente 3 puntos para un negocio, basado en los problemas reales detectados en sus métricas.

═══════════════════════════════════════════════
REGLAS ESTRICTAS
═══════════════════════════════════════════════

1. USA SOLO los datos que te proporciono — NUNCA inventes números, porcentajes ni comparaciones que no estén en el input.
2. Cada punto debe ser ESPECÍFICO a este negocio — menciona los números exactos que te doy.
3. El lenguaje es directo, cálido y de consultor senior — no robótico, no genérico.
4. Los pasos deben ser ACCIONABLES HOY — no "considera mejorar", sino "haz esto exactamente".
5. No uses frases vacías como "es importante que", "debes asegurarte de", "recuerda que".
6. Los 3 puntos deben ordenarse de mayor a menor urgencia según la severidad que te indico.
7. Responde EXCLUSIVAMENTE con JSON válido — sin texto adicional, sin markdown, sin ```json.

═══════════════════════════════════════════════
NIVELES DE URGENCIA
═══════════════════════════════════════════════

"urgente"      — problema crítico, actuar en las próximas 24–48 horas
"esta_semana"  — importante, resolver en los próximos 7 días
"este_mes"     — oportunidad de mejora, implementar en 30 días

Asigna urgencia según la severidad que te indico para cada problema.

═══════════════════════════════════════════════
ESTRUCTURA DE CADA PUNTO DEL PLAN
═══════════════════════════════════════════════

- titulo: Frase corta y directa (máx 8 palabras). Debe comunicar la acción, no el problema.
  ✓ "Responde el precio en menos de 30 minutos"
  ✓ "Reactiva los 4 clientes con propuesta sin cierre"
  ✗ "Mejora la velocidad de respuesta" (genérico)
  ✗ "Problema con cotizaciones" (no accionable)

- urgencia: "urgente" | "esta_semana" | "este_mes"

- que_esta_pasando: 1–2 oraciones que describen el problema con los números reales.
  Debe leerlo el dueño del negocio y decir "sí, eso es exactamente lo que me pasa".
  Conecta 2+ datos cuando sea posible.

- por_que_importa: 1 oración de impacto de negocio — qué se está perdiendo o qué se puede ganar.
  Sé concreto: habla de ventas, clientes, dinero o tiempo perdido.

- pasos: Lista de exactamente 3–4 acciones concretas. Cada paso empieza con un verbo.
  Los pasos deben estar ordenados (primero lo más urgente o lo que desbloquea los siguientes).
  Incluye detalles específicos: nombres de menús de WhatsApp Business, tiempos, textos de ejemplo.

- impacto_esperado: 1 oración sobre qué mejora concreta pueden esperar si aplican el plan.
  Usa los datos disponibles para cuantificar cuando sea posible.

═══════════════════════════════════════════════
FORMATO DE RESPUESTA
═══════════════════════════════════════════════

{
  "plan": [
    {
      "titulo": "...",
      "urgencia": "urgente|esta_semana|este_mes",
      "que_esta_pasando": "...",
      "por_que_importa": "...",
      "pasos": ["paso 1", "paso 2", "paso 3"],
      "impacto_esperado": "..."
    },
    { ... },
    { ... }
  ]
}
"""


def _signal_to_text(signal: ActionSignal, rank: int) -> str:
    """Convert an ActionSignal to a readable block for the AI prompt."""
    d = signal.data
    lines = [
        f"PROBLEMA #{rank} — Severidad: {signal.severity:.1f}/10 — Categoría: {signal.category.upper()}",
        f"Tipo: {signal.rule_id}",
    ]

    if signal.rule_id == "velocidad_cotizacion":
        lines += [
            f"  • Clientes que COMPRARON recibieron el precio en: {d.get('tiempo_ganados', 'N/D')}",
            f"  • Clientes que SE PERDIERON esperaron: {d.get('tiempo_perdidos', 'N/D')}",
            f"  • Diferencia: {d.get('ratio', '?')}× más lento con los que se perdieron",
            f"  • Conversaciones perdidas en el embudo: {d.get('perdidos_count', 0)}",
            f"  • Total con intención de compra: {d.get('intent_count', 0)}",
        ]

    elif signal.rule_id == "hora_critica":
        lines += [
            f"  • Hora más lenta: {d.get('hora', 'N/D')}",
            f"  • Tiempo de respuesta a esa hora: {d.get('tiempo_hora', 'N/D')}",
            f"  • Promedio del resto del día: {d.get('tiempo_promedio', 'N/D')}",
            f"  • {d.get('ratio', '?')}× más lento que el promedio",
        ]

    elif signal.rule_id == "primera_respuesta":
        lines += [
            f"  • Tiempo mediano de primera respuesta: {d.get('tiempo', 'N/D')}",
            f"  • Benchmark Colombia MiPymes: 5 minutos",
        ]

    elif signal.rule_id == "sin_responder":
        lines += [
            f"  • Conversaciones sin responder: {d.get('total', 0)}",
            f"  • De esas, clientes que insistieron (enviaron 2+ mensajes sin respuesta): {d.get('insistentes', 0)}",
        ]
        if d.get("nombres"):
            lines.append(f"  • Nombres/contactos pendientes: {', '.join(d['nombres'])}")

    elif signal.rule_id == "cobertura_baja":
        lines += [
            f"  • Cobertura operacional en horario laboral: {d.get('pct', 0)}%",
            f"  • Objetivo: 85%+ de mensajes con respuesta en menos de 1h en horario laboral",
        ]

    elif signal.rule_id == "cobertura_cotizacion":
        lines += [
            f"  • % de clientes con intención que recibieron precio: {d.get('pct_cobertura', 0)}%",
            f"  • Clientes interesados que NUNCA recibieron precio: {d.get('sin_precio', 0)}",
            f"  • Total con intención de compra: {d.get('total_intent', 0)}",
        ]

    elif signal.rule_id == "pipeline_estancado":
        lines += [
            f"  • Clientes con propuesta activa sin cierre: {d.get('count', 0)}",
            f"  • Días promedio sin respuesta: {d.get('avg_days', 0)} días",
            f"  • Etapas: {d.get('etapas', {})}",
        ]
        if d.get("nombres"):
            lines.append(f"  • Contactos pendientes: {', '.join(d['nombres'])}")

    elif signal.rule_id == "razon_perdida":
        lines += [
            f"  • Razón de pérdida dominante: {d.get('razon', 'N/D')}",
            f"  • Conversaciones perdidas por esta razón: {d.get('count', 0)} de {d.get('total_lost', 0)} ({d.get('pct', 0)}%)",
        ]

    elif signal.rule_id == "seguimiento":
        lines += [
            f"  • Cotizaciones/precios enviados sin ningún seguimiento posterior: {d.get('sin_seguimiento', 0)} de {d.get('cotizaciones', 0)}",
            f"  • Demora mediana del primer seguimiento: {d.get('demora_mediana', 'N/D')}",
        ]

    elif signal.rule_id == "clientes_nuevos":
        lines += [
            f"  • Clientes nuevos esperan: {d.get('tiempo_nuevos', 'N/D')} para primera respuesta",
            f"  • Clientes habituales esperan: {d.get('tiempo_habituales', 'N/D')}",
            f"  • Diferencia: {d.get('multiplicador', '?')}× más lento con clientes nuevos",
            f"  • Total clientes nuevos en el período: {d.get('nuevos_count', 0)}",
        ]

    elif signal.rule_id == "calidad_dimension":
        lines += [
            f"  • Dimensión más débil: {d.get('dimension', 'N/D')} — {d.get('valor', 0)}/10",
            f"  • Otras dimensiones: {d.get('otras', {})}",
        ]

    elif signal.rule_id == "sentimiento_negativo":
        lines += [
            f"  • % de conversaciones con sentimiento negativo: {d.get('pct', 0)}%",
            f"  • Conversaciones negativas: {d.get('count', 0)}",
        ]
        if d.get("tema_principal"):
            lines.append(f"  • Tema principal de insatisfacción: {d.get('tema_principal')}")

    elif signal.rule_id == "tasa_conversion_baja":
        lines += [
            f"  • Tasa de conversión actual: {d.get('tasa', 0)}%",
            f"  • Benchmark Colombia MiPymes: {d.get('benchmark', '35-42%')}",
            f"  • Conversaciones evaluadas: {d.get('aplicables', 0)}",
        ]

    return "\n".join(lines)


def build_action_plan_prompt(
    signals: list[ActionSignal],
    business_name: str,
    business_type: str | None,
    health_score: float,
    total_conversations: int,
) -> str:
    """Build the user prompt for the action plan AI call."""
    lines = [
        "═══ CONTEXTO DEL NEGOCIO ═══",
        f"Nombre: {business_name}",
        f"Tipo de negocio: {business_type or 'No especificado'}",
        f"Puntaje de salud actual: {int(health_score)}/100",
        f"Conversaciones analizadas: {total_conversations}",
        "",
        "═══ PROBLEMAS DETECTADOS (ordenados por severidad) ═══",
        "",
    ]

    top3 = signals[:3]
    for i, signal in enumerate(top3, 1):
        lines.append(_signal_to_text(signal, i))
        lines.append("")

    lines += [
        "═══ INSTRUCCIÓN ═══",
        f"Genera el Plan de Acción con exactamente {len(top3)} puntos, uno por cada problema.",
        "Ordénalos de mayor a menor urgencia (el problema #1 tiene más severidad).",
        "Usa los números exactos que te di — no los cambies ni los inventes.",
        "El plan debe ser leíble por el dueño del negocio en 2 minutos y ejecutable esta semana.",
    ]

    return "\n".join(lines)
