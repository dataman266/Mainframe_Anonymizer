from anonymizer.copybook.model import parse_picture, storage_length, PictureInfo


def test_parse_alphanumeric():
    info = parse_picture("X(30)")
    assert info == PictureInfo(numeric=False, signed=False, total_digits=0,
                               decimals=0, display_length=30)


def test_parse_unsigned_numeric():
    info = parse_picture("9(08)")
    assert info.numeric and not info.signed
    assert info.total_digits == 8 and info.decimals == 0
    assert info.display_length == 8


def test_parse_signed_decimal():
    info = parse_picture("S9(09)V99")
    assert info.numeric and info.signed
    assert info.total_digits == 11 and info.decimals == 2
    assert info.display_length == 11  # V and S take no storage in DISPLAY


def test_parse_literal_repeats():
    assert parse_picture("999").total_digits == 3
    assert parse_picture("XXX").display_length == 3
    assert parse_picture("9(02)V9(04)").decimals == 4


def test_storage_length_display():
    assert storage_length(parse_picture("X(20)"), "display") == 20
    assert storage_length(parse_picture("S9(09)V99"), "display") == 11


def test_storage_length_comp3():
    # digits // 2 + 1
    assert storage_length(parse_picture("S9(09)V99"), "comp-3") == 6
    assert storage_length(parse_picture("S9(11)V99"), "comp-3") == 7


def test_storage_length_comp():
    assert storage_length(parse_picture("9(04)"), "comp") == 2
    assert storage_length(parse_picture("9(09)"), "comp") == 4
    assert storage_length(parse_picture("9(18)"), "comp") == 8
