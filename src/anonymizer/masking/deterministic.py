"""Deterministic per-value random streams via HMAC-SHA256."""
from __future__ import annotations

import hashlib
import hmac
import random


def value_rng(seed: str, rule: str, value: str, salt: str = "") -> random.Random:
    digest = hmac.new(seed.encode("utf-8"),
                      f"{rule}|{salt}|{value}".encode("utf-8"),
                      hashlib.sha256).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
