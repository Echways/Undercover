from collections.abc import Iterable, Mapping, Sequence
from datetime import timedelta
from typing import Final

from undercover.game.engine import MAX_NAME_LENGTH, MAX_PLAYERS, MIN_PLAYERS
from undercover.game.models import Ruleset, Winner
from undercover.game.voting import Refusal

BRAND: Final = "Undercover"

GAME_COMMAND: Final = "undercover"
STATS_COMMAND: Final = "undercover_stats"


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
    STATS_COMMAND_DESCRIPTION: Final = "Зал славы чата"


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


class Rules:
    FULL: Final = (
        f"{BRAND} — игра в шпиона.\n\n"
        "Все за столом получают одно и то же слово. Все, кроме шпиона: ему "
        "достаётся только подсказка, а само слово он выясняет по чужим "
        "ассоциациям.\n\n"
        "Ход партии:\n"
        "1. Круг высказываний — каждый называет одну ассоциацию к слову. Само "
        "слово вслух не произносят: мирный так дарит разгадку шпиону, а шпион "
        "выдаёт себя.\n"
        "2. После круга стол решает, говорить ещё или голосовать. Решает "
        "половина состава плюс один голос.\n"
        "3. На голосовании каждый живой игрок называет одного подозреваемого. "
        "Выбывает тот, кого назвали чаще; при равенстве идёт переголосование "
        "между лидерами, а второе равенство оставляет всех на местах.\n"
        "4. Выбывший сразу открывает карту.\n\n"
        "Кто победил:\n"
        "— Мирные, когда среди живых не осталось ни одного шпиона.\n"
        "— Шпионы, когда их становится не меньше, чем мирных.\n\n"
        "Режимы:\n"
        "— Классика: партия идёт, пока одна из сторон не возьмёт своё.\n"
        "— Навылет: первое голосование решает всё. Выбили мирного — партия "
        "сразу уходит шпионам.\n\n"
        "Слово приходит в личку, ходы идут в группе. Играете за одним столом? "
        "Отправьте мне /start — партия пойдёт с одного телефона."
    )


class Lobby:
    TITLE: Final = f"{BRAND} — набор в партию."
    SYNOPSIS: Final = (
        "Всем одно слово, шпиону — только подсказка. По кругу называете по одной "
        "ассоциации и ищете того, кто выкручивается."
    )
    ROSTER: Final = "В игре ({count} из {limit}):\n{names_list}"
    EMPTY_ROSTER: Final = "Пока никого."
    SUMMARY: Final = (
        "Игроков: {players_count}, из них шпионов: {spies_count}.\n"
        "Слова: {chosen_categories}.\n{ruleset}"
    )
    CALL: Final = "Жмите «Я в игре» — слово придёт в личку. Разбор правил — под кнопкой «Правила»."

    RULESET_CLASSIC: Final = "Режим: классика — партия идёт до победы одной из сторон."
    RULESET_SUDDEN_DEATH: Final = (
        "Режим: навылет — выбьете мирного первым голосованием, и партия уйдёт шпионам."
    )
    RULES_SENT: Final = "Правила ушли вам в личку."

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


class Vote:
    DIRECTION_TALLY: Final = "Ещё круг — {round}, голосуем — {vote}"
    HOT_SEAT_PROMPT: Final = "Стол решил — отметьте, кто выбывает."
    PROGRESS: Final = "Проголосовали {given} из {total}"

    ALREADY_VOTED: Final = "Ваш голос уже учтён."
    NOT_A_VOTER: Final = "Вы не в этой партии."
    IS_OUT: Final = "Вы выбыли — голосуют оставшиеся."

    TIE: Final = "Голоса разделились. Переголосуем между лидерами."
    NO_ELIMINATION: Final = "Голоса снова разделились — никто не выбывает."

    VERDICT_SPY: Final = "{name} выбывает. Это был шпион."
    VERDICT_CIVILIAN: Final = "{name} выбывает. Это был мирный житель."
    TALLY_LINE: Final = "{name} — {votes}"

    CIVILIANS_WIN: Final = "Шпионов не осталось. Победа мирных."
    SPIES_WIN: Final = "Шпионов столько же, сколько мирных. Победа шпионов."
    SPIES_WIN_MISFIRE: Final = "Первым выбыл мирный житель. В режиме навылет партия за шпионами."

    WRONG_PHASE: Final = "Голосование уже закончено."


class Timer:
    COUNTDOWN: Final = "{bar}  {seconds} с"
    SPENT: Final = "Время хода: {seconds} с"
    EXPIRED: Final = "Время вышло"


class Stats:
    TITLE: Final = f"{BRAND} — зал славы."
    TOTALS: Final = "Партий в этом чате: {games} — мирные взяли {civilian_wins}, шпионы {spy_wins}."
    PRIVATE_TOTALS: Final = (
        "Партий с этого телефона: {games} — мирные взяли {civilian_wins}, шпионы {spy_wins}."
    )
    SPY_OF_THE_MONTH: Final = "Шпион месяца: {name} — {value} из {total} за шпиона"
    BEST_DETECTIVE: Final = "Лучший сыщик: {name} — {value} из {total} за мирного"
    FIRST_VICTIM: Final = "Первая жертва: {name} — {value} {times}"
    LONGEST_STREAK: Final = "Серия побед: {name} — {value} подряд"

    NO_GAMES: Final = (
        "Здесь ещё не доигрывали партий. Зал славы откроется, когда наберётся статистика."
    )
    NO_TITLES: Final = "Титулов пока нет — сыграйте ещё несколько партий."
    PRIVATE: Final = (
        "Зал славы ведётся в группах: там бот знает, кто есть кто.\n"
        "Партии с одного телефона в личный зачёт не идут."
    )

    PROFILE_TOTAL: Final = "Партий: {games} · Побед: {wins} ({rate}%)"
    PROFILE_SPY: Final = "За шпиона: {wins} из {games}"
    PROFILE_CIVILIAN: Final = "За мирного: {wins} из {games}"
    PROFILE_STREAK: Final = "Серия побед: {value}"
    PROFILE_FIRST_OUTS: Final = "Вылетали первым: {value} {times}"
    NO_PROFILE: Final = "Вы ещё не играли в этом чате."


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
    AUTOFILL_NAMES: Final = "Придумать имена"
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
    RULESET: Final = "Режим: {name}"
    RULES: Final = "Правила"

    SHOW_CARD: Final = "Посмотреть карточку"
    NEXT_PLAYER: Final = "Дальше"
    START_DISCUSSION: Final = "Перейти к обсуждению"

    NEXT_SPEAKER: Final = "Следующий игрок"
    ANOTHER_ROUND: Final = "Ещё круг"
    SHOW_SPIES: Final = "Раскрыть карты"
    GO_TO_VOTE: Final = "Голосовать"
    BACK_TO_TALK: Final = "Вернуться к обсуждению"
    CONTINUE_TALK: Final = "Продолжить обсуждение"
    SHOW_RESULT: Final = "Итог партии"
    PLAY_AGAIN: Final = "Ещё партия"
    NEW_GAME: Final = "Новый состав"

    HALL_OF_FAME: Final = "Зал славы"
    MY_STATS: Final = "Моя статистика"


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

    VOTE_CAPTION: Final = "ГОЛОСОВАНИЕ"
    VOTE_HEADLINE: Final = "Кого выбиваем"
    VOTE_FOOTNOTE: Final = "Один голос на игрока"

    VERDICT_CAPTION: Final = "ВЫБЫВАЕТ"
    VERDICT_SPY: Final = "ШПИОН"
    VERDICT_CIVILIAN: Final = "МИРНЫЙ ЖИТЕЛЬ"

    WIN_CIVILIANS: Final = "ПОБЕДА МИРНЫХ"
    WIN_SPIES: Final = "ПОБЕДА ШПИОНОВ"

    RESULT_SPY_CAPTION: Final = "ШПИОН"
    RESULT_SPIES_CAPTION: Final = "ШПИОНЫ"
    RESULT_WORD_CAPTION: Final = "ЗАГАДАННОЕ СЛОВО"

    SUMMARY_CASE: Final = "ДЕЛО № {number}"
    SUMMARY_CASE_DATE: Final = "ДЕЛО ОТ {date}"
    SUMMARY_ROSTER: Final = "СОСТАВ"
    SUMMARY_SPY_TAG: Final = "ШПИОН"
    SUMMARY_OUT_TAG: Final = "{order}-Й ВЫЛЕТ"
    SUMMARY_OUT_TAG_SHORT: Final = "{order}-Й"
    SUMMARY_TAG_JOINER: Final = " · "
    SUMMARY_HINT_ONE: Final = "подсказка шпиону: «{hints}»"
    SUMMARY_HINT_MANY: Final = "подсказки шпионам: «{hints}»"
    SUMMARY_HINT_JOINER: Final = "», «"
    SUMMARY_METRICS_JOINER: Final = " · "
    SUMMARY_SHORT_GAME: Final = "меньше минуты"
    SUMMARY_MINUTES: Final = "{minutes} мин"
    SUMMARY_HOURS: Final = "{hours} ч {minutes:02d} мин"
    PROMO: Final = "t.me/{username}"


TIMES: Final = ("раз", "раза", "раз")
ROUNDS: Final = ("круг", "круга", "кругов")
PLAYERS: Final = ("игрок", "игрока", "игроков")

CASE_DATE_FORMAT: Final = "%d.%m.%Y"
MINUTES_IN_HOUR: Final = 60

BAR_CELLS: Final = 10
BAR_FULL: Final = "█"
BAR_EMPTY: Final = "░"


VOTE_REFUSALS: Final[Mapping[Refusal, str]] = {
    Refusal.NOT_A_VOTER: Vote.NOT_A_VOTER,
    Refusal.IS_OUT: Vote.IS_OUT,
    Refusal.ALREADY_VOTED: Vote.ALREADY_VOTED,
    Refusal.UNKNOWN_OPTION: Errors.STALE_TURN,
}

WIN_CAPTIONS: Final[Mapping[Winner, str]] = {
    Winner.CIVILIANS: Cards.WIN_CIVILIANS,
    Winner.SPIES: Cards.WIN_SPIES,
}

WIN_LINES: Final[Mapping[Winner, str]] = {
    Winner.CIVILIANS: Vote.CIVILIANS_WIN,
    Winner.SPIES: Vote.SPIES_WIN,
}

RULESET_NAMES: Final[Mapping[Ruleset, str]] = {
    Ruleset.CLASSIC: "классика",
    Ruleset.SUDDEN_DEATH: "навылет",
}

RULESET_LINES: Final[Mapping[Ruleset, str]] = {
    Ruleset.CLASSIC: Lobby.RULESET_CLASSIC,
    Ruleset.SUDDEN_DEATH: Lobby.RULESET_SUDDEN_DEATH,
}


def win_line(winner: Winner, *, misfire: bool = False) -> str:
    if winner is Winner.SPIES and misfire:
        return Vote.SPIES_WIN_MISFIRE
    return WIN_LINES[winner]


def empty_catalog_text(category_ids: Sequence[int]) -> str:
    return Errors.EMPTY_CATEGORIES if category_ids else Errors.EMPTY_CATALOG


def chosen_categories_text(titles: Iterable[str]) -> str:
    return ", ".join(titles) or Setup.ALL_CATEGORIES


def plural(count: int, forms: tuple[str, str, str]) -> str:
    if 11 <= count % 100 <= 14:
        return forms[2]
    match count % 10:
        case 1:
            return forms[0]
        case 2 | 3 | 4:
            return forms[1]
        case _:
            return forms[2]


def duration_text(spent: timedelta) -> str:
    minutes = int(spent.total_seconds()) // 60
    if minutes < 1:
        return Cards.SUMMARY_SHORT_GAME

    hours, rest = divmod(minutes, MINUTES_IN_HOUR)
    if not hours:
        return Cards.SUMMARY_MINUTES.format(minutes=minutes)
    return Cards.SUMMARY_HOURS.format(hours=hours, minutes=rest)


def countdown_line(seconds_left: int, total: int) -> str:
    filled = round(BAR_CELLS * seconds_left / total) if total > 0 else 0
    return Timer.COUNTDOWN.format(
        bar=BAR_FULL * filled + BAR_EMPTY * (BAR_CELLS - filled), seconds=seconds_left
    )
