from pathlib import Path

import pytest

from anonymizer.copybook.cb2xml_runner import (CopybookParseError,
                                               JavaNotFoundError,
                                               parse_copybook, find_java)

SAMPLES = Path(__file__).resolve().parents[1] / "samples" / "copybooks"

java_missing = find_java() is None


@pytest.mark.skipif(java_missing, reason="java not installed")
def test_parse_customer_copybook_end_to_end():
    layout = parse_copybook(SAMPLES / "customer.cpy")
    assert layout.name == "CUSTOMER-RECORD"
    assert layout.record_length == 202
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["CUST-SIN"].offset == 105
    assert by_name["CUST-BALANCE"].usage == "comp-3"
    assert by_name["CUST-BALANCE"].length == 6
    assert by_name["CUST-BRANCH-CODE"].usage == "comp"
    assert "CUST-PHONE(2)" in by_name


@pytest.mark.skipif(java_missing, reason="java not installed")
def test_parse_account_copybook_end_to_end():
    layout = parse_copybook(SAMPLES / "account.cpy")
    assert layout.record_length == 71
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["ACCT-BALANCE"].length == 7


@pytest.mark.skipif(java_missing, reason="java not installed")
def test_garbage_copybook_raises_friendly_error(tmp_path):
    bad = tmp_path / "bad.cpy"
    bad.write_text("this is not cobol at all {{{{")
    with pytest.raises((CopybookParseError,)):
        parse_copybook(bad)


def test_java_missing_error_message(monkeypatch):
    import anonymizer.copybook.cb2xml_runner as runner
    monkeypatch.setattr(runner, "find_java", lambda: None)
    with pytest.raises(JavaNotFoundError, match="Java"):
        runner.parse_copybook(SAMPLES / "customer.cpy")
