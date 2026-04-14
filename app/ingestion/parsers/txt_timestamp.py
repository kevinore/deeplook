"""
Timestamp extraction for WhatsApp .txt exports.

Handles all observed format variations:
  1. Spanish Android 12h:  1/11/25, 10:39 a. m.
  2. Spanish Android 12h:  1/11/25, 10:39 a.m.
  3. Spanish Android 12h:  01/11/2025, 10:39 a. m.  (4-digit year)
  4. English Android 12h:  1/11/25, 10:39 AM
  5. Android 24h:          1/11/25, 22:39
  6. iOS Spanish:          [1/11/25, 10:39:00 a. m.]
  7. iOS English:          [1/11/25, 10:39:00 AM]
"""
import re
from datetime import datetime

# Matches optional leading bracket, date part, time, optional AM/PM
_TS_PATTERN = re.compile(
    r"""
    ^
    \[?                                         # optional opening bracket (iOS)
    (?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{2,4})  # date
    ,\s*
    (?P<hour>\d{1,2}):(?P<minute>\d{2})         # hour:minute
    (?::(?P<second>\d{2}))?                     # optional seconds (iOS)
    \s*
    (?P<ampm>
        [Aa]\.?\s*[Mm]\.?                       # a.m. / a. m. / am / AM
        |[Pp]\.?\s*[Mm]\.?                      # p.m. / p. m. / pm / PM
    )?
    \]?                                         # optional closing bracket (iOS)
    \s*-\s*                                     # separator
    """,
    re.VERBOSE,
)

_SEPARATOR_PATTERN = re.compile(
    r"""
    ^\[?
    \d{1,2}/\d{1,2}/\d{2,4}
    ,\s*\d{1,2}:\d{2}(?::\d{2})?
    \s*(?:[AaPp]\.?\s*[Mm]\.?)?
    \]?\s*-\s*
    """,
    re.VERBOSE,
)


def has_timestamp(line: str) -> bool:
    """Return True if the line starts with a recognised WhatsApp timestamp."""
    return bool(_SEPARATOR_PATTERN.match(line))


def extract_timestamp(line: str) -> tuple[datetime | None, str]:
    """
    Parse the timestamp from the start of a line.

    Returns (datetime_or_None, remainder_of_line_after_separator).
    Remainder includes the sender + message content.
    """
    m = _TS_PATTERN.match(line)
    if not m:
        return None, line

    day = int(m.group("day"))
    month = int(m.group("month"))
    year = int(m.group("year"))
    hour = int(m.group("hour"))
    minute = int(m.group("minute"))
    second = int(m.group("second") or 0)

    # Normalise 2-digit year
    if year < 100:
        year += 2000

    # AM/PM handling
    ampm_raw = (m.group("ampm") or "").strip().replace(" ", "").replace(".", "").upper()
    if ampm_raw in ("AM", "A M"):
        if hour == 12:
            hour = 0
    elif ampm_raw in ("PM", "P M"):
        if hour != 12:
            hour += 12

    try:
        dt = datetime(year, month, day, hour, minute, second)
    except ValueError:
        # Try swapping day/month for ambiguous dates
        try:
            dt = datetime(year, day, month, hour, minute, second)
        except ValueError:
            return None, line

    remainder = line[m.end():]
    return dt, remainder
