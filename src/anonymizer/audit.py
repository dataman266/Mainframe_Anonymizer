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
