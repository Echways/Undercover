import random
from random import Random

from undercover.game.engine import secure_rng


def test_is_a_drop_in_replacement_for_random() -> None:
    assert isinstance(secure_rng(), Random)


def test_is_not_reproducible_from_a_seed() -> None:
    first, second = secure_rng(), secure_rng()
    first.seed(42)
    second.seed(42)

    assert [first.getrandbits(64) for _ in range(5)] != [second.getrandbits(64) for _ in range(5)]


def test_does_not_share_state_with_the_global_random() -> None:
    random.seed(0)
    first = secure_rng().getrandbits(64)
    random.seed(0)
    second = secure_rng().getrandbits(64)

    assert first != second
