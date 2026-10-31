"""Small time helpers for Ground: minutes from midnight, DOT-style HHMM, HH:MM."""


# Converts "HH:MM" or DOT-style "HHMM" (incl. "2400") to minutes from midnight.
# Args: s - time string.
# Returns: minutes from midnight (0..1440).
# Raises: ValueError if s is not a valid time.
def hhmm_to_min(s: str) -> int:
    s = s.strip().replace(":", "")
    if not s.isdigit() or len(s) > 4:
        raise ValueError(f"bad time {s!r}")
    s = s.zfill(4)
    h, m = int(s[:2]), int(s[2:])
    if m > 59 or h > 24:
        raise ValueError(f"bad time {s!r}")
    return h * 60 + m


# Formats minutes from midnight as "HH:MM", wrapping past midnight.
# Args: m - minutes from midnight (may exceed 1440).
# Returns: "HH:MM" string.
def min_to_hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"
