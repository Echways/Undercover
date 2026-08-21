from random import Random, SystemRandom


def secure_rng() -> Random:
    return SystemRandom()
