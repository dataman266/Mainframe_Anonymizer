# Mainframe Anonymizer — Information Needed from the Team

Please provide answers/inputs for the following. These are needed to validate and configure
the mainframe file anonymizer tool.

## 1. Sample files
Provide a real COBOL copybook (.cpy) and a small matching data file (5–10 records is enough).
The data file may be de-identified/dummy — we only need it to validate layout parsing.

- Copybook file: ______
- Sample data file: ______

## 2. EBCDIC code page
Which EBCDIC code page do our mainframe files use?
(Common: cp037 US/Canada, cp1047 Latin-1 Open Systems, cp500 International)

- Answer: ______

## 3. Record format
Are the files fixed-length (RECFM=FB) or variable-length (RECFM=VB, with RDW record-length
prefixes)? If both exist, list which files are which.

- Answer: ______

## 4. Java availability
Will the machines running this tool have a Java runtime (version 8 or newer) installed, or
can one be installed? (Required by the copybook parser.)

- Answer: ______

## 5. ID checksum rules
Should masked SIN numbers pass checksum (Luhn) validation? Do any downstream ingestion
validators enforce checksums on SIN, credit card numbers (PAN), or other IDs? List any other
validated ID fields we should know about.

- Answer: ______
