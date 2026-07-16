# Mainframe File Anonymizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Streamlit app that masks PII/PCI in mainframe files (EBCDIC cp037 or ASCII, fixed-length; VB/RDW and ODO supported) using their COBOL copybook, deterministically and format-preservingly, writing byte-layout-identical output plus an audit report.

**Architecture:** The bundled cb2xml jar (one-shot Java subprocess) parses the copybook into XML; everything else is pure Python: an immutable `Layout` field model, a codec layer (EBCDIC text, zoned, COMP-3, COMP), a streaming record engine, a deterministic HMAC-seeded masking engine with format-preserving rules, a synthesis mode for record counts beyond the input, and a 5-step Streamlit wizard.

**Tech Stack:** Python 3.10+, Streamlit (UI + `streamlit.testing.v1.AppTest`), Faker, pytest + pytest-cov, cb2xml (Java 8+ runtime required).

**Spec:** `docs/superpowers/specs/2026-07-15-mainframe-anonymizer-design.md`

## File structure (final state)

```
app.py                                  # Streamlit entry point + wizard shell
pyproject.toml, requirements.txt, .gitignore, README.md
vendor/cb2xml.jar                       # bundled copybook parser
samples/copybooks/customer.cpy, account.cpy
samples/data/customer.cp037.dat, customer.ascii.dat, account.cp037.dat, account.ascii.dat
tools/generate_samples.py               # deterministic fixture generator
src/anonymizer/
    copybook/model.py                   # Field, Layout, OdoInfo, parse_picture
    copybook/xml_mapper.py              # cb2xml XML -> Layout
    copybook/cb2xml_runner.py           # java detection + subprocess
    codec/text.py  codec/zoned.py  codec/packed.py  codec/binary.py  codec/dispatch.py
    engine/reader.py  engine/writer.py
    masking/luhn.py  masking/deterministic.py  masking/rules.py  masking/classifier.py
    pipeline.py                         # orchestration, synthesis, RunResult
    audit.py                            # markdown audit report
    ui/helpers.py                       # describe_field, detect_encoding
    ui/steps.py                         # render functions for the 5 wizard steps
tests/  (one test file per module, fixtures under tests/fixtures/)
```

Conventions used throughout: all offsets are 0-based byte offsets; all decoded values cross module boundaries as `str` (numerics are `decimal.Decimal` strings like `-1234.56`); `codepage` is `"cp037"` or `"ascii"`.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `src/anonymizer/__init__.py`, `tests/test_sanity.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "mainframe-anonymizer"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["streamlit>=1.35", "Faker>=25"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `requirements.txt`**

```
streamlit>=1.35
Faker>=25
pytest>=8
pytest-cov>=5
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.coverage
htmlcov/
output/
*.egg-info/
build/
```

- [ ] **Step 4: Create package + sanity test**

`src/anonymizer/__init__.py` — empty file.

`tests/test_sanity.py`:
```python
def test_package_imports():
    import anonymizer  # noqa: F401
```

- [ ] **Step 5: Install and verify**

Run: `pip install -r requirements.txt` then `pip install -e .` then `python -m pytest -q`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt .gitignore src tests
git commit -m "chore: scaffold python project with src layout and pytest"
```

---

### Task 2: Vendor cb2xml jar and sample copybooks

**Files:**
- Create: `vendor/cb2xml.jar`, `samples/copybooks/customer.cpy`, `samples/copybooks/account.cpy`

- [ ] **Step 1: Download cb2xml jar**

Download the latest release jar from https://github.com/bmTas/cb2xml/releases (asset named like `cb2xml.jar` inside the release zip; SourceForge mirror: https://sourceforge.net/projects/cb2xml/files/). Save it as `vendor/cb2xml.jar`.

PowerShell example (adjust the version/asset URL to the latest release):
```powershell
New-Item -ItemType Directory -Force vendor
Invoke-WebRequest -Uri "<latest-release-jar-url>" -OutFile vendor/cb2xml.jar
```

- [ ] **Step 2: Create `samples/copybooks/customer.cpy`** (record length 202 bytes)

```
       01  CUSTOMER-RECORD.
           05  CUST-ID              PIC 9(08).
           05  CUST-NAME            PIC X(30).
           05  CUST-AGE             PIC 9(03).
           05  CUST-DOB             PIC 9(08).
           05  CUST-STREET-ADDR     PIC X(30).
           05  CUST-CITY            PIC X(20).
           05  CUST-ZIPCODE         PIC X(06).
           05  CUST-SIN             PIC 9(09).
           05  CUST-PHONE           PIC X(12) OCCURS 2 TIMES.
           05  CUST-EMAIL           PIC X(30).
           05  CUST-CARD-NUM        PIC 9(16).
           05  CUST-BALANCE         PIC S9(09)V99 COMP-3.
           05  CUST-BRANCH-CODE     PIC 9(04) COMP.
           05  FILLER               PIC X(10).
```

- [ ] **Step 3: Create `samples/copybooks/account.cpy`** (record length 71 bytes)

```
       01  ACCOUNT-RECORD.
           05  ACCT-CUST-ID         PIC 9(08).
           05  ACCT-NUMBER          PIC 9(12).
           05  ACCT-TYPE            PIC X(03).
           05  ACCT-OPEN-DT         PIC 9(08).
           05  ACCT-LAST-UPDT-DT    PIC 9(08).
           05  ACCT-STATUS          PIC X(01).
           05  ACCT-BRANCH          PIC 9(04).
           05  ACCT-BALANCE         PIC S9(11)V99 COMP-3.
           05  ACCT-INT-RATE        PIC 9(02)V9(04).
           05  FILLER               PIC X(14).
```

- [ ] **Step 4: Smoke-run the jar**

Run: `java -jar vendor/cb2xml.jar samples/copybooks/customer.cpy`
Expected: XML printed to stdout containing `<item level="05" name="CUST-ID"` (attribute casing/names may differ slightly — note the exact attribute names for Task 4).

- [ ] **Step 5: Commit**

```bash
git add vendor samples
git commit -m "chore: vendor cb2xml jar and add banking sample copybooks"
```

---

### Task 3: Picture parser and layout model

**Files:**
- Create: `src/anonymizer/copybook/__init__.py` (empty), `src/anonymizer/copybook/model.py`
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_model.py`:
```python
from anonymizer.copybook.model import parse_picture, storage_length, PictureInfo


def test_parse_alphanumeric():
    info = parse_picture("X(30)")
    assert info == PictureInfo(numeric=False, signed=False, total_digits=0,
                               decimals=0, display_length=30)


def test_parse_unsigned_numeric():
    info = parse_picture("9(08)")
    assert info.numeric and not info.signed
    assert info.total_digits == 8 and info.decimals == 0
    assert info.display_length == 8


def test_parse_signed_decimal():
    info = parse_picture("S9(09)V99")
    assert info.numeric and info.signed
    assert info.total_digits == 11 and info.decimals == 2
    assert info.display_length == 11  # V and S take no storage in DISPLAY


def test_parse_literal_repeats():
    assert parse_picture("999").total_digits == 3
    assert parse_picture("XXX").display_length == 3
    assert parse_picture("9(02)V9(04)").decimals == 4


def test_storage_length_display():
    assert storage_length(parse_picture("X(20)"), "display") == 20
    assert storage_length(parse_picture("S9(09)V99"), "display") == 11


def test_storage_length_comp3():
    # digits // 2 + 1
    assert storage_length(parse_picture("S9(09)V99"), "comp-3") == 6
    assert storage_length(parse_picture("S9(11)V99"), "comp-3") == 7


def test_storage_length_comp():
    assert storage_length(parse_picture("9(04)"), "comp") == 2
    assert storage_length(parse_picture("9(09)"), "comp") == 4
    assert storage_length(parse_picture("9(18)"), "comp") == 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_model.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'anonymizer.copybook'`

- [ ] **Step 3: Implement `src/anonymizer/copybook/model.py`**

```python
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
```

Also create empty `src/anonymizer/copybook/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_model.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/copybook tests/test_model.py
git commit -m "feat: add PIC parser and immutable copybook layout model"
```

---

### Task 4: XML mapper (cb2xml XML → Layout)

**Files:**
- Create: `src/anonymizer/copybook/xml_mapper.py`
- Test: `tests/test_xml_mapper.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_xml_mapper.py` (the XML mimics cb2xml's "new format" output; Task 5 verifies against the real jar):
```python
import pytest

from anonymizer.copybook.xml_mapper import layout_from_xml, UnsupportedCopybookError

CUSTOMER_XML = """
<copybook filename="customer.cpy">
  <item level="01" name="CUSTOMER-RECORD" position="1" storage-length="202">
    <item level="05" name="CUST-ID" position="1" storage-length="8" picture="9(08)" numeric="true"/>
    <item level="05" name="CUST-NAME" position="9" storage-length="30" picture="X(30)"/>
    <item level="05" name="CUST-PHONE" position="39" storage-length="12" picture="X(12)" occurs="2"/>
    <item level="05" name="CUST-BALANCE" position="63" storage-length="6" picture="S9(09)V99"
          numeric="true" signed="true" usage="packed-decimal"/>
    <item level="05" name="CUST-BRANCH-CODE" position="69" storage-length="2" picture="9(04)"
          numeric="true" usage="binary"/>
  </item>
</copybook>
"""

REDEFINES_XML = """
<copybook filename="r.cpy">
  <item level="01" name="REC" position="1" storage-length="10">
    <item level="05" name="RAW-DATE" position="1" storage-length="8" picture="9(08)" numeric="true"/>
    <item level="05" name="DATE-PARTS" position="1" storage-length="8" redefines="RAW-DATE">
      <item level="10" name="DP-YEAR" position="1" storage-length="4" picture="9(04)" numeric="true"/>
      <item level="10" name="DP-MMDD" position="5" storage-length="4" picture="9(04)" numeric="true"/>
    </item>
    <item level="05" name="REC-FILLER" position="9" storage-length="2" picture="X(02)"/>
  </item>
</copybook>
"""

ODO_XML = """
<copybook filename="odo.cpy">
  <item level="01" name="REC" position="1" storage-length="26">
    <item level="05" name="TXN-COUNT" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="TXN-AMT" position="3" storage-length="8" picture="9(08)" numeric="true"
          occurs="3" depending-on="TXN-COUNT"/>
  </item>
</copybook>
"""

ODO_TAIL_XML = """
<copybook filename="bad.cpy">
  <item level="01" name="REC" position="1" storage-length="30">
    <item level="05" name="TXN-COUNT" position="1" storage-length="2" picture="9(02)" numeric="true"/>
    <item level="05" name="TXN-AMT" position="3" storage-length="8" picture="9(08)" numeric="true"
          occurs="3" depending-on="TXN-COUNT"/>
    <item level="05" name="TRAILER" position="27" storage-length="4" picture="X(04)"/>
  </item>
</copybook>
"""


def test_leaf_offsets_and_types():
    layout = layout_from_xml(CUSTOMER_XML)
    assert layout.name == "CUSTOMER-RECORD"
    assert layout.record_length == 202
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["CUST-ID"].offset == 0 and by_name["CUST-ID"].length == 8
    assert by_name["CUST-ID"].numeric and by_name["CUST-ID"].usage == "display"
    assert by_name["CUST-NAME"].offset == 8
    bal = by_name["CUST-BALANCE"]
    assert bal.usage == "comp-3" and bal.signed and bal.decimals == 2 and bal.total_digits == 11
    assert by_name["CUST-BRANCH-CODE"].usage == "comp"


def test_occurs_expansion():
    layout = layout_from_xml(CUSTOMER_XML)
    names = [f.name for f in layout.leaves]
    assert "CUST-PHONE(1)" in names and "CUST-PHONE(2)" in names
    by_name = {f.name: f for f in layout.leaves}
    assert by_name["CUST-PHONE(1)"].offset == 38
    assert by_name["CUST-PHONE(2)"].offset == 50


def test_redefines_are_overlays():
    layout = layout_from_xml(REDEFINES_XML)
    leaf_names = {f.name for f in layout.leaves}
    overlay_names = {f.name for f in layout.overlays}
    assert "RAW-DATE" in leaf_names
    assert "DP-YEAR" in overlay_names and "DP-MMDD" in overlay_names
    assert "DP-YEAR" not in leaf_names


def test_odo_captured():
    layout = layout_from_xml(ODO_XML)
    assert layout.odo is not None
    assert layout.odo.counter.name == "TXN-COUNT"
    assert layout.odo.element_length == 8
    assert layout.odo.max_count == 3
    assert layout.odo.array_offset == 2
    assert layout.record_length_for(1) == 10
    assert layout.record_length_for(3) == 26


def test_odo_with_trailing_fields_rejected():
    with pytest.raises(UnsupportedCopybookError):
        layout_from_xml(ODO_TAIL_XML)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_xml_mapper.py -q`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Implement `src/anonymizer/copybook/xml_mapper.py`**

```python
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
    if children and not length_attr:
        length = sum(c.length * (c.occurs or 1) for c in children)
    return Field(
        name=el.get("name", "FILLER"),
        level=int(el.get("level", "0")),
        offset=int(el.get("position", "1")) - 1,
        length=length,
        picture=picture,
        usage=usage,
        numeric=bool(info and info.numeric),
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
             leaves: list[Field], overlays: list[Field]) -> None:
    in_redefines = in_redefines or f.redefines is not None
    reps = f.occurs or 1
    for i in range(reps):
        suffix = f"({i + 1})" if f.occurs else ""
        delta = shift + i * f.length
        if f.is_group:
            for c in f.children:
                # group instance suffix is carried by shifting children only
                _collect(c, delta, in_redefines, leaves, overlays)
        else:
            leaf = _shift(f, delta, suffix)
            (overlays if in_redefines else leaves).append(leaf)


def _find_odo(leaves: list[Field], record_length: int) -> OdoInfo | None:
    odo_leaves = [f for f in leaves if f.depending_on]
    if not odo_leaves:
        return None
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_xml_mapper.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/copybook/xml_mapper.py tests/test_xml_mapper.py
git commit -m "feat: map cb2xml XML to layout with occurs, redefines, and ODO"
```

---

### Task 5: cb2xml runner (Java subprocess)

**Files:**
- Create: `src/anonymizer/copybook/cb2xml_runner.py`
- Test: `tests/test_cb2xml_runner.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cb2xml_runner.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cb2xml_runner.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/copybook/cb2xml_runner.py`**

```python
"""Run the bundled cb2xml jar to parse a COBOL copybook."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from anonymizer.copybook.model import Layout
from anonymizer.copybook.xml_mapper import CopybookMappingError, layout_from_xml

DEFAULT_JAR = Path(__file__).resolve().parents[3] / "vendor" / "cb2xml.jar"
_TIMEOUT_SECONDS = 60


class JavaNotFoundError(Exception):
    """No Java runtime available on this machine."""


class CopybookParseError(Exception):
    """cb2xml rejected the copybook."""


def find_java() -> str | None:
    return shutil.which("java")


def parse_copybook(copybook_path: Path, jar_path: Path = DEFAULT_JAR) -> Layout:
    java = find_java()
    if java is None:
        raise JavaNotFoundError(
            "A Java runtime (version 8 or newer) is required to read the "
            "copybook but was not found. Please install Java and try again.")
    if not jar_path.exists():
        raise CopybookParseError(f"cb2xml jar not found at {jar_path}")
    result = subprocess.run(
        [java, "-jar", str(jar_path), str(copybook_path)],
        capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise CopybookParseError(
            f"The copybook could not be parsed. Parser said:\n{detail}")
    try:
        return layout_from_xml(result.stdout)
    except CopybookMappingError as exc:
        raise CopybookParseError(str(exc)) from exc
```

- [ ] **Step 4: Verify against the REAL jar output**

Run: `java -jar vendor/cb2xml.jar samples/copybooks/customer.cpy > actual.xml` and inspect `actual.xml`.
Compare attribute names against what `xml_mapper` reads (`name`, `level`, `position`, `storage-length`, `picture`, `usage`, `occurs`, `redefines`, `depending-on`). **If any attribute name or semantics differ (e.g., OCCURS storage-length is total rather than per-instance), fix `xml_mapper.py` and its test XML fixtures now.** Delete `actual.xml` afterwards.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cb2xml_runner.py tests/test_xml_mapper.py -q`
Expected: all pass (integration tests skip automatically if java is absent)

- [ ] **Step 6: Commit**

```bash
git add src/anonymizer/copybook/cb2xml_runner.py tests/test_cb2xml_runner.py
git commit -m "feat: parse copybooks via bundled cb2xml jar with friendly errors"
```

---

### Task 6: Codec — text

**Files:**
- Create: `src/anonymizer/codec/__init__.py` (empty), `src/anonymizer/codec/text.py`
- Test: `tests/test_codec_text.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_codec_text.py`:
```python
from anonymizer.codec.text import decode_text, encode_text


def test_ebcdic_round_trip():
    raw = "JOHN SMITH".encode("cp037").ljust(15, b"\x40")  # 0x40 = EBCDIC space
    assert decode_text(raw, "cp037") == "JOHN SMITH     "
    assert encode_text("JOHN SMITH", 15, "cp037") == raw


def test_ascii_round_trip():
    assert decode_text(b"TORONTO   ", "ascii") == "TORONTO   "
    assert encode_text("TORONTO", 10, "ascii") == b"TORONTO   "


def test_encode_truncates_to_field_length():
    assert encode_text("ABCDEFGHIJ", 5, "ascii") == b"ABCDE"


def test_encode_replaces_unmappable_chars():
    out = encode_text("CAFÉ☃", 6, "ascii")
    assert len(out) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_codec_text.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/codec/text.py`**

```python
"""Alphanumeric (PIC X) encode/decode for EBCDIC and ASCII."""
from __future__ import annotations


def decode_text(raw: bytes, codepage: str) -> str:
    return raw.decode(codepage, errors="replace")


def encode_text(value: str, length: int, codepage: str) -> bytes:
    encoded = value[:length].encode(codepage, errors="replace")
    pad = " ".encode(codepage)
    return (encoded + pad * length)[:length]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_codec_text.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/codec tests/test_codec_text.py
git commit -m "feat: add alphanumeric text codec for cp037 and ascii"
```

---

### Task 7: Codec — packed decimal (COMP-3)

**Files:**
- Create: `src/anonymizer/codec/packed.py`
- Test: `tests/test_codec_packed.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_codec_packed.py`:
```python
from decimal import Decimal

import pytest

from anonymizer.codec.packed import pack_comp3, unpack_comp3


def test_unpack_positive():
    # 12345.67 as S9(5)V99 -> digits 1234567, sign C
    assert unpack_comp3(bytes([0x12, 0x34, 0x56, 0x7C]), 2) == Decimal("12345.67")


def test_unpack_negative():
    assert unpack_comp3(bytes([0x12, 0x34, 0x56, 0x7D]), 2) == Decimal("-12345.67")


def test_unpack_unsigned_f_sign():
    assert unpack_comp3(bytes([0x00, 0x12, 0x3F]), 0) == Decimal("123")


def test_pack_round_trip_signed():
    raw = pack_comp3(Decimal("-9876543.21"), total_digits=11, decimals=2, signed=True)
    assert len(raw) == 6  # 11 digits -> 6 bytes
    assert unpack_comp3(raw, 2) == Decimal("-9876543.21")


def test_pack_round_trip_unsigned():
    raw = pack_comp3(Decimal("42"), total_digits=5, decimals=0, signed=False)
    assert len(raw) == 3
    assert unpack_comp3(raw, 0) == Decimal("42")


def test_pack_overflow_raises():
    with pytest.raises(ValueError):
        pack_comp3(Decimal("123456"), total_digits=5, decimals=0, signed=False)


def test_unpack_garbage_raises():
    with pytest.raises(ValueError):
        unpack_comp3(bytes([0xAB, 0xCD]), 0)  # A/B are not decimal digits
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_codec_packed.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/codec/packed.py`**

```python
"""COMP-3 (packed decimal) encode/decode."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_NEGATIVE_SIGNS = (0x0B, 0x0D)


def unpack_comp3(raw: bytes, decimals: int) -> Decimal:
    if not raw:
        raise ValueError("empty packed field")
    nibbles: list[int] = []
    for b in raw:
        nibbles.append((b >> 4) & 0x0F)
        nibbles.append(b & 0x0F)
    sign_nibble = nibbles.pop()
    if sign_nibble < 0x0A:
        raise ValueError(f"invalid packed sign nibble 0x{sign_nibble:X}")
    if any(d > 9 for d in nibbles):
        raise ValueError("invalid digit nibble in packed field")
    number = int("".join(str(d) for d in nibbles) or "0")
    if sign_nibble in _NEGATIVE_SIGNS:
        number = -number
    return Decimal(number).scaleb(-decimals)


def pack_comp3(value: Decimal, total_digits: int, decimals: int,
               signed: bool) -> bytes:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    negative = scaled < 0
    digit_str = str(abs(scaled))
    if len(digit_str) > total_digits:
        raise ValueError(
            f"value {value} does not fit in {total_digits} digits")
    digit_str = digit_str.rjust(total_digits, "0")
    if total_digits % 2 == 0:          # keep an odd digit count before the sign
        digit_str = "0" + digit_str
    sign = 0x0D if (signed and negative) else (0x0C if signed else 0x0F)
    nibbles = [int(c) for c in digit_str] + [sign]
    return bytes((nibbles[i] << 4) | nibbles[i + 1]
                 for i in range(0, len(nibbles), 2))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_codec_packed.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/codec/packed.py tests/test_codec_packed.py
git commit -m "feat: add COMP-3 packed decimal codec"
```

---

### Task 8: Codec — binary (COMP)

**Files:**
- Create: `src/anonymizer/codec/binary.py`
- Test: `tests/test_codec_binary.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_codec_binary.py`:
```python
from decimal import Decimal

import pytest

from anonymizer.codec.binary import decode_binary, encode_binary


def test_decode_halfword():
    assert decode_binary(b"\x30\x39", decimals=0, signed=False) == Decimal("12345")


def test_decode_signed_negative():
    assert decode_binary(b"\xFF\xFF", decimals=0, signed=True) == Decimal("-1")


def test_decode_with_decimals():
    assert decode_binary(b"\x30\x39", decimals=2, signed=False) == Decimal("123.45")


def test_encode_round_trip_fullword():
    raw = encode_binary(Decimal("-123456.78"), length=4, decimals=2, signed=True)
    assert len(raw) == 4
    assert decode_binary(raw, decimals=2, signed=True) == Decimal("-123456.78")


def test_encode_overflow_raises():
    with pytest.raises(ValueError):
        encode_binary(Decimal("70000"), length=2, decimals=0, signed=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_codec_binary.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/codec/binary.py`**

```python
"""COMP (big-endian binary) encode/decode."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def decode_binary(raw: bytes, decimals: int, signed: bool) -> Decimal:
    number = int.from_bytes(raw, "big", signed=signed)
    return Decimal(number).scaleb(-decimals)


def encode_binary(value: Decimal, length: int, decimals: int,
                  signed: bool) -> bytes:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    try:
        return scaled.to_bytes(length, "big", signed=signed)
    except OverflowError as exc:
        raise ValueError(
            f"value {value} does not fit in {length} binary bytes") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_codec_binary.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/codec/binary.py tests/test_codec_binary.py
git commit -m "feat: add COMP binary codec"
```

---

### Task 9: Codec — zoned decimal (DISPLAY numeric)

**Files:**
- Create: `src/anonymizer/codec/zoned.py`
- Test: `tests/test_codec_zoned.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_codec_zoned.py`:
```python
from decimal import Decimal

import pytest

from anonymizer.codec.zoned import decode_zoned, encode_zoned


def test_ebcdic_unsigned_round_trip():
    raw = "0012345".encode("cp037")
    assert decode_zoned(raw, decimals=0, signed=False, codepage="cp037") == Decimal("12345")
    assert encode_zoned(Decimal("12345"), 7, 0, False, "cp037") == raw


def test_ebcdic_signed_negative():
    # -123: F1 F2 D3 (last zone D = negative)
    raw = bytes([0xF1, 0xF2, 0xD3])
    assert decode_zoned(raw, 0, True, "cp037") == Decimal("-123")
    assert encode_zoned(Decimal("-123"), 3, 0, True, "cp037") == raw


def test_ebcdic_signed_positive():
    raw = bytes([0xF1, 0xF2, 0xC3])
    assert decode_zoned(raw, 0, True, "cp037") == Decimal("123")
    assert encode_zoned(Decimal("123"), 3, 0, True, "cp037") == raw


def test_ascii_unsigned_round_trip():
    assert decode_zoned(b"0099", 2, False, "ascii") == Decimal("0.99")
    assert encode_zoned(Decimal("0.99"), 4, 2, False, "ascii") == b"0099"


def test_ascii_signed_overpunch():
    # -125 in ASCII overpunch: "12N" (N = -5)
    assert decode_zoned(b"12N", 0, True, "ascii") == Decimal("-125")
    assert encode_zoned(Decimal("-125"), 3, 0, True, "ascii") == b"12N"
    # +125: "12E"
    assert decode_zoned(b"12E", 0, True, "ascii") == Decimal("125")


def test_overflow_raises():
    with pytest.raises(ValueError):
        encode_zoned(Decimal("1234"), 3, 0, False, "ascii")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_codec_zoned.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/codec/zoned.py`**

```python
"""Zoned decimal (PIC 9 DISPLAY) encode/decode for EBCDIC and ASCII."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ASCII_POS = "{ABCDEFGHI"   # overpunch for +0..+9
_ASCII_NEG = "}JKLMNOPQR"   # overpunch for -0..-9


def _scaled_digits(value: Decimal, total_digits: int, decimals: int) -> tuple[str, bool]:
    scaled = int(value.scaleb(decimals).to_integral_value(rounding=ROUND_HALF_UP))
    negative = scaled < 0
    digits = str(abs(scaled))
    if len(digits) > total_digits:
        raise ValueError(f"value {value} does not fit in {total_digits} digits")
    return digits.rjust(total_digits, "0"), negative


def decode_zoned(raw: bytes, decimals: int, signed: bool, codepage: str) -> Decimal:
    if codepage == "cp037":
        digits = [b & 0x0F for b in raw]
        if any(d > 9 for d in digits):
            raise ValueError("invalid zoned digit")
        negative = signed and (raw[-1] >> 4) == 0x0D
    else:
        text = raw.decode("ascii")
        last = text[-1]
        negative = False
        if last in _ASCII_POS:
            text = text[:-1] + str(_ASCII_POS.index(last))
        elif last in _ASCII_NEG:
            text = text[:-1] + str(_ASCII_NEG.index(last))
            negative = True
        if not text.isdigit():
            raise ValueError(f"invalid zoned value {raw!r}")
        digits = [int(c) for c in text]
    number = int("".join(str(d) for d in digits) or "0")
    if negative:
        number = -number
    return Decimal(number).scaleb(-decimals)


def encode_zoned(value: Decimal, total_digits: int, decimals: int,
                 signed: bool, codepage: str) -> bytes:
    digits, negative = _scaled_digits(value, total_digits, decimals)
    if codepage == "cp037":
        out = bytearray(0xF0 | int(c) for c in digits)
        if signed:
            zone = 0xD0 if negative else 0xC0
            out[-1] = zone | int(digits[-1])
        return bytes(out)
    if signed:
        table = _ASCII_NEG if negative else _ASCII_POS
        return (digits[:-1] + table[int(digits[-1])]).encode("ascii")
    return digits.encode("ascii")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_codec_zoned.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/codec/zoned.py tests/test_codec_zoned.py
git commit -m "feat: add zoned decimal codec with EBCDIC and ASCII overpunch signs"
```

---

### Task 10: Codec — field-level dispatch

**Files:**
- Create: `src/anonymizer/codec/dispatch.py`
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_dispatch.py`:
```python
from anonymizer.codec.dispatch import decode_field, encode_field
from anonymizer.copybook.model import Field

NAME = Field(name="CUST-NAME", level=5, offset=0, length=10)
SIN = Field(name="CUST-SIN", level=5, offset=10, length=9, picture="9(09)",
            numeric=True, total_digits=9)
BAL = Field(name="CUST-BALANCE", level=5, offset=19, length=6, usage="comp-3",
            picture="S9(09)V99", numeric=True, signed=True,
            total_digits=11, decimals=2)
BRANCH = Field(name="CUST-BRANCH-CODE", level=5, offset=25, length=2,
               usage="comp", picture="9(04)", numeric=True, total_digits=4)


def _record() -> bytes:
    rec = bytearray(27)
    rec[0:10] = encode_field(NAME, "JOHN SMITH", "cp037")
    rec[10:19] = encode_field(SIN, "046454286", "cp037")
    rec[19:25] = encode_field(BAL, "-12345.67", "cp037")
    rec[25:27] = encode_field(BRANCH, "1234", "cp037")
    return bytes(rec)


def test_round_trip_all_usages():
    rec = _record()
    assert decode_field(NAME, rec, "cp037") == "JOHN SMITH"
    assert decode_field(SIN, rec, "cp037") == "046454286"
    assert decode_field(BAL, rec, "cp037") == "-12345.67"
    assert decode_field(BRANCH, rec, "cp037") == "1234"


def test_numeric_display_preserves_leading_zeros():
    rec = _record()
    assert decode_field(SIN, rec, "cp037").startswith("0")


def test_encode_field_length_is_exact():
    assert len(encode_field(BAL, "1.00", "cp037")) == 6
    assert len(encode_field(NAME, "AB", "cp037")) == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dispatch.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/codec/dispatch.py`**

```python
"""Decode/encode a single field from/to raw record bytes.

All values cross this boundary as strings; numeric values are Decimal
strings.  Display numerics keep their leading zeros so masking rules see
the exact on-file representation.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from anonymizer.codec.binary import decode_binary, encode_binary
from anonymizer.codec.packed import pack_comp3, unpack_comp3
from anonymizer.codec.text import decode_text, encode_text
from anonymizer.codec.zoned import decode_zoned, encode_zoned
from anonymizer.copybook.model import Field


class FieldCodecError(Exception):
    """A field could not be decoded or encoded."""


def _slice(field: Field, record: bytes) -> bytes:
    return record[field.offset:field.offset + field.length]


def decode_field(field: Field, record: bytes, codepage: str) -> str:
    raw = _slice(field, record)
    try:
        if field.usage == "comp-3":
            return str(unpack_comp3(raw, field.decimals))
        if field.usage == "comp":
            return str(decode_binary(raw, field.decimals, field.signed))
        if field.numeric:
            value = decode_zoned(raw, field.decimals, field.signed, codepage)
            if field.decimals == 0:
                return str(int(value)).rjust(field.total_digits, "0")
            return str(value)
        return decode_text(raw, codepage)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FieldCodecError(
            f"field {field.name} at byte {field.offset}: {exc}") from exc


def encode_field(field: Field, value: str, codepage: str) -> bytes:
    try:
        if field.usage == "comp-3":
            return pack_comp3(Decimal(value), field.total_digits,
                              field.decimals, field.signed)
        if field.usage == "comp":
            return encode_binary(Decimal(value), field.length,
                                 field.decimals, field.signed)
        if field.numeric:
            return encode_zoned(Decimal(value), field.total_digits,
                                field.decimals, field.signed, codepage)
        return encode_text(value, field.length, codepage)
    except (ValueError, InvalidOperation) as exc:
        raise FieldCodecError(
            f"field {field.name}: cannot encode {value!r}: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dispatch.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/codec/dispatch.py tests/test_dispatch.py
git commit -m "feat: add field-level codec dispatch keyed on usage"
```

---

### Task 11: Streaming record reader/writer

**Files:**
- Create: `src/anonymizer/engine/__init__.py` (empty), `src/anonymizer/engine/reader.py`, `src/anonymizer/engine/writer.py`
- Test: `tests/test_reader_writer.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_reader_writer.py`:
```python
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


def test_validate_fixed_file(tmp_path):
    p = tmp_path / "f.dat"
    p.write_bytes(b"A" * 10)
    assert validate_fixed_file(p, _fixed_layout(5)) is None
    problem = validate_fixed_file(p, _fixed_layout(4))
    assert problem is not None and "record length" in problem


def test_write_record_rdw():
    buf = io.BytesIO()
    write_record(buf, b"ABC", rdw=True)
    assert buf.getvalue() == b"\x00\x07\x00\x00ABC"
    buf2 = io.BytesIO()
    write_record(buf2, b"ABC", rdw=False)
    assert buf2.getvalue() == b"ABC"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reader_writer.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/engine/reader.py`**

```python
"""Streaming record readers for fixed, RDW (VB), and ODO files."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Iterator

from anonymizer.codec.dispatch import decode_field
from anonymizer.copybook.model import Layout

_RDW_HEADER = 4


class TruncatedRecordError(Exception):
    """The file ended in the middle of a record."""


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
        count = int(Decimal(decode_field(odo.counter, head, codepage)))
        if not 0 <= count <= odo.max_count:
            raise TruncatedRecordError(
                f"ODO counter {odo.counter.name}={count} outside 0..{odo.max_count}")
        body = f.read(count * odo.element_length)
        if len(body) < count * odo.element_length:
            raise TruncatedRecordError("file ended inside a variable array")
        yield head + body


def iter_records(path: Path, layout: Layout, codepage: str,
                 rdw: bool = False) -> Iterator[bytes]:
    with open(path, "rb") as f:
        if rdw:
            yield from _iter_rdw(f)
        elif layout.odo is not None:
            yield from _iter_odo(f, layout, codepage)
        else:
            yield from _iter_fixed(f, layout.record_length)


def validate_fixed_file(path: Path, layout: Layout) -> str | None:
    """Return a plain-language problem description, or None if it looks fine."""
    size = os.path.getsize(path)
    if size == 0:
        return "The data file is empty."
    if layout.odo is None and size % layout.record_length != 0:
        return (f"The file is {size:,} bytes, which is not a whole number of "
                f"{layout.record_length}-byte records. The copybook may not "
                "match this file, the file may be variable-length (try the "
                "VB option), or the encoding may be wrong.")
    return None
```

Implement `src/anonymizer/engine/writer.py`:
```python
"""Record writer with optional RDW framing."""
from __future__ import annotations

from typing import BinaryIO

_RDW_HEADER = 4


def write_record(f: BinaryIO, record: bytes, rdw: bool = False) -> None:
    if rdw:
        f.write((len(record) + _RDW_HEADER).to_bytes(2, "big") + b"\x00\x00")
    f.write(record)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reader_writer.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/engine tests/test_reader_writer.py
git commit -m "feat: add streaming readers for fixed, RDW, and ODO records"
```

---

### Task 12: Luhn helper and deterministic RNG

**Files:**
- Create: `src/anonymizer/masking/__init__.py` (empty), `src/anonymizer/masking/luhn.py`, `src/anonymizer/masking/deterministic.py`
- Test: `tests/test_luhn.py`, `tests/test_deterministic.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_luhn.py`:
```python
from anonymizer.masking.luhn import is_luhn_valid, luhn_check_digit, make_luhn_valid


def test_known_valid_numbers():
    assert is_luhn_valid("4532015112830366")   # classic test PAN
    assert is_luhn_valid("046454286")          # canonical test SIN


def test_check_digit():
    assert luhn_check_digit("453201511283036") == "6"


def test_make_luhn_valid():
    fixed = make_luhn_valid("123456789")
    assert len(fixed) == 9
    assert fixed[:8] == "12345678"
    assert is_luhn_valid(fixed)
```

`tests/test_deterministic.py`:
```python
from anonymizer.masking.deterministic import value_rng


def test_same_inputs_same_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454286")
    assert [a.randint(0, 9) for _ in range(10)] == [b.randint(0, 9) for _ in range(10)]


def test_different_value_different_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454287")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]


def test_different_seed_different_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed2", "sin", "046454286")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]


def test_salt_changes_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454286", salt="syn-1")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_luhn.py tests/test_deterministic.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/anonymizer/masking/luhn.py`:
```python
"""Luhn checksum helpers (used by SIN and card-number rules)."""
from __future__ import annotations


def luhn_check_digit(partial: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def is_luhn_valid(digits: str) -> bool:
    return digits.isdigit() and digits[-1] == luhn_check_digit(digits[:-1])


def make_luhn_valid(digits: str) -> str:
    return digits[:-1] + luhn_check_digit(digits[:-1])
```

`src/anonymizer/masking/deterministic.py`:
```python
"""Deterministic per-value random streams via HMAC-SHA256."""
from __future__ import annotations

import hashlib
import hmac
import random


def value_rng(seed: str, rule: str, value: str, salt: str = "") -> random.Random:
    digest = hmac.new(seed.encode("utf-8"),
                      f"{rule}|{salt}|{value}".encode("utf-8"),
                      hashlib.sha256).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_luhn.py tests/test_deterministic.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/masking tests/test_luhn.py tests/test_deterministic.py
git commit -m "feat: add luhn helpers and HMAC-based deterministic rng"
```

---

### Task 13: Masking rules

**Files:**
- Create: `src/anonymizer/masking/rules.py`
- Test: `tests/test_rules.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_rules.py`:
```python
from anonymizer.copybook.model import Field
from anonymizer.masking.luhn import is_luhn_valid
from anonymizer.masking.rules import RULES, apply_rule

TEXT30 = Field(name="CUST-NAME", level=5, offset=0, length=30)
SIN = Field(name="CUST-SIN", level=5, offset=0, length=9, numeric=True, total_digits=9)
CARD = Field(name="CUST-CARD-NUM", level=5, offset=0, length=16, numeric=True,
             total_digits=16)
DOB = Field(name="CUST-DOB", level=5, offset=0, length=8, numeric=True, total_digits=8)
BAL = Field(name="CUST-BALANCE", level=5, offset=0, length=6, usage="comp-3",
            numeric=True, signed=True, total_digits=11, decimals=2)
SEED = "unit-test-seed"


def test_registry_contains_all_rules():
    for name in ["keep", "person_name", "sin", "credit_card", "digits",
                 "street_address", "city", "email", "scramble",
                 "date_jitter", "numeric_noise"]:
        assert name in RULES


def test_every_rule_is_deterministic():
    for name in RULES:
        v = "19850214" if name in ("date_jitter",) else "046454286"
        f = DOB if name == "date_jitter" else SIN
        assert apply_rule(name, v, f, SEED) == apply_rule(name, v, f, SEED)


def test_keep_is_identity():
    assert apply_rule("keep", "ANYTHING", TEXT30, SEED) == "ANYTHING"


def test_person_name_changes_and_fits():
    out = apply_rule("person_name", "JOHN SMITH", TEXT30, SEED)
    assert out != "JOHN SMITH"
    assert len(out) <= 30


def test_sin_is_nine_digits_luhn_valid_and_changed():
    out = apply_rule("sin", "046454286", SIN, SEED)
    assert len(out) == 9 and out.isdigit()
    assert is_luhn_valid(out)
    assert out != "046454286"


def test_credit_card_preserves_length_and_luhn():
    out = apply_rule("credit_card", "4532015112830366", CARD, SEED)
    assert len(out) == 16 and out.isdigit()
    assert is_luhn_valid(out)
    assert out != "4532015112830366"


def test_digits_preserves_non_digits():
    out = apply_rule("digits", "416-555-1234", TEXT30, SEED)
    assert len(out) == 12 and out[3] == "-" and out[7] == "-"
    assert out != "416-555-1234"


def test_scramble_preserves_char_classes():
    out = apply_rule("scramble", "M5V 2T6", TEXT30, SEED)
    assert len(out) == 7 and out[3] == " "
    assert out[0].isupper() and out[1].isdigit()


def test_date_jitter_stays_parseable():
    out = apply_rule("date_jitter", "19850214", DOB, SEED)
    assert len(out) == 8 and out.isdigit()
    assert out != "19850214"


def test_date_jitter_falls_back_on_garbage():
    out = apply_rule("date_jitter", "99999999", DOB, SEED)
    assert len(out) == 8 and out.isdigit()


def test_numeric_noise_changes_value_within_capacity():
    out = apply_rule("numeric_noise", "-12345.67", BAL, SEED)
    assert out != "-12345.67"
    from decimal import Decimal
    d = Decimal(out)
    assert abs(d) < Decimal(10) ** (BAL.total_digits - BAL.decimals)
    assert d.as_tuple().exponent == -2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rules.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/masking/rules.py`**

```python
"""Format-preserving, deterministic masking rules.

Every rule has signature (value, field, seed, salt) -> str and must return
a value that encode_field() can write back into the same field.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from faker import Faker

from anonymizer.copybook.model import Field
from anonymizer.masking.deterministic import value_rng
from anonymizer.masking.luhn import make_luhn_valid

_fake = Faker()
_MIN_YEAR = 1900


def _rng(rule: str, value: str, seed: str, salt: str):
    return value_rng(seed, rule, value, salt)


def _faker_for(rule: str, value: str, seed: str, salt: str) -> Faker:
    _fake.seed_instance(_rng(rule, value, seed, salt).getrandbits(32))
    return _fake


def rule_keep(value: str, field: Field, seed: str, salt: str) -> str:
    return value


def rule_person_name(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("person_name", value, seed, salt).name().upper()[:field.length]


def rule_street_address(value: str, field: Field, seed: str, salt: str) -> str:
    fake = _faker_for("street_address", value, seed, salt)
    return fake.street_address().upper().replace("\n", " ")[:field.length]


def rule_city(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("city", value, seed, salt).city().upper()[:field.length]


def rule_email(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("email", value, seed, salt).email().lower()[:field.length]


def rule_digits(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("digits", value, seed, salt)
    return "".join(str(rng.randint(0, 9)) if c.isdigit() else c for c in value)


def rule_sin(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("sin", value, seed, salt)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
    candidate = make_luhn_valid(digits)
    if candidate == value:                      # astronomically unlikely
        candidate = make_luhn_valid("1" + digits[1:])
    return candidate


def rule_credit_card(value: str, field: Field, seed: str, salt: str) -> str:
    n = len(value.strip()) or field.total_digits or 16
    rng = _rng("credit_card", value, seed, salt)
    digits = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9))
                                              for _ in range(n - 1))
    candidate = make_luhn_valid(digits)
    if candidate == value.strip():
        candidate = make_luhn_valid(str((int(digits[0]) % 9) + 1) + digits[1:])
    return candidate


def rule_scramble(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("scramble", value, seed, salt)
    out = []
    for c in value:
        if c.isdigit():
            out.append(str(rng.randint(0, 9)))
        elif c.isupper():
            out.append(chr(rng.randint(ord("A"), ord("Z"))))
        elif c.islower():
            out.append(chr(rng.randint(ord("a"), ord("z"))))
        else:
            out.append(c)
    return "".join(out)


def rule_date_jitter(value: str, field: Field, seed: str, salt: str) -> str:
    v = value.strip()
    try:
        date = datetime.strptime(v, "%Y%m%d")
    except ValueError:
        return rule_digits(value, field, seed, salt)
    rng = _rng("date_jitter", value, seed, salt)
    days = rng.randint(-365, 365) or 1
    shifted = date + timedelta(days=days)
    if shifted.year < _MIN_YEAR:
        shifted = date + timedelta(days=abs(days))
    return shifted.strftime("%Y%m%d")


def rule_numeric_noise(value: str, field: Field, seed: str, salt: str) -> str:
    d = Decimal(value)
    rng = _rng("numeric_noise", value, seed, salt)
    factor = Decimal(rng.randint(80, 121)) / 100   # 0.80 .. 1.21, never 1.00
    if factor == 1:
        factor = Decimal("1.05")
    result = (d * factor).quantize(Decimal(1).scaleb(-field.decimals))
    cap = Decimal(10) ** (field.total_digits - field.decimals)
    if abs(result) >= cap:
        result = (cap - Decimal(1).scaleb(-field.decimals)).copy_sign(result)
    if result == d:
        result = d + Decimal(1).scaleb(-field.decimals)
    return str(result)


RULES: dict[str, tuple[str, object]] = {
    "keep":           ("Keep unchanged", rule_keep),
    "person_name":    ("Fake person name", rule_person_name),
    "sin":            ("New SIN (checksum valid)", rule_sin),
    "credit_card":    ("New card number (checksum valid)", rule_credit_card),
    "digits":         ("Replace digits", rule_digits),
    "street_address": ("Fake street address", rule_street_address),
    "city":           ("Fake city", rule_city),
    "email":          ("Fake email", rule_email),
    "scramble":       ("Scramble letters/digits", rule_scramble),
    "date_jitter":    ("Shift date up to a year", rule_date_jitter),
    "numeric_noise":  ("Adjust amount up to 20%", rule_numeric_noise),
}


def apply_rule(rule_name: str, value: str, field: Field,
               seed: str, salt: str = "") -> str:
    _, fn = RULES[rule_name]
    return fn(value, field, seed, salt)


def rule_label(rule_name: str) -> str:
    return RULES[rule_name][0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rules.py -q`
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/masking/rules.py tests/test_rules.py
git commit -m "feat: add deterministic format-preserving masking rules"
```

---

### Task 14: Field classifier

**Files:**
- Create: `src/anonymizer/masking/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_classifier.py`:
```python
from anonymizer.copybook.model import Field
from anonymizer.masking.classifier import suggest_rule


def _f(name: str, numeric: bool = False, decimals: int = 0) -> Field:
    return Field(name=name, level=5, offset=0, length=10, numeric=numeric,
                 total_digits=10 if numeric else 0, decimals=decimals)


def test_pii_fields():
    assert suggest_rule(_f("CUST-NAME")) == ("person_name", True)
    assert suggest_rule(_f("CUST-SIN", numeric=True)) == ("sin", True)
    assert suggest_rule(_f("CUST-CARD-NUM", numeric=True)) == ("credit_card", True)
    assert suggest_rule(_f("CUST-STREET-ADDR")) == ("street_address", True)
    assert suggest_rule(_f("CUST-CITY")) == ("city", True)
    assert suggest_rule(_f("CUST-ZIPCODE")) == ("scramble", True)
    assert suggest_rule(_f("CUST-EMAIL")) == ("email", True)
    assert suggest_rule(_f("CUST-PHONE(1)")) == ("digits", True)


def test_dates():
    assert suggest_rule(_f("CUST-DOB", numeric=True)) == ("date_jitter", True)
    assert suggest_rule(_f("ACCT-OPEN-DT", numeric=True)) == ("date_jitter", True)
    assert suggest_rule(_f("ACCT-LAST-UPDT-DT", numeric=True)) == ("date_jitter", True)


def test_amounts():
    assert suggest_rule(_f("ACCT-BALANCE", numeric=True, decimals=2)) == ("numeric_noise", True)
    assert suggest_rule(_f("ACCT-INT-RATE", numeric=True, decimals=4)) == ("numeric_noise", True)
    assert suggest_rule(_f("CUST-AGE", numeric=True)) == ("numeric_noise", True)


def test_structural_fields_kept_and_unselected():
    assert suggest_rule(_f("FILLER")) == ("keep", False)
    assert suggest_rule(_f("ACCT-TYPE")) == ("keep", False)
    assert suggest_rule(_f("ACCT-STATUS")) == ("keep", False)
    assert suggest_rule(_f("REC-TYPE-CODE")) == ("keep", False)


def test_defaults():
    assert suggest_rule(_f("SOME-FREE-TEXT")) == ("scramble", True)
    assert suggest_rule(_f("ACCT-NUMBER", numeric=True)) == ("digits", True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_classifier.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/masking/classifier.py`**

```python
"""Suggest a masking rule per field from its copybook name and type.

Returns (rule_name, enabled).  Structural fields (record types, statuses,
filler) default to keep/unselected because masking them breaks downstream
parsing.  Evaluation order matters: first match wins.
"""
from __future__ import annotations

from anonymizer.copybook.model import Field

_KEEP_KEYWORDS = ("FILLER", "TYPE", "STATUS", "CODE", "IND", "FLAG")
_RULE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("SIN", "SSN"), "sin"),
    (("CARD", "PAN"), "credit_card"),
    (("NAME",), "person_name"),
    (("STREET", "ADDR"), "street_address"),
    (("CITY",), "city"),
    (("ZIP", "POSTAL"), "zipcode_scramble"),
    (("EMAIL",), "email"),
    (("PHONE", "TEL"), "digits"),
    (("DOB", "BIRTH", "DATE", "-DT"), "date_jitter"),
    (("BAL", "AMT", "AMOUNT", "RATE", "AGE"), "numeric_noise"),
)


def suggest_rule(field: Field) -> tuple[str, bool]:
    upper = field.name.upper()
    # PII keywords take priority: CUST-ZIPCODE must match ZIP before
    # the structural keyword CODE.
    for keywords, rule in _RULE_KEYWORDS:
        if any(k in upper for k in keywords):
            if rule == "zipcode_scramble":
                return ("scramble", True)
            if rule == "date_jitter" and not field.numeric:
                continue
            return (rule, True)
    for keyword in _KEEP_KEYWORDS:
        if keyword in upper:
            return ("keep", False)
    if field.numeric:
        return ("digits", True)
    return ("scramble", True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_classifier.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/masking/classifier.py tests/test_classifier.py
git commit -m "feat: classify copybook fields into masking rule suggestions"
```

---

### Task 15: Pipeline (masking + synthesis + sample)

**Files:**
- Create: `src/anonymizer/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:
```python
from decimal import Decimal
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


def test_default_plans_uses_classifier():
    plans = default_plans(_layout())
    by_name = {p.field.name: p for p in plans}
    assert by_name["CUST-SIN"].rule == "sin" and by_name["CUST-SIN"].enabled
    assert by_name["REC-TYPE"].rule == "keep" and not by_name["REC-TYPE"].enabled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/pipeline.py`**

```python
"""End-to-end anonymization pipeline.

Streams records from the input file, masks the enabled fields, and writes
them to the output file.  When target_count exceeds the input record count
the input is cycled again with a per-cycle salt ("syn-1", "syn-2", ...) so
each synthetic pass produces different masked values (spec: synthesis).
The first 10 records of the first pass are captured as a before/after
sample for the UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from anonymizer.codec.dispatch import decode_field, encode_field
from anonymizer.copybook.model import Field, Layout
from anonymizer.engine.reader import iter_records
from anonymizer.engine.writer import write_record
from anonymizer.masking.classifier import suggest_rule
from anonymizer.masking.rules import apply_rule

SAMPLE_RECORDS = 10
_PROGRESS_EVERY = 500


@dataclass(frozen=True)
class FieldPlan:
    field: Field
    rule: str
    enabled: bool


@dataclass(frozen=True)
class RunResult:
    records_written: int
    real_records: int
    synthetic_records: int
    sample: list[dict]


def default_plans(layout: Layout) -> list[FieldPlan]:
    counter = layout.odo.counter.name if layout.odo else None
    plans = []
    for f in layout.leaves:
        if f.name == counter:
            plans.append(FieldPlan(field=f, rule="keep", enabled=False))
            continue
        rule, enabled = suggest_rule(f)
        plans.append(FieldPlan(field=f, rule=rule, enabled=enabled))
    return plans


def mask_record(record: bytes, plans: list[FieldPlan], codepage: str,
                seed: str, salt: str = "",
                sample_rows: list[dict] | None = None,
                record_no: int = 0) -> bytes:
    out = bytearray(record)
    for plan in plans:
        f = plan.field
        if f.offset + f.length > len(record):
            continue                      # ODO instance not present
        before = decode_field(f, record, codepage)
        if plan.enabled and plan.rule != "keep":
            after = apply_rule(plan.rule, before, f, seed, salt)
            out[f.offset:f.offset + f.length] = encode_field(f, after, codepage)
        else:
            after = before
        if sample_rows is not None:
            sample_rows.append({"record": record_no, "field": f.name,
                                "before": before, "after": after})
    return bytes(out)


def run_anonymization(input_path: Path, output_path: Path, layout: Layout,
                      codepage: str, plans: list[FieldPlan], seed: str,
                      target_count: int, rdw: bool = False,
                      progress_cb: Callable[[int, int], None] | None = None,
                      ) -> RunResult:
    written = 0
    real_records = 0
    cycle = 0
    sample: list[dict] = []
    with open(output_path, "wb") as out:
        while written < target_count:
            salt = "" if cycle == 0 else f"syn-{cycle}"
            read_any = False
            for record in iter_records(input_path, layout, codepage, rdw=rdw):
                read_any = True
                capture = sample if (cycle == 0 and
                                     written < SAMPLE_RECORDS) else None
                masked = mask_record(record, plans, codepage, seed, salt,
                                     sample_rows=capture,
                                     record_no=written + 1)
                write_record(out, masked, rdw=rdw)
                written += 1
                if cycle == 0:
                    real_records += 1
                if progress_cb and (written % _PROGRESS_EVERY == 0
                                    or written == target_count):
                    progress_cb(written, target_count)
                if written >= target_count:
                    break
            if not read_any:
                raise ValueError("The input file is empty — nothing to mask.")
            cycle += 1
    if progress_cb:
        progress_cb(written, target_count)
    return RunResult(records_written=written, real_records=real_records,
                     synthetic_records=written - real_records, sample=sample)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/pipeline.py tests/test_pipeline.py
git commit -m "feat: add streaming anonymization pipeline with synthesis and sampling"
```

---

### Task 16: Audit report

**Files:**
- Create: `src/anonymizer/audit.py`
- Test: `tests/test_audit.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_audit.py`:
```python
from anonymizer.audit import build_audit_report
from anonymizer.copybook.model import Field
from anonymizer.pipeline import FieldPlan, RunResult

NAME = Field(name="CUST-NAME", level=5, offset=0, length=10)
TYPE = Field(name="REC-TYPE", level=5, offset=10, length=1)


def test_report_contents():
    result = RunResult(records_written=100, real_records=40,
                       synthetic_records=60, sample=[])
    plans = [FieldPlan(field=NAME, rule="person_name", enabled=True),
             FieldPlan(field=TYPE, rule="keep", enabled=False)]
    report = build_audit_report(result, plans, seed="topsecret",
                                input_name="in.dat", output_name="out.dat")
    assert "CUST-NAME" in report and "Fake person name" in report
    assert "REC-TYPE" in report and "not masked" in report
    assert "100" in report and "60" in report
    assert "topsecret" not in report            # seed never leaks
    assert "Seed fingerprint" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_audit.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/audit.py`**

```python
"""Markdown audit report for an anonymization run."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from anonymizer.masking.rules import rule_label
from anonymizer.pipeline import FieldPlan, RunResult


def build_audit_report(result: RunResult, plans: list[FieldPlan], seed: str,
                       input_name: str, output_name: str) -> str:
    fingerprint = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Anonymization Audit Report",
        "",
        f"- Generated: {when}",
        f"- Input file: {input_name}",
        f"- Output file: {output_name}",
        f"- Records written: {result.records_written}",
        f"- From real records: {result.real_records}",
        f"- Synthetic records: {result.synthetic_records}",
        f"- Seed fingerprint: {fingerprint} (the seed itself is never stored)",
        "",
        "| Field | Action |",
        "|---|---|",
    ]
    for plan in plans:
        action = (rule_label(plan.rule)
                  if plan.enabled and plan.rule != "keep" else "not masked")
        lines.append(f"| {plan.field.name} | {action} |")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_audit.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/audit.py tests/test_audit.py
git commit -m "feat: add markdown audit report with seed fingerprint"
```

---

### Task 17: Sample data generator + fixtures

**Files:**
- Create: `tools/generate_samples.py`, `samples/data/*` (generated)

- [ ] **Step 1: Implement `tools/generate_samples.py`**

```python
"""Generate deterministic banking sample data files for both encodings.

Usage:  python tools/generate_samples.py
Writes samples/data/{customer,account}.{cp037,ascii}.dat
Requires Java (uses cb2xml to parse the sample copybooks).
"""
from __future__ import annotations

import sys
from pathlib import Path

from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anonymizer.codec.dispatch import encode_field          # noqa: E402
from anonymizer.copybook.cb2xml_runner import parse_copybook  # noqa: E402
from anonymizer.copybook.model import Layout                 # noqa: E402

CUSTOMERS = 50
ACCOUNTS = 120
ACCOUNT_TYPES = ["CHQ", "SAV", "TFS", "RSP"]


def customer_row(fake: Faker, i: int) -> dict[str, str]:
    dob = fake.date_of_birth(minimum_age=19, maximum_age=90)
    return {
        "CUST-ID": str(10000000 + i),
        "CUST-NAME": fake.name().upper(),
        "CUST-AGE": str(fake.random_int(19, 90)),
        "CUST-DOB": dob.strftime("%Y%m%d"),
        "CUST-STREET-ADDR": fake.street_address().upper(),
        "CUST-CITY": fake.city().upper(),
        "CUST-ZIPCODE": fake.bothify("?#?#?#").upper(),
        "CUST-SIN": fake.numerify("#########"),
        "CUST-PHONE(1)": fake.numerify("416#######"),
        "CUST-PHONE(2)": fake.numerify("905#######"),
        "CUST-EMAIL": fake.email().lower(),
        "CUST-CARD-NUM": fake.numerify("45320151########"),
        "CUST-BALANCE": str(fake.pydecimal(left_digits=7, right_digits=2)),
        "CUST-BRANCH-CODE": str(fake.random_int(1, 9999)),
    }


def account_row(fake: Faker, i: int) -> dict[str, str]:
    opened = fake.date_between(start_date="-20y", end_date="-1y")
    updated = fake.date_between(start_date="-1y", end_date="today")
    return {
        "ACCT-CUST-ID": str(10000000 + (i % CUSTOMERS)),
        "ACCT-NUMBER": fake.numerify("############"),
        "ACCT-TYPE": fake.random_element(ACCOUNT_TYPES),
        "ACCT-OPEN-DT": opened.strftime("%Y%m%d"),
        "ACCT-LAST-UPDT-DT": updated.strftime("%Y%m%d"),
        "ACCT-STATUS": fake.random_element(["A", "C", "D"]),
        "ACCT-BRANCH": str(fake.random_int(1, 9999)),
        "ACCT-BALANCE": str(fake.pydecimal(left_digits=9, right_digits=2)),
        "ACCT-INT-RATE": str(fake.pydecimal(left_digits=2, right_digits=4,
                                            positive=True)),
    }


def encode_row(layout: Layout, row: dict[str, str], codepage: str) -> bytes:
    record = bytearray(" ".encode(codepage) * layout.record_length)
    for field in layout.leaves:
        value = row.get(field.name, "0" if field.numeric else "")
        record[field.offset:field.offset + field.length] = \
            encode_field(field, value, codepage)
    return bytes(record)


def generate(copybook: str, row_fn, count: int, stem: str) -> None:
    layout = parse_copybook(ROOT / "samples" / "copybooks" / copybook)
    fake = Faker()
    fake.seed_instance(42)
    rows = [row_fn(fake, i) for i in range(count)]
    for codepage in ("cp037", "ascii"):
        out = ROOT / "samples" / "data" / f"{stem}.{codepage}.dat"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            for row in rows:
                f.write(encode_row(layout, row, codepage))
        print(f"wrote {out} ({count} records x {layout.record_length} bytes)")


if __name__ == "__main__":
    generate("customer.cpy", customer_row, CUSTOMERS, "customer")
    generate("account.cpy", account_row, ACCOUNTS, "account")
```

- [ ] **Step 2: Run the generator**

Run: `python tools/generate_samples.py`
Expected: four files written; `customer.cp037.dat` is exactly 50 × 202 = 10,100 bytes; `account.ascii.dat` is 120 × 71 = 8,520 bytes. Verify sizes:
`(Get-Item samples/data/customer.cp037.dat).Length` → `10100`

- [ ] **Step 3: Commit**

```bash
git add tools/generate_samples.py samples/data
git commit -m "feat: add deterministic banking sample data in cp037 and ascii"
```

---

### Task 18: Golden integration test

**Files:**
- Test: `tests/test_golden.py`

- [ ] **Step 1: Write the integration tests**

`tests/test_golden.py`:
```python
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

pytestmark = pytest.mark.skipif(find_java() is None, reason="java not installed")


@pytest.fixture(scope="module")
def layout():
    return parse_copybook(CPY)


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


def test_cross_file_referential_integrity(tmp_path, layout):
    """Same value + same rule + same seed -> same masked value (join keys)."""
    from anonymizer.masking.rules import apply_rule
    by_name = {f.name: f for f in layout.leaves}
    cust_id = by_name["CUST-ID"]
    a = apply_rule("digits", "10000007", cust_id, "golden")
    b = apply_rule("digits", "10000007", cust_id, "golden")
    assert a == b
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_golden.py -q`
Expected: `4 passed` (or all skipped without java)

- [ ] **Step 3: Commit**

```bash
git add tests/test_golden.py
git commit -m "test: add end-to-end golden tests over sample banking files"
```

---

### Task 19: UI helpers

**Files:**
- Create: `src/anonymizer/ui/__init__.py` (empty), `src/anonymizer/ui/helpers.py`
- Test: `tests/test_ui_helpers.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_ui_helpers.py`:
```python
from anonymizer.copybook.model import Field
from anonymizer.ui.helpers import describe_field, detect_encoding


def test_describe_text():
    f = Field(name="X", level=5, offset=0, length=30)
    assert describe_field(f) == "Text, 30 characters"


def test_describe_display_number():
    f = Field(name="X", level=5, offset=0, length=9, numeric=True, total_digits=9)
    assert describe_field(f) == "Number, 9 digits"


def test_describe_comp3_with_decimals():
    f = Field(name="X", level=5, offset=0, length=6, usage="comp-3",
              numeric=True, signed=True, total_digits=11, decimals=2)
    assert describe_field(f) == "Packed number, 11 digits (2 after the decimal point)"


def test_describe_comp():
    f = Field(name="X", level=5, offset=0, length=2, usage="comp",
              numeric=True, total_digits=4)
    assert describe_field(f) == "Binary number, 4 digits"


def test_detect_encoding_ascii():
    assert detect_encoding(b"HELLO WORLD 12345 MAIN ST") == "ascii"


def test_detect_encoding_ebcdic():
    assert detect_encoding("HELLO WORLD 12345".encode("cp037")) == "cp037"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ui_helpers.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/anonymizer/ui/helpers.py`**

```python
"""Plain-language helpers for the wizard UI."""
from __future__ import annotations

from anonymizer.copybook.model import Field

_ASCII_PRINTABLE_THRESHOLD = 0.7


def describe_field(field: Field) -> str:
    if field.usage == "comp-3":
        base = f"Packed number, {field.total_digits} digits"
    elif field.usage == "comp":
        base = f"Binary number, {field.total_digits} digits"
    elif field.numeric:
        base = f"Number, {field.total_digits} digits"
    else:
        return f"Text, {field.length} characters"
    if field.decimals:
        base += f" ({field.decimals} after the decimal point)"
    return base


def detect_encoding(first_bytes: bytes) -> str:
    """Heuristic: mostly ASCII-printable bytes -> ascii, else cp037."""
    if not first_bytes:
        return "ascii"
    printable = sum(1 for b in first_bytes if 0x20 <= b < 0x7F)
    if printable / len(first_bytes) >= _ASCII_PRINTABLE_THRESHOLD:
        return "ascii"
    return "cp037"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ui_helpers.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/anonymizer/ui tests/test_ui_helpers.py
git commit -m "feat: add plain-language field descriptions and encoding detection"
```

---

### Task 20: Streamlit wizard

**Files:**
- Create: `src/anonymizer/ui/steps.py`, `app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Implement `src/anonymizer/ui/steps.py`**

```python
"""Render functions for the 5 wizard steps.  All state in st.session_state."""
from __future__ import annotations

import secrets
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from anonymizer.audit import build_audit_report
from anonymizer.codec.dispatch import FieldCodecError, decode_field
from anonymizer.copybook.cb2xml_runner import (CopybookParseError,
                                               JavaNotFoundError,
                                               parse_copybook)
from anonymizer.engine.reader import iter_records, validate_fixed_file
from anonymizer.masking.rules import RULES, apply_rule, rule_label
from anonymizer.pipeline import FieldPlan, default_plans, run_anonymization
from anonymizer.ui.helpers import describe_field, detect_encoding

MIN_RECORDS, MAX_RECORDS = 5, 1_000_000
_RULE_NAMES = list(RULES.keys())
_RULE_LABELS = {rule_label(n): n for n in _RULE_NAMES}


def _workdir() -> Path:
    if "workdir" not in st.session_state:
        st.session_state.workdir = Path(tempfile.mkdtemp(prefix="anonymizer-"))
    return st.session_state.workdir


def _save_upload(uploaded, name: str) -> Path:
    path = _workdir() / name
    path.write_bytes(uploaded.getvalue())
    return path


def _first_record() -> bytes | None:
    try:
        return next(iter_records(st.session_state.data_path,
                                 st.session_state.layout,
                                 st.session_state.codepage,
                                 rdw=st.session_state.rdw), None)
    except Exception:
        return None


def render_upload() -> None:
    st.subheader("Step 1 — Upload your files")
    data_file = st.file_uploader("Mainframe data file", key="u_data")
    cpy_file = st.file_uploader("Copybook (.cpy / .txt)", key="u_cpy",
                                type=None)
    st.session_state.rdw = st.checkbox(
        "File is variable-length (VB with record headers)", value=False)
    encoding_choice = st.radio(
        "File encoding", ["Detect automatically", "EBCDIC (cp037)", "ASCII"],
        horizontal=True)
    if not (data_file and cpy_file):
        st.info("Upload both files to continue.")
        return
    data_path = _save_upload(data_file, "input.dat")
    cpy_path = _save_upload(cpy_file, "copybook.cpy")
    try:
        layout = parse_copybook(cpy_path)
    except JavaNotFoundError as exc:
        st.error(str(exc))
        return
    except CopybookParseError as exc:
        st.error(f"Copybook problem: {exc}")
        return
    if encoding_choice == "EBCDIC (cp037)":
        codepage = "cp037"
    elif encoding_choice == "ASCII":
        codepage = "ascii"
    else:
        codepage = detect_encoding(data_path.read_bytes()[:layout.record_length])
        st.caption(f"Detected encoding: "
                   f"{'EBCDIC (cp037)' if codepage == 'cp037' else 'ASCII'}")
    if not st.session_state.rdw:
        problem = validate_fixed_file(data_path, layout)
        if problem:
            st.error(problem)
            return
    st.session_state.data_path = data_path
    st.session_state.layout = layout
    st.session_state.codepage = codepage
    st.success(f"Copybook OK: record **{layout.name}**, "
               f"{layout.record_length} bytes, {len(layout.leaves)} fields.")
    if st.button("Next: review fields", type="primary"):
        st.session_state.step = 1
        st.rerun()


def render_fields() -> None:
    st.subheader("Step 2 — Fields found in your file")
    layout = st.session_state.layout
    first = _first_record()
    rows = []
    for f in layout.leaves:
        sample = ""
        if first is not None:
            try:
                sample = decode_field(f, first, st.session_state.codepage)
            except FieldCodecError:
                sample = "(unreadable)"
        rows.append({"Field": f.name, "Type": describe_field(f),
                     "Starts at byte": f.offset + 1, "Length": f.length,
                     "Sample value": sample.strip()})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if layout.overlays:
        with st.expander("Overlay views (REDEFINES — masked via primary field)"):
            st.dataframe(pd.DataFrame(
                [{"Field": f.name, "Type": describe_field(f)}
                 for f in layout.overlays]), hide_index=True)
    col1, col2 = st.columns(2)
    if col1.button("Back"):
        st.session_state.step = 0
        st.rerun()
    if col2.button("Next: choose masking", type="primary"):
        st.session_state.step = 2
        st.rerun()


def render_rules() -> None:
    st.subheader("Step 3 — Choose what gets masked")
    st.caption("Every field starts pre-selected with a suggested rule. "
               "Untick anything that must stay unchanged.")
    layout = st.session_state.layout
    if "plans" not in st.session_state:
        st.session_state.plans = default_plans(layout)
    first = _first_record()
    seed_preview = st.session_state.get("seed", "preview")
    rows = []
    for plan in st.session_state.plans:
        f = plan.field
        example = ""
        if first is not None and plan.enabled and plan.rule != "keep":
            try:
                before = decode_field(f, first, st.session_state.codepage)
                example = apply_rule(plan.rule, before, f, seed_preview).strip()
            except (FieldCodecError, Exception):
                example = ""
        rows.append({"Mask?": plan.enabled, "Field": f.name,
                     "Rule": rule_label(plan.rule), "Example": example})
    edited = st.data_editor(
        pd.DataFrame(rows),
        column_config={
            "Mask?": st.column_config.CheckboxColumn(),
            "Rule": st.column_config.SelectboxColumn(
                options=[rule_label(n) for n in _RULE_NAMES]),
            "Field": st.column_config.TextColumn(disabled=True),
            "Example": st.column_config.TextColumn(disabled=True),
        },
        hide_index=True, use_container_width=True, key="rules_editor")
    new_plans = []
    for plan, (_, row) in zip(st.session_state.plans, edited.iterrows()):
        new_plans.append(FieldPlan(field=plan.field,
                                   rule=_RULE_LABELS[row["Rule"]],
                                   enabled=bool(row["Mask?"])))
    st.session_state.plans = new_plans
    col1, col2 = st.columns(2)
    if col1.button("Back"):
        st.session_state.step = 1
        st.rerun()
    if col2.button("Next: generate", type="primary"):
        st.session_state.step = 3
        st.rerun()


def render_generate() -> None:
    st.subheader("Step 4 — Generate the masked file")
    layout = st.session_state.layout
    input_size = st.session_state.data_path.stat().st_size
    approx_input = (input_size // layout.record_length
                    if layout.odo is None and not st.session_state.rdw else None)
    if approx_input is not None:
        st.caption(f"Your input file has about {approx_input:,} records.")
    target = st.number_input("How many output records do you want?",
                             min_value=MIN_RECORDS, max_value=MAX_RECORDS,
                             value=min(max(approx_input or 100, MIN_RECORDS),
                                       MAX_RECORDS))
    if approx_input is not None and target > approx_input:
        st.info(f"{target - approx_input:,} extra records will be synthesized "
                "from the patterns in your data.")
    if "seed" not in st.session_state:
        st.session_state.seed = secrets.token_hex(8)
    seed = st.text_input(
        "Masking seed (keep it to reproduce the same masked values)",
        value=st.session_state.seed)
    st.session_state.seed = seed
    col1, col2 = st.columns(2)
    if col1.button("Back"):
        st.session_state.step = 2
        st.rerun()
    if col2.button("Generate masked file", type="primary"):
        out_path = _workdir() / "masked_output.dat"
        bar = st.progress(0.0, text="Masking records…")

        def update(done: int, total: int) -> None:
            bar.progress(min(done / total, 1.0),
                         text=f"Masking records… {done:,} / {total:,}")

        try:
            result = run_anonymization(
                st.session_state.data_path, out_path, layout,
                st.session_state.codepage, st.session_state.plans,
                seed=seed, target_count=int(target),
                rdw=st.session_state.rdw, progress_cb=update)
        except Exception as exc:
            st.error(f"Something went wrong while masking: {exc}")
            return
        st.session_state.result = result
        st.session_state.output_path = out_path
        st.session_state.step = 4
        st.rerun()


def render_preview() -> None:
    st.subheader("Step 5 — Before & after preview")
    result = st.session_state.result
    st.success(f"Done! {result.records_written:,} records written "
               f"({result.real_records:,} from your file, "
               f"{result.synthetic_records:,} synthesized).")
    df = pd.DataFrame(result.sample)
    df.columns = ["Record #", "Field", "Before", "After"]
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    audit = build_audit_report(result, st.session_state.plans,
                               st.session_state.seed,
                               input_name="uploaded data file",
                               output_name="masked_output.dat")
    col1, col2 = st.columns(2)
    col1.download_button("Download masked file",
                         st.session_state.output_path.read_bytes(),
                         file_name="masked_output.dat")
    col2.download_button("Download audit report", audit,
                         file_name="audit_report.md")
    if st.button("Start over"):
        workdir = st.session_state.get("workdir")
        if workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
```

- [ ] **Step 2: Implement `app.py`**

```python
"""Mainframe File Anonymizer — Streamlit entry point."""
import streamlit as st

from anonymizer.ui import steps

st.set_page_config(page_title="Mainframe File Anonymizer", page_icon="🛡️",
                   layout="wide")

STEP_NAMES = ["Upload", "Fields", "Masking", "Generate", "Preview"]
RENDERERS = [steps.render_upload, steps.render_fields, steps.render_rules,
             steps.render_generate, steps.render_preview]

if "step" not in st.session_state:
    st.session_state.step = 0

st.title("🛡️ Mainframe File Anonymizer")
st.caption("Mask sensitive data in mainframe files for safe use in test "
           "environments. Everything stays on this machine.")

cols = st.columns(len(STEP_NAMES))
for i, (col, name) in enumerate(zip(cols, STEP_NAMES)):
    marker = "🔵" if i == st.session_state.step else (
        "✅" if i < st.session_state.step else "⚪")
    col.markdown(f"{marker} **{i + 1}. {name}**")
st.divider()

RENDERERS[st.session_state.step]()
```

- [ ] **Step 3: Write the AppTest smoke test**

`tests/test_app.py`:
```python
from streamlit.testing.v1 import AppTest


def test_app_boots_without_exception():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert at.title[0].value == "🛡️ Mainframe File Anonymizer"


def test_upload_step_asks_for_both_files():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert any("Upload both files" in info.value for info in at.info)
```

- [ ] **Step 4: Run the tests and a manual smoke**

Run: `python -m pytest tests/test_app.py -q`
Expected: `2 passed`

Manual smoke: `streamlit run app.py`, then in the browser: upload `samples/data/customer.cp037.dat` + `samples/copybooks/customer.cpy`, walk all 5 steps with 60 output records, confirm the before/after table shows masked names/SINs and the download buttons work. Stop the server.

- [ ] **Step 5: Commit**

```bash
git add app.py src/anonymizer/ui/steps.py tests/test_app.py
git commit -m "feat: add 5-step streamlit wizard for non-technical users"
```

---

### Task 21: README and final verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Mainframe File Anonymizer

Mask PII/PCI in mainframe files (EBCDIC or ASCII) using their COBOL copybook,
entirely on your own machine. Output files keep the exact byte layout of the
input so downstream ingestion jobs run unchanged.

## Requirements
- Python 3.10+
- Java 8+ on PATH (used only to parse the copybook)

## Setup
    pip install -r requirements.txt
    pip install -e .

## Run
    streamlit run app.py

Then follow the 5 steps: Upload → Fields → Masking → Generate → Preview.
Sample files to try it with are in `samples/` (banking customer + account
data in EBCDIC cp037 and ASCII).

## Key behaviors
- **Deterministic**: the same seed + input value always produces the same
  masked value — across files and runs (join keys stay consistent).
- **Format-preserving**: masked SINs and card numbers pass Luhn checks;
  numbers stay within their field's digit capacity; text fits its field.
- **Synthesis**: ask for more records than the input has and the extras are
  synthesized from your data's patterns (5 to 1,000,000 records).
- **Private**: no network calls; the seed is never written to any output.

## Tests
    python -m pytest --cov=anonymizer --cov-fail-under=80
```

- [ ] **Step 2: Full test run with coverage**

Run: `python -m pytest --cov=anonymizer --cov-report=term-missing --cov-fail-under=80 -q`
Expected: all tests pass, total coverage ≥ 80%. If coverage is short, the gap will be in `ui/steps.py` — exclude it if needed by adding to `pyproject.toml`:

```toml
[tool.coverage.run]
omit = ["src/anonymizer/ui/steps.py"]
```

(UI rendering is covered by AppTest smoke + manual verification; core logic must stay covered.)

- [ ] **Step 3: Commit and push**

```bash
git add README.md pyproject.toml
git commit -m "docs: add README with setup and usage"
git push
```

---

## Definition of done

- `python -m pytest --cov=anonymizer --cov-fail-under=80 -q` passes.
- `streamlit run app.py` manual walkthrough works with both sample datasets
  (cp037 and ascii) end to end, including synthesis past the input count.
- Output file size = record_length × requested count; unmasked fields byte-identical.
- Same seed twice → byte-identical outputs.
