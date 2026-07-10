from loop.live_config import dump_default_config, load_live_config


def test_can_dump_and_load_example_config(tmp_path):
    file_path = tmp_path / "live.json"
    dump_default_config(str(file_path))
    config = load_live_config(str(file_path))
    assert config.network_interface == ""
    assert config.hand_joint == "L10"
    assert config.intensity == "low"
