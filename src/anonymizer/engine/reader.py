"""Streaming record readers for fixed, RDW (VB), and ODO files."""
from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO, Iterator

from anonymizer.codec.dispatch import FieldCodecError, decode_field
from anonymizer.copybook.model import Layout

_RDW_HEADER = 4


class TruncatedRecordError(Exception):
    """The file ended in the middle of a record, or a record is malformed."""


def _iter_fixed(f: BinaryIO, reclen: int) -> Iterator[bytes]:
    while chunk := f.read(reclen):
        if len(chunk) < reclen:
            raise TruncatedRecordError(
                f"last record is {len(chunk)} bytes, expected {reclen}")
        yield chunk


def _iter_rdw(f: BinaryIO) -> Iterator[bytes]:
    while header := f.read(_RDW_HEADER):
        if len(header) < _RDW_HEADER:
            raise TruncatedRecordError("file ended inside an RDW header")
        total = int.from_bytes(header[:2], "big")
        if total < _RDW_HEADER:
            raise TruncatedRecordError(f"invalid RDW length {total}")
        payload = f.read(total - _RDW_HEADER)
        if len(payload) < total - _RDW_HEADER:
            raise TruncatedRecordError("file ended inside a variable record")
        yield payload


def _iter_odo(f: BinaryIO, layout: Layout, codepage: str) -> Iterator[bytes]:
    odo = layout.odo
    assert odo is not None
    while head := f.read(odo.array_offset):
        if len(head) < odo.array_offset:
            raise TruncatedRecordError("file ended inside a record header")
        try:
            count = int(decode_field(odo.counter, head, codepage))
        except (FieldCodecError, ValueError) as exc:
            raise TruncatedRecordError(
                f"ODO counter {odo.counter.name} could not be decoded: {exc}"
            ) from exc
        if not 0 <= count <= odo.max_count:
            raise TruncatedRecordError(
                f"ODO counter {odo.counter.name}={count} outside 0..{odo.max_count}")
        body = f.read(count * odo.element_length)
        if len(body) < count * odo.element_length:
            raise TruncatedRecordError("file ended inside a variable array")
        yield head + body


def _iterate(path: Path, layout: Layout, codepage: str,
             rdw: bool) -> Iterator[bytes]:
    with open(path, "rb") as f:
        if rdw:
            yield from _iter_rdw(f)
        elif layout.odo is not None:
            yield from _iter_odo(f, layout, codepage)
        else:
            yield from _iter_fixed(f, layout.record_length)


def iter_records(path: Path, layout: Layout, codepage: str,
                 rdw: bool = False) -> Iterator[bytes]:
    """Return an iterator over the fixed, RDW, or ODO records in ``path``.

    The path and layout are validated eagerly, before any generator is
    created, so a missing file or a degenerate layout (e.g. a zero-length
    fixed record, or an ODO header with no bytes) raises immediately at
    call time rather than on first iteration. The returned generator holds
    the file open until it is exhausted or closed; callers that stop
    iterating early should call ``.close()`` on it to release the handle.
    """
    os.stat(path)
    if layout.odo is not None:
        if layout.odo.array_offset <= 0:
            raise ValueError(
                "ODO array_offset must be positive, got "
                f"{layout.odo.array_offset}")
        counter = layout.odo.counter
        if counter.offset + counter.length > layout.odo.array_offset:
            raise ValueError(
                "ODO counter field extends past the record header")
    elif not rdw and layout.record_length <= 0:
        raise ValueError(
            f"record_length must be positive, got {layout.record_length}")
    return _iterate(path, layout, codepage, rdw)


def validate_fixed_file(path: Path, layout: Layout) -> str | None:
    """Return a plain-language problem description, or None if it looks fine."""
    size = os.path.getsize(path)
    if size == 0:
        return "The data file is empty."
    if layout.odo is None and size % layout.record_length != 0:
        return (f"The file is {size:,} bytes, which is not a whole number of "
                f"records at the copybook's record length of "
                f"{layout.record_length} bytes. The copybook may not match "
                "this file, the file may be variable-length (try the VB "
                "option), or the encoding may be wrong.")
    return None
