from anonymizer.copybook.model import Field
from anonymizer.ui.helpers import describe_field, detect_encoding


def test_describe_text():
    f = Field(name="X", level=5, offset=0, length=30)
    assert describe_field(f) == "Text, 30 characters"


def test_describe_display_number():
    f = Field(name="X", level=5, offset=0, length=9, numeric=True, total_digits=9)
    assert describe_field(f) == "Number, 9 digits"


def test_describe_comp3_with_decimals():
    f = Field(name="X", level=5, offset=0, length=6, usage="comp-3",
              numeric=True, signed=True, total_digits=11, decimals=2)
    assert describe_field(f) == "Packed number, 11 digits (2 after the decimal point)"


def test_describe_comp():
    f = Field(name="X", level=5, offset=0, length=2, usage="comp",
              numeric=True, total_digits=4)
    assert describe_field(f) == "Binary number, 4 digits"


def test_detect_encoding_ascii():
    assert detect_encoding(b"HELLO WORLD 12345 MAIN ST") == "ascii"


def test_detect_encoding_ebcdic():
    assert detect_encoding("HELLO WORLD 12345".encode("cp037")) == "cp037"


def test_detect_encoding_empty_defaults_ascii():
    assert detect_encoding(b"") == "ascii"
