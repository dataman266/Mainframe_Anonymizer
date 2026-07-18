from pathlib import Path

import pytest

from anonymizer import pipeline
from anonymizer.codec.dispatch import FieldCodecError, decode_field, encode_field
from anonymizer.copybook.model import Field, Layout, OdoInfo
from anonymizer.engine.reader import TruncatedRecordError, iter_records
from anonymizer.engine.writer import write_record
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
    assert not dst.exists()


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


def _corrupt_record2_sin(src: Path) -> None:
    """Overwrite record 2's SIN bytes with non-digit ascii text so decoding
    that field raises FieldCodecError."""
    data = bytearray(src.read_bytes())
    rec2_start = 1 * RECLEN
    data[rec2_start + 10:rec2_start + 19] = b"XXXXXXXXX"
    src.write_bytes(bytes(data))


def test_field_codec_error_includes_record_number(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    _corrupt_record2_sin(src)
    with pytest.raises(FieldCodecError, match="record 2"):
        run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 3)


def test_failed_run_leaves_no_output_or_tmp_file(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    _corrupt_record2_sin(src)
    with pytest.raises(FieldCodecError):
        run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 3)
    assert not dst.exists()
    assert not dst.with_suffix(dst.suffix + ".tmp").exists()


def test_synthesis_reuses_cached_records_instead_of_reopening(tmp_path, monkeypatch):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    calls: list[int] = []
    original = pipeline.iter_records

    def counting_iter_records(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "iter_records", counting_iter_records)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 10)
    assert result.records_written == 10
    assert len(calls) == 1


def test_target_count_below_one_raises(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)
    with pytest.raises(ValueError, match="target_count must be at least 1"):
        run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 0)


def test_rdw_roundtrip_masks_and_preserves_record_count(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    layout = _layout()
    with open(src, "wb") as f:
        for name, sin, rtype in ROWS:
            rec = bytearray(RECLEN)
            rec[0:10] = encode_field(NAME, name, "ascii")
            rec[10:19] = encode_field(SIN, sin, "ascii")
            rec[19:20] = encode_field(TYPE, rtype, "ascii")
            write_record(f, bytes(rec), rdw=True)

    result = run_anonymization(src, dst, layout, "ascii", _plans(), "s1", 3, rdw=True)
    assert result.records_written == 3

    out_records = list(iter_records(dst, layout, "ascii", rdw=True))
    assert len(out_records) == 3
    assert decode_field(NAME, out_records[0], "ascii").strip() != "JOHN SMITH"
    assert decode_field(TYPE, out_records[0], "ascii") == "A"


CNT = Field(name="CNT", level=5, offset=0, length=2, picture="9(02)",
           numeric=True, total_digits=2)
ELEM0 = Field(name="ELEM0", level=5, offset=2, length=8)
ELEM1 = Field(name="ELEM1", level=5, offset=10, length=8)


def _odo_layout() -> Layout:
    root = Field(name="REC", level=1, offset=0, length=26)
    odo = OdoInfo(counter=CNT, element_length=8, max_count=3, array_offset=2)
    return Layout(name="REC", record_length=26, root=root,
                  leaves=(CNT, ELEM0, ELEM1), overlays=(), odo=odo)


def test_odo_roundtrip_preserves_length_and_counter(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    rec1 = b"02" + b"AAAAAAAA" + b"BBBBBBBB"    # count=2 -> 18 bytes
    rec2 = b"01" + b"CCCCCCCC"                   # count=1 -> 10 bytes
    src.write_bytes(rec1 + rec2)
    layout = _odo_layout()
    plans = [FieldPlan(field=CNT, rule="keep", enabled=False),
             FieldPlan(field=ELEM0, rule="scramble", enabled=True),
             FieldPlan(field=ELEM1, rule="scramble", enabled=True)]

    result = run_anonymization(src, dst, layout, "ascii", plans, "s1", 2)
    assert result.records_written == 2

    out_records = list(iter_records(dst, layout, "ascii"))
    assert len(out_records) == 2
    assert len(out_records[0]) == len(rec1)
    assert len(out_records[1]) == len(rec2)
    assert out_records[0][:2] == b"02"           # counter untouched
    assert out_records[1][:2] == b"01"
    assert out_records[0] != rec1                 # masked elements differ


def test_truncated_record_error_includes_record_number(tmp_path):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    rec1 = b"02" + b"AAAAAAAA" + b"BBBBBBBB"    # count=2 -> valid
    rec2 = b"01" + b"CCCCCCCC"                   # count=1 -> valid
    rec3 = b"09" + b"1" * 16                     # count=9 -> outside 0..3
    src.write_bytes(rec1 + rec2 + rec3)
    layout = _odo_layout()
    plans = [FieldPlan(field=CNT, rule="keep", enabled=False),
             FieldPlan(field=ELEM0, rule="scramble", enabled=True),
             FieldPlan(field=ELEM1, rule="scramble", enabled=True)]
    with pytest.raises(TruncatedRecordError, match="record 3"):
        run_anonymization(src, dst, layout, "ascii", plans, "s1", 3)


def test_cache_falls_back_to_rereading_input_when_over_budget(tmp_path, monkeypatch):
    src, dst = tmp_path / "in.dat", tmp_path / "out.dat"
    _write_input(src, ROWS)                       # 3 records x RECLEN(20) bytes
    monkeypatch.setattr(pipeline, "_CACHE_BUDGET_BYTES", 10)
    calls: list[int] = []
    original = pipeline.iter_records

    def counting_iter_records(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "iter_records", counting_iter_records)
    result = run_anonymization(src, dst, _layout(), "ascii", _plans(), "s1", 7)
    assert result.records_written == 7
    assert len(calls) > 1
