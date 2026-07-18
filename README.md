# Mainframe File Anonymizer

Mask PII/PCI in mainframe files (EBCDIC or ASCII) using their COBOL copybook,
entirely on your own machine. Output files keep the exact byte layout of the
input so downstream ingestion jobs run unchanged.

## Requirements
- Python 3.10+
- Java 8+ on PATH (used only to parse the copybook)

## Setup
Run each command on its own line (PowerShell 5.1 does not support `&&`).
If your machine has more than one Python, replace `python` with the launcher
for a 3.10+ install, e.g. `py -3.10`:

    python -m pip install -r requirements.txt
    python -m pip install -e .

## Run
    python -m streamlit run app.py

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
- **Private**: no network calls; the seed is never written to any output;
  temporary files are cleaned up automatically.

## The masking seed
The seed (step 4 of the wizard) is the secret key that drives how every value
is disguised. The same seed + the same input value always produces the same
masked value — across files and across runs.

- **Reuse one seed for files that must join.** Customer and account files
  masked with the same seed turn the same `customer_id` into the same masked
  ID in both files, so downstream joins keep working. Different seeds break
  that link.
- **Keep the seed to reproduce a dataset.** Re-running with the same seed
  regenerates the exact same masked output; a new seed gives a completely
  different (equally valid) one.
- **Treat it like a password.** The seed is the only thing that ties masked
  values back to a masking run, so store it in a password vault and never
  ship it alongside the masked data. The audit report records only a short
  fingerprint of the seed, never the seed itself.

The wizard pre-fills a random seed. For real use, pick one seed per test-data
universe (e.g. per environment or release cycle) and reuse it for every
related file. Step 4's **Team seed vault** panel stores named seeds in an
encrypted file (protect it with a team passphrase; place it on a shared drive
or set `ANONYMIZER_SEEDSTORE`) so teammates can pick the right seed by name
instead of passing secrets around.

For the full details — cross-file joins, staggered file deliveries, what can
silently break consistency, seed management, and security properties — see
[docs/seed-masking.md](docs/seed-masking.md).

## The output file (`masked_output.dat`)
The download in step 5 is a mainframe data file, not a CSV. It preserves the
input's exact byte layout: same record length, same field positions, same
encoding (EBCDIC in, EBCDIC out), same COMP-3/COMP representations. Only the
contents of the fields you chose to mask are different. Feed it to your
downstream ingestion jobs with the same copybook as the original file — no
conversion needed. (An EBCDIC output will look like gibberish in a text
editor; that is expected. Read it with the copybook.)

Alongside it you can download `audit_report.md`, which lists every field,
the rule applied to it, the record counts (real vs synthesized), and the
seed fingerprint.

## Copybook support
COMP-3 (packed), COMP (binary), zoned decimal, OCCURS, REDEFINES (masked via
the primary view), and OCCURS DEPENDING ON (as the last field in the record).
Fixed-length (FB) and variable-length (VB/RDW) files.

## Tests
    python -m pytest --cov=anonymizer --cov-fail-under=80
