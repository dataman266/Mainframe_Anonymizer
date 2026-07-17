from anonymizer.codec.dispatch import decode_field, encode_field
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
