"""Decode/encode a single field from/to raw record bytes.

All values cross this boundary as strings; numeric values are Decimal
strings.  Display numerics keep their leading zeros so masking rules see
the exact on-file representation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from anonymizer.codec.binary import decode_binary, encode_binary
from anonymizer.codec.packed import pack_comp3, unpack_comp3
from anonymizer.codec.text import decode_text, encode_text
from anonymizer.codec.zoned import decode_zoned, encode_zoned
from anonymizer.copybook.model import Field


class FieldCodecError(Exception):
    """A field could not be decoded or encoded."""


def _slice(field: Field, record: bytes) -> bytes:
    return record[field.offset:field.offset + field.length]


def _format_numeric(value: Decimal, decimals: int, pad_to: int | None = None) -> str:
    """Render a decoded numeric value without scientific notation.

    decimals > 0 always uses fixed-point notation.  decimals == 0 renders a
    sign-aware, zero-padded integer when ``pad_to`` is given (DISPLAY
    numerics, where leading zeros are part of the on-file representation);
    otherwise a plain sign-aware integer string (COMP / COMP-3, which have
    no meaningful "leading zero" width).
    """
    if decimals > 0:
        return format(value, "f")
    number = int(value)
    if pad_to:
        digits = str(abs(number)).rjust(pad_to, "0")
        return f"-{digits}" if number < 0 else digits
    return str(number)


def decode_field(field: Field, record: bytes, codepage: str) -> str:
    raw = _slice(field, record)
    try:
        if field.usage == "comp-3":
            value = unpack_comp3(raw, field.decimals)
            return _format_numeric(value, field.decimals)
        if field.usage == "comp":
            value = decode_binary(raw, field.decimals, field.signed)
            return _format_numeric(value, field.decimals)
        if field.numeric:
            value = decode_zoned(raw, field.decimals, field.signed, codepage)
            return _format_numeric(value, field.decimals, field.total_digits)
        return decode_text(raw, codepage)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FieldCodecError(
            f"field {field.name} at byte {field.offset}: {exc}") from exc


def encode_field(field: Field, value: str, codepage: str) -> bytes:
    try:
        if field.usage == "comp-3":
            return pack_comp3(Decimal(value), field.total_digits,
                              field.decimals, field.signed)
        if field.usage == "comp":
            return encode_binary(Decimal(value), field.length,
                                 field.decimals, field.signed)
        if field.numeric:
            return encode_zoned(Decimal(value), field.total_digits,
                                field.decimals, field.signed, codepage)
        return encode_text(value, field.length, codepage)
    except (ValueError, InvalidOperation) as exc:
        raise FieldCodecError(
            f"field {field.name}: cannot encode {value!r}: {exc}") from exc
