"""Record writer with optional RDW framing."""
from __future__ import annotations

from typing import BinaryIO

_RDW_HEADER = 4


def write_record(f: BinaryIO, record: bytes, rdw: bool = False) -> None:
    if rdw:
        f.write((len(record) + _RDW_HEADER).to_bytes(2, "big") + b"\x00\x00")
    f.write(record)
