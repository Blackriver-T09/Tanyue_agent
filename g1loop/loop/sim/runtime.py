"""MuJoCo runtime wrapper for Unitree G1 simulation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import ensure_model_exists


def _import_mujoco():
    try:
        import mujoco  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "mujoco is not installed. Install with `pip install mujoco` or `pip install .[sim]`."
        ) from exc
    return mujoco


@dataclass
class G1MujocoRuntime:
    """Owns Unitree G1 model/data/viewer lifecycle."""

    model_path: Path | None = None
    model_name: str = "default"
    gui: bool = True
    time_step_hz: float = 240.0

    def __post_init__(self) -> None:
        self.model_path = self.model_path or ensure_model_exists(self.model_name)
        self._mujoco = _import_mujoco()
        self.model = self._mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = self._mujoco.MjData(self.model)
        self.viewer: Any = None
        self._viewer_module: Any = None
        self._launched = False

    def launch(self) -> None:
        """Optionally launch a passive viewer."""

        if self.gui and not self._launched:
            try:
                import mujoco.viewer as mujoco_viewer  # type: ignore
            except ImportError as exc:
                raise RuntimeError("mujoco.viewer is unavailable in this environment") from exc
            self._viewer_module = mujoco_viewer
            self.viewer = mujoco_viewer.launch_passive(self.model, self.data)
        self._launched = True

    def step(self, n: int = 1, sync_viewer: bool = True) -> None:
        """Advance physics by n steps."""

        if n < 1:
            return
        for _ in range(n):
            self._mujoco.mj_step(self.model, self.data)
            if self.viewer is not None and sync_viewer and self.viewer.is_running():
                self.viewer.sync()

    def run_forever(self, sleep_s: float | None = None) -> None:
        """Run the viewer loop until the window closes."""

        self.launch()
        sleep_s = sleep_s if sleep_s is not None else (1.0 / self.time_step_hz)
        if self.viewer is None:
            raise RuntimeError("run_forever requires gui=True")
        while self.viewer.is_running():
            self.step(1, sync_viewer=True)
            if sleep_s > 0:
                time.sleep(sleep_s)

    def close(self) -> None:
        """Close any active viewer."""

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None
