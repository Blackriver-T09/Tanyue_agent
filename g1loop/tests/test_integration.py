from loop.adapters.body_adapter import FakeBodyAdapter
from loop.adapters.linkerhand_adapter import FakeLinkerHandAdapter
from loop.service import EmoteService


def test_fake_adapters_run_full_plan():
    body = FakeBodyAdapter()
    hands = FakeLinkerHandAdapter(enabled=True)
    result = EmoteService(body=body, hands=hands).perform_emote("轻蔑", dry_run=False)
    assert result.success is True
    assert body.calls[0]["action_name"] == "dismiss"
    assert hands.calls[0]["hand"] == "left"


def test_failure_recovers_to_idle():
    body = FakeBodyAdapter(fail_actions={"beg"})
    hands = FakeLinkerHandAdapter(enabled=True)
    result = EmoteService(body=body, hands=hands).perform_emote("求饶", dry_run=False)
    assert result.success is False
    assert any(call.get("action_name") == "idle" for call in body.calls)


def test_hand_can_be_disabled_and_body_still_runs():
    body = FakeBodyAdapter()
    hands = FakeLinkerHandAdapter(enabled=False)
    result = EmoteService(body=body, hands=hands).perform_emote("惊讶", dry_run=False)
    assert result.success is True
