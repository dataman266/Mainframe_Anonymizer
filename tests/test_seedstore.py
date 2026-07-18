from pathlib import Path

import pytest

from anonymizer.seedstore import (SeedStoreError, WrongPassphraseError,
                                  default_store_path, load_seeds, remove_seed,
                                  save_seed)


def test_save_and_load_round_trip(tmp_path):
    store = tmp_path / "seeds.enc"
    save_seed(store, "team-pass", "SIT-2026Q3", "a1b2c3d4")
    seeds = load_seeds(store, "team-pass")
    assert seeds["SIT-2026Q3"]["seed"] == "a1b2c3d4"
    assert "saved" in seeds["SIT-2026Q3"]


def test_multiple_seeds_accumulate(tmp_path):
    store = tmp_path / "seeds.enc"
    save_seed(store, "pw", "SIT", "seed-one")
    save_seed(store, "pw", "UAT", "seed-two")
    seeds = load_seeds(store, "pw")
    assert set(seeds) == {"SIT", "UAT"}
    assert seeds["UAT"]["seed"] == "seed-two"


def test_wrong_passphrase_raises(tmp_path):
    store = tmp_path / "seeds.enc"
    save_seed(store, "right", "SIT", "s")
    with pytest.raises(WrongPassphraseError):
        load_seeds(store, "wrong")


def test_saving_with_wrong_passphrase_rejected(tmp_path):
    store = tmp_path / "seeds.enc"
    save_seed(store, "right", "SIT", "s")
    with pytest.raises(WrongPassphraseError):
        save_seed(store, "wrong", "UAT", "t")
    assert set(load_seeds(store, "right")) == {"SIT"}


def test_missing_store_loads_empty(tmp_path):
    assert load_seeds(tmp_path / "nope.enc", "pw") == {}


def test_corrupt_file_raises_store_error(tmp_path):
    store = tmp_path / "seeds.enc"
    store.write_bytes(b"garbage not a vault")
    with pytest.raises(SeedStoreError):
        load_seeds(store, "pw")


def test_remove_seed(tmp_path):
    store = tmp_path / "seeds.enc"
    save_seed(store, "pw", "SIT", "one")
    save_seed(store, "pw", "UAT", "two")
    remove_seed(store, "pw", "SIT")
    assert set(load_seeds(store, "pw")) == {"UAT"}


def test_default_store_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "shared" / "vault.enc"
    monkeypatch.setenv("ANONYMIZER_SEEDSTORE", str(target))
    assert default_store_path() == target


def test_default_store_path_home(monkeypatch):
    monkeypatch.delenv("ANONYMIZER_SEEDSTORE", raising=False)
    p = default_store_path()
    assert p == Path.home() / ".mainframe_anonymizer" / "seedstore.enc"
