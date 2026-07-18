"""Generate deterministic banking sample data files for both encodings.

Usage:  python tools/generate_samples.py
Writes samples/data/{customer,account}.{cp037,ascii}.dat
Requires Java (uses cb2xml to parse the sample copybooks).
"""
from __future__ import annotations

import sys
from pathlib import Path

from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anonymizer.codec.dispatch import encode_field          # noqa: E402
from anonymizer.copybook.cb2xml_runner import parse_copybook  # noqa: E402
from anonymizer.copybook.model import Layout                 # noqa: E402

CUSTOMERS = 50
ACCOUNTS = 120
ACCOUNT_TYPES = ["CHQ", "SAV", "TFS", "RSP"]


def customer_row(fake: Faker, i: int) -> dict[str, str]:
    dob = fake.date_of_birth(minimum_age=19, maximum_age=90)
    return {
        "CUST-ID": str(10000000 + i),
        "CUST-NAME": fake.name().upper(),
        "CUST-AGE": str(fake.random_int(19, 90)),
        "CUST-DOB": dob.strftime("%Y%m%d"),
        "CUST-STREET-ADDR": fake.street_address().upper(),
        "CUST-CITY": fake.city().upper(),
        "CUST-ZIPCODE": fake.bothify("?#?#?#").upper(),
        "CUST-SIN": fake.numerify("#########"),
        "CUST-PHONE(1)": fake.numerify("416#######"),
        "CUST-PHONE(2)": fake.numerify("905#######"),
        "CUST-EMAIL": fake.email().lower(),
        "CUST-CARD-NUM": fake.numerify("45320151########"),
        "CUST-BALANCE": str(fake.pydecimal(left_digits=7, right_digits=2)),
        "CUST-BRANCH-CODE": str(fake.random_int(1, 9999)),
    }


def account_row(fake: Faker, i: int) -> dict[str, str]:
    opened = fake.date_between(start_date="-20y", end_date="-1y")
    updated = fake.date_between(start_date="-1y", end_date="today")
    return {
        "ACCT-CUST-ID": str(10000000 + (i % CUSTOMERS)),
        "ACCT-NUMBER": fake.numerify("############"),
        "ACCT-TYPE": fake.random_element(ACCOUNT_TYPES),
        "ACCT-OPEN-DT": opened.strftime("%Y%m%d"),
        "ACCT-LAST-UPDT-DT": updated.strftime("%Y%m%d"),
        "ACCT-STATUS": fake.random_element(["A", "C", "D"]),
        "ACCT-BRANCH": str(fake.random_int(1, 9999)),
        "ACCT-BALANCE": str(fake.pydecimal(left_digits=9, right_digits=2)),
        "ACCT-INT-RATE": str(fake.pydecimal(left_digits=2, right_digits=4,
                                            positive=True)),
    }


def encode_row(layout: Layout, row: dict[str, str], codepage: str) -> bytes:
    record = bytearray(" ".encode(codepage) * layout.record_length)
    for field in layout.leaves:
        value = row.get(field.name, "0" if field.numeric else "")
        record[field.offset:field.offset + field.length] = \
            encode_field(field, value, codepage)
    return bytes(record)


def generate(copybook: str, row_fn, count: int, stem: str) -> None:
    layout = parse_copybook(ROOT / "samples" / "copybooks" / copybook)
    fake = Faker()
    fake.seed_instance(42)
    rows = [row_fn(fake, i) for i in range(count)]
    for codepage in ("cp037", "ascii"):
        out = ROOT / "samples" / "data" / f"{stem}.{codepage}.dat"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            for row in rows:
                f.write(encode_row(layout, row, codepage))
        print(f"wrote {out} ({count} records x {layout.record_length} bytes)")


if __name__ == "__main__":
    generate("customer.cpy", customer_row, CUSTOMERS, "customer")
    generate("account.cpy", account_row, ACCOUNTS, "account")
