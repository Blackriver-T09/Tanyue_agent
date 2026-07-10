from loop.motions.emote_library import build_plan, list_emotes, normalize_emote


def test_supported_emotes_are_listed():
    assert list_emotes() == ["惊讶", "求饶", "轻蔑"]


def test_plan_for_surprised_maps_to_gasp():
    plan = build_plan("惊讶", "medium")
    assert plan.canonical_name == "惊讶"
    assert [step.action_name for step in plan.steps] == ["body_gasp", "hand_open_palm"]


def test_alias_normalization_works():
    assert normalize_emote("gasp") == "惊讶"
