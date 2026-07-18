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


def run_anonymization(input_path: Path, output_path: Path, layout: Layout,
                      codepage: str, plans: list[FieldPlan], seed: str,
                      target_count: int, rdw: bool = False,
                      progress_cb: Callable[[int, int], None] | None = None,
                      ) -> RunResult:
    validate_plans(plans)
    written = 0
    real_records = 0
    cycle = 0
    sample: list[dict] = []
    with open(output_path, "wb") as out:
        while written < target_count:
            salt = "" if cycle == 0 else f"syn-{cycle}"
            read_any = False
            records = iter_records(input_path, layout, codepage, rdw=rdw)
            try:
                for record in records:
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
            finally:
                records.close()
            if not read_any:
                raise ValueError("The input file is empty — nothing to mask.")
            cycle += 1
    if progress_cb:
        progress_cb(written, target_count)
    return RunResult(records_written=written, real_records=real_records,
                     synthetic_records=written - real_records, sample=sample)
