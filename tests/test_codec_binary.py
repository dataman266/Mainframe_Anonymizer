from decimal import Decimal

import pytest

from anonymizer.codec.binary import decode_binary, encode_binary


def test_decode_halfword():
    assert decode_binary(b"\x30\x39", decimals=0, signed=False) == Decimal("12345")


def test_decode_signed_negative():
    assert decode_binary(b"\xFF\xFF", decimals=0, signed=True) == Decimal("-1")


def test_decode_with_decimals():
    assert decode_binary(b"\x30\x39", decimals=2, signed=False) == Decimal("123.45")


def test_encode_round_trip_fullword():
    raw = encode_binary(Decimal("-123456.78"), length=4, decimals=2, signed=True)
    assert len(raw) == 4
    assert decode_binary(raw, decimals=2, signed=True) == Decimal("-123456.78")


def test_encode_overflow_raises():
    with pytest.raises(ValueError):
        encode_binary(Decimal("70000"), length=2, decimals=0, signed=True)
