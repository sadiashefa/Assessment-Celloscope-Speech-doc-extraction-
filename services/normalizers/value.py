"""
Value normaliser — parses raw OCR value strings into a canonical form.

Canonical form:
  numeric    : float   — always present
  comparator : str | None — "<", ">", "<=", ">=" extracted from prefix

Supported input formats (all from the assessment spec):
  "12.5"          → (12.5, None)
  "12,500"        → (12500.0, None)   thousands-comma separator
  "<0.5"          → (0.5, "<")
  "> 10"          → (10.0, ">")
  "<=2.5"         → (2.5, "<=")
  ">=5"           → (5.0, ">=")
  "1.2 x 10^3"   → (1200.0, None)   plain-text scientific
  "1.2 x 10³"    → (1200.0, None)   unicode superscript
  "1.2×10^3"     → (1200.0, None)   unicode ×
  "1.2e3"         → (1200.0, None)   standard scientific notation
  "1.2E+3"        → (1200.0, None)
  "0.8"           → (0.8, None)

Anything that cannot be confidently parsed raises ValueError.
The caller is responsible for preserving the raw string verbatim.
"""

import re
from dataclasses import dataclass

# Map unicode superscripts to their digit equivalents
_SUPERSCRIPT_MAP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

# Comparator prefixes to extract
_COMPARATOR_RE = re.compile(r"^(<=|>=|<|>)\s*")

# Matches "1.2 x 10^3", "1.2×10³", "1.2 × 10^3", "1.2x10^3" etc.
_SCIENTIFIC_TEXT_RE = re.compile(
    r"^([+-]?\d+(?:[.,]\d+)?)\s*[×x]\s*10\s*[\^]?\s*([⁰¹²³⁴⁵⁶⁷⁸⁹\d]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NormalizedValue:
    numeric: float
    comparator: str | None  # "<" | ">" | "<=" | ">=" | None


def _strip_thousands_comma(s: str) -> str:
    """Remove thousands-separator commas: '12,500' → '12500'."""
    # Only strip commas that are thousands separators (digit,digit{3})
    return re.sub(r"(\d),(\d{3})", r"\1\2", s)


def _parse_superscripts(s: str) -> str:
    """Replace unicode superscript digits with ASCII equivalents."""
    return s.translate(_SUPERSCRIPT_MAP)


def parse_value(raw: str) -> NormalizedValue:
    """
    Parse a raw OCR value string into a NormalizedValue.

    Raises ValueError if the string cannot be confidently parsed as a number.
    The caller must preserve the raw string verbatim and never guess.
    """
    if not raw or not raw.strip():
        raise ValueError(f"Empty value string: {raw!r}")

    s = raw.strip()
    s = _parse_superscripts(s)

    # Extract comparator prefix
    comparator: str | None = None
    m = _COMPARATOR_RE.match(s)
    if m:
        comparator = m.group(1)
        s = s[m.end():]

    s = s.strip()

    # Try plain-text scientific notation: "1.2 x 10^3"
    sci_match = _SCIENTIFIC_TEXT_RE.match(s)
    if sci_match:
        mantissa_str = _strip_thousands_comma(sci_match.group(1)).replace(",", ".")
        exponent_str = _parse_superscripts(sci_match.group(2))
        try:
            mantissa = float(mantissa_str)
            exponent = int(exponent_str)
            return NormalizedValue(numeric=mantissa * (10**exponent), comparator=comparator)
        except (ValueError, OverflowError):
            raise ValueError(f"Cannot parse scientific notation: {raw!r}")

    # Remove thousands commas before float conversion
    s = _strip_thousands_comma(s)

    # Replace comma-decimal separator (European style) only if no dot present
    if "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        return NormalizedValue(numeric=float(s), comparator=comparator)
    except ValueError:
        raise ValueError(f"Cannot parse numeric value: {raw!r}")
