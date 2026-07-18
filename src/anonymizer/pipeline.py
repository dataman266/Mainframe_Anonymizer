"""End-to-end anonymization pipeline.

Streams records from the input file, masks the enabled fields, and writes
them to the output file.  When target_count exceeds the input record count
the input is cycled again with a per-cycle salt ("syn-1", "syn-2", ...) so
each synthetic pass produces different masked values (spec: synthesis).
The first 10 records of the first pass are captured as a before/after
sample for the UI.

Output is written to a sibling ``<output>.tmp`` file and only moved into
place with ``os.replace`` once the whole run succeeds, so a failure partway
through (a corrupt field, a cancelled run) never leaves a partial or
misleading file at the destination path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from anonymizer.codec.dispatch import FieldCodecError, decode_field, encode_field
from anonymizer.copybook.model import Field, Layout
from anonymizer.engine.reader import iter_records
from anonymizer.engine.writer import write_record
from anonymizer.masking.classifier import suggest_rule
from anonymizer.masking.rules import apply_rule, is_rule_compatible

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


def validate_plans(plans: list[FieldPlan]) -> None:
    for plan in plans:
        if plan.enabled and not is_rule_compatible(plan.rule, plan.field):
            raise ValueError(
                f"Rule '{plan.rule}' cannot be applied to numeric field "
                f"{plan.field.name}. Choose a numeric-friendly rule instead.")


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


def _should_cache_cycle_zero(input_path: Path, layout: Layout, rdw: bool,
                             target_count: int) -> bool:
    """Whether cycle 0 should cache raw records in memory for reuse by
    later synthesis cycles, instead of re-opening and re-reading the input
    file (and, for ODO, re-parsing every record header) on every cycle.

    For fixed-length, non-RDW layouts the record count can be estimated
    cheaply from the file size, so caching is only worth its memory cost
    when synthesis will actually happen (target_count exceeds that
    estimate). RDW and ODO layouts have no cheap size-based estimate, so we
    always cache for them: input files are bounded to roughly 200MB by the
    product target, making the memory cost acceptable, and it is far
    cheaper than re-reading (and, for ODO, re-parsing) the whole file on
    every synthesis cycle.
    """
    if rdw or layout.odo is not None or layout.record_length <= 0:
        return True
    estimate = os.path.getsize(input_path) // layout.record_length
    return target_count > estimate


def run_anonymization(input_path: Path, output_path: Path, layout: Layout,
                      codepage: str, plans: list[FieldPlan], seed: str,
                      target_count: int, rdw: bool = False,
                      progress_cb: Callable[[int, int], None] | None = None,
                      ) -> RunResult:
    if target_count < 1:
        raise ValueError("target_count must be at least 1")
    validate_plans(plans)

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    cache_enabled = _should_cache_cycle_zero(input_path, layout, rdw,
                                             target_count)
    cache: list[bytes] | None = None

    written = 0
    real_records = 0
    cycle = 0
    sample: list[dict] = []
    try:
        with open(tmp_path, "wb") as out:
            while written < target_count:
                salt = "" if cycle == 0 else f"syn-{cycle}"
                read_any = False
                using_cache = cycle > 0 and cache is not None
                records = None if using_cache else iter_records(
                    input_path, layout, codepage, rdw=rdw)
                source = cache if using_cache else records
                try:
                    for record in source:
                        read_any = True
                        if cycle == 0 and cache_enabled:
                            if cache is None:
                                cache = []
                            cache.append(record)
                        capture = sample if (cycle == 0 and
                                             written < SAMPLE_RECORDS) else None
                        try:
                            masked = mask_record(record, plans, codepage, seed,
                                                 salt, sample_rows=capture,
                                                 record_no=written + 1)
                        except FieldCodecError as exc:
                            raise FieldCodecError(
                                f"record {written + 1}: {exc}") from exc
                        write_record(out, masked, rdw=rdw)
                        written += 1
                        if cycle == 0:
                            real_records += 1
                        if progress_cb and (written % _PROGRESS_EVERY == 0
                                            or written == target_count):
                            progress_cb(written, target_count)
                        if written >= target_count:
                            break
                finally:
                    if records is not None:
                        records.close()
                if not read_any:
                    raise ValueError("The input file is empty — nothing to mask.")
                cycle += 1
        os.replace(tmp_path, output_path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    if progress_cb:
        progress_cb(written, target_count)
    return RunResult(records_written=written, real_records=real_records,
                     synthetic_records=written - real_records, sample=sample)
