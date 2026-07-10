import pytest

from loop.sim.controller import G1MujocoController
from loop.sim.runtime import G1MujocoRuntime


@pytest.fixture
def runtime():
    pytest.importorskip("mujoco", reason="mujoco not installed")
    rt = G1MujocoRuntime(gui=False)
    yield rt
    rt.close()


def test_invalid_group_length_raises(runtime):
    controller = G1MujocoController(runtime)
    with pytest.raises(ValueError):
        controller.set_waist([0.1, 0.2])


def test_out_of_range_target_raises(runtime):
    controller = G1MujocoController(runtime)
    with pytest.raises(ValueError):
        controller.set_left_arm([9.9, 0.0, 0.0, 0.0, 0.0])


def test_unknown_group_raises(runtime):
    pytest.importorskip("mujoco", reason="mujoco not installed")
    controller = G1MujocoController(runtime)
    with pytest.raises(KeyError):
        controller.get_joint_positions("head")
