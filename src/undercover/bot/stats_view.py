from aiogram.types import InlineKeyboardMarkup

from undercover.bot.callbacks import StatsAction, StatsCB
from undercover.bot.keyboards import single_button
from undercover.game.stats import Champion, ChatTotals, HallOfFame, PlayerProfile
from undercover.texts import TIMES, Buttons, Stats, plural


def hall_of_fame_text(hall: HallOfFame) -> str:
    if not hall.totals.games:
        return "\n\n".join((Stats.TITLE, Stats.NO_GAMES))

    titles = "\n".join(_titles(hall)) if hall.has_titles else Stats.NO_TITLES
    return "\n\n".join((Stats.TITLE, _totals(Stats.TOTALS, hall.totals), titles))


def hall_of_fame_keyboard() -> InlineKeyboardMarkup:
    return single_button(Buttons.MY_STATS, StatsCB(action=StatsAction.ME))


def private_text(totals: ChatTotals) -> str:
    if not totals.games:
        return "\n\n".join((Stats.TITLE, Stats.NO_GAMES))
    return "\n\n".join((Stats.TITLE, _totals(Stats.PRIVATE_TOTALS, totals), Stats.PRIVATE))


def profile_text(profile: PlayerProfile | None) -> str:
    if profile is None:
        return Stats.NO_PROFILE

    lines = [
        Stats.PROFILE_TOTAL.format(games=profile.games, wins=profile.wins, rate=profile.win_rate)
    ]
    if profile.spy_games:
        lines.append(Stats.PROFILE_SPY.format(wins=profile.spy_wins, games=profile.spy_games))
    if profile.civilian_games:
        lines.append(
            Stats.PROFILE_CIVILIAN.format(wins=profile.civilian_wins, games=profile.civilian_games)
        )
    if profile.streak:
        lines.append(Stats.PROFILE_STREAK.format(value=profile.streak))
    if profile.first_outs:
        lines.append(
            Stats.PROFILE_FIRST_OUTS.format(
                value=profile.first_outs, times=plural(profile.first_outs, TIMES)
            )
        )
    return "\n".join(lines)


def _totals(template: str, totals: ChatTotals) -> str:
    return template.format(
        games=totals.games, civilian_wins=totals.civilian_wins, spy_wins=totals.spy_wins
    )


def _titles(hall: HallOfFame) -> list[str]:
    pairs = (
        (Stats.SPY_OF_THE_MONTH, hall.spy_of_the_month),
        (Stats.BEST_DETECTIVE, hall.best_detective),
        (Stats.FIRST_VICTIM, hall.first_victim),
        (Stats.LONGEST_STREAK, hall.longest_streak),
    )
    return [_title(template, holder) for template, holder in pairs if holder is not None]


def _title(template: str, champion: Champion) -> str:
    return template.format(
        name=champion.name,
        value=champion.value,
        total=champion.total,
        times=plural(champion.value, TIMES),
    )
