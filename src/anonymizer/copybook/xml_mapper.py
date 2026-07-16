"""Map cb2xml XML output to the internal Layout model."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from anonymizer.copybook.model import (Field, Layout, OdoInfo, parse_picture,
                                       storage_length)

_USAGE_MAP = {
    "packed-decimal": "comp-3",
    "computational-3": "comp-3",
    "comp-3": "comp-3",
    "binary": "comp",
    "computational": "comp",
    "comp": "comp",
}


class CopybookMappingError(Exception):
    """The XML could not be mapped to a layout."""


class UnsupportedCopybookError(CopybookMappingError):
    """The copybook uses a construct this tool does not support."""


def _build(el: ET.Element) -> Field:
    picture = el.get("picture")
    info = parse_picture(picture) if picture else None
    usage = _USAGE_MAP.get((el.get("usage") or "").lower(), "display")
    length_attr = el.get("storage-length")
    if length_attr is not None:
        length = int(length_attr)
    elif info is not None:
        length = storage_length(info, usage)
    else:
        length = 0
    children = tuple(_build(c) for c in el.findall("item"))
    if children and length_attr is None:
        length = sum(c.length * (c.occurs or 1) for c in children)
    return Field(
        name=el.get("name", "FILLER"),
        level=int(el.get("level", "0")),
        offset=int(el.get("position", "1")) - 1,
        length=length,
        picture=picture,
        usage=usage,
        numeric=bool((el.get("numeric") == "true") or (info and info.numeric)),
        signed=bool(info and info.signed) or el.get("signed") == "true",
        total_digits=info.total_digits if info else 0,
        decimals=info.decimals if info else 0,
        occurs=int(el.get("occurs")) if el.get("occurs") else None,
        depending_on=el.get("depending-on"),
        redefines=el.get("redefines"),
        children=children,
    )


def _shift(f: Field, delta: int, suffix: str) -> Field:
    return Field(
        name=f"{f.name}{suffix}", level=f.level, offset=f.offset + delta,
        length=f.length, picture=f.picture, usage=f.usage, numeric=f.numeric,
        signed=f.signed, total_digits=f.total_digits, decimals=f.decimals,
        occurs=None, depending_on=f.depending_on, redefines=f.redefines,
        children=f.children,
    )


def _collect(f: Field, shift: int, in_redefines: bool,
             leaves: list[Field], overlays: list[Field],
             suffix_prefix: str = "") -> None:
    if f.is_group and f.depending_on:
        raise UnsupportedCopybookError(
            "OCCURS DEPENDING ON on a group is not supported")
    in_redefines = in_redefines or f.redefines is not None
    reps = f.occurs or 1
    for i in range(reps):
        suffix = f"({i + 1})" if f.occurs else ""
        combined_suffix = f"{suffix_prefix}{suffix}"
        delta = shift + i * f.length
        if f.is_group:
            for c in f.children:
                # instance suffix accumulates through nested groups so each
                # descendant leaf gets a unique "(group)(leaf)" style name
                _collect(c, delta, in_redefines, leaves, overlays,
                         combined_suffix)
        else:
            leaf = _shift(f, delta, combined_suffix)
            (overlays if in_redefines else leaves).append(leaf)


def _find_odo(leaves: list[Field], record_length: int) -> OdoInfo | None:
    odo_leaves = [f for f in leaves if f.depending_on]
    if not odo_leaves:
        return None
    counter_names = {f.depending_on for f in odo_leaves}
    if len(counter_names) > 1:
        raise UnsupportedCopybookError(
            "Multiple OCCURS DEPENDING ON arrays with different counters "
            "are not supported")
    first = min(odo_leaves, key=lambda f: f.offset)
    array_offset = first.offset
    element_length = first.length
    max_count = len(odo_leaves)
    counter_name = first.depending_on
    counters = [f for f in leaves if f.name == counter_name]
    if not counters:
        raise CopybookMappingError(
            f"OCCURS DEPENDING ON counter '{counter_name}' not found")
    end = array_offset + max_count * element_length
    trailing = [f for f in leaves
                if not f.depending_on and f.offset >= array_offset]
    if trailing or end != record_length:
        raise UnsupportedCopybookError(
            "OCCURS DEPENDING ON is only supported as the last field in the "
            "record (no fields after the variable array)")
    return OdoInfo(counter=counters[0], element_length=element_length,
                   max_count=max_count, array_offset=array_offset)


def layout_from_xml(xml_text: str) -> Layout:
    try:
        doc = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise CopybookMappingError(f"cb2xml produced invalid XML: {exc}") from exc
    record_el = doc.find("item")
    if record_el is None:
        raise CopybookMappingError("no record definition found in copybook")
    root = _build(record_el)
    leaves: list[Field] = []
    overlays: list[Field] = []
    _collect(root, 0, False, leaves, overlays)
    leaves.sort(key=lambda f: f.offset)
    odo = _find_odo(leaves, root.length)
    return Layout(name=root.name, record_length=root.length, root=root,
                  leaves=tuple(leaves), overlays=tuple(overlays), odo=odo)
