from decimal import Decimal

import pytest

from anonymizer.codec.zoned import decode_zoned, encode_zoned


def test_ebcdic_unsigned_round_trip():
    raw = "0012345".encode("cp037")
    assert decode_zoned(raw, decimals=0, signed=False, codepage="cp037") == Decimal("12345")
    assert encode_zoned(Decimal("12345"), 7, 0, False, "cp037") == raw


def test_ebcdic_signed_negative():
    # -123: F1 F2 D3 (last zone D = negative)
    raw = bytes([0xF1, 0xF2, 0xD3])
    assert decode_zoned(raw, 0, True, "cp037") == Decimal("-123")
    assert encode_zoned(Decimal("-123"), 3, 0, True, "cp037") == raw


def test_ebcdic_signed_positive():
    raw = bytes([0xF1, 0xF2, 0xC3])
    assert decode_zoned(raw, 0, True, "cp037") == Decimal("123")
    assert encode_zoned(Decimal("123"), 3, 0, True, "cp037") == raw


def test_ascii_unsigned_round_trip():
    assert decode_zoned(b"0099", 2, False, "ascii") == Decimal("0.99")
    assert encode_zoned(Decimal("0.99"), 4, 2, False, "ascii") == b"0099"


def test_ascii_signed_overpunch():
    # -125 in ASCII overpunch: "12N" (N = -5)
    assert decode_zoned(b"12N", 0, True, "ascii") == Decimal("-125")
    assert encode_zoned(Decimal("-125"), 3, 0, True, "ascii") == b"12N"
    # +125: "12E"
    assert decode_zoned(b"12E", 0, True, "ascii") == Decimal("125")


def test_overflow_raises():
    with pytest.raises(ValueError):
        encode_zoned(Decimal("1234"), 3, 0, False, "ascii")
