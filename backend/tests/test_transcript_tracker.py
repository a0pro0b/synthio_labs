from agents.realtime.items import InputAudio, UserMessageItem

from app.ws import FAILED_TRANSCRIPT_TEXT, TranscriptTracker


def _user_audio(item_id: str, transcript: str | None) -> UserMessageItem:
    return UserMessageItem(item_id=item_id, content=[InputAudio(transcript=transcript)])


def test_user_speech_deltas_show_before_transcription_completes() -> None:
    tracker = TranscriptTracker()
    tracker.apply_history_item(_user_audio("u1", None))
    tracker.apply_delta("u1", "What does", role="user")
    tracker.apply_delta("u1", " it cost?", role="user")
    tracker.apply_history([_user_audio("u1", None)])

    [item] = tracker.snapshot().items
    assert (item.role, item.text, item.final) == ("user", "What does it cost?", False)

    tracker.apply_history([_user_audio("u1", "What does it cost?")])
    [item] = tracker.snapshot().items
    assert (item.text, item.final) == ("What does it cost?", True)


def test_failed_transcription_still_shows_the_user_turn() -> None:
    tracker = TranscriptTracker()
    tracker.apply_history_item(_user_audio("u1", None))
    tracker.mark_failed("u1")
    tracker.apply_history([_user_audio("u1", None)])

    [item] = tracker.snapshot().items
    assert (item.role, item.text, item.final) == ("user", FAILED_TRANSCRIPT_TEXT, True)
