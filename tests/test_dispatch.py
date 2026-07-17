import pytest

from anonymizer.codec.dispatch import FieldCodecError, decode_field, encode_field
from anonymizer.copybook.model import Field

NAME = Field(name="CUST-NAME", level=5, offset=0, length=10)
SIN = Field(name="CUST-SIN", level=5, offset=10, length=9, picture="9(09)",
            numeric=True, total_digits=9)
BAL = Field(name="CUST-BALANCE", level=5, offset=19, length=6, usage="comp-3",
            picture="S9(09)V99", numeric=True, signed=True,
            total_digits=11, decimals=2)
BRANCH = Field(name="CUST-BRANCH-CODE", level=5, offset=25, length=2,
               usage="comp", picture="9(04)", numeric=True, total_digits=4)


def _record() -> bytes:
    rec = bytearray(27)
    rec[0:10] = encode_field(NAME, "JOHN SMITH", "cp037")
    rec[10:19] = encode_field(SIN, "046454286", "cp037")
    rec[19:25] = encode_field(BAL, "-12345.67", "cp037")
    rec[25:27] = encode_field(BRANCH, "1234", "cp037")
    return bytes(rec)


def test_round_trip_all_usages():
    rec = _record()
    assert decode_field(NAME, rec, "cp037") == "JOHN SMITH"
    assert decode_field(SIN, rec, "cp037") == "046454286"
    assert decode_field(BAL, rec, "cp037") == "-12345.67"
    assert decode_field(BRANCH, rec, "cp037") == "1234"


def test_numeric_display_preserves_leading_zeros():
    rec = _record()
    assert decode_field(SIN, rec, "cp037").startswith("0")


def test_encode_field_length_is_exact():
    assert len(encode_field(BAL, "1.00", "cp037")) == 6
    assert len(encode_field(NAME, "AB", "cp037")) == 10


SIGNED_NUM = Field(name="SIGNED-NUM", level=5, offset=0, length=5,
                    picture="S9(05)", numeric=True, signed=True,
                    total_digits=5, decimals=0)


def test_signed_zero_decimal_display_round_trips_with_sign():
    encoded = encode_field(SIGNED_NUM, "-123", "cp037")
    decoded = decode_field(SIGNED_NUM, encoded, "cp037")
    assert decoded == "-00123"
    re_encoded = encode_field(SIGNED_NUM, decoded, "cp037")
    assert re_encoded == encoded


TINY_COMP = Field(name="TINY-COMP", level=5, offset=0, length=4, usage="comp",
                   picture="9(01)V9(07)", numeric=True, signed=False,
                   total_digits=8, decimals=7)


def test_comp_decimals_seven_avoids_scientific_notation():
    encoded = encode_field(TINY_COMP, "0.0000001", "cp037")
    assert decode_field(TINY_COMP, encoded, "cp037") == "0.0000001"


BAD_TEXT = Field(name="BAD-TEXT", level=5, offset=0, length=1)


def test_decode_field_on_invalid_bytes_raises_field_codec_error():
    with pytest.raises(FieldCodecError):
        decode_field(BAD_TEXT, b"\xff", "ascii")
