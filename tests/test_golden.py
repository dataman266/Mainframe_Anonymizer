"""End-to-end tests over the committed sample files (require java)."""
from pathlib import Path

import pytest

from anonymizer.codec.dispatch import decode_field
from anonymizer.copybook.cb2xml_runner import find_java, parse_copybook
from anonymizer.engine.reader import iter_records
from anonymizer.masking.luhn import is_luhn_valid
from anonymizer.pipeline import default_plans, run_anonymization

ROOT = Path(__file__).resolve().parents[1]
CPY = ROOT / "samples" / "copybooks" / "customer.cpy"
DATA = ROOT / "samples" / "data" / "customer.cp037.dat"
ACCOUNT_CPY = ROOT / "samples" / "copybooks" / "account.cpy"
ACCOUNT_DATA = ROOT / "samples" / "data" / "account.cp037.dat"

pytestmark = pytest.mark.skipif(find_java() is None, reason="java not installed")


@pytest.fixture(scope="module")
def layout():
    return parse_copybook(CPY)


@pytest.fixture(scope="module")
def account_layout():
    return parse_copybook(ACCOUNT_CPY)


def test_end_to_end_masking(tmp_path, layout):
    out = tmp_path / "masked.dat"
    plans = default_plans(layout)
    result = run_anonymization(DATA, out, layout, "cp037", plans,
                               seed="golden", target_count=50)
    assert result.records_written == 50
    assert out.stat().st_size == DATA.stat().st_size    # layout preserved
    by_name = {f.name: f for f in layout.leaves}
    originals = list(iter_records(DATA, layout, "cp037"))
    masked = list(iter_records(out, layout, "cp037"))
    for orig, new in zip(originals, masked):
        # PII changed
        assert decode_field(by_name["CUST-NAME"], new, "cp037") != \
            decode_field(by_name["CUST-NAME"], orig, "cp037")
        # SIN changed and Luhn-valid
        sin = decode_field(by_name["CUST-SIN"], new, "cp037")
        assert is_luhn_valid(sin)
        assert sin != decode_field(by_name["CUST-SIN"], orig, "cp037")
        # structural bytes untouched (FILLER field)
        filler = by_name["FILLER"]
        assert new[filler.offset:filler.offset + filler.length] == \
            orig[filler.offset:filler.offset + filler.length]


def test_determinism_across_runs(tmp_path, layout):
    o1, o2 = tmp_path / "a.dat", tmp_path / "b.dat"
    plans = default_plans(layout)
    run_anonymization(DATA, o1, layout, "cp037", plans, "golden", 50)
    run_anonymization(DATA, o2, layout, "cp037", plans, "golden", 50)
    assert o1.read_bytes() == o2.read_bytes()


def test_synthesis_to_120_records(tmp_path, layout):
    out = tmp_path / "big.dat"
    plans = default_plans(layout)
    result = run_anonymization(DATA, out, layout, "cp037", plans, "golden", 120)
    assert result.records_written == 120
    assert result.synthetic_records == 70
    records = list(iter_records(out, layout, "cp037"))
    assert len(records) == 120
    by_name = {f.name: f for f in layout.leaves}
    for rec in records:                       # every record still decodes
        decode_field(by_name["CUST-BALANCE"], rec, "cp037")


def test_ascii_variant_end_to_end(tmp_path, layout):
    data = ROOT / "samples" / "data" / "customer.ascii.dat"
    out = tmp_path / "masked_ascii.dat"
    plans = default_plans(layout)
    result = run_anonymization(data, out, layout, "ascii", plans,
                               seed="golden", target_count=50)
    assert result.records_written == 50
    assert out.stat().st_size == data.stat().st_size


def test_cross_file_referential_integrity(tmp_path, layout, account_layout):
    """Same value + same rule + same seed -> same masked value, even across
    two distinct Field objects from different copybooks (customer.CUST-ID
    and account.ACCT-CUST-ID). This is what makes customer<->account joins
    survive masking: the masked value must depend only on
    (value, rule, seed), never on the Field identity, or the same real-world
    ID would mask differently in each file and break the join.
    """
    from anonymizer.masking.rules import apply_rule
    cust_id = {f.name: f for f in layout.leaves}["CUST-ID"]
    acct_cust_id = {f.name: f for f in account_layout.leaves}["ACCT-CUST-ID"]
    a = apply_rule("digits", "10000007", cust_id, "golden")
    b = apply_rule("digits", "10000007", acct_cust_id, "golden")
    assert a == b


def test_account_end_to_end(tmp_path, account_layout):
    out = tmp_path / "masked_account.dat"
    plans = default_plans(account_layout)
    result = run_anonymization(ACCOUNT_DATA, out, account_layout, "cp037",
                               plans, seed="golden", target_count=120)
    assert result.records_written == 120
    assert out.stat().st_size == ACCOUNT_DATA.stat().st_size  # layout preserved

    from anonymizer.masking.rules import apply_rule
    by_name = {f.name: f for f in account_layout.leaves}
    acct_cust_id = by_name["ACCT-CUST-ID"]
    original = next(iter_records(ACCOUNT_DATA, account_layout, "cp037"))
    masked = next(iter_records(out, account_layout, "cp037"))
    before = decode_field(acct_cust_id, original, "cp037")
    after = decode_field(acct_cust_id, masked, "cp037")
    # Masking must be consistent with the rule a customer-file join key
    # would use for the same ID and seed (real record -> no synthesis salt).
    assert after == apply_rule("digits", before, acct_cust_id, "golden")
