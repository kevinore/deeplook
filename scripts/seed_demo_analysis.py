"""
Seed demo-quality analysis data for job 4d3da0c1-8c5c-48ed-8fd5-10b5517a61f5.

Design targets:
- 16 conversations (update 4 existing + add 12 new)
- Health score ~74/100  ("Bueno" — good but not perfect)
- Sentiments: 10 positive, 4 neutral, 2 negative
- Conversion: 8 converted, 2 lost, 4 pending, 2 not_applicable
- FRT avg ~8 min (fires "reduce response time" recommendation)
- 1 unanswered conversation (fires "unanswered" recommendation)
- 7/16 = 44% precios y cotizaciones (fires "create quick-reply" recommendation)
- Quality avg ~7.5/10
- Business context: servicio de estética / belleza, Colombia

Run from project root:
    python scripts/seed_demo_analysis.py
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
from dotenv import load_dotenv

load_dotenv(".env")

JOB_ID      = "4d3da0c1-8c5c-48ed-8fd5-10b5517a61f5"
CLIENT_ID   = "f0ff7352-520c-4df3-967e-70e4dd90dae2"

# ── Existing analyses to UPDATE (keep conversation rows intact) ──────────────

EXISTING_UPDATES = [
    {
        "analysis_id": "fbe6c797-39db-42cb-a90b-204bd4a2b426",
        "conversation_id": "7a58c157-faeb-469a-92e7-91fbf1147e74",
        "sentiment": "positive",
        "sentiment_score": 0.82,
        "sentiment_reason": "La clienta expresó satisfacción con los precios y la atención recibida",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["información de servicios"],
        "quality_score": 8.2,
        "quality_breakdown": {"helpfulness": 8.5, "tone": 9.0, "completeness": 7.5},
        "conversion_status": "converted",
        "conversion_reason": "La clienta confirmó la cita y realizó el pago anticipado",
        "summary": "La clienta consultó los precios del servicio de manicure y pedicure. La asesora respondió de manera clara y detallada, ofreciendo un paquete con precio especial para el combo. La clienta quedó satisfecha y confirmó la cita realizando el pago anticipado. Conversación exitosa.",
        "key_points": ["Precio combo manicure+pedicure comunicado claramente", "Oferta de paquete especial aceptada", "Pago anticipado confirmado"],
        "customer_questions": ["¿Cuánto vale el combo de manicure y pedicure?", "¿Tienen disponibilidad esta semana?"],
        "first_response_time_seconds": 90.0,
        "avg_response_time_seconds": 145.0,
        "median_response_time_seconds": 120.0,
        "p95_response_time_seconds": 280.0,
        "unanswered_count": 0,
        "total_messages": 14,
        "inbound_count": 7,
        "outbound_count": 7,
        "duration_minutes": 18.0,
        "delivery_rate": 1.0,
        "read_rate": 0.9,
        "is_ghosted": False,
        "operational_coverage_score": 85.0,
    },
    {
        "analysis_id": "3278b13a-f2cd-4c8e-b562-77e93dfc72b2",
        "conversation_id": "32dbf1f2-b16d-4f12-9da3-9bcb85a3818e",
        "sentiment": "positive",
        "sentiment_score": 0.75,
        "sentiment_reason": "El cliente mostró entusiasmo al confirmar la cita y agradeció la rápida atención",
        "primary_topic": "disponibilidad y horarios",
        "secondary_topics": ["confirmación de pedidos"],
        "quality_score": 7.8,
        "quality_breakdown": {"helpfulness": 8.0, "tone": 8.5, "completeness": 7.0},
        "conversion_status": "converted",
        "conversion_reason": "El cliente agendó su cita y confirmó la asistencia",
        "summary": "El cliente preguntó por la disponibilidad de citas para el fin de semana. La respuesta fue inmediata con horarios disponibles bien explicados. El cliente seleccionó el sábado a las 2pm y confirmó su asistencia. Atención eficiente y conversión exitosa.",
        "key_points": ["Disponibilidad del fin de semana informada rápidamente", "Horario sábado 2pm reservado", "Cliente confirmó asistencia"],
        "customer_questions": ["¿Tienen citas disponibles este sábado?", "¿Hasta qué hora atienden?"],
        "first_response_time_seconds": 180.0,
        "avg_response_time_seconds": 220.0,
        "median_response_time_seconds": 200.0,
        "p95_response_time_seconds": 350.0,
        "unanswered_count": 0,
        "total_messages": 10,
        "inbound_count": 5,
        "outbound_count": 5,
        "duration_minutes": 12.0,
        "delivery_rate": 1.0,
        "read_rate": 1.0,
        "is_ghosted": False,
        "operational_coverage_score": 90.0,
    },
    {
        "analysis_id": "a26fadfa-6c43-4bf4-a8ce-8e34bd24be53",
        "conversation_id": "f7f3f2bc-bb1a-46f2-be73-a2a9f27780d2",
        "sentiment": "positive",
        "sentiment_score": 0.88,
        "sentiment_reason": "La clienta expresó alto nivel de satisfacción e interés durante toda la conversación",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["información de servicios"],
        "quality_score": 8.5,
        "quality_breakdown": {"helpfulness": 8.5, "tone": 9.5, "completeness": 7.5},
        "conversion_status": "converted",
        "conversion_reason": "La clienta agendó el tratamiento de keratina después de recibir información detallada",
        "summary": "La clienta solicitó información sobre el costo y el proceso del tratamiento de keratina. La asesora respondió con detalle sobre los tipos disponibles, duración del efecto y precios de cada modalidad. La clienta quedó convencida y agendó su cita para la semana siguiente.",
        "key_points": ["Tres tipos de keratina explicados con precios", "Duración del efecto detallada (3-6 meses)", "Cita agendada para semana siguiente"],
        "customer_questions": ["¿Cuánto vale la keratina?", "¿Cuánto tiempo dura el efecto?", "¿Qué productos usan?"],
        "first_response_time_seconds": 120.0,
        "avg_response_time_seconds": 190.0,
        "median_response_time_seconds": 180.0,
        "p95_response_time_seconds": 320.0,
        "unanswered_count": 0,
        "total_messages": 18,
        "inbound_count": 9,
        "outbound_count": 9,
        "duration_minutes": 25.0,
        "delivery_rate": 1.0,
        "read_rate": 1.0,
        "is_ghosted": False,
        "operational_coverage_score": 88.0,
    },
    {
        "analysis_id": "558ae87f-e8c6-41f2-9368-1f48a0785b42",
        "conversation_id": "d8c54275-f0b7-4727-bdd1-1f52ac7c07f7",
        "sentiment": "neutral",
        "sentiment_score": 0.52,
        "sentiment_reason": "El cliente mostró interés pero sin compromiso claro, solicitó tiempo para decidir",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["disponibilidad y horarios"],
        "quality_score": 7.2,
        "quality_breakdown": {"helpfulness": 7.5, "tone": 7.0, "completeness": 7.0},
        "conversion_status": "pending",
        "conversion_reason": "El cliente recibió la información y dijo que evaluaría la propuesta",
        "summary": "El cliente preguntó sobre los precios del servicio de corte y tinte. Se le enviaron las tarifas actualizadas con el catálogo de colores disponibles. La conversación fue informativa pero el cliente indicó que necesitaba pensarlo antes de confirmar.",
        "key_points": ["Tarifas de corte y tinte enviadas", "Catálogo de colores compartido", "Cliente solicitó tiempo para decidir"],
        "customer_questions": ["¿Cuánto vale el corte con tinte?", "¿Qué colores tienen disponibles?"],
        "first_response_time_seconds": 300.0,
        "avg_response_time_seconds": 380.0,
        "median_response_time_seconds": 360.0,
        "p95_response_time_seconds": 520.0,
        "unanswered_count": 0,
        "total_messages": 12,
        "inbound_count": 6,
        "outbound_count": 6,
        "duration_minutes": 20.0,
        "delivery_rate": 1.0,
        "read_rate": 0.85,
        "is_ghosted": False,
        "operational_coverage_score": 72.0,
    },
]

# ── New contacts to create ───────────────────────────────────────────────────

NEW_CONTACTS = [
    {"id": str(uuid.uuid4()), "phone": "573112345678", "name": "María García"},
    {"id": str(uuid.uuid4()), "phone": "573009876543", "name": "Carlos Rodríguez"},
    {"id": str(uuid.uuid4()), "phone": "573215550012", "name": "Ana Martínez"},
    {"id": str(uuid.uuid4()), "phone": "573158887766", "name": "Juan Pérez"},
    {"id": str(uuid.uuid4()), "phone": "573024443322", "name": "Luisa Herrera"},
    {"id": str(uuid.uuid4()), "phone": "573187775544", "name": "Pedro Díaz"},
    {"id": str(uuid.uuid4()), "phone": "573126669988", "name": "Isabel Castro"},
    {"id": str(uuid.uuid4()), "phone": "573253331100", "name": "Roberto Silva"},
]

# ── New conversations + analyses to INSERT ───────────────────────────────────

def _t(days_ago: float, hour: int = 10, minute: int = 0) -> datetime:
    """Timestamp helper — N days ago at given hour."""
    base = datetime.now(tz=timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base - timedelta(days=days_ago)


NEW_RECORDS = [
    # 5 — CONVERTED, positive, precios y cotizaciones
    {
        "contact_key": 0,  # María García
        "conv_started_at": _t(6, 9, 15),
        "conv_messages": 16, "conv_inbound": 8, "conv_outbound": 8,
        "sentiment": "positive", "sentiment_score": 0.79,
        "sentiment_reason": "La clienta mostró entusiasmo durante toda la consulta y agradeció la atención personalizada",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["información de servicios"],
        "quality_score": 7.9,
        "quality_breakdown": {"helpfulness": 8.0, "tone": 8.5, "completeness": 7.0},
        "conversion_status": "converted",
        "conversion_reason": "La clienta eligió el plan mensual de servicios y agendó su primera cita",
        "summary": "La clienta preguntó sobre promociones vigentes y el precio del combo mensual de manicure, pedicure y limpieza facial. La asesora explicó los paquetes disponibles con detalle. La clienta eligió el plan mensual y agendó su primera sesión para el siguiente viernes.",
        "key_points": ["Plan mensual combo presentado con descuento", "Diferencias entre paquetes explicadas", "Cita agendada viernes siguiente"],
        "customer_questions": ["¿Tienen planes mensuales?", "¿Cuánto ahorro con el combo?"],
        "frt": 150.0, "avg_rt": 210.0, "unanswered": 0, "duration": 22.0,
        "op_coverage": 80.0,
    },
    # 6 — CONVERTED, positive, disponibilidad y horarios
    {
        "contact_key": 1,  # Carlos Rodríguez
        "conv_started_at": _t(5, 14, 30),
        "conv_messages": 8, "conv_inbound": 4, "conv_outbound": 4,
        "sentiment": "positive", "sentiment_score": 0.91,
        "sentiment_reason": "El cliente expresó satisfacción con la rapidez de la atención y confirmó la cita con entusiasmo",
        "primary_topic": "disponibilidad y horarios",
        "secondary_topics": ["confirmación de pedidos"],
        "quality_score": 8.8,
        "quality_breakdown": {"helpfulness": 9.0, "tone": 9.5, "completeness": 8.0},
        "conversion_status": "converted",
        "conversion_reason": "El cliente confirmó su cita previamente agendada y verificó la dirección",
        "summary": "El cliente escribió para confirmar su cita previamente agendada y preguntar la dirección exacta del local. La atención fue muy rápida, la asesora respondió con la dirección completa y referencia de ubicación. El cliente confirmó su asistencia y llegó puntual a su cita.",
        "key_points": ["Dirección del local enviada con referencia", "Cita confirmada exitosamente", "Tiempo de respuesta excelente"],
        "customer_questions": ["¿Cuál es la dirección exacta?", "¿Hay parqueadero cerca?"],
        "frt": 60.0, "avg_rt": 90.0, "unanswered": 0, "duration": 8.0,
        "op_coverage": 95.0,
    },
    # 7 — CONVERTED, positive, información de servicios
    {
        "contact_key": 2,  # Ana Martínez
        "conv_started_at": _t(5, 11, 0),
        "conv_messages": 20, "conv_inbound": 10, "conv_outbound": 10,
        "sentiment": "positive", "sentiment_score": 0.76,
        "sentiment_reason": "La clienta recibió información completa que despejó sus dudas y la motivó a tomar una decisión",
        "primary_topic": "información de servicios",
        "secondary_topics": ["precios y cotizaciones"],
        "quality_score": 7.5,
        "quality_breakdown": {"helpfulness": 7.5, "tone": 8.0, "completeness": 7.0},
        "conversion_status": "converted",
        "conversion_reason": "La clienta decidió agendar el alisado permanente después de resolver todas sus dudas",
        "summary": "La clienta preguntó sobre el proceso y duración del alisado permanente, los materiales usados y los cuidados posteriores necesarios. La asesora respondió con información completa sobre el procedimiento, incluyendo duración (3 horas), producto utilizado y guía de cuidados post-tratamiento. La clienta agendó el servicio.",
        "key_points": ["Proceso de alisado explicado paso a paso", "Tiempo de duración del tratamiento: 3 horas", "Guía de cuidados post-tratamiento compartida"],
        "customer_questions": ["¿Qué productos usan para el alisado?", "¿Cuánto tiempo dura en el cabello?", "¿Qué cuidados se necesitan después?"],
        "frt": 200.0, "avg_rt": 280.0, "unanswered": 0, "duration": 35.0,
        "op_coverage": 78.0,
    },
    # 8 — CONVERTED, positive, precios y cotizaciones
    {
        "contact_key": 3,  # Juan Pérez
        "conv_started_at": _t(4, 16, 0),
        "conv_messages": 12, "conv_inbound": 6, "conv_outbound": 6,
        "sentiment": "positive", "sentiment_score": 0.81,
        "sentiment_reason": "El cliente quedó satisfecho con el precio presentado y confirmó la cita sin dudas",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["disponibilidad y horarios"],
        "quality_score": 8.0,
        "quality_breakdown": {"helpfulness": 8.0, "tone": 8.5, "completeness": 7.5},
        "conversion_status": "converted",
        "conversion_reason": "El cliente confirmó cita de barbería premium después de recibir la cotización",
        "summary": "El cliente solicitó una cotización para los servicios de barbería premium: corte, barba y cejas. La asesora presentó los precios del paquete completo con claridad. El cliente consideró el precio razonable y confirmó su cita para el siguiente lunes.",
        "key_points": ["Paquete barbería premium cotizado", "Precio final del combo presentado", "Cita confirmada para el lunes"],
        "customer_questions": ["¿Cuánto vale el corte con barba y cejas?", "¿Tienen citas para el lunes?"],
        "frt": 170.0, "avg_rt": 230.0, "unanswered": 0, "duration": 16.0,
        "op_coverage": 82.0,
    },
    # 9 — CONVERTED, positive, confirmación de pedidos
    {
        "contact_key": 4,  # Luisa Herrera
        "conv_started_at": _t(3, 10, 30),
        "conv_messages": 10, "conv_inbound": 5, "conv_outbound": 5,
        "sentiment": "positive", "sentiment_score": 0.73,
        "sentiment_reason": "La clienta mostró confianza y satisfacción al coordinar la recogida de sus productos",
        "primary_topic": "confirmación de pedidos",
        "secondary_topics": [],
        "quality_score": 7.6,
        "quality_breakdown": {"helpfulness": 7.5, "tone": 8.5, "completeness": 7.0},
        "conversion_status": "converted",
        "conversion_reason": "La clienta confirmó la recogida de productos capilares y realizó el pago",
        "summary": "La clienta confirmó el pedido de productos capilares para recoger en el local. Verificó disponibilidad de los productos en inventario y acordó la hora de recogida para las 3pm. Todo quedó coordinado correctamente y la clienta recogió su pedido.",
        "key_points": ["Disponibilidad de productos verificada", "Hora de recogida acordada (3pm)", "Pago coordinado exitosamente"],
        "customer_questions": ["¿Ya llegaron los productos que pedí?", "¿A qué hora puedo pasar?"],
        "frt": 240.0, "avg_rt": 310.0, "unanswered": 0, "duration": 14.0,
        "op_coverage": 75.0,
    },
    # 10 — LOST, neutral, precios y cotizaciones (slow response)
    {
        "contact_key": 5,  # Pedro Díaz
        "conv_started_at": _t(7, 13, 0),
        "conv_messages": 6, "conv_inbound": 4, "conv_outbound": 2,
        "sentiment": "neutral", "sentiment_score": 0.48,
        "sentiment_reason": "El cliente no mostró señales claras de satisfacción o insatisfacción, simplemente dejó de responder",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": [],
        "quality_score": 5.8,
        "quality_breakdown": {"helpfulness": 6.0, "tone": 6.5, "completeness": 5.0},
        "conversion_status": "lost",
        "conversion_reason": "La demora en la respuesta hizo que el cliente buscara otras alternativas",
        "summary": "El cliente preguntó el precio del servicio de depilación láser. La respuesta tardó aproximadamente 30 minutos en llegar. Para cuando se envió la cotización, el cliente ya no estaba disponible para responder. Conversación perdida por demora en la atención.",
        "key_points": ["Tiempo de respuesta superior a 30 minutos", "Cotización enviada sin retorno del cliente", "Cliente posiblemente atendido por la competencia"],
        "customer_questions": ["¿Cuánto vale la depilación láser de piernas?"],
        "frt": 1800.0, "avg_rt": 1800.0, "unanswered": 0, "duration": 32.0,
        "op_coverage": 40.0,
    },
    # 11 — LOST, negative, soporte y quejas
    {
        "contact_key": 1,  # reuse Carlos Rodríguez (different conversation)
        "conv_started_at": _t(8, 15, 0),
        "conv_messages": 14, "conv_inbound": 8, "conv_outbound": 6,
        "sentiment": "negative", "sentiment_score": 0.18,
        "sentiment_reason": "La clienta expresó inconformidad explícita con el resultado del servicio y frustración por la falta de solución",
        "primary_topic": "soporte y quejas",
        "secondary_topics": ["pagos y facturación"],
        "quality_score": 4.5,
        "quality_breakdown": {"helpfulness": 4.0, "tone": 5.5, "completeness": 4.0},
        "conversion_status": "lost",
        "conversion_reason": "La clienta no obtuvo una solución satisfactoria y expresó que no regresaría",
        "summary": "La clienta expresó su inconformidad con el resultado del tinte aplicado, que no coincidió con el color acordado previamente. La respuesta del negocio fue tardía y no ofreció una solución concreta ni compensación. La clienta quedó insatisfecha y comunicó que no regresaría al local.",
        "key_points": ["Queja por color de tinte incorrecto", "Tiempo de respuesta alto para una queja", "No se ofreció solución ni compensación", "Clienta expresó intención de no regresar"],
        "customer_questions": ["¿Por qué el color no quedó igual a la foto?", "¿Qué solución me ofrecen?"],
        "frt": 2700.0, "avg_rt": 2400.0, "unanswered": 0, "duration": 55.0,
        "op_coverage": 30.0,
    },
    # 12 — PENDING, positive, precios y cotizaciones
    {
        "contact_key": 6,  # Isabel Castro
        "conv_started_at": _t(2, 11, 15),
        "conv_messages": 14, "conv_inbound": 7, "conv_outbound": 7,
        "sentiment": "positive", "sentiment_score": 0.70,
        "sentiment_reason": "La clienta mostró interés genuino y valoró la información sobre el portafolio de trabajos",
        "primary_topic": "precios y cotizaciones",
        "secondary_topics": ["información de servicios"],
        "quality_score": 7.8,
        "quality_breakdown": {"helpfulness": 8.0, "tone": 8.0, "completeness": 7.5},
        "conversion_status": "pending",
        "conversion_reason": "La clienta recibió la propuesta y dijo que confirmaría después de hablar con su esposo",
        "summary": "La clienta preguntó precios y disponibilidad para el servicio de extensiones de cabello. Se le enviaron los precios según el tipo de extensión, junto con un portafolio de trabajos anteriores. La clienta quedó impresionada con los resultados pero indicó que necesitaba consultarlo antes de confirmar.",
        "key_points": ["Tipos de extensiones y precios enviados", "Portafolio de trabajos compartido", "Clienta interesada pero pendiente de confirmar"],
        "customer_questions": ["¿Cuánto valen las extensiones?", "¿Cuánto tiempo duran?", "¿Pueden mostrarme trabajos previos?"],
        "frt": 300.0, "avg_rt": 400.0, "unanswered": 0, "duration": 28.0,
        "op_coverage": 70.0,
    },
    # 13 — PENDING, neutral, disponibilidad y horarios
    {
        "contact_key": 2,  # reuse Ana Martínez
        "conv_started_at": _t(1, 9, 45),
        "conv_messages": 8, "conv_inbound": 4, "conv_outbound": 4,
        "sentiment": "neutral", "sentiment_score": 0.51,
        "sentiment_reason": "La clienta solicitó información de manera directa sin mostrar preferencia clara todavía",
        "primary_topic": "disponibilidad y horarios",
        "secondary_topics": [],
        "quality_score": 7.0,
        "quality_breakdown": {"helpfulness": 7.0, "tone": 7.5, "completeness": 6.5},
        "conversion_status": "pending",
        "conversion_reason": "La clienta recibió los horarios disponibles pero aún no ha confirmado su cita",
        "summary": "La clienta consultó sobre los horarios disponibles para la próxima semana. Se le informaron los turnos disponibles de lunes a sábado con los horarios de atención. La clienta agradeció la información e indicó que confirmaría durante el día.",
        "key_points": ["Horarios semana siguiente informados", "Disponibilidad lunes a sábado compartida", "Confirmación pendiente por parte de la clienta"],
        "customer_questions": ["¿Qué horarios tienen disponibles la próxima semana?"],
        "frt": 360.0, "avg_rt": 420.0, "unanswered": 0, "duration": 12.0,
        "op_coverage": 68.0,
    },
    # 14 — NOT_APPLICABLE, positive, agradecimiento y feedback
    {
        "contact_key": 7,  # Roberto Silva
        "conv_started_at": _t(3, 17, 0),
        "conv_messages": 6, "conv_inbound": 4, "conv_outbound": 2,
        "sentiment": "positive", "sentiment_score": 0.95,
        "sentiment_reason": "La clienta expresó gratitud espontánea y compartió una recomendación genuina del servicio",
        "primary_topic": "agradecimiento y feedback",
        "secondary_topics": [],
        "quality_score": 8.5,
        "quality_breakdown": {"helpfulness": 8.5, "tone": 9.0, "completeness": 8.0},
        "conversion_status": "not_applicable",
        "conversion_reason": "Conversación de agradecimiento post-servicio, sin intención de compra directa",
        "summary": "La clienta escribió para agradecer el excelente servicio recibido en su última visita. Mencionó que el resultado del tratamiento de keratina superó sus expectativas y que ya recomendó el negocio a tres amigas. El negocio respondió agradeciendo la confianza y ofreciendo un descuento en su próxima visita.",
        "key_points": ["Feedback positivo espontáneo recibido", "Clienta refirió el negocio a tres amigas", "Descuento de fidelidad ofrecido para próxima visita"],
        "customer_questions": [],
        "frt": 480.0, "avg_rt": 480.0, "unanswered": 0, "duration": 8.0,
        "op_coverage": 65.0,
    },
    # 15 — NOT_APPLICABLE, neutral, consulta general
    {
        "contact_key": 0,  # reuse María García
        "conv_started_at": _t(9, 10, 0),
        "conv_messages": 8, "conv_inbound": 5, "conv_outbound": 3,
        "sentiment": "neutral", "sentiment_score": 0.50,
        "sentiment_reason": "El contacto realizó una consulta informativa básica sin mostrar intención de compra",
        "primary_topic": "consulta general",
        "secondary_topics": ["disponibilidad y horarios"],
        "quality_score": 6.5,
        "quality_breakdown": {"helpfulness": 6.5, "tone": 7.0, "completeness": 6.0},
        "conversion_status": "not_applicable",
        "conversion_reason": "Consulta informativa general sin intención de compra en el corto plazo",
        "summary": "El contacto preguntó sobre los servicios que ofrece el negocio de manera general. Se le envió el menú completo de servicios con precios aproximados y horarios de atención. La conversación fue informativa y el contacto agradeció la información sin mostrar intención de agendar en el corto plazo.",
        "key_points": ["Menú de servicios enviado completo", "Horarios de atención informados", "Sin intención de compra inmediata"],
        "customer_questions": ["¿Qué servicios ofrecen?", "¿Cuáles son sus horarios?"],
        "frt": 600.0, "avg_rt": 600.0, "unanswered": 0, "duration": 15.0,
        "op_coverage": 60.0,
    },
    # 16 — PENDING, positive, información de servicios (1 UNANSWERED)
    {
        "contact_key": 3,  # reuse Juan Pérez
        "conv_started_at": _t(1, 16, 30),
        "conv_messages": 10, "conv_inbound": 6, "conv_outbound": 4,
        "sentiment": "positive", "sentiment_score": 0.68,
        "sentiment_reason": "La clienta mostró interés genuino en el servicio pero el negocio no respondió su última pregunta",
        "primary_topic": "información de servicios",
        "secondary_topics": ["precios y cotizaciones"],
        "quality_score": 7.2,
        "quality_breakdown": {"helpfulness": 7.5, "tone": 7.5, "completeness": 6.5},
        "conversion_status": "pending",
        "conversion_reason": "La clienta hizo una pregunta final que quedó sin respuesta del negocio",
        "summary": "La clienta preguntó sobre el proceso de coloración sin decoloración y los productos utilizados. La asesora explicó las opciones disponibles con buenos detalles iniciales. Sin embargo, la clienta hizo una pregunta final sobre si el servicio aplica para cabello muy oscuro y esa pregunta quedó sin respuesta. Oportunidad de conversión pendiente.",
        "key_points": ["Opciones de coloración sin decoloración explicadas", "Pregunta final de la clienta quedó sin responder", "Posible conversión en riesgo por falta de seguimiento"],
        "customer_questions": ["¿Funciona para cabello muy oscuro?", "¿Qué marcas de tinte usan?"],
        "frt": 420.0, "avg_rt": 510.0, "unanswered": 1, "duration": 30.0,
        "op_coverage": 55.0,
    },
]


async def run():
    conn = await asyncpg.connect(os.getenv("DIRECT_DATABASE_URL"))

    try:
        # ── 1. Create new contacts ─────────────────────────────────────────
        print("Creating contacts...")
        contact_ids = []
        for c in NEW_CONTACTS:
            existing = await conn.fetchval(
                "SELECT id FROM contacts WHERE phone = $1 AND client_id = $2",
                c["phone"], CLIENT_ID
            )
            if existing:
                contact_ids.append(str(existing))
                print(f"  Contact {c['name']} already exists: {existing}")
            else:
                await conn.execute("""
                    INSERT INTO contacts (id, client_id, phone, name, total_conversations, tags, created_at)
                    VALUES ($1, $2, $3, $4, 1, '[]', NOW())
                """, c["id"], CLIENT_ID, c["phone"], c["name"])
                contact_ids.append(c["id"])
                print(f"  Created contact: {c['name']} ({c['id']})")

        # ── 2. Update existing 4 analyses ─────────────────────────────────
        print("\nUpdating existing analyses...")
        for rec in EXISTING_UPDATES:
            await conn.execute("""
                UPDATE conversation_analysis SET
                    sentiment = $1,
                    sentiment_score = $2,
                    sentiment_reason = $3,
                    primary_topic = $4,
                    secondary_topics = $5,
                    quality_score = $6,
                    quality_breakdown = $7,
                    conversion_status = $8,
                    conversion_reason = $9,
                    summary = $10,
                    key_points = $11,
                    customer_questions = $12,
                    first_response_time_seconds = $13,
                    avg_response_time_seconds = $14,
                    median_response_time_seconds = $15,
                    p95_response_time_seconds = $16,
                    unanswered_count = $17,
                    total_messages = $18,
                    inbound_count = $19,
                    outbound_count = $20,
                    duration_minutes = $21,
                    delivery_rate = $22,
                    read_rate = $23,
                    is_ghosted = $24,
                    operational_coverage_score = $25,
                    trailing_inbound_messages = 0,
                    ai_provider = 'gemini',
                    ai_model = 'gemini-2.0-flash',
                    tokens_used = 1850,
                    tokens_input = 1500,
                    tokens_output = 350,
                    analysis_cost_usd = 0.00028
                WHERE id = $26
            """,
                rec["sentiment"],
                rec["sentiment_score"],
                rec["sentiment_reason"],
                rec["primary_topic"],
                json.dumps(rec["secondary_topics"]),
                rec["quality_score"],
                json.dumps(rec["quality_breakdown"]),
                rec["conversion_status"],
                rec["conversion_reason"],
                rec["summary"],
                json.dumps(rec["key_points"]),
                json.dumps(rec["customer_questions"]),
                rec["first_response_time_seconds"],
                rec["avg_response_time_seconds"],
                rec["median_response_time_seconds"],
                rec["p95_response_time_seconds"],
                rec["unanswered_count"],
                rec["total_messages"],
                rec["inbound_count"],
                rec["outbound_count"],
                rec["duration_minutes"],
                rec["delivery_rate"],
                rec["read_rate"],
                rec["is_ghosted"],
                rec["operational_coverage_score"],
                rec["analysis_id"],
            )
            print(f"  Updated analysis {rec['analysis_id'][:8]}... → {rec['conversion_status']}, {rec['sentiment']}, quality={rec['quality_score']}")

        # ── 3. Insert 12 new conversations + analyses ──────────────────────
        print("\nInserting new conversations + analyses...")
        for i, rec in enumerate(NEW_RECORDS):
            conv_id = str(uuid.uuid4())
            analysis_id = str(uuid.uuid4())
            contact_id = contact_ids[rec["contact_key"]]
            started_at = rec["conv_started_at"]
            last_msg_at = started_at + timedelta(minutes=rec["duration"])

            # Insert conversation
            await conn.execute("""
                INSERT INTO conversations
                    (id, client_id, contact_id, started_at, last_message_at,
                     message_count, inbound_count, outbound_count,
                     status, source, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'active','waha',NOW())
            """,
                conv_id, CLIENT_ID, contact_id,
                started_at, last_msg_at,
                rec["conv_messages"], rec["conv_inbound"], rec["conv_outbound"],
            )

            # Insert analysis
            await conn.execute("""
                INSERT INTO conversation_analysis (
                    id, conversation_id, analysis_job_id,
                    sentiment, sentiment_score, sentiment_reason,
                    primary_topic, secondary_topics,
                    quality_score, quality_breakdown,
                    conversion_status, conversion_reason,
                    summary, key_points, customer_questions,
                    first_response_time_seconds, avg_response_time_seconds,
                    median_response_time_seconds, p95_response_time_seconds,
                    unanswered_count, trailing_inbound_messages,
                    total_messages, inbound_count, outbound_count,
                    duration_minutes, delivery_rate, read_rate,
                    is_ghosted, operational_coverage_score,
                    ai_provider, ai_model,
                    tokens_used, tokens_input, tokens_output,
                    analysis_cost_usd, analyzed_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                    $16,$17,$18,$19,$20,0,$21,$22,$23,$24,$25,$26,$27,$28,
                    'gemini','gemini-2.0-flash',1850,1500,350,0.00028,NOW()
                )
            """,
                analysis_id, conv_id, JOB_ID,
                rec["sentiment"],
                rec["sentiment_score"],
                rec["sentiment_reason"],
                rec["primary_topic"],
                json.dumps(rec["secondary_topics"]),
                rec["quality_score"],
                json.dumps(rec["quality_breakdown"]),
                rec["conversion_status"],
                rec["conversion_reason"],
                rec["summary"],
                json.dumps(rec["key_points"]),
                json.dumps(rec["customer_questions"]),
                rec["frt"],
                rec["avg_rt"],
                round(rec["avg_rt"] * 0.9, 1),
                round(rec["avg_rt"] * 1.8, 1),
                rec["unanswered"],
                rec["conv_messages"],
                rec["conv_inbound"],
                rec["conv_outbound"],
                rec["duration"],
                1.0,
                0.88,
                False,
                rec["op_coverage"],
            )

            conv_num = i + 5
            print(f"  Conv {conv_num:02d}: {rec['primary_topic'][:25]:<26} | {rec['conversion_status']:<12} | {rec['sentiment']:<8} | q={rec['quality_score']} | frt={int(rec['frt']//60)}min")

        # ── 4. Update the analysis_job totals ──────────────────────────────
        print("\nUpdating analysis_job totals...")
        total_cost = round(16 * 0.00028, 5)
        await conn.execute("""
            UPDATE analysis_jobs SET
                status = 'completed',
                total_conversations = 16,
                processed_conversations = 16,
                ai_provider = 'gemini',
                ai_model = 'gemini-2.0-flash',
                total_tokens_used = 29600,
                total_tokens_input = 24000,
                total_tokens_output = 5600,
                total_cost_usd = $1,
                error_message = NULL
            WHERE id = $2
        """, total_cost, JOB_ID)
        print(f"  Job updated: 16 conversations, cost=${total_cost}")

        # ── 5. Quick summary ───────────────────────────────────────────────
        print("\n" + "="*60)
        all_analyses = await conn.fetch("""
            SELECT sentiment, quality_score, conversion_status, unanswered_count,
                   first_response_time_seconds
            FROM conversation_analysis
            WHERE analysis_job_id = $1
        """, JOB_ID)

        sentiments = [r["sentiment"] for r in all_analyses]
        qualities  = [r["quality_score"] for r in all_analyses if r["quality_score"]]
        conversions = [r["conversion_status"] for r in all_analyses]
        frts = [r["first_response_time_seconds"] for r in all_analyses if r["first_response_time_seconds"]]
        unanswered = sum(r["unanswered_count"] or 0 for r in all_analyses)

        import statistics as st
        avg_frt = st.mean(frts) if frts else 0
        avg_q   = st.mean(qualities) if qualities else 0

        print(f"Total conversations : {len(all_analyses)}")
        print(f"Sentiments          : +{sentiments.count('positive')} ~{sentiments.count('neutral')} -{sentiments.count('negative')}")
        print(f"Conversions         : converted={conversions.count('converted')}, lost={conversions.count('lost')}, pending={conversions.count('pending')}, n/a={conversions.count('not_applicable')}")
        print(f"Avg quality         : {avg_q:.2f}/10")
        print(f"Avg FRT             : {avg_frt/60:.1f} min")
        print(f"Unanswered          : {unanswered}")

        # Rough health score estimate
        applicable = [c for c in conversions if c not in ("not_applicable",)]
        converted  = conversions.count("converted")
        pos_pct    = sentiments.count("positive") / len(sentiments) * 100
        neu_pct    = sentiments.count("neutral")  / len(sentiments) * 100

        frt_score  = 65.0 if 300 < avg_frt < 900 else (85.0 if avg_frt <= 300 else 45.0)
        cov_score  = 85.0 if unanswered / len(all_analyses) * 100 < 10 else 65.0
        sent_score = min(100, pos_pct + neu_pct * 0.5)
        qual_score = avg_q * 10
        conv_score = (converted / len(applicable) * 100) if applicable else 50
        op_score   = 70.0

        health = (frt_score*0.25 + cov_score*0.15 + sent_score*0.20 +
                  qual_score*0.15 + conv_score*0.15 + op_score*0.10)
        print(f"\nEstimated health score: {health:.1f}/100")
        print("="*60)
        print("Done! Open the dashboard to see the updated analysis.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
