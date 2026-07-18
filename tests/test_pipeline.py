from pathlib import Path

import pytest

from anonymizer.codec.dispatch import decode_field, encode_field
from anonymizer.copybook.model import Field, Layout
from anonymizer.pipeline import FieldPlan, default_plans, run_anonymization

NAME = Field(name="CUST-NAME", level=5, offset=0, length=10)
SIN = Field(name="CUST-SIN", level=5, offset=10, length=9, picture="9(09)",
            numeric=True, total_digits=9)
TYPE = Field(name="REC-TYPE", level=5, offset=19, length=1)
RECLEN = 20


def _layout() -> Layout:
    root = Field(name="REC", level=1, offset=0, length=RECLEN,
                 children=(NAME, SIN, TYPE))
    return Layout(name="REC", record_length=RECLEN, root=root,
                  leaves=(NAME, SIN, TYPE), overlays=())


def _write_input(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with open(path, "wb") as f:
        for name, sin, rtype in rows:
            rec = bytearray(RECLEN)
            rec[0:10] = encode_field(NAME, name, "ascii")
            rec[10:19] = encode_field(SIN, sin, "ascii")
            rec[19:20] = encode_field(TYPE, rtype, "ascii")
            f.write(bytes(rec))


ROWS = [("JOHN SMITH", "046454286", "A"),
        ("JANE DOE", "123456782", "B"),
        ("BOB MARTIN", "554433221", "A")]


def _plans() -> list[FieldPlan]:
    return [FieldPlan(field=NAME, rule="person_name", enabled=True),
            FieldPlan(field=SIN, rule="sin", enabled=True),
            FieldPlan(field=TYPE, rule="keep", enabled=False)]


def test_masks_selected_fields_and_keeps_others(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(),
                               seed="s1", target_count=3)
    assert result.records_written == 3
    assert result.real_records == 3 and result.synthetic_records == 0
    out = dst.read_bytes()
    assert len(out) == 3 * RECLEN
    rec0 = out[:RECLEN]
    assert decode_field(NAME, rec0, "ascii").strip() != "JOHN SMITH"
    assert decode_field(TYPE, rec0, "ascii") == "A"          # kept byte-exact
    assert rec0[19:20] == b"A"


def test_deterministic_across_runs(tmp_path):
    src = tmp_path / "in.dat"
    _write_input(src, ROWS)
    d1, d2 = tmp_path / "o1.dat", tmp_path / "o2.dat"
    run_anonymization(src, d1, _layout(), "ascii", _plans(), "s1", 3)
    run_anonymization(src, d2, _layout(), "ascii", _plans(), "s1", 3)
    assert d1.read_bytes() == d2.read_bytes()


def test_truncates_to_target(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 2)
    assert result.records_written == 2
    assert len(dst.read_bytes()) == 2 * RECLEN


def test_synthesizes_beyond_input(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 8)
    assert result.records_written == 8
    assert result.real_records == 3 and result.synthetic_records == 5
    out = dst.read_bytes()
    assert len(out) == 8 * RECLEN
    # synthetic copy of record 0 must differ from masked record 0
    assert out[:RECLEN] != out[3 * RECLEN:4 * RECLEN]


def test_sample_has_before_and_after(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 3)
    assert len(result.sample) == 3 * 3          # 3 records x 3 fields
    first = result.sample[0]
    assert first["record"] == 1 and first["field"] == "CUST-NAME"
    assert first["before"].strip() == "JOHN SMITH"
    assert first["after"].strip() != "JOHN SMITH"


def test_progress_callback_called(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    calls: list[tuple[int, int]] = []
    run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 3,
                      progress_cb=lambda done, total: calls.append((done, total)))
    assert calls and calls[-1] == (3, 3)


def test_empty_input_raises(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    src.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 5)


def test_incompatible_plan_rejected_before_run(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    bad_plans = [FieldPlan(field=SIN, rule="person_name", enabled=True)]
    with pytest.raises(ValueError, match="person_name"):
        run_anonymization(src, dst, _layout(), "ascii", bad_plans, "s1", 3)
    assert not dst.exists() or dst.stat().st_size == 0


def test_default_plans_uses_classifier():
    plans = default_plans(_layout())
    by_name = {p.field.name: p for p in plans}
    assert by_name["CUST-SIN"].rule == "sin" and by_name["CUST-SIN"].enabled
    assert by_name["REC-TYPE"].rule == "keep" and not by_name["REC-TYPE"].enabled
