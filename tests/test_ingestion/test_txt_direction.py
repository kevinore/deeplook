"""Tests for business vs customer direction detection."""
import pytest

from app.ingestion.parsers.txt_direction import auto_detect_business, detect_direction


def test_direction_name_match():
    assert detect_direction("Wellness By Diego Omar", ["Wellness By Diego Omar"]) == "outbound"


def test_direction_partial_match():
    assert detect_direction("Valentina Ávila", ["Valentina"]) == "outbound"


def test_direction_phone_match():
    assert detect_direction("+57 313 485 9647", ["+57 3134859647"]) == "outbound"


def test_direction_phone_last_10_digits():
    assert detect_direction("313 485 9647", ["3134859647"]) == "outbound"


def test_direction_customer_inbound():
    assert detect_direction("María González", ["Negocio XYZ"]) == "inbound"


def test_direction_case_insensitive():
    assert detect_direction("wellness by diego omar", ["Wellness By Diego Omar"]) == "outbound"


def test_auto_detect_business():
    senders = ["Negocio", "Negocio", "Negocio", "Cliente", "Cliente"]
    business, confident = auto_detect_business(senders)
    assert business == "Negocio"
    assert confident is False


def test_auto_detect_empty():
    business, _ = auto_detect_business([])
    assert business is None
