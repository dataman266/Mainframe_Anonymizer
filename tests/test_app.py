import os
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from anonymizer.ui import steps


def test_app_boots_without_exception():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert at.title[0].value == "🛡️ Mainframe File Anonymizer"


def test_upload_step_asks_for_both_files():
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert any("Upload both files" in info.value for info in at.info)


# --- _reset_derived_state ---------------------------------------------


def test_reset_derived_state_drops_stale_plans_on_new_fingerprint(monkeypatch):
    monkeypatch.setattr(steps.st, "session_state", {
        "upload_fingerprint": "aaa",
        "plans": ["stale-plan"],
        "result": "stale-result",
        "output_path": "stale-path",
        "output_bytes": b"stale",
        "first_record": b"stale-record",
    })

    steps._reset_derived_state("bbb")

    state = steps.st.session_state
    assert "plans" not in state
    assert "result" not in state
    assert "output_path" not in state
    assert "output_bytes" not in state
    assert "first_record" not in state
    assert state["upload_fingerprint"] == "bbb"


def test_reset_derived_state_keeps_plans_when_fingerprint_unchanged(monkeypatch):
    monkeypatch.setattr(steps.st, "session_state", {
        "upload_fingerprint": "aaa",
        "plans": ["kept-plan"],
    })

    steps._reset_derived_state("aaa")

    assert steps.st.session_state["plans"] == ["kept-plan"]


def test_reset_derived_state_sets_fingerprint_on_first_upload(monkeypatch):
    monkeypatch.setattr(steps.st, "session_state", {})

    steps._reset_derived_state("first-fingerprint")

    assert steps.st.session_state["upload_fingerprint"] == "first-fingerprint"


# --- _sweep_stale_workdirs -----------------------------------------------


def test_sweep_stale_workdirs_removes_only_old_anonymizer_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(steps.tempfile, "gettempdir", lambda: str(tmp_path))

    old_dir = tmp_path / "anonymizer-old"
    old_dir.mkdir()
    (old_dir / "input.dat").write_bytes(b"pii")
    new_dir = tmp_path / "anonymizer-new"
    new_dir.mkdir()
    unrelated_dir = tmp_path / "other-tempdir"
    unrelated_dir.mkdir()

    now = time.time()
    old_mtime = now - steps._STALE_WORKDIR_AGE_SECONDS - 3600
    os.utime(old_dir, (old_mtime, old_mtime))

    removed = steps._sweep_stale_workdirs(now=now)

    assert removed == 1
    assert not old_dir.exists()
    assert new_dir.exists()
    assert unrelated_dir.exists()


def test_sweep_stale_workdirs_returns_zero_when_nothing_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(steps.tempfile, "gettempdir", lambda: str(tmp_path))
    (tmp_path / "anonymizer-fresh").mkdir()

    assert steps._sweep_stale_workdirs(now=time.time()) == 0


# --- _parse_copybook_cached ------------------------------------------------


def test_parse_copybook_cached_parses_bytes_via_temp_file(monkeypatch):
    calls = []

    def fake_parse_copybook(path):
        calls.append(Path(path).read_bytes())
        return "FAKE-LAYOUT"

    monkeypatch.setattr(steps, "parse_copybook", fake_parse_copybook)
    steps._parse_copybook_cached.clear()

    result = steps._parse_copybook_cached(b"01 REC PIC X(5).")

    assert result == "FAKE-LAYOUT"
    assert calls == [b"01 REC PIC X(5)."]


def test_parse_copybook_cached_reuses_result_for_same_bytes(monkeypatch):
    calls = []

    def fake_parse_copybook(path):
        calls.append(1)
        return "FAKE-LAYOUT"

    monkeypatch.setattr(steps, "parse_copybook", fake_parse_copybook)
    steps._parse_copybook_cached.clear()

    steps._parse_copybook_cached(b"same bytes")
    steps._parse_copybook_cached(b"same bytes")

    assert len(calls) == 1
