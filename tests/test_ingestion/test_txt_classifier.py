"""Tests for line classification (Pass 1)."""
import pytest

from app.ingestion.parsers.txt_classifier import LineType, classify_line


def test_message_start():
    cl = classify_line("1/11/25, 10:39 a. m. - María: Hola, buenos días!")
    assert cl.line_type == LineType.MESSAGE_START
    assert cl.sender == "María"
    assert "Hola" in cl.content


def test_system_message_encryption():
    cl = classify_line("1/11/25, 10:00 a. m. - Los mensajes y llamadas están cifrados de extremo a extremo.")
    assert cl.line_type == LineType.SYSTEM_MESSAGE


def test_continuation_line():
    cl = classify_line("  - Lunes a las 10am")
    assert cl.line_type == LineType.CONTINUATION


def test_empty_line():
    cl = classify_line("")
    assert cl.line_type == LineType.EMPTY

    cl2 = classify_line("   ")
    assert cl2.line_type == LineType.EMPTY


def test_message_start_24h():
    cl = classify_line("1/11/25, 22:39 - Negocio: ¡Confirmado!")
    assert cl.line_type == LineType.MESSAGE_START
    assert cl.sender == "Negocio"


def test_message_start_ios():
    cl = classify_line("[1/11/25, 10:39:00 a. m.] - Customer: Hello there")
    assert cl.line_type == LineType.MESSAGE_START
    assert cl.sender == "Customer"
