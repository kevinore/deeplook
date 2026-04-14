"""Tests for system message detection."""
import pytest

from app.ingestion.parsers.txt_system import is_system_message


@pytest.mark.parametrize("text", [
    "Los mensajes y llamadas están cifrados de extremo a extremo.",
    "Messages and calls are end-to-end encrypted.",
    "Diego creó el grupo \"Clientes VIP\"",
    "María fue eliminado",
    "was removed",
    "added John to the group",
    "Llamada de voz perdida",
    "Missed voice call",
    "activó los mensajes temporales",
    "turned on disappearing messages",
    "<b>System notification</b>",
    "cambió su número de teléfono a un número nuevo.",
])
def test_known_system_messages(text):
    assert is_system_message(text), f"Expected system message: {text}"


@pytest.mark.parametrize("text", [
    "Hola, ¿cómo estás?",
    "Me gustaría agendar una cita",
    "¡Confirmado! Nos vemos el jueves.",
    "¿Cuál es el precio?",
    "Hello, I need help with my order",
])
def test_non_system_messages(text):
    assert not is_system_message(text), f"Should NOT be system message: {text}"
