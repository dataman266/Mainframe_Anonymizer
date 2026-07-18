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

Any error raised while advancing to the next record (a corrupt field
decode, a malformed/truncated record) is re-raised with a "record N: "
prefix so failures deep into a large run are locatable without re-running
with extra instrumentation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from anonymizer.codec.dispatch import FieldCodecError, decode_field, encode_field
from anonymizer.copybook.model import Field, Layout
from anonymizer.engine.reader import TruncatedRecordError, iter_records
from anonymizer.engine.writer import write_record
from anonymizer.masking.classifier import suggest_rule
from anonymizer.masking.rules import apply_rule, is_rule_compatible

SAMPLE_RECORDS = 10
_PROGRESS_EVERY = 500

# Cap on how much raw input we hold in memory to serve synthesis cycles
# (cycles beyond the first, when target_count exceeds the input's record
# count) without re-opening and re-reading the file. Small inputs — the
# case where many cycles are needed to reach a large target_count — always
# fit comfortably under this budget. Oversized inputs need relatively few
# cycles to reach any given target, so falling back to re-reading the file
# for those is cheap; it is not worth holding a huge file fully in memory
# just to save a handful of re-reads.
_CACHE_BUDGET_BYTES = 64 * 1024 * 1024


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
    if target_count < 1:
        raise ValueError("target_count must be at least 1")
    validate_plans(plans)

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    # Cache of cycle 0's raw records, for reuse by later synthesis cycles.
    # Stays a list while cycle 0 is under budget; flips to None permanently
    # (for the rest of this run) the moment it would exceed the budget, at
    # which point later cycles fall back to re-reading the input file.
    cache: list[bytes] | None = []
    cached_bytes = 0

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
                source: Iterator[bytes] = iter(cache) if using_cache else records
                try:
                    while True:
                        try:
                            record = next(source)
                        except StopIteration:
                            break
                        except TruncatedRecordError as exc:
                            raise TruncatedRecordError(
                                f"record {written + 1}: {exc}") from exc
                        read_any = True
                        if cycle == 0 and cache is not None:
                            cached_bytes += len(record)
                            if cached_bytes > _CACHE_BUDGET_BYTES:
                                cache = None
                            else:
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
