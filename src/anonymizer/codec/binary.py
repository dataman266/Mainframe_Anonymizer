"""COMP (big-endian binary) encode/decode."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def decode_binary(raw: bytes, decimals: int, signed: bool) -> Decimal:
    number = int.from_bytes(raw, "big", signed=signed)
    return Decimal(number).scaleb(-decimals)


def encode_binary(value: Decimal, length: int, decimals: int,
                  signed: bool) -> bytes:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    try:
        return scaled.to_bytes(length, "big", signed=signed)
    except OverflowError as exc:
        raise ValueError(
            f"value {value} does not fit in {length} binary bytes") from exc
