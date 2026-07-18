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
- **Private**: no network calls; the seed is never written to any output;
  temporary files are cleaned up automatically.

## Copybook support
COMP-3 (packed), COMP (binary), zoned decimal, OCCURS, REDEFINES (masked via
the primary view), and OCCURS DEPENDING ON (as the last field in the record).
Fixed-length (FB) and variable-length (VB/RDW) files.

## Tests
    py -3.10 -m pytest --cov=anonymizer --cov-fail-under=80
