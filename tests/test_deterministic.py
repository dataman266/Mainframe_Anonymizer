from anonymizer.masking.deterministic import value_rng


def test_same_inputs_same_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454286")
    assert [a.randint(0, 9) for _ in range(10)] == [b.randint(0, 9) for _ in range(10)]


def test_different_value_different_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454287")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]


def test_different_seed_different_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed2", "sin", "046454286")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]


def test_salt_changes_stream():
    a = value_rng("seed1", "sin", "046454286")
    b = value_rng("seed1", "sin", "046454286", salt="syn-1")
    assert [a.randint(0, 9) for _ in range(10)] != [b.randint(0, 9) for _ in range(10)]
