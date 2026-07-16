"""COMP-3 (packed decimal) encode/decode."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_NEGATIVE_SIGNS = (0x0B, 0x0D)


def unpack_comp3(raw: bytes, decimals: int) -> Decimal:
    if not raw:
        raise ValueError("empty packed field")
    nibbles: list[int] = []
    for b in raw:
        nibbles.append((b >> 4) & 0x0F)
        nibbles.append(b & 0x0F)
    sign_nibble = nibbles.pop()
    if sign_nibble < 0x0A:
        raise ValueError(f"invalid packed sign nibble 0x{sign_nibble:X}")
    if any(d > 9 for d in nibbles):
        raise ValueError("invalid digit nibble in packed field")
    number = int("".join(str(d) for d in nibbles) or "0")
    if sign_nibble in _NEGATIVE_SIGNS:
        number = -number
    return Decimal(number).scaleb(-decimals)


def pack_comp3(value: Decimal, total_digits: int, decimals: int,
               signed: bool) -> bytes:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    negative = scaled < 0
    digit_str = str(abs(scaled))
    if len(digit_str) > total_digits:
        raise ValueError(
            f"value {value} does not fit in {total_digits} digits")
    digit_str = digit_str.rjust(total_digits, "0")
    if total_digits % 2 == 0:          # keep an odd digit count before the sign
        digit_str = "0" + digit_str
    sign = 0x0D if (signed and negative) else (0x0C if signed else 0x0F)
    nibbles = [int(c) for c in digit_str] + [sign]
    return bytes((nibbles[i] << 4) | nibbles[i + 1]
                 for i in range(0, len(nibbles), 2))
