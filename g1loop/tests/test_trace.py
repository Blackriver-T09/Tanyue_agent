import json
from pathlib import Path

from loop.service import EmoteService


def test_dry_run_persists_trace(tmp_path, monkeypatch):
    from loop import service as service_module

    monkeypatch.setattr(service_module, "TRACE_DIR", tmp_path)
    result = EmoteService().perform_emote("求饶", dry_run=True)
    trace_path = Path(result.trace_path)
    assert trace_path.exists()
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert payload["emote_name"] == "求饶"
    assert payload["dry_run"] is True
    assert payload["final_status"] == "success"
    assert payload["steps"][0]["action_name"] == "body_beg"
