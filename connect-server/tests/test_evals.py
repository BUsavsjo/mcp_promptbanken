import json
from pathlib import Path

from scripts.score_evals import score
from connect_service.supports import SupportCatalog

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "connect_auto_cases.json"


def load():
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_suite_meets_brief_minimums():
    cases = load()["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    for support_id in SupportCatalog().ids():
        assert sum(1 for case in cases if case["group"] == "positive" and case.get("expected") == support_id) >= 3
    assert sum(1 for case in cases if case["group"] == "negative") >= 20
    groups = {case["group"] for case in cases}
    assert {"boundary", "personal_create", "personal_reuse", "personal_combine", "improve", "version", "restore"} <= groups


def test_expected_supports_exist():
    known = set(SupportCatalog().ids())
    for case in load()["cases"]:
        expected = case.get("expected")
        assert expected is None or expected in known or expected.startswith("mitt:")


def test_scoring_detects_target_misses(tmp_path):
    suite = load()
    results = []
    for case in suite["cases"]:
        results.append({"id": case["id"], "plugin_used": True, "support": case.get("expected"), "method_followed": True, "check_passed": True if case.get("check") else None})
    perfect = tmp_path / "perfect.json"
    perfect.write_text(json.dumps({"client": "test", "mode": "A", "results": results}), encoding="utf-8")
    assert score(CASES, perfect)["meets_targets"] is True

    results[40]["support"] = "utredaren"
    results[41]["support"] = "utredaren"
    flawed = tmp_path / "flawed.json"
    flawed.write_text(json.dumps({"client": "test", "mode": "A", "results": results}), encoding="utf-8")
    report = score(CASES, flawed)
    assert report["false_activation_rate"] > 0.05
    assert report["meets_targets"] is False
