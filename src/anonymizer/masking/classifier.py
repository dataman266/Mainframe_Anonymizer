"""Suggest a masking rule per field from its copybook name and type.

Returns (rule_name, enabled).  PII keywords are checked before structural
keep-keywords so e.g. CUST-ZIPCODE matches ZIP before CODE.  Structural
fields (record types, statuses, filler) default to keep/unselected because
masking them breaks downstream parsing.  First match wins.
"""
from __future__ import annotations

from anonymizer.copybook.model import Field

# Keyword matching below is unanchored substring search (e.g. "AGE" also
# matches inside "PACKAGE"), not word-boundary matching. This trades some
# false positives for simplicity; copybook field names are short and
# hyphen-segmented in practice, which keeps false hits rare.
_KEEP_KEYWORDS = ("FILLER", "TYPE", "STATUS", "CODE", "IND", "FLAG")
_RULE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("SIN", "SSN"), "sin"),
    (("CARD", "PAN"), "credit_card"),
    (("NAME",), "person_name"),
    (("STREET", "ADDR"), "street_address"),
    (("CITY",), "city"),
    (("ZIP", "POSTAL"), "zipcode_scramble"),
    (("EMAIL",), "email"),
    (("PHONE", "TEL"), "digits"),
    (("DOB", "BIRTH", "DATE", "-DT"), "date_jitter"),
    (("BAL", "AMT", "AMOUNT", "RATE", "AGE"), "numeric_noise"),
)


def suggest_rule(field: Field) -> tuple[str, bool]:
    upper = field.name.upper()
    for keywords, rule in _RULE_KEYWORDS:
        if any(k in upper for k in keywords):
            if rule == "zipcode_scramble":
                return ("scramble", True)
            if rule == "date_jitter" and not field.numeric:
                continue
            return (rule, True)
    for keyword in _KEEP_KEYWORDS:
        if keyword in upper:
            return ("keep", False)
    if field.numeric:
        return ("digits", True)
    return ("scramble", True)
