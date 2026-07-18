"""Plain-language helpers for the wizard UI."""
from __future__ import annotations

from anonymizer.copybook.model import Field

_ASCII_PRINTABLE_THRESHOLD = 0.7


def describe_field(field: Field) -> str:
    if field.usage == "comp-3":
        base = f"Packed number, {field.total_digits} digits"
    elif field.usage == "comp":
        base = f"Binary number, {field.total_digits} digits"
    elif field.numeric:
        base = f"Number, {field.total_digits} digits"
    else:
        return f"Text, {field.length} characters"
    if field.decimals:
        base += f" ({field.decimals} after the decimal point)"
    return base


def detect_encoding(first_bytes: bytes) -> str:
    """Heuristic: mostly ASCII-printable bytes -> ascii, else cp037."""
    if not first_bytes:
        return "ascii"
    printable = sum(1 for b in first_bytes if 0x20 <= b < 0x7F)
    if printable / len(first_bytes) >= _ASCII_PRINTABLE_THRESHOLD:
        return "ascii"
    return "cp037"
