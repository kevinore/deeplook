"""
Tests for timestamp parsing — one test per format variation.
"""
import pytest
from datetime import datetime

from app.ingestion.parsers.txt_timestamp import extract_timestamp, has_timestamp


# All 7 format variations from the spec
@pytest.mark.parametrize("line,expected_dt", [
    # 1. Spanish Android 12h: a. m. with spaces
    ("1/11/25, 10:39 a. m. - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # 2. Spanish Android 12h: a.m. without space
    ("1/11/25, 10:39 a.m. - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # 3. Spanish Android 4-digit year
    ("01/11/2025, 10:39 a. m. - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # 4. English Android 12h AM
    ("1/11/25, 10:39 AM - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # 5. Android 24h
    ("1/11/25, 22:39 - Sender: Hello", datetime(2025, 11, 1, 22, 39, 0)),
    # 6. iOS Spanish: brackets + seconds
    ("[1/11/25, 10:39:00 a. m.] - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # 7. iOS English
    ("[1/11/25, 10:39:00 AM] - Sender: Hello", datetime(2025, 11, 1, 10, 39, 0)),
    # PM conversion
    ("1/11/25, 2:30 p. m. - Sender: Hello", datetime(2025, 11, 1, 14, 30, 0)),
    # Noon edge case
    ("1/11/25, 12:00 p. m. - Sender: Hello", datetime(2025, 11, 1, 12, 0, 0)),
    # Midnight edge case
    ("1/11/25, 12:00 a. m. - Sender: Hello", datetime(2025, 11, 1, 0, 0, 0)),
])
def test_timestamp_formats(line, expected_dt):
    dt, remainder = extract_timestamp(line)
    assert dt == expected_dt
    assert "Sender: Hello" in remainder


def test_has_timestamp_true():
    assert has_timestamp("1/11/25, 10:39 a. m. - Sender: msg")
    assert has_timestamp("[1/11/25, 10:39:00 AM] - Sender: msg")


def test_has_timestamp_false():
    assert not has_timestamp("This is a continuation line")
    assert not has_timestamp("- Some line without timestamp")
    assert not has_timestamp("")


def test_extract_timestamp_invalid():
    dt, remainder = extract_timestamp("Not a timestamp line")
    assert dt is None
    assert remainder == "Not a timestamp line"
