"""Record writer with optional RDW framing."""
from __future__ import annotations

from typing import BinaryIO

_RDW_HEADER = 4
_RDW_MAX_TOTAL = 0xFFFF
_RDW_MAX_RECORD = _RDW_MAX_TOTAL - _RDW_HEADER


def write_record(f: BinaryIO, record: bytes, rdw: bool = False) -> None:
    if rdw:
        if len(record) > _RDW_MAX_RECORD:
            raise ValueError(
                f"record of {len(record)} bytes exceeds the "
                f"{_RDW_MAX_RECORD:,}-byte limit for variable-length (RDW) files")
        f.write((len(record) + _RDW_HEADER).to_bytes(2, "big") + b"\x00\x00")
    f.write(record)
