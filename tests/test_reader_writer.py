import io

import pytest

from anonymizer.copybook.model import Field, Layout, OdoInfo
from anonymizer.engine.reader import (TruncatedRecordError, iter_records,
                                      validate_fixed_file)
from anonymizer.engine.writer import write_record


def _fixed_layout(reclen: int) -> Layout:
    root = Field(name="REC", level=1, offset=0, length=reclen)
    return Layout(name="REC", record_length=reclen, root=root,
                  leaves=(root,), overlays=())


def _odo_layout() -> Layout:
    counter = Field(name="CNT", level=5, offset=0, length=2, picture="9(02)",
                    numeric=True, total_digits=2)
    root = Field(name="REC", level=1, offset=0, length=26)
    odo = OdoInfo(counter=counter, element_length=8, max_count=3, array_offset=2)
    return Layout(name="REC", record_length=26, root=root,
                  leaves=(counter,), overlays=(), odo=odo)


def test_fixed_records(tmp_path):
    p = tmp_path / "f.dat"
    p.write_bytes(b"AAAA" + b"BBBB" + b"CCCC")
    layout = _fixed_layout(4)
    assert list(iter_records(p, layout, "ascii")) == [b"AAAA", b"BBBB", b"CCCC"]


def test_fixed_truncated_tail_raises(tmp_path):
    p = tmp_path / "f.dat"
    p.write_bytes(b"AAAABB")
    with pytest.raises(TruncatedRecordError):
        list(iter_records(p, _fixed_layout(4), "ascii"))


def test_rdw_records(tmp_path):
    p = tmp_path / "v.dat"
    # RDW: 2-byte big-endian total length (incl. 4-byte RDW) + 2 zero bytes
    p.write_bytes(b"\x00\x07\x00\x00ABC" + b"\x00\x06\x00\x00XY")
    layout = _fixed_layout(3)
    assert list(iter_records(p, layout, "ascii", rdw=True)) == [b"ABC", b"XY"]


def test_odo_records(tmp_path):
    p = tmp_path / "o.dat"
    #  count=02 -> 2 + 2*8 = 18 bytes; count=01 -> 10 bytes
    rec1 = b"02" + b"1" * 16
    rec2 = b"01" + b"2" * 8
    p.write_bytes(rec1 + rec2)
    layout = _odo_layout()
    assert list(iter_records(p, layout, "ascii")) == [rec1, rec2]


def test_odo_counter_out_of_range_raises(tmp_path):
    p = tmp_path / "o.dat"
    p.write_bytes(b"09" + b"1" * 16)
    with pytest.raises(TruncatedRecordError):
        list(iter_records(p, _odo_layout(), "ascii"))


def test_validate_fixed_file(tmp_path):
    p = tmp_path / "f.dat"
    p.write_bytes(b"A" * 10)
    assert validate_fixed_file(p, _fixed_layout(5)) is None
    problem = validate_fixed_file(p, _fixed_layout(4))
    assert problem is not None and "record length" in problem


def test_validate_empty_file(tmp_path):
    p = tmp_path / "e.dat"
    p.write_bytes(b"")
    assert validate_fixed_file(p, _fixed_layout(4)) == "The data file is empty."


def test_write_record_rdw():
    buf = io.BytesIO()
    write_record(buf, b"ABC", rdw=True)
    assert buf.getvalue() == b"\x00\x07\x00\x00ABC"
    buf2 = io.BytesIO()
    write_record(buf2, b"ABC", rdw=False)
    assert buf2.getvalue() == b"ABC"


def test_odo_corrupt_counter_raises_handled_error(tmp_path):
    """A non-numeric ODO counter must surface as a handled error, not crash."""
    p = tmp_path / "o.dat"
    p.write_bytes(b"XX" + b"1" * 16)
    from anonymizer.codec.dispatch import FieldCodecError
    with pytest.raises((FieldCodecError, TruncatedRecordError)):
        list(iter_records(p, _odo_layout(), "ascii"))
