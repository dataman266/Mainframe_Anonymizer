"""Encrypted, file-based team seed vault.

Stores named masking seeds in a single encrypted file that can live on a
shared drive (point ANONYMIZER_SEEDSTORE at it, or use the path field in
the UI).  A team passphrase is stretched with PBKDF2-HMAC-SHA256
(600,000 iterations) into a Fernet key; without the passphrase the file is
unreadable.  Writes require the correct passphrase too, so one vault can
never silently mix seeds saved under different passphrases.

File format: b"MFAV1" magic + 16-byte random salt + Fernet token.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_MAGIC = b"MFAV1"
_SALT_LEN = 16
_ITERATIONS = 600_000


class SeedStoreError(Exception):
    """The seed store file is unreadable or malformed."""


class WrongPassphraseError(SeedStoreError):
    """The passphrase does not match this seed store."""


def default_store_path() -> Path:
    env = os.environ.get("ANONYMIZER_SEEDSTORE")
    if env:
        return Path(env)
    return Path.home() / ".mainframe_anonymizer" / "seedstore.enc"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=_ITERATIONS)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def load_seeds(path: Path, passphrase: str) -> dict[str, dict]:
    """Return {name: {"seed": ..., "saved": ...}}; empty if no store yet."""
    if not path.exists():
        return {}
    raw = path.read_bytes()
    if len(raw) < len(_MAGIC) + _SALT_LEN or not raw.startswith(_MAGIC):
        raise SeedStoreError(
            f"{path} is not a seed store file (or is corrupted).")
    salt = raw[len(_MAGIC):len(_MAGIC) + _SALT_LEN]
    token = raw[len(_MAGIC) + _SALT_LEN:]
    try:
        data = Fernet(_derive_key(passphrase, salt)).decrypt(token)
    except InvalidToken as exc:
        raise WrongPassphraseError(
            "The passphrase does not match this seed store.") from exc
    return json.loads(data.decode("utf-8"))


def _write(path: Path, passphrase: str, seeds: dict[str, dict]) -> None:
    salt = secrets.token_bytes(_SALT_LEN)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(
        json.dumps(seeds).encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MAGIC + salt + token)


def save_seed(path: Path, passphrase: str, name: str, seed: str) -> None:
    seeds = load_seeds(path, passphrase)
    saved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    seeds = {**seeds, name: {"seed": seed, "saved": saved}}
    _write(path, passphrase, seeds)


def remove_seed(path: Path, passphrase: str, name: str) -> None:
    seeds = load_seeds(path, passphrase)
    seeds = {k: v for k, v in seeds.items() if k != name}
    _write(path, passphrase, seeds)
