from typing import Final

from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS, MIN_PLAYERS

BRAND: Final = "Undercover"


class Start:
    GREETING: Final = (
        f"{BRAND} — игра в шпиона на одном телефоне.\n\n"
        "Все за столом получают одно и то же слово. Все, кроме шпиона, — ему "
        "достаётся лишь подсказка. Дальше по кругу: одна ассоциация от каждого, "
        "и вы ищете того, кто выкручивается.\n\n"
        "Телефон передаётся из рук в руки, карточки открывает ведущий.\n\n"
        "Соберём состав."
    )
    COMMAND_DESCRIPTION: Final = "Новая партия"


class Setup:
    ASK_PLAYERS_COUNT: Final = (
        f"{BRAND} — новая партия.\n\n"
        f"Сколько игроков за столом? Пришлите число от {MIN_PLAYERS} до {MAX_PLAYERS}."
    )
    ASK_SPIES_COUNT: Final = (
        "Игроков за столом: {players_count}.\n\n"
        "Сколько среди них шпионов? Число от 1 до {max_spies}.\n"
        "Классика — один шпион на компанию."
    )
    ASK_PLAYER_NAMES: Final = (
        "Имена — по одному в сообщении.\n"
        "Порядок ввода тот же, в котором телефон пойдёт по кругу.\n\n"
        "Введено {entered} из {players_count}:\n{names_list}"
    )
    CONFIRM_START: Final = (
        "Состав собран.\n\n"
        "Игроков: {players_count}, из них шпионов: {spies_count}.\n"
        "Порядок раздачи карточек:\n{names_list}"
    )

    NO_NAMES_YET: Final = "пока пусто"
    ERROR_PREFIX: Final = "{error}"

    NOT_A_NUMBER: Final = "Это не число. Пришлите цифрами — например, 6."
    BAD_PLAYERS_COUNT: Final = (
        f"Игроков должно быть от {MIN_PLAYERS} до {MAX_PLAYERS}: вдвоём партия уже "
        "складывается, а больше шестнадцати телефон не обойдёт."
    )
    BAD_SPIES_COUNT: Final = (
        "Шпионов на {players_count} игроков — от 1 до {max_spies}: мирные должны "
        "остаться в большинстве, иначе искать некого."
    )
    EMPTY_NAME: Final = "Имя пустое. Напишите, как называть игрока."
    TOO_LONG_NAME: Final = (
        f"Имя длиннее {MAX_NAME_LENGTH} символов не поместится на карточку. Сократите."
    )
    DUPLICATE_NAME: Final = (
        "«{name}» уже в составе. Двух одинаковых имён на карточках не различить — "
        "добавьте фамилию или прозвище."
    )
    BROKEN_DRAFT: Final = "Настройки партии потерялись. Соберём состав заново."


class Reveal:
    TURN_CAPTION: Final = "Ход {position} из {total}. Передайте телефон: {name}"
    VIEWED_CAPTION: Final = "{name}: карточка открыта. Запомните её и передайте телефон дальше."
    LAST_VIEWED_CAPTION: Final = "{name}: карточка открыта. Все посмотрели — время обсуждать."

    WRONG_PHASE: Final = "Раздача карточек уже закончена."
    ALREADY_VIEWED: Final = "Эта карточка уже открыта."
    NOT_VIEWED_YET: Final = "Сначала откройте карточку."


class Discussion:
    TALK_CAPTION: Final = "Ход {position} из {total}. Говорит: {name}"
    LAST_TALK_CAPTION: Final = "Последним говорит {name}. Дальше — ищите шпиона."

    SPY_TITLE_ONE: Final = "Шпион"
    SPY_TITLE_MANY: Final = "Шпионы"
    FINAL_CAPTION: Final = "{title}: {spies}\nЗагаданное слово: {word}"

    WRONG_PHASE: Final = "Обсуждение уже закончено."
    GAME_IS_ON: Final = "Партия ещё идёт — сначала доиграйте её."
    ALL_SPOKE: Final = "Высказались все — время искать шпиона."


class Errors:
    SESSION_NOT_FOUND: Final = "Партия не найдена — похоже, она уже закончилась."
    NOT_HOST: Final = "Партия идёт с телефона ведущего — кнопки нажимает только он."
    STALE_TURN: Final = "Сейчас очередь другого игрока — смотрите на экран партии."
    BROKEN_SESSION: Final = "Партия повреждена. Начните новую."
    EMPTY_CATALOG: Final = (
        "Словарь игры пуст — загадать нечего. Сообщите администратору бота; "
        "состав никуда не денется."
    )
    UNEXPECTED: Final = "Что-то пошло не так. Попробуйте ещё раз — партия никуда не делась."
    STALE_BUTTON: Final = (
        "Эта кнопка осталась от прошлой партии. Отправьте /start, чтобы начать новую."
    )
    TOO_FAST: Final = "Слишком быстро — подождите мгновение."


class Buttons:
    UNDO_NAME: Final = "Убрать последнее"
    PLAY: Final = "Начать партию"
    RESTART: Final = "Собрать заново"

    SHOW_CARD: Final = "Посмотреть карточку"
    NEXT_PLAYER: Final = "Дальше"
    START_DISCUSSION: Final = "Перейти к обсуждению"

    NEXT_SPEAKER: Final = "Следующий игрок"
    SHOW_SPIES: Final = "Раскрыть карты"
    PLAY_AGAIN: Final = "Ещё партия"
    NEW_GAME: Final = "Новый состав"


class Cards:
    HIDDEN_CAPTION: Final = "ПЕРЕДАЙТЕ ТЕЛЕФОН"
    HIDDEN_FOOTNOTE: Final = "Остальные отворачиваются"

    CIVILIAN_CAPTION: Final = "ВАШЕ СЛОВО"
    CIVILIAN_FOOTNOTE: Final = "Не произносите его вслух"

    SPY_PLATE: Final = BRAND.upper()
    SPY_CAPTION: Final = "ВАША ПОДСКАЗКА"
    SPY_FOOTNOTE: Final = "Слова вы не знаете — подыгрывайте"

    SPEAKER_CAPTION: Final = "СЕЙЧАС ГОВОРИТ"
    SPEAKER_FOOTNOTE: Final = "Одна ассоциация вслух — и передайте телефон"

    RESULT_SPY_CAPTION: Final = "ШПИОН"
    RESULT_SPIES_CAPTION: Final = "ШПИОНЫ"
    RESULT_WORD_CAPTION: Final = "ЗАГАДАННОЕ СЛОВО"
