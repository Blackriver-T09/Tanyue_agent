from __future__ import annotations

from typing import Any


ACTION_DURATIONS = {
    "cover_face_then_turn_away": 2.6,
    "slow_point_then_retreat": 2.4,
    "basketball_feint": 2.2,
    "rhythm_shake_then_pose": 2.8,
    "sharp_point_then_pause": 1.8,
    "dramatic_stop": 1.5,
    "recoil_then_salute": 2.5,
    "dramatic_retreat": 2.4,
    "ward_off_push": 2.0,
    "confused_scan": 2.1,
    "salute_hold": 2.3,
    "shrug_then_wave": 2.2,
    "calm_down_sip": 2.4,
    "elegant_penguin_pose": 2.8,
    "voice_only_nod": 1.4,
    "imperial_small_wave": 1.8,
    "accordion_gesture": 3.2,
    "ymca_dance": 8.0,
    "idle_listen": 1.2,
}

INTENSITY_CAPS = {
    "voice_only": 0.35,
    "small_motion": 0.55,
    "show_opening": 0.85,
}


class ActionPlanner:
    def plan(self, recognition: dict[str, Any], emotion: dict[str, Any]) -> dict[str, Any]:
        actions = recognition.get("actions") or []
        if not recognition.get("meme_id") or not actions:
            return self._idle_action()

        if recognition.get("meme_id") == "cyber_trump":
            arm_action = (
                "ymca_dance"
                if "YMCA" in (recognition.get("matched_symbols") or [])
                else "accordion_gesture"
            )
        else:
            arm_action = self._choose_action(actions, emotion)
        confidence = float(recognition.get("confidence") or 0.0)
        dominant_value = float(
            emotion.get("dimensions", {}).get(emotion.get("dominant_state"), 0.0)
        )
        intensity = max(0.2, min(1.0, confidence * 0.6 + dominant_value * 0.4))
        performance_tier = recognition.get("response_mode") or "small_motion"
        intensity = min(intensity, INTENSITY_CAPS.get(performance_tier, 0.55))

        return {
            "action_id": arm_action,
            "arm_action": arm_action,
            "intensity": round(float(intensity), 2),
            "duration_s": ACTION_DURATIONS.get(arm_action, 2.0),
            "line": recognition.get("line") or "",
            "safety": "safe_no_contact",
            "target": "performer_space",
            "performance_tier": performance_tier,
            "asset_id": recognition.get("asset_id") or "",
        }

    def _choose_action(self, actions: list[str], emotion: dict[str, Any]) -> str:
        dominant = emotion.get("dominant_state")
        if dominant in {"mocking", "playful"} and len(actions) > 1:
            return actions[1]
        return actions[0]

    def _idle_action(self) -> dict[str, Any]:
        return {
            "action_id": "idle_listen",
            "arm_action": "idle_listen",
            "intensity": 0.2,
            "duration_s": ACTION_DURATIONS["idle_listen"],
            "line": "",
            "safety": "safe_no_contact",
            "target": "performer_space",
            "performance_tier": "idle",
            "asset_id": "",
        }
