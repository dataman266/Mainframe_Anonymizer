import pytest

from anonymizer.codec.text import decode_text, encode_text


def test_ebcdic_round_trip():
    raw = "JOHN SMITH".encode("cp037").ljust(15, b"\x40")  # 0x40 = EBCDIC space
    assert decode_text(raw, "cp037") == "JOHN SMITH     "
    assert encode_text("JOHN SMITH", 15, "cp037") == raw


def test_ascii_round_trip():
    assert decode_text(b"TORONTO   ", "ascii") == "TORONTO   "
    assert encode_text("TORONTO", 10, "ascii") == b"TORONTO   "


def test_encode_truncates_to_field_length():
    assert encode_text("ABCDEFGHIJ", 5, "ascii") == b"ABCDE"


def test_encode_replaces_unmappable_chars():
    out = encode_text("CAFÉ☃", 6, "ascii")
    assert len(out) == 6


def test_decode_strict_raises_on_invalid_bytes():
    with pytest.raises(UnicodeDecodeError):
        decode_text(b"\xff", "ascii")
