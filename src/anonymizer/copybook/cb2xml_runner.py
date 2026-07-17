"""Run the bundled cb2xml jar to parse a COBOL copybook."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from anonymizer.copybook.model import Layout
from anonymizer.copybook.xml_mapper import CopybookMappingError, layout_from_xml

DEFAULT_JAR = Path(__file__).resolve().parents[3] / "vendor" / "cb2xml.jar"
_MAIN_CLASS = "net.sf.cb2xml.Cb2Xml"
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
    try:
        result = subprocess.run(
            [java, "-cp", str(jar_path), _MAIN_CLASS, str(copybook_path)],
            capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise CopybookParseError(
            f"The copybook parser timed out after {_TIMEOUT_SECONDS} seconds."
        ) from exc
    if result.returncode != 0 or not result.stdout.strip() or "<item" not in result.stdout:
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise CopybookParseError(
            f"The copybook could not be parsed. Parser said:\n{detail}")
    try:
        return layout_from_xml(result.stdout)
    except CopybookMappingError as exc:
        raise CopybookParseError(str(exc)) from exc
