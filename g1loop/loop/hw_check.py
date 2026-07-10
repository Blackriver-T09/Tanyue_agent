"""Hardware readiness checks for first-on-robot validation."""

from __future__ import annotations

import importlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import TRACE_DIR
from .live_config import LiveConfig, load_live_config
from .service import EmoteService


@dataclass
class CheckItem:
    """One hardware check result."""

    name: str
    success: bool
    detail: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class HardwareCheckReport:
    """Aggregate report for hardware readiness."""

    mode: str
    config: dict[str, Any]
    checks: list[CheckItem] = field(default_factory=list)
    final_status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "config": self.config,
            "checks": [
                {
                    "name": item.name,
                    "success": item.success,
                    "detail": item.detail,
                    "payload": item.payload,
                }
                for item in self.checks
            ],
            "final_status": self.final_status,
        }


def check_python_imports(enable_hands: bool) -> list[CheckItem]:
    """Check whether required SDKs are importable."""

    checks: list[CheckItem] = []
    sdk_root = Path(__file__).resolve().parents[2] / "unitree_sdk2_python"
    if str(sdk_root) not in sys.path:
        sys.path.append(str(sdk_root))
    try:
        importlib.import_module("unitree_sdk2py")
        checks.append(CheckItem(name="import_unitree_sdk", success=True, detail="unitree_sdk2py import ok"))
    except Exception as exc:
        checks.append(CheckItem(name="import_unitree_sdk", success=False, detail=str(exc)))

    if enable_hands:
        try:
            importlib.import_module("LinkerHand.linker_hand_api")
            checks.append(CheckItem(name="import_linkerhand_sdk", success=True, detail="LinkerHand import ok"))
        except Exception as exc:
            checks.append(CheckItem(name="import_linkerhand_sdk", success=False, detail=str(exc)))
    else:
        checks.append(
            CheckItem(
                name="import_linkerhand_sdk",
                success=True,
                detail="skipped because hands are disabled",
            )
        )
    return checks


def run_live_checks(config: LiveConfig) -> list[CheckItem]:
    """Run live SDK initialization and a safe idle check."""

    checks: list[CheckItem] = []
    service = EmoteService.create_live(
        network_interface=config.network_interface,
        enable_hands=config.enable_hands,
        hand_joint=config.hand_joint,
        can=config.can,
        modbus=config.modbus,
    )
    try:
        started_at = time.perf_counter()
        service.initialize()
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        checks.append(
            CheckItem(
                name="initialize_live_service",
                success=True,
                detail="live service initialized",
                payload={"duration_ms": elapsed_ms},
            )
        )
    except Exception as exc:
        checks.append(CheckItem(name="initialize_live_service", success=False, detail=str(exc)))
        try:
            service.shutdown()
        except Exception:
            pass
        return checks

    try:
        idle_result = service.body.go_idle()
        checks.append(
            CheckItem(
                name="body_idle",
                success=idle_result.success,
                detail=idle_result.status if idle_result.success else (idle_result.error or idle_result.status),
                payload={"verification": idle_result.verification},
            )
        )
    except Exception as exc:
        checks.append(CheckItem(name="body_idle", success=False, detail=str(exc)))

    if config.enable_hands:
        try:
            left_result = service.hands.perform_gesture("left", "neutral", intensity="low")
            right_result = service.hands.perform_gesture("right", "neutral", intensity="low")
            checks.append(
                CheckItem(
                    name="hands_neutral",
                    success=left_result.success and right_result.success,
                    detail="left/right hand neutral ok"
                    if left_result.success and right_result.success
                    else f"left={left_result.error or left_result.status}, right={right_result.error or right_result.status}",
                    payload={
                        "left": left_result.snapshot,
                        "right": right_result.snapshot,
                    },
                )
            )
        except Exception as exc:
            checks.append(CheckItem(name="hands_neutral", success=False, detail=str(exc)))

    try:
        service.shutdown()
    except Exception as exc:
        checks.append(CheckItem(name="shutdown_live_service", success=False, detail=str(exc)))
    else:
        checks.append(CheckItem(name="shutdown_live_service", success=True, detail="shutdown ok"))
    return checks


def write_report(report: HardwareCheckReport) -> str:
    """Persist a hardware check report next to traces."""

    report_dir = TRACE_DIR / "hw_checks"
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"hw_check_{int(time.time())}.json"
    path = report_dir / filename
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def run_hardware_check(config_path: str | None = None, live: bool = False) -> tuple[HardwareCheckReport, str]:
    """Execute import-only or live hardware checks and persist a report."""

    config = load_live_config(config_path)
    mode = "live" if live or config.use_live else "import_only"
    report = HardwareCheckReport(mode=mode, config=asdict(config))
    report.checks.extend(check_python_imports(enable_hands=config.enable_hands))
    if mode == "live":
        report.checks.extend(run_live_checks(config))
    report.final_status = "success" if all(item.success for item in report.checks) else "failed"
    report_path = write_report(report)
    return report, report_path


def main() -> int:
    """CLI entry for the hardware checker."""

    import argparse

    parser = argparse.ArgumentParser(description="Check local SDK and live hardware readiness.")
    parser.add_argument("--config", help="Path to a JSON live config file")
    parser.add_argument("--live", action="store_true", help="Run live initialization and idle checks")
    args = parser.parse_args()

    report, report_path = run_hardware_check(config_path=args.config, live=args.live)
    print(f"status={report.final_status}")
    print(f"mode={report.mode}")
    print(f"report={report_path}")
    for item in report.checks:
        marker = "ok" if item.success else "fail"
        print(f"[{marker}] {item.name}: {item.detail}")
    return 0 if report.final_status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
