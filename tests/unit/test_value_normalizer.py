"""
Tests for the value normaliser.

Covers every format mentioned in the assessment spec plus boundary cases.
Each test has one clear purpose — a failure tells you exactly what broke.
"""

import pytest

from services.normalizers.value import NormalizedValue, parse_value


# ---------------------------------------------------------------------------
# Happy-path cases
# ---------------------------------------------------------------------------

def test_plain_float():
    result = parse_value("12.5")
    assert result == NormalizedValue(numeric=12.5, comparator=None)


def test_plain_integer():
    result = parse_value("42")
    assert result == NormalizedValue(numeric=42.0, comparator=None)


def test_thousands_comma():
    """12,500 is a thousands-separated number, not a decimal comma."""
    result = parse_value("12,500")
    assert result == NormalizedValue(numeric=12500.0, comparator=None)


def test_large_thousands_comma():
    result = parse_value("1,234,567")
    assert result == NormalizedValue(numeric=1234567.0, comparator=None)


def test_comparator_less_than():
    result = parse_value("<0.5")
    assert result == NormalizedValue(numeric=0.5, comparator="<")


def test_comparator_greater_than_with_space():
    result = parse_value("> 10")
    assert result == NormalizedValue(numeric=10.0, comparator=">")


def test_comparator_less_equal():
    result = parse_value("<=2.5")
    assert result == NormalizedValue(numeric=2.5, comparator="<=")


def test_comparator_greater_equal():
    result = parse_value(">=5")
    assert result == NormalizedValue(numeric=5.0, comparator=">=")


def test_scientific_text_notation():
    """1.2 x 10^3 → 1200.0"""
    result = parse_value("1.2 x 10^3")
    assert result == NormalizedValue(numeric=1200.0, comparator=None)


def test_scientific_unicode_times():
    """1.2×10^3 using unicode × character."""
    result = parse_value("1.2×10^3")
    assert result == NormalizedValue(numeric=1200.0, comparator=None)


def test_scientific_unicode_superscript():
    """1.2 x 10³ using unicode superscript digit."""
    result = parse_value("1.2 x 10³")
    assert result == NormalizedValue(numeric=1200.0, comparator=None)


def test_standard_e_notation():
    result = parse_value("1.2e3")
    assert result.numeric == pytest.approx(1200.0)
    assert result.comparator is None


def test_standard_e_notation_uppercase():
    result = parse_value("1.2E+3")
    assert result.numeric == pytest.approx(1200.0)


def test_whitespace_trimmed():
    result = parse_value("  7.4  ")
    assert result == NormalizedValue(numeric=7.4, comparator=None)


def test_comparator_with_thousands():
    """Comparator combined with thousands-separated number."""
    result = parse_value(">12,500")
    assert result == NormalizedValue(numeric=12500.0, comparator=">")


# ---------------------------------------------------------------------------
# Error cases — must raise ValueError, never guess
# ---------------------------------------------------------------------------

def test_empty_string_raises():
    with pytest.raises(ValueError):
        parse_value("")


def test_whitespace_only_raises():
    with pytest.raises(ValueError):
        parse_value("   ")


def test_text_gibberish_raises():
    with pytest.raises(ValueError):
        parse_value("N/A")


def test_pure_text_raises():
    with pytest.raises(ValueError):
        parse_value("Positive")


def test_range_string_raises():
    """A reference range like '0.8 - 1.2' must not be silently parsed."""
    with pytest.raises(ValueError):
        parse_value("0.8 - 1.2")
