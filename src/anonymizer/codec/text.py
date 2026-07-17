"""Alphanumeric (PIC X) encode/decode for EBCDIC and ASCII."""
from __future__ import annotations


def decode_text(raw: bytes, codepage: str) -> str:
    return raw.decode(codepage, errors="strict")


def encode_text(value: str, length: int, codepage: str) -> bytes:
    encoded = value[:length].encode(codepage, errors="replace")
    pad = " ".encode(codepage)
    return encoded.ljust(length, pad)
