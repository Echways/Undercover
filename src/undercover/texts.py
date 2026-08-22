from collections.abc import Sequence
from typing import Final

from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS, MIN_PLAYERS

BRAND: Final = "Undercover"

GAME_COMMAND: Final = "undercover"


class Start:
    GREETING: Final = (
        f"{BRAND} — игра в шпиона.\n\n"
        "Все за столом получают одно и то же слово. Все, кроме шпиона, — ему "
        "достаётся лишь подсказка. Дальше по кругу: одна ассоциация от каждого, "
        "и вы ищете того, кто выкручивается.\n\n"
        "Здесь партия идёт с одного телефона: он передаётся из рук в руки, "
        "карточки открывает ведущий.\n\n"
        "Играете не за одним столом? Добавьте бота в группу и отправьте там "
        f"/{GAME_COMMAND} — слово придёт каждому в личку.\n\n"
        "Соберём состав."
    )
    COMMAND_DESCRIPTION: Final = "Новая партия"
    GAME_COMMAND_DESCRIPTION: Final = "Партия в группе"


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
    ASK_CATEGORIES: Final = (
        "Откуда брать слово?\n\n"
        "Отметьте категории — можно несколько. Без отметок сыграем по всему "
        "словарю.\n\n"
        "Сейчас: {chosen_categories}"
    )
    CONFIRM_START: Final = (
        "Состав собран.\n\n"
        "Игроков: {players_count}, из них шпионов: {spies_count}.\n"
        "Слова: {chosen_categories}.\n"
        "Порядок раздачи карточек:\n{names_list}"
    )

    ALL_CATEGORIES: Final = "весь словарь"
    CATEGORY_CHOSEN: Final = "• {item[title]}"
    CATEGORY_FREE: Final = "{item[title]}"

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


class Lobby:
    TITLE: Final = f"{BRAND} — набор в партию."
    ROSTER: Final = "В игре ({count} из {limit}):\n{names_list}"
    EMPTY_ROSTER: Final = "Пока никого."
    SUMMARY: Final = (
        "Игроков: {players_count}, из них шпионов: {spies_count}.\nСлова: {chosen_categories}."
    )
    CALL: Final = "Жмите «Я в игре» — слово придёт в личку."

    PICK_CATEGORIES: Final = (
        "Откуда брать слово?\n\nОтметьте категории — можно несколько. Без отметок "
        "сыграем по всему словарю."
    )
    CATEGORY_CHOSEN: Final = "• {title}"
    CATEGORY_FREE: Final = "{title}"

    ALREADY_IN: Final = "Вы уже в составе."
    NOT_IN: Final = "Вас нет в составе."
    DM_WELCOME: Final = "Вы в составе. Слово придёт сюда, как только ведущий начнёт партию."
    STARTED: Final = "Партия началась. Роли ушли в личку."
    DELIVERY_FAILED: Final = "Роли дошли не всем — партия не началась."
    OPEN_DM: Final = (
        "Не получилось написать в личку: {names}.\nОткройте бота, нажмите «Старт» — "
        "и возвращайтесь в состав."
    )


class Reveal:
    TURN_CAPTION: Final = "Ход {position} из {total}. Передайте телефон: {name}"
    VIEWED_CAPTION: Final = "{name}: карточка открыта. Запомните её и передайте телефон дальше."
    LAST_VIEWED_CAPTION: Final = "{name}: карточка открыта. Все посмотрели — время обсуждать."

    WRONG_PHASE: Final = "Раздача карточек уже закончена."
    ALREADY_VIEWED: Final = "Эта карточка уже открыта."
    NOT_VIEWED_YET: Final = "Сначала откройте карточку."


class Delivery:
    ROLE_CAPTION: Final = "Ваша карточка. Запомните её и возвращайтесь в группу."


class Discussion:
    ROUND_PREFIX: Final = "Круг {round}. "
    TALK_CAPTION: Final = "Ход {position} из {total}. Говорит: {name}"
    LAST_TALK_CAPTION: Final = "Последним говорит {name}. Дальше — ищите шпиона."

    SPY_TITLE_ONE: Final = "Шпион"
    SPY_TITLE_MANY: Final = "Шпионы"
    FINAL_CAPTION: Final = "{title}: {spies}\nЗагаданное слово: {word}"

    WRONG_PHASE: Final = "Обсуждение уже закончено."
    GAME_IS_ON: Final = "Партия ещё идёт — сначала доиграйте её."
    ALL_SPOKE: Final = "Высказались все — время искать шпиона."


class Timer:
    COUNTDOWN: Final = "{bar}  {seconds} с"
    SPENT: Final = "Время хода: {seconds} с"
    EXPIRED: Final = "Время вышло"


class Errors:
    SESSION_NOT_FOUND: Final = "Партия не найдена — похоже, она уже закончилась."
    NOT_HOST: Final = "Сейчас эта кнопка не ваша — её нажимает ведущий."
    LOBBY_CLOSED: Final = f"Это лобби уже закрыто. Отправьте /{GAME_COMMAND}, чтобы собрать новое."
    GAME_IN_CHAT: Final = "В этом чате уже идёт партия — сначала доиграйте её."
    GROUP_ONLY: Final = f"Так играют в группе: добавьте бота туда и отправьте /{GAME_COMMAND}."
    STALE_TURN: Final = "Сейчас очередь другого игрока — смотрите на экран партии."
    BROKEN_SESSION: Final = "Партия повреждена. Начните новую."
    EMPTY_CATALOG: Final = (
        "Словарь игры пуст — загадать нечего. Сообщите администратору бота; "
        "состав никуда не денется."
    )
    EMPTY_CATEGORIES: Final = (
        "В выбранных категориях не осталось слов. Отметьте другие — состав никуда не денется."
    )
    UNEXPECTED: Final = "Что-то пошло не так. Попробуйте ещё раз — партия никуда не делась."
    STALE_BUTTON: Final = (
        "Эта кнопка осталась от прошлой партии. Отправьте /start, чтобы начать новую."
    )
    TOO_FAST: Final = "Слишком быстро — подождите мгновение."


class Buttons:
    UNDO_NAME: Final = "Убрать последнее"
    CATEGORIES_DONE: Final = "Готово"
    CHANGE_CATEGORIES: Final = "Категории"
    PLAY: Final = "Начать партию"
    RESTART: Final = "Собрать заново"

    JOIN_LOBBY: Final = "Я в игре"
    LEAVE_LOBBY: Final = "Выйти из состава"
    SPIES_COUNT: Final = "Шпионов: {count}"
    TURN_LIMIT: Final = "Ход: {seconds} с"
    TURN_OFF: Final = "Ход: без таймера"

    SHOW_CARD: Final = "Посмотреть карточку"
    NEXT_PLAYER: Final = "Дальше"
    START_DISCUSSION: Final = "Перейти к обсуждению"

    NEXT_SPEAKER: Final = "Следующий игрок"
    ANOTHER_ROUND: Final = "Ещё круг"
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


BAR_CELLS: Final = 10
BAR_FULL: Final = "█"
BAR_EMPTY: Final = "░"


def empty_catalog_text(category_ids: Sequence[int]) -> str:
    return Errors.EMPTY_CATEGORIES if category_ids else Errors.EMPTY_CATALOG


def countdown_line(seconds_left: int, total: int) -> str:
    filled = round(BAR_CELLS * seconds_left / total) if total > 0 else 0
    return Timer.COUNTDOWN.format(
        bar=BAR_FULL * filled + BAR_EMPTY * (BAR_CELLS - filled), seconds=seconds_left
    )
