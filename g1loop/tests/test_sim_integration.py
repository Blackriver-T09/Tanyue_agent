import pytest

from loop.sim.controller import G1MujocoController
from loop.sim.runtime import G1MujocoRuntime


@pytest.fixture
def runtime():
    pytest.importorskip("mujoco", reason="mujoco not installed")
    rt = G1MujocoRuntime(gui=False)
    yield rt
    rt.close()


def test_model_loads_and_waist_moves(runtime):
    controller = G1MujocoController(runtime)
    before = controller.get_joint_positions("waist")
    controller.set_waist([0.1])
    controller.step(200)
    after = controller.get_joint_positions("waist")
    assert len(before) == 1
    assert len(after) == 1
    assert abs(after[0] - before[0]) > 1e-4


def test_home_pose_returns_group_snapshots(runtime):
    controller = G1MujocoController(runtime)
    result = controller.move_to_home_pose(step_count=200)
    assert result.success is True
    assert "left_arm" in result.actual
    assert len(result.actual["left_arm"]) == 5


def test_model_loads_and_left_arm_moves():
    pytest.importorskip("mujoco", reason="mujoco not installed")
    runtime = G1MujocoRuntime(gui=False)
    try:
        controller = G1MujocoController(runtime)
        before = controller.get_joint_positions("left_arm")
        controller.set_left_arm([0.5, 0.2, -0.1, 1.2, 0.1])
        controller.step(200)
        after = controller.get_joint_positions("left_arm")
        assert len(after) == 5
        assert any(abs(a - b) > 1e-4 for a, b in zip(after, before))
    finally:
        runtime.close()
