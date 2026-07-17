"""Immutable copybook layout model and PIC-clause parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass

_PAREN = re.compile(r"([XA9SVP])\((\d+)\)", re.I)


@dataclass(frozen=True)
class PictureInfo:
    numeric: bool
    signed: bool
    total_digits: int
    decimals: int
    display_length: int


def _expand(pic: str) -> str:
    return _PAREN.sub(lambda m: m.group(1).upper() * int(m.group(2)), pic.upper())


def parse_picture(pic: str) -> PictureInfo:
    p = _expand(pic)
    signed = p.startswith("S")
    if signed:
        p = p[1:]
    if "9" in p and "X" not in p and "A" not in p:
        int_part, _, dec_part = p.partition("V")
        ints = int_part.count("9")
        decs = dec_part.count("9")
        return PictureInfo(True, signed, ints + decs, decs, ints + decs)
    return PictureInfo(False, False, 0, 0, len(p))


def storage_length(info: PictureInfo, usage: str) -> int:
    if usage == "comp-3":
        return info.total_digits // 2 + 1
    if usage == "comp":
        if info.total_digits <= 4:
            return 2
        if info.total_digits <= 9:
            return 4
        return 8
    return info.display_length


@dataclass(frozen=True)
class Field:
    name: str
    level: int
    offset: int                      # 0-based byte offset in the record
    length: int                      # storage bytes
    picture: str | None = None
    usage: str = "display"           # "display" | "comp" | "comp-3"
    numeric: bool = False
    signed: bool = False
    total_digits: int = 0
    decimals: int = 0
    occurs: int | None = None
    depending_on: str | None = None
    redefines: str | None = None
    children: tuple["Field", ...] = ()

    @property
    def is_group(self) -> bool:
        return len(self.children) > 0


@dataclass(frozen=True)
class OdoInfo:
    counter: Field
    element_length: int
    max_count: int
    array_offset: int


@dataclass(frozen=True)
class Layout:
    name: str
    record_length: int               # maximum record length in bytes
    root: Field
    leaves: tuple[Field, ...]        # elementary, OCCURS-expanded, primary only
    overlays: tuple[Field, ...]      # leaves inside a REDEFINES (read-only views)
    odo: OdoInfo | None = None

    def record_length_for(self, count: int) -> int:
        if self.odo is None:
            return self.record_length
        return self.odo.array_offset + count * self.odo.element_length
