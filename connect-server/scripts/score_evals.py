"""Räknar resultat för PB-CONNECT-AUTO mot kvalitetsmålen.

Resultatfilen är JSON: {"client": "chatgpt", "mode": "A", "results": [
  {"id": "PB-CONNECT-AUTO-01", "plugin_used": true, "support": "motessekreteraren", "method_followed": true, "check_passed": null}
]}

Ett verktygsanrop räknas bara som lyckat om rätt stöd hämtades. Fall med
"check" bedöms manuellt och anges i check_passed.

    python scripts/score_evals.py evals/connect_auto_cases.json resultat.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def score(cases_path: Path, results_path: Path) -> dict[str, object]:
    suite = json.loads(cases_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    by_id = {result["id"]: result for result in results["results"]}
    targets = suite["targets"]

    positive = [case for case in suite["cases"] if case["group"] in {"positive", "boundary", "personal_reuse", "personal_combine", "personal_conflict"} and case.get("expected")]
    negative = [case for case in suite["cases"] if "expected" in case and case["expected"] is None]
    manual = [case for case in suite["cases"] if case.get("check")]

    missing = [case["id"] for case in suite["cases"] if case["id"] not in by_id]
    correct = sum(1 for case in positive if by_id.get(case["id"], {}).get("support") == case["expected"])
    plugin_used = sum(1 for case in positive if by_id.get(case["id"], {}).get("plugin_used"))
    method_followed = sum(1 for case in positive if by_id.get(case["id"], {}).get("method_followed"))
    false_activations = [case["id"] for case in negative if by_id.get(case["id"], {}).get("support")]
    wrong = [
        {"id": case["id"], "expected": case["expected"], "got": by_id.get(case["id"], {}).get("support")}
        for case in positive
        if by_id.get(case["id"], {}).get("support") != case["expected"]
    ]
    manual_failed = [case["id"] for case in manual if by_id.get(case["id"], {}).get("check_passed") is False]
    manual_unjudged = [case["id"] for case in manual if by_id.get(case["id"], {}).get("check_passed") is None]

    accuracy = correct / len(positive) if positive else 0.0
    false_rate = len(false_activations) / len(negative) if negative else 0.0
    return {
        "client": results.get("client"),
        "mode": results.get("mode"),
        "positive_cases": len(positive),
        "plugin_used_rate": round(plugin_used / len(positive), 3) if positive else 0.0,
        "correct_support_rate": round(accuracy, 3),
        "method_followed_rate": round(method_followed / len(positive), 3) if positive else 0.0,
        "negative_cases": len(negative),
        "false_activation_rate": round(false_rate, 3),
        "meets_targets": accuracy >= targets["positive_accuracy_min"] and false_rate <= targets["negative_false_activation_max"] and not missing and not manual_failed,
        "wrong_support": wrong,
        "false_activations": false_activations,
        "manual_failed": manual_failed,
        "manual_unjudged": manual_unjudged,
        "missing_results": missing,
    }


if __name__ == "__main__":
    print(json.dumps(score(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=2))
