"""Format-preserving, deterministic masking rules.

Every rule has signature (value, field, seed, salt) -> str and must return
a value that encode_field() can write back into the same field.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from faker import Faker

from anonymizer.copybook.model import Field
from anonymizer.masking.deterministic import value_rng
from anonymizer.masking.luhn import make_luhn_valid

_fake = Faker()
_MIN_YEAR = 1900


def _rng(rule: str, value: str, seed: str, salt: str):
    return value_rng(seed, rule, value, salt)


def _faker_for(rule: str, value: str, seed: str, salt: str) -> Faker:
    _fake.seed_instance(_rng(rule, value, seed, salt).getrandbits(32))
    return _fake


def rule_keep(value: str, field: Field, seed: str, salt: str) -> str:
    return value


def rule_person_name(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("person_name", value, seed, salt).name().upper()[:field.length]


def rule_street_address(value: str, field: Field, seed: str, salt: str) -> str:
    fake = _faker_for("street_address", value, seed, salt)
    return fake.street_address().upper().replace("\n", " ")[:field.length]


def rule_city(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("city", value, seed, salt).city().upper()[:field.length]


def rule_email(value: str, field: Field, seed: str, salt: str) -> str:
    return _faker_for("email", value, seed, salt).email().lower()[:field.length]


def rule_digits(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("digits", value, seed, salt)
    return "".join(str(rng.randint(0, 9)) if c.isdigit() else c for c in value)


def rule_sin(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("sin", value, seed, salt)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
    candidate = make_luhn_valid(digits)
    if candidate == value:                      # astronomically unlikely
        candidate = make_luhn_valid("1" + digits[1:])
    return candidate


def rule_credit_card(value: str, field: Field, seed: str, salt: str) -> str:
    n = len(value.strip()) or field.total_digits or 16
    rng = _rng("credit_card", value, seed, salt)
    digits = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9))
                                              for _ in range(n - 1))
    candidate = make_luhn_valid(digits)
    if candidate == value.strip():
        candidate = make_luhn_valid(str((int(digits[0]) % 9) + 1) + digits[1:])
    return candidate


def rule_scramble(value: str, field: Field, seed: str, salt: str) -> str:
    rng = _rng("scramble", value, seed, salt)
    out = []
    for c in value:
        if c.isdigit():
            out.append(str(rng.randint(0, 9)))
        elif c.isupper():
            out.append(chr(rng.randint(ord("A"), ord("Z"))))
        elif c.islower():
            out.append(chr(rng.randint(ord("a"), ord("z"))))
        else:
            out.append(c)
    return "".join(out)


def rule_date_jitter(value: str, field: Field, seed: str, salt: str) -> str:
    v = value.strip()
    try:
        date = datetime.strptime(v, "%Y%m%d")
    except ValueError:
        return rule_digits(value, field, seed, salt)
    rng = _rng("date_jitter", value, seed, salt)
    days = rng.randint(-365, 365) or 1
    shifted = date + timedelta(days=days)
    if shifted.year < _MIN_YEAR:
        shifted = date + timedelta(days=abs(days))
    return shifted.strftime("%Y%m%d")


def rule_numeric_noise(value: str, field: Field, seed: str, salt: str) -> str:
    d = Decimal(value)
    rng = _rng("numeric_noise", value, seed, salt)
    factor = Decimal(rng.randint(80, 121)) / 100
    if factor == 1:
        factor = Decimal("1.05")
    result = (d * factor).quantize(Decimal(1).scaleb(-field.decimals))
    cap = Decimal(10) ** (field.total_digits - field.decimals)
    if abs(result) >= cap:
        result = (cap - Decimal(1).scaleb(-field.decimals)).copy_sign(result)
    if result == d:
        result = d + Decimal(1).scaleb(-field.decimals)
    return str(result)


RULES: dict[str, tuple[str, object]] = {
    "keep":           ("Keep unchanged", rule_keep),
    "person_name":    ("Fake person name", rule_person_name),
    "sin":            ("New SIN (checksum valid)", rule_sin),
    "credit_card":    ("New card number (checksum valid)", rule_credit_card),
    "digits":         ("Replace digits", rule_digits),
    "street_address": ("Fake street address", rule_street_address),
    "city":           ("Fake city", rule_city),
    "email":          ("Fake email", rule_email),
    "scramble":       ("Scramble letters/digits", rule_scramble),
    "date_jitter":    ("Shift date up to a year", rule_date_jitter),
    "numeric_noise":  ("Adjust amount up to 20%", rule_numeric_noise),
}


def apply_rule(rule_name: str, value: str, field: Field,
               seed: str, salt: str = "") -> str:
    _, fn = RULES[rule_name]
    return fn(value, field, seed, salt)


def rule_label(rule_name: str) -> str:
    return RULES[rule_name][0]
