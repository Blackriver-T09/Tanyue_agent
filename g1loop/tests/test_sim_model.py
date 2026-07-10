from loop.sim.model import (
    DEFAULT_XML,
    GROUPS,
    actuator_names_for_group,
    get_default_urdf_path,
    get_model_xml_path,
    load_actuator_metadata,
)


def test_default_unitree_model_paths_exist():
    assert DEFAULT_XML.exists()
    assert get_default_urdf_path().exists()


def test_group_lengths_are_expected():
    assert len(GROUPS["waist"]) == 1
    assert len(GROUPS["left_arm"]) == 5
    assert len(GROUPS["right_arm"]) == 5


def test_actuator_metadata_contains_core_groups():
    metadata = load_actuator_metadata()
    assert "waist_yaw_joint" in metadata
    assert "left_wrist_roll_joint" in metadata
    assert "right_wrist_roll_joint" in metadata
    assert actuator_names_for_group("left_arm")[0] == "left_shoulder_pitch_joint"


def test_default_variant_points_to_unitree_g1_xml():
    variant_path = get_model_xml_path("default")
    metadata = load_actuator_metadata(model_path=variant_path)
    xml_text = variant_path.read_text(encoding="utf-8")
    assert variant_path.exists()
    assert "left_gripper_joint" not in metadata
    assert "g1_23dof_rev_1_0" in xml_text
