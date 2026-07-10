"""Static metadata for the bundled Unitree G1 simulation model."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import xml.etree.ElementTree as ET

SIM_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SIM_ROOT.parents[2]
ENV_MODEL_ROOT = os.environ.get("UNITREE_G1_DESCRIPTION_DIR")
MODEL_ROOT = Path(ENV_MODEL_ROOT) if ENV_MODEL_ROOT else next(
    (
        candidate
        for candidate in (
            REPO_ROOT / "unitree_ros" / "robots" / "g1_description",
            REPO_ROOT / "g1loop" / "unitree_ros" / "robots" / "g1_description",
        )
        if candidate.exists()
    ),
    REPO_ROOT / "unitree_ros" / "robots" / "g1_description",
)
DEFAULT_URDF = MODEL_ROOT / "g1_23dof_rev_1_0.urdf"
SOURCE_XML = MODEL_ROOT / "g1_23dof_rev_1_0.xml"
GENERATED_ROOT = SIM_ROOT / "assets" / "generated"
DEFAULT_XML = GENERATED_ROOT / "g1_23dof_rev_1_0_fixed_base.xml"
MODEL_VARIANTS = ("default",)

GROUPS: dict[str, list[str]] = {
    "waist": ["waist_yaw_joint"],
    "left_arm": [
        "left_shoulder_pitch_joint",
        "left_shoulder_roll_joint",
        "left_shoulder_yaw_joint",
        "left_elbow_joint",
        "left_wrist_roll_joint",
    ],
    "right_arm": [
        "right_shoulder_pitch_joint",
        "right_shoulder_roll_joint",
        "right_shoulder_yaw_joint",
        "right_elbow_joint",
        "right_wrist_roll_joint",
    ],
}


HOME_POSE: dict[str, list[float]] = {
    "waist": [0.0],
    "left_arm": [0.35, 0.15, 0.0, 1.05, 0.0],
    "right_arm": [-0.35, -0.15, 0.0, 1.05, 0.0],
}


@dataclass(frozen=True)
class ActuatorInfo:
    """One actuator definition extracted from the Unitree model XML."""

    name: str
    joint: str
    ctrl_min: float
    ctrl_max: float
    kind: str


def get_default_urdf_path() -> Path:
    """Return the canonical Unitree G1 URDF path."""

    return DEFAULT_URDF


def get_source_model_xml_path() -> Path:
    """Return the upstream Unitree XML path before simulation-specific patching."""

    return SOURCE_XML


def ensure_fixed_base_model_exists() -> Path:
    """Generate a fixed-base XML variant for local MuJoCo simulation."""

    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    if not SOURCE_XML.exists():
        raise FileNotFoundError(
            "Unitree G1 source XML not found. Set UNITREE_G1_DESCRIPTION_DIR to the directory that contains "
            "g1_23dof_rev_1_0.xml and the meshes/ folder."
        )
    root = ET.fromstring(SOURCE_XML.read_text(encoding="utf-8"))
    compiler = root.find("compiler")
    if compiler is not None:
        compiler.set("meshdir", str(MODEL_ROOT / "meshes"))
    pelvis = root.find("./worldbody/body[@name='pelvis']")
    if pelvis is None:
        raise ValueError("Expected pelvis body in Unitree G1 XML")
    floating_joint = pelvis.find("./joint[@name='floating_base_joint']")
    if floating_joint is not None:
        pelvis.remove(floating_joint)
    ET.indent(root)
    xml_text = ET.tostring(root, encoding="unicode")
    DEFAULT_XML.write_text(xml_text, encoding="utf-8")
    return DEFAULT_XML


def get_model_xml_path(model: str = "default") -> Path:
    """Return the XML path for a supported model variant."""

    if model != "default":
        raise KeyError(f"Unknown model variant: {model}")
    return ensure_fixed_base_model_exists()


def ensure_model_exists(model: str = "default") -> Path:
    """Validate that the selected XML model exists."""

    model_path = get_model_xml_path(model)
    if not model_path.exists():
        raise FileNotFoundError(f"XML model not found for {model}: {model_path}")
    return model_path


def load_actuator_metadata(model_path: Path | None = None, model: str = "default") -> dict[str, ActuatorInfo]:
    """Parse actuator metadata from XML and fall back to joint ranges."""

    model_path = model_path or ensure_model_exists(model)
    root = ET.fromstring(model_path.read_text(encoding="utf-8"))
    joint_limits: dict[str, tuple[float, float]] = {}
    for joint in root.findall(".//joint"):
        name = joint.attrib.get("name")
        if not name:
            continue
        range_value = joint.attrib.get("range")
        if range_value:
            lower_s, upper_s = range_value.split()
            joint_limits[name] = (float(lower_s), float(upper_s))
    actuator_root = root.find("actuator")
    if actuator_root is None:
        raise ValueError("No <actuator> section found in Unitree G1 XML")
    metadata: dict[str, ActuatorInfo] = {}
    for child in actuator_root:
        name = child.attrib.get("name")
        joint = child.attrib.get("joint")
        if not name or not joint:
            continue
        ctrlrange = child.attrib.get("ctrlrange")
        if ctrlrange:
            ctrl_min_s, ctrl_max_s = ctrlrange.split()
            ctrl_min = float(ctrl_min_s)
            ctrl_max = float(ctrl_max_s)
        else:
            ctrl_min, ctrl_max = joint_limits.get(joint, (-3.2, 3.2))
        metadata[name] = ActuatorInfo(
            name=name,
            joint=joint,
            ctrl_min=ctrl_min,
            ctrl_max=ctrl_max,
            kind=child.tag,
        )
    return metadata


def actuator_names_for_group(group: str) -> list[str]:
    """Return actuator names for a logical group."""

    if group not in GROUPS:
        raise KeyError(f"Unknown group: {group}")
    return list(GROUPS[group])


def supported_groups_for_model(model_path: Path | None = None, model: str = "default") -> dict[str, list[str]]:
    """Return only groups whose actuators exist in the selected model."""

    metadata = load_actuator_metadata(model_path=model_path, model=model)
    supported: dict[str, list[str]] = {}
    for group, actuators in GROUPS.items():
        if all(actuator in metadata for actuator in actuators):
            supported[group] = list(actuators)
    return supported
