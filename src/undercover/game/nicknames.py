from collections.abc import Iterable
from random import Random
from typing import Final

NICKNAMES: Final = (
    "Аксолотль",
    "Барсук",
    "Бобр",
    "Броненосец",
    "Выдра",
    "Гепард",
    "Голубь",
    "Дельфин",
    "Ёж",
    "Енот",
    "Жираф",
    "Игуана",
    "Кабан",
    "Кит",
    "Койот",
    "Кролик",
    "Ламантин",
    "Лемур",
    "Лисица",
    "Мангуст",
    "Морж",
    "Носорог",
    "Опоссум",
    "Осьминог",
    "Панголин",
    "Пингвин",
    "Рысь",
    "Сурикат",
    "Тапир",
    "Тукан",
    "Фламинго",
    "Хамелеон",
)


def pick_nicknames(count: int, taken: Iterable[str], rng: Random) -> tuple[str, ...]:
    used = {name.casefold() for name in taken}
    free = [nickname for nickname in NICKNAMES if nickname.casefold() not in used]
    return tuple(rng.sample(free, count))
