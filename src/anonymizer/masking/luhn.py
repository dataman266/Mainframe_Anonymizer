"""Luhn checksum helpers (used by SIN and card-number rules)."""
from __future__ import annotations


def luhn_check_digit(partial: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def is_luhn_valid(digits: str) -> bool:
    return digits.isdigit() and digits[-1] == luhn_check_digit(digits[:-1])


def make_luhn_valid(digits: str) -> str:
    return digits[:-1] + luhn_check_digit(digits[:-1])
