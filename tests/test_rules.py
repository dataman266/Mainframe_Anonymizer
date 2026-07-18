from anonymizer.copybook.model import Field
from anonymizer.masking.luhn import is_luhn_valid
from anonymizer.masking.rules import RULES, apply_rule

TEXT30 = Field(name="CUST-NAME", level=5, offset=0, length=30)
SIN = Field(name="CUST-SIN", level=5, offset=0, length=9, numeric=True, total_digits=9)
CARD = Field(name="CUST-CARD-NUM", level=5, offset=0, length=16, numeric=True,
             total_digits=16)
DOB = Field(name="CUST-DOB", level=5, offset=0, length=8, numeric=True, total_digits=8)
BAL = Field(name="CUST-BALANCE", level=5, offset=0, length=6, usage="comp-3",
            numeric=True, signed=True, total_digits=11, decimals=2)
SEED = "unit-test-seed"


def test_registry_contains_all_rules():
    for name in ["keep", "person_name", "sin", "credit_card", "digits",
                 "street_address", "city", "email", "scramble",
                 "date_jitter", "numeric_noise"]:
        assert name in RULES


def test_every_rule_is_deterministic():
    for name in RULES:
        v = "19850214" if name in ("date_jitter",) else "046454286"
        f = DOB if name == "date_jitter" else SIN
        assert apply_rule(name, v, f, SEED) == apply_rule(name, v, f, SEED)


def test_keep_is_identity():
    assert apply_rule("keep", "ANYTHING", TEXT30, SEED) == "ANYTHING"


def test_person_name_changes_and_fits():
    out = apply_rule("person_name", "JOHN SMITH", TEXT30, SEED)
    assert out != "JOHN SMITH"
    assert len(out) <= 30


def test_sin_is_nine_digits_luhn_valid_and_changed():
    out = apply_rule("sin", "046454286", SIN, SEED)
    assert len(out) == 9 and out.isdigit()
    assert is_luhn_valid(out)
    assert out != "046454286"


def test_credit_card_preserves_length_and_luhn():
    out = apply_rule("credit_card", "4532015112830366", CARD, SEED)
    assert len(out) == 16 and out.isdigit()
    assert is_luhn_valid(out)
    assert out != "4532015112830366"


def test_digits_preserves_non_digits():
    out = apply_rule("digits", "416-555-1234", TEXT30, SEED)
    assert len(out) == 12 and out[3] == "-" and out[7] == "-"
    assert out != "416-555-1234"


def test_scramble_preserves_char_classes():
    out = apply_rule("scramble", "M5V 2T6", TEXT30, SEED)
    assert len(out) == 7 and out[3] == " "
    assert out[0].isupper() and out[1].isdigit()


def test_date_jitter_stays_parseable():
    out = apply_rule("date_jitter", "19850214", DOB, SEED)
    assert len(out) == 8 and out.isdigit()
    assert out != "19850214"


def test_date_jitter_falls_back_on_garbage():
    out = apply_rule("date_jitter", "99999999", DOB, SEED)
    assert len(out) == 8 and out.isdigit()


def test_numeric_noise_changes_value_within_capacity():
    out = apply_rule("numeric_noise", "-12345.67", BAL, SEED)
    assert out != "-12345.67"
    from decimal import Decimal
    d = Decimal(out)
    assert abs(d) < Decimal(10) ** (BAL.total_digits - BAL.decimals)
    assert d.as_tuple().exponent == -2
