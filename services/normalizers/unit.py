"""
Unit and date normalisers.

Unit canonical forms:
  Mass concentration : g/dL, mg/dL, μg/dL, ng/dL
  Molar              : mmol/L, μmol/L, nmol/L, pmol/L
  Enzyme activity    : IU/L, U/L, mIU/L
  Cell counts        : 10³/μL, 10⁶/μL, cells/μL
  Ratio/fraction     : % (percentage)
  Pressure           : mmHg
  Unknown            : preserved verbatim

Date canonical form: ISO 8601 YYYY-MM-DD
If the date cannot be confidently parsed, the raw string is returned unchanged.
"""

import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Unit normalisation
# ---------------------------------------------------------------------------

# Map raw OCR variants → canonical form
_UNIT_MAP: dict[str, str] = {
    # g/dL variants
    "g/dl": "g/dL",
    "gm/dl": "g/dL",
    "gm/dL": "g/dL",
    "G/dl": "g/dL",
    "G/dL": "g/dL",
    "g/dL": "g/dL",
    # mg/dL variants
    "mg/dl": "mg/dL",
    "Mg/dl": "mg/dL",
    "MG/DL": "mg/dL",
    "mg/dL": "mg/dL",
    # μg/dL variants
    "ug/dl": "μg/dL",
    "ug/dL": "μg/dL",
    "mcg/dL": "μg/dL",
    "μg/dL": "μg/dL",
    # mmol/L variants
    "mmol/l": "mmol/L",
    "mmol/L": "mmol/L",
    "MMOL/L": "mmol/L",
    # μmol/L variants
    "umol/L": "μmol/L",
    "umol/l": "μmol/L",
    "μmol/L": "μmol/L",
    # IU/L variants
    "iu/l": "IU/L",
    "IU/l": "IU/L",
    "U/L": "IU/L",
    "u/L": "IU/L",
    "IU/L": "IU/L",
    # Cell count variants
    "10^3/ul": "10³/μL",
    "10^3/μL": "10³/μL",
    "10^3/uL": "10³/μL",
    "x10^3/uL": "10³/μL",
    "x10^3/μL": "10³/μL",
    "10³/μL": "10³/μL",
    "10^3/μl": "10³/μL",
    "10^6/ul": "10⁶/μL",
    "10^6/μL": "10⁶/μL",
    "10⁶/μL": "10⁶/μL",
    "cells/ul": "cells/μL",
    "cells/μL": "cells/μL",
    # Percentage
    "%": "%",
    # mmHg
    "mmhg": "mmHg",
    "mmHg": "mmHg",
    # ng/dL
    "ng/dl": "ng/dL",
    "ng/dL": "ng/dL",
}


def normalize_unit(raw: str) -> str:
    """
    Return canonical unit string.
    Strips surrounding whitespace before lookup.
    Unknown units are returned verbatim — never dropped or guessed.
    """
    stripped = raw.strip()
    return _UNIT_MAP.get(stripped, stripped)


# ---------------------------------------------------------------------------
# Date normalisation
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%d/%m/%Y",   # 15/07/2026
    "%d-%m-%Y",   # 15-07-2026
    "%Y-%m-%d",   # 2026-07-15  (already ISO)
    "%d %b %Y",   # 15 Jul 2026
    "%d %B %Y",   # 15 July 2026
    "%B %d, %Y",  # July 15, 2026
    "%b %d, %Y",  # Jul 15, 2026
    "%d.%m.%Y",   # 15.07.2026
    "%m/%d/%Y",   # 07/15/2026  (US format — lower priority)
]


def normalize_date(raw: str) -> str:
    """
    Parse raw date string and return ISO 8601 (YYYY-MM-DD).
    Returns the original string verbatim if parsing fails.
    """
    stripped = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Cannot parse — return verbatim, never guess
    return stripped
