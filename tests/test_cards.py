from aiogram.types import BufferedInputFile

from undercover.bot.cards import card_photo


def test_card_photo_names_the_file_by_its_kind() -> None:
    photo = card_photo(b"\xff\xd8", "speaker_3")

    assert isinstance(photo, BufferedInputFile)
    assert photo.filename == "speaker_3.jpg"


def test_card_photo_passes_a_cached_file_id_through() -> None:
    assert card_photo("AgACAgIAAx0", "speaker_3") == "AgACAgIAAx0"
