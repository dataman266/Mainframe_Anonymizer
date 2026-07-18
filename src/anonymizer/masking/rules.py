"""Format-preserving, deterministic masking rules.

Every rule has signature (value, field, seed, salt) -> str and must return
a value that encode_field() can write back into the same field.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from faker import Faker

from anonymizer.copybook.model import Field
from anonymizer.masking.deterministic import value_rng
from anonymizer.masking.luhn import make_luhn_valid

# Module-level Faker instance reused across calls and reseeded per value via
# seed_instance() for determinism. This assumes single-threaded use: sharing
# one Faker instance across threads and reseeding it is not thread-safe.
_fake = Faker()
_MIN_YEAR = 1900

TEXT_ONLY_RULES = frozenset({"person_name", "street_address", "city", "email"})


def is_rule_compatible(rule_name: str, field: Field) -> bool:
    """Whether a rule can sensibly be applied to a field's declared type.

    Text-generating rules (names, addresses, cities, emails) produce
    non-numeric output and must not be offered for numeric fields, since
    encode_field() would fail to pack the result back into the field.
    """
    return not (field.numeric and rule_name in TEXT_ONLY_RULES)


def _rng(rule: str, value: str, seed: str, salt: str) -> random.Random:
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
    n = field.total_digits or 9
    rng = _rng("sin", value, seed, salt)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(n))
    candidate = make_luhn_valid(digits)
    if candidate == value:                      # astronomically unlikely
        bumped = str((int(digits[0]) + 1) % 10)
        candidate = make_luhn_valid(bumped + digits[1:])
    return candidate


def rule_credit_card(value: str, field: Field, seed: str, salt: str) -> str:
    n = sum(c.isdigit() for c in value) or field.total_digits or 16
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
    try:
        shifted = date + timedelta(days=days)
    except OverflowError:
        # Shifting by `days` pushed past datetime's year 1 / 9999 range
        # (e.g. sentinel dates like 99991231 or 00010101). Flip direction:
        # subtracting `days` moves the opposite way regardless of its sign.
        shifted = date - timedelta(days=days)
    if shifted.year < _MIN_YEAR:
        shifted = date + timedelta(days=abs(days))
    return shifted.strftime("%Y%m%d")


def rule_numeric_noise(value: str, field: Field, seed: str, salt: str) -> str:
    d = Decimal(value)
    rng = _rng("numeric_noise", value, seed, salt)
    factor = Decimal(rng.randint(80, 121)) / 100
    if factor == 1:
        factor = Decimal("1.05")
    epsilon = Decimal(1).scaleb(-field.decimals)
    cap = Decimal(10) ** (field.total_digits - field.decimals)
    result = (d * factor).quantize(epsilon, rounding=ROUND_HALF_UP)
    if abs(result) >= cap:
        result = (cap - epsilon).copy_sign(result)
    if result == d:
        result = d + epsilon
        # d itself may already sit at the field's max magnitude (e.g.
        # 999999999.99 in S9(9)V99): the anti-noop bump above would then
        # push past the cap and blow up encode_field(). Bump toward zero
        # instead when that happens.
        if abs(result) >= cap:
            result = d - epsilon
    return str(result)


RULES: dict[str, tuple[str, Callable[[str, Field, str, str], str]]] = {
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
