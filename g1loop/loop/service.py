"""High-level service entry points."""

from __future__ import annotations

import uuid
from dataclasses import replace

from .adapters.body_adapter import BaseBodyAdapter, BodyConfig, FakeBodyAdapter, UnitreeG1Adapter
from .adapters.linkerhand_adapter import (
    BaseLinkerHandAdapter,
    FakeLinkerHandAdapter,
    LinkerHandAdapter,
    LinkerHandConfig,
)
from .agent.loop import AgentLoop
from .agent.models import ExecutionTrace, RunResult
from .agent.trace import TraceRecorder
from .config import TRACE_DIR
from .motions.emote_library import list_emotes


class EmoteService:
    """Facade for performing abstract emotes locally."""

    def __init__(
        self,
        body: BaseBodyAdapter | None = None,
        hands: BaseLinkerHandAdapter | None = None,
    ) -> None:
        self.body = body or FakeBodyAdapter()
        self.hands = hands or FakeLinkerHandAdapter(enabled=False)
        self.last_trace_path: str | None = None
        self._initialized = False

    @classmethod
    def create_live(
        cls,
        network_interface: str = "",
        enable_hands: bool = True,
        hand_joint: str = "L10",
        can: str = "can0",
        modbus: str = "None",
    ) -> "EmoteService":
        """Create a real-hardware service instance."""

        hand_adapter: BaseLinkerHandAdapter
        if enable_hands:
            hand_adapter = LinkerHandAdapter(
                config=LinkerHandConfig(
                    enabled=True,
                    hand_joint=hand_joint,
                    can=can,
                    modbus=modbus,
                )
            )
        else:
            hand_adapter = FakeLinkerHandAdapter(enabled=False)
        return cls(body=UnitreeG1Adapter(config=BodyConfig(network_interface=network_interface)), hands=hand_adapter)

    def initialize(self) -> None:
        if self._initialized:
            return
        self.body.initialize()
        self.hands.initialize()
        self._initialized = True

    def shutdown(self) -> None:
        self.hands.shutdown()
        self.body.shutdown()
        self._initialized = False

    def list_emotes(self) -> list[str]:
        """Return the supported emotes."""

        return list_emotes()

    def stop_motion(self) -> None:
        """Best-effort stop for all controlled hardware."""

        self.hands.stop_motion()
        self.body.stop_motion()

    def perform_emote(
        self,
        name: str,
        intensity: str = "medium",
        repeat: int = 1,
        dry_run: bool = False,
    ) -> RunResult:
        """Run one abstract emote request."""

        self.initialize()
        trace = ExecutionTrace(
            run_id=uuid.uuid4().hex[:12],
            emote_name=name,
            canonical_name="",
            dry_run=dry_run,
            intensity=intensity,
            repeat=repeat,
        )
        recorder = TraceRecorder(trace=trace, output_dir=TRACE_DIR)
        loop = AgentLoop(
            body_executor=self.body.body_action,
            hand_executor=self.hands.perform_gesture,
            go_idle=self.body.go_idle,
            stop_motion=self.stop_motion,
            max_retries=1,
        )
        success, error = loop.run(
            emote_name=name,
            intensity=intensity,
            repeat=repeat,
            dry_run=dry_run,
            recorder=recorder,
        )
        status = "success" if success else "failed"
        trace_path = recorder.finish(status=status, error=error)
        self.last_trace_path = trace_path
        return RunResult(
            success=success,
            status=status,
            trace_path=trace_path,
            trace=recorder.trace.to_dict(),
            error=error,
        )
