from anonymizer.copybook.model import Field
from anonymizer.masking.classifier import suggest_rule


def _f(name: str, numeric: bool = False, decimals: int = 0) -> Field:
    return Field(name=name, level=5, offset=0, length=10, numeric=numeric,
                 total_digits=10 if numeric else 0, decimals=decimals)


def test_pii_fields():
    assert suggest_rule(_f("CUST-NAME")) == ("person_name", True)
    assert suggest_rule(_f("CUST-SIN", numeric=True)) == ("sin", True)
    assert suggest_rule(_f("CUST-CARD-NUM", numeric=True)) == ("credit_card", True)
    assert suggest_rule(_f("CUST-STREET-ADDR")) == ("street_address", True)
    assert suggest_rule(_f("CUST-CITY")) == ("city", True)
    assert suggest_rule(_f("CUST-ZIPCODE")) == ("scramble", True)
    assert suggest_rule(_f("CUST-EMAIL")) == ("email", True)
    assert suggest_rule(_f("CUST-PHONE(1)")) == ("digits", True)


def test_dates():
    assert suggest_rule(_f("CUST-DOB", numeric=True)) == ("date_jitter", True)
    assert suggest_rule(_f("ACCT-OPEN-DT", numeric=True)) == ("date_jitter", True)
    assert suggest_rule(_f("ACCT-LAST-UPDT-DT", numeric=True)) == ("date_jitter", True)


def test_amounts():
    assert suggest_rule(_f("ACCT-BALANCE", numeric=True, decimals=2)) == ("numeric_noise", True)
    assert suggest_rule(_f("ACCT-INT-RATE", numeric=True, decimals=4)) == ("numeric_noise", True)
    assert suggest_rule(_f("CUST-AGE", numeric=True)) == ("numeric_noise", True)


def test_structural_fields_kept_and_unselected():
    assert suggest_rule(_f("FILLER")) == ("keep", False)
    assert suggest_rule(_f("ACCT-TYPE")) == ("keep", False)
    assert suggest_rule(_f("ACCT-STATUS")) == ("keep", False)
    assert suggest_rule(_f("REC-TYPE-CODE")) == ("keep", False)


def test_defaults():
    assert suggest_rule(_f("SOME-FREE-TEXT")) == ("scramble", True)
    assert suggest_rule(_f("ACCT-NUMBER", numeric=True)) == ("digits", True)
