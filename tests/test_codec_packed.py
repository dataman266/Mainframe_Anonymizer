from decimal import Decimal

import pytest

from anonymizer.codec.packed import pack_comp3, unpack_comp3


def test_unpack_positive():
    # 12345.67 as S9(5)V99 -> digits 1234567, sign C
    assert unpack_comp3(bytes([0x12, 0x34, 0x56, 0x7C]), 2) == Decimal("12345.67")


def test_unpack_negative():
    assert unpack_comp3(bytes([0x12, 0x34, 0x56, 0x7D]), 2) == Decimal("-12345.67")


def test_unpack_unsigned_f_sign():
    assert unpack_comp3(bytes([0x00, 0x12, 0x3F]), 0) == Decimal("123")


def test_pack_round_trip_signed():
    raw = pack_comp3(Decimal("-9876543.21"), total_digits=11, decimals=2, signed=True)
    assert len(raw) == 6  # 11 digits -> 6 bytes
    assert unpack_comp3(raw, 2) == Decimal("-9876543.21")


def test_pack_round_trip_unsigned():
    raw = pack_comp3(Decimal("42"), total_digits=5, decimals=0, signed=False)
    assert len(raw) == 3
    assert unpack_comp3(raw, 0) == Decimal("42")


def test_pack_overflow_raises():
    with pytest.raises(ValueError):
        pack_comp3(Decimal("123456"), total_digits=5, decimals=0, signed=False)


def test_unpack_garbage_raises():
    with pytest.raises(ValueError):
        unpack_comp3(bytes([0xAB, 0xCD]), 0)  # A/B are not decimal digits
