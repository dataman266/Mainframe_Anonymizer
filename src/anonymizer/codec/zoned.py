"""Zoned decimal (PIC 9 DISPLAY) encode/decode for EBCDIC and ASCII."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ASCII_POS = "{ABCDEFGHI"   # overpunch for +0..+9
_ASCII_NEG = "}JKLMNOPQR"   # overpunch for -0..-9


def _scaled_digits(value: Decimal, total_digits: int, decimals: int) -> tuple[str, bool]:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    negative = scaled < 0
    digits = str(abs(scaled))
    if len(digits) > total_digits:
        raise ValueError(f"value {value} does not fit in {total_digits} digits")
    return digits.rjust(total_digits, "0"), negative


def decode_zoned(raw: bytes, decimals: int, signed: bool, codepage: str) -> Decimal:
    if codepage == "cp037":
        digits = [b & 0x0F for b in raw]
        if any(d > 9 for d in digits):
            raise ValueError("invalid zoned digit")
        negative = signed and (raw[-1] >> 4) == 0x0D
    else:
        text = raw.decode("ascii")
        last = text[-1]
        negative = False
        if last in _ASCII_POS:
            text = text[:-1] + str(_ASCII_POS.index(last))
        elif last in _ASCII_NEG:
            text = text[:-1] + str(_ASCII_NEG.index(last))
            negative = True
        if not text.isdigit():
            raise ValueError(f"invalid zoned value {raw!r}")
        digits = [int(c) for c in text]
    number = int("".join(str(d) for d in digits) or "0")
    if negative:
        number = -number
    return Decimal(number).scaleb(-decimals)


def encode_zoned(value: Decimal, total_digits: int, decimals: int,
                 signed: bool, codepage: str) -> bytes:
    digits, negative = _scaled_digits(value, total_digits, decimals)
    if codepage == "cp037":
        out = bytearray(0xF0 | int(c) for c in digits)
        if signed:
            zone = 0xD0 if negative else 0xC0
            out[-1] = zone | int(digits[-1])
        return bytes(out)
    if signed:
        table = _ASCII_NEG if negative else _ASCII_POS
        return (digits[:-1] + table[int(digits[-1])]).encode("ascii")
    return digits.encode("ascii")
