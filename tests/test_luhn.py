from anonymizer.masking.luhn import is_luhn_valid, luhn_check_digit, make_luhn_valid


def test_known_valid_numbers():
    assert is_luhn_valid("4532015112830366")   # classic test PAN
    assert is_luhn_valid("046454286")          # canonical test SIN


def test_check_digit():
    assert luhn_check_digit("453201511283036") == "6"


def test_make_luhn_valid():
    fixed = make_luhn_valid("123456789")
    assert len(fixed) == 9
    assert fixed[:8] == "12345678"
    assert is_luhn_valid(fixed)
