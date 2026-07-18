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
from anonymizer.masking.rules import (RULES, apply_rule, is_rule_compatible,
                                      rule_label)
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
        records = iter_records(st.session_state.data_path,
                               st.session_state.layout,
                               st.session_state.codepage,
                               rdw=st.session_state.rdw)
        try:
            return next(records, None)
        finally:
            records.close()
    except Exception:
        return None


def render_upload() -> None:
    st.subheader("Step 1 — Upload your files")
    data_file = st.file_uploader("Mainframe data file", key="u_data")
    cpy_file = st.file_uploader("Copybook (.cpy / .txt)", key="u_cpy")
    st.session_state.rdw = st.checkbox(
        "File is variable-length (VB with record headers)",
        value=st.session_state.get("rdw", False))
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
    if not st.session_state.rdw and layout.odo is None:
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
            except FieldCodecError:
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
    incompatible: list[str] = []
    for plan, (_, row) in zip(st.session_state.plans, edited.iterrows()):
        rule = _RULE_LABELS[row["Rule"]]
        enabled = bool(row["Mask?"])
        if enabled and not is_rule_compatible(rule, plan.field):
            incompatible.append(
                f"{plan.field.name}: '{row['Rule']}' cannot be used on a "
                "number field")
            rule, enabled = plan.rule, plan.enabled
        new_plans.append(FieldPlan(field=plan.field, rule=rule,
                                   enabled=enabled))
    st.session_state.plans = new_plans
    for message in incompatible:
        st.warning(message)
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
    default_target = min(max(approx_input or 100, MIN_RECORDS), MAX_RECORDS)
    target = st.number_input("How many output records do you want?",
                             min_value=MIN_RECORDS, max_value=MAX_RECORDS,
                             value=default_target)
    if approx_input is not None and target > approx_input:
        st.info(f"{target - approx_input:,} extra records will be synthesized "
                "from the patterns in your data.")
    if "seed" not in st.session_state:
        st.session_state.seed = secrets.token_hex(8)
    seed = st.text_input(
        "Masking seed (keep it to reproduce the same masked values)",
        value=st.session_state.seed)
    st.session_state.seed = seed or secrets.token_hex(8)
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
                seed=st.session_state.seed, target_count=int(target),
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
