from undercover.bot.callbacks import (
    DIRECTIONS,
    FinalAction,
    FinalCB,
    LobbyAction,
    LobbyCB,
    PickCB,
    RevealAction,
    RevealCB,
    StatsAction,
    StatsCB,
    TalkAction,
    TalkCB,
    VoteAction,
    VoteCB,
)
from undercover.game.models import Direction


def test_every_callback_keeps_its_prefix() -> None:
    packed = (
        RevealCB(action=RevealAction.SHOW, session_id="s", order_index=0).pack(),
        TalkCB(action=TalkAction.NEXT, session_id="s", cursor=0).pack(),
        VoteCB(action=VoteAction.BACK, session_id="s").pack(),
        PickCB(session_id="s", order_index=0).pack(),
        FinalCB(action=FinalAction.AGAIN, session_id="s").pack(),
        LobbyCB(action=LobbyAction.JOIN).pack(),
        StatsCB(action=StatsAction.BOARD).pack(),
    )

    assert [data.split(":")[0] for data in packed] == [
        "reveal",
        "talk",
        "vote",
        "pick",
        "final",
        "lobby",
        "stats",
    ]


def test_directions_map_talk_actions_onto_the_ballot() -> None:
    assert DIRECTIONS == {
        TalkAction.ROUND: Direction.ROUND,
        TalkAction.VOTE: Direction.VOTE,
    }
