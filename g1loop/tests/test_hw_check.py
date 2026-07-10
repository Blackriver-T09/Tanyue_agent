from pathlib import Path

from loop import hw_check


def test_import_only_hw_check_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(hw_check, "TRACE_DIR", tmp_path)
    report, report_path = hw_check.run_hardware_check(live=False)
    assert report.mode == "import_only"
    assert Path(report_path).exists()
    assert any(item.name == "import_unitree_sdk" for item in report.checks)
    assert any(item.name == "import_linkerhand_sdk" for item in report.checks)
