from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent import PunGenAgent


BEATS = {
    "xinteng_giegie": {
        "id": "green_tea_grievance",
        "label": "绿茶委屈",
        "goal": "让机械臂用委屈和嫌弃制造喜剧反差。",
        "stage_direction": "捂脸、慢指、轻微后撤，像被龙王一句话伤到。",
    },
    "ikun_basketball": {
        "id": "meme_rhythm_callout",
        "label": "节奏调侃",
        "goal": "用观众熟悉的节奏动作快速建立热梗识别。",
        "stage_direction": "做短促节奏摆动，最后定格成舞台姿态。",
    },
    "ni_gan_ma": {
        "id": "comic_interruption",
        "label": "喜剧打断",
        "goal": "用突然停顿制造反应点。",
        "stage_direction": "快速指向玩家，然后停住半拍。",
    },
    "dragon_king_reveal": {
        "id": "status_reversal",
        "label": "身份反转",
        "goal": "配合龙王短剧的打脸和服软桥段。",
        "stage_direction": "先后仰，再收束成服软姿态。",
    },
    "tui_tui_tui": {
        "id": "boundary_rejection",
        "label": "边界拒绝",
        "goal": "用非接触驱离动作制造恶毒女配的嫌弃感。",
        "stage_direction": "连续摆手后撤，拒绝龙王靠近。",
    },
    "listen_to_yourself": {
        "id": "confusion_callout",
        "label": "离谱反问",
        "goal": "把玩家的离谱台词转成可见的疑惑反应。",
        "stage_direction": "先扫视，再停顿回指，表现“你认真的吗”。",
    },
    "zhijing_salute": {
        "id": "respect_payoff",
        "label": "高光致敬",
        "goal": "让短剧在反转或爆点后有可截屏的定格姿态。",
        "stage_direction": "机械臂抬起并短暂停住，像弹幕刷屏致敬。",
    },
    "you_neng_zen": {
        "id": "resigned_shrug",
        "label": "无奈认输",
        "goal": "用摊手和小幅挥退表达被剧情拿捏。",
        "stage_direction": "摊手后轻轻挥开，表现“算了，又能怎”。",
    },
    "sigua_soup": {
        "id": "self_soothing",
        "label": "破防自愈",
        "goal": "从冲突降温到自我安慰，制造节奏变化。",
        "stage_direction": "做端碗动作再缓慢下压，像喝口汤冷静一下。",
    },
    "elegant_penguin": {
        "id": "absurd_dance",
        "label": "抽象舞步",
        "goal": "用节奏摆动制造观众容易记住的舞台点。",
        "stage_direction": "左右小幅摆动两次，最后定格为高雅姿态。",
    },
}

DEFAULT_BEAT = {
    "id": "safe_listening",
    "label": "安全倾听",
    "goal": "没有稳定梗触发时保持角色在场，不抢戏。",
    "stage_direction": "保持待机倾听，等待下一句更明确的梗线索。",
}


@dataclass
class ShortDramaSession:
    scene: str = "龙王短剧"
    player_role: str = "龙王"
    robot_role: str = "恶毒女配机械臂"
    agent: PunGenAgent = field(default_factory=PunGenAgent.from_default_library)
    history: list[dict[str, Any]] = field(default_factory=list)

    def step(self, text: str, speaker: str = "player") -> dict[str, Any]:
        agent_response = self.agent.respond(text, scene=self.scene)
        beat = self._select_beat(agent_response)
        turn_index = len(self.history) + 1
        performance_plan = self._build_performance_plan(agent_response, beat)
        history_entry = {
            "turn_index": turn_index,
            "speaker": speaker,
            "text": text,
            "meme_id": agent_response["recognition"].get("meme_id"),
            "beat_id": beat["id"],
            "dominant_state": agent_response["emotion"].get("dominant_state"),
            "arm_action": agent_response["action"].get("arm_action"),
        }
        self.history.append(history_entry)

        return {
            "protocol_version": "pungen-scene/v0",
            "scene": {
                "name": self.scene,
                "player_role": self.player_role,
                "robot_role": self.robot_role,
            },
            "turn": {
                "index": turn_index,
                "speaker": speaker,
                "text": text,
            },
            "beat": beat,
            "arc": {
                "dominant_state": agent_response["emotion"].get("dominant_state"),
                "heart_value": agent_response["emotion"].get("heart_value"),
                "dimensions": agent_response["emotion"].get("dimensions"),
            },
            "performance_plan": performance_plan,
            "agent_response": agent_response,
            "history": list(self.history),
        }

    def _select_beat(self, agent_response: dict[str, Any]) -> dict[str, str]:
        meme_id = agent_response["recognition"].get("meme_id")
        return dict(BEATS.get(meme_id, DEFAULT_BEAT))

    def _build_performance_plan(
        self,
        agent_response: dict[str, Any],
        beat: dict[str, str],
    ) -> dict[str, Any]:
        action = agent_response["action"]
        return {
            "arm_action": action.get("arm_action"),
            "intensity": action.get("intensity"),
            "duration_s": action.get("duration_s"),
            "line": action.get("line"),
            "safety": action.get("safety"),
            "beat_id": beat["id"],
            "stage_direction": beat["stage_direction"],
        }
