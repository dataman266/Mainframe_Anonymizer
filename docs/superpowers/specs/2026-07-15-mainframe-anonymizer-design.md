# Mainframe File Anonymizer — Design Spec

**Date:** 2026-07-15
**Status:** Approved by user (brainstorming session)

## Purpose

A local Python application, operated through a Streamlit UI, that masks/anonymizes PII and PCI
data in mainframe files (EBCDIC or ASCII flat files) using their COBOL copybook, producing
output files that are byte-layout-identical to the input so they can be used for ingestion
testing in lower environments. The UI must be operable by non-technical staff.

## Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Record count > input size | Synthesize extra records following copybook layout and observed field patterns |
| Masking consistency | Deterministic: HMAC-SHA256(project seed, value) — same input value → same masked value across runs and files |
| Field selection | All copybook fields pre-selected for masking with type-appropriate rules; user can untick or change rule per field |
| Copybook scope | COMP-3, COMP (binary), zoned decimal, alphanumeric, OCCURS (fixed), REDEFINES, OCCURS DEPENDING ON |
| Parsing foundation | JVM bridge: bundled **cb2xml** jar parses copybook → XML via one-shot subprocess; all data-path work stays in Python |
| Output format | Byte-exact preservation of input encoding and record layout (EBCDIC in → EBCDIC out) |
| Privacy | 100% local processing; no network calls; session temp files deleted on session end; seed never written to output |

## Constraints

- Requires a Java runtime (8+) on the user's machine for cb2xml. The app detects its absence
  and shows a plain-language install prompt instead of crashing.
- Output record count: 5 to 1,000,000.
- Must stream: 1M records must never be fully loaded into RAM.

## Architecture

```
copybook.cpy ──> cb2xml.jar (bundled, one-shot subprocess) ──> XML ──> LayoutModel
                                                                          │
data file ──> RecordReader (fixed / ODO-variable / optional RDW) ─────────┤
                                                                          ▼
              Codec layer (EBCDIC cp037/cp1047, COMP-3, COMP, zoned, alphanum)
                                                                          ▼
              Classifier (auto-assigns rule per field, ALL pre-selected) ──> UI review grid
                                                                          ▼
              Masking engine (deterministic, format-preserving)
              + Synthesizer (extra records beyond input count)
                                                                          ▼
              RecordWriter (re-encodes byte-exact) ──> output file + audit report
```

## Components

| Module | Responsibility |
|---|---|
| `copybook/` | Run cb2xml (locate `java`, invoke bundled jar), map its XML to an immutable field tree: name, level, offset, length, PIC, usage, OCCURS count, REDEFINES target, ODO counter link. Flattening and offset resolution. |
| `codec/` | Encode/decode per COBOL usage: EBCDIC/ASCII text, COMP-3 packed decimal, COMP binary, zoned decimal. Every codec round-trips byte-exact. |
| `engine/` | Streaming record reader/writer in chunks (~10k records). Fixed-length, ODO-driven variable length, optional RDW (RECFM=VB) toggle. Record-length sanity checks (file size ÷ record length). |
| `masking/` | Rule registry + deterministic value mapper. Rules: name substitution (seeded Faker), digit replacement preserving length/format (SIN; PAN with Luhn re-validation), date jitter, address swap, generic alphanumeric scramble, numeric noise, keep-intact. Determinism via HMAC-SHA256(seed, field-value). |
| `synth/` | Generate synthetic records when requested count exceeds input count, sampling each field's observed value patterns from the (masked) real data. |
| `app/` | Streamlit 5-step wizard (see UI section). |
| `audit/` | Downloadable run report: fields, rules applied, record counts (real vs synthetic), seed fingerprint (hash prefix, never the seed itself). |

### REDEFINES policy

Mask through the **primary** (first) definition. Redefining views are displayed read-only in
the UI and inherit the masked bytes.

### Protected fields

ODO counter fields and detected record-type/filler fields are auto-flagged **keep intact**
(user can override), because masking them breaks downstream parsing.

## UI — 5-step wizard (non-technical audience)

Progress stepper across the top; plain-language copy throughout; no COBOL jargon.

1. **Upload** — two drop zones (data file, copybook). Encoding auto-detect with EBCDIC/ASCII
   override toggle. Instant validation feedback on both files.
2. **Fields** — parsed field table: name, plain-words type ("Packed number, 7 digits"),
   position, sample value from the first record.
3. **Masking rules** — interactive grid (`st.data_editor`): every field pre-ticked with a
   suggested rule; user unticks or changes rule via dropdown; live example column shows a
   masked sample value.
4. **Generate** — record-count input (5–1,000,000) with a note when synthesis will kick in;
   seed field (pre-filled, changeable); progress bar during generation.
5. **Preview & download** — before/after table of the first 10 records (rows: Field | Before |
   After), download buttons for the output file and the audit report.

## Error handling

- Copybook parse errors surfaced with line numbers and plain-language hints.
- File-size/record-length mismatch produces actionable suggestions (wrong encoding? RDW
  present? wrong copybook?).
- Missing Java runtime → guided install message.
- All errors keep the user inside the wizard with a clear next action; no stack traces in the UI.

## Testing

pytest, ≥80% coverage:

- Round-trip encode/decode tests per codec.
- Determinism and format-preservation tests per masking rule (incl. Luhn validity for PAN).
- Parser mapping tests against real-world copybook fixtures: OCCURS, REDEFINES, ODO, COMP-3.
- Streaming reader tests for fixed, ODO-variable, and RDW record formats.
- Golden-file integration test: sample EBCDIC file + copybook → byte-exact expected output.

## Out of scope

- Multi-record-type files (multiple copybooks per file / record-type dispatch).
- Direct mainframe connectivity (FTP/z/OS datasets); files arrive via upload only.
- User management, authentication, multi-tenancy.
