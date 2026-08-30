"""Analyst feedback capture and the learning loop. Every insight card supports
accept / reject / correct in one click; corrections are logged and used to
reweight driver prioritization for future runs — a real human-in-the-loop
mechanism, not a one-way broadcast."""
import json
from datetime import datetime, timezone
from pathlib import Path

FEEDBACK_PATH = Path(__file__).parent.parent / "data" / "feedback.json"
WEIGHTS_PATH = Path(__file__).parent.parent / "data" / "rule_weights.json"

DEFAULT_WEIGHTS = {"mix": 1.0, "price": 1.0, "volume": 1.0}


def _load_json(path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_feedback_log():
    return _load_json(FEEDBACK_PATH, [])


def load_rule_weights():
    return _load_json(WEIGHTS_PATH, dict(DEFAULT_WEIGHTS))


def submit_feedback(insight_id, action, corrected_driver=None, note=None):
    """action: 'accept' | 'reject' | 'correct'. If 'correct', corrected_driver
    should name the driver the analyst believes is actually responsible."""
    if action not in {"accept", "reject", "correct"}:
        raise ValueError("action must be one of: accept, reject, correct")
    if action == "correct" and corrected_driver not in {"mix", "price", "volume"}:
        raise ValueError("corrected_driver must be one of: mix, price, volume")

    log = load_feedback_log()
    entry = {
        "insight_id": insight_id,
        "action": action,
        "corrected_driver": corrected_driver,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    log.append(entry)
    _save_json(FEEDBACK_PATH, log)

    weights = load_rule_weights()
    if action == "correct" and corrected_driver:
        # Nudge the corrected driver's prioritization weight up slightly, and
        # every other driver down slightly, so future runs surface the
        # analyst-validated cause more prominently. Small, bounded step size.
        step = 0.05
        for driver in weights:
            weights[driver] = max(0.5, min(2.0, weights[driver] - step))
        weights[corrected_driver] = max(0.5, min(2.0, weights[corrected_driver] + step + step * len(weights)))
        _save_json(WEIGHTS_PATH, weights)

    return entry


def feedback_summary():
    log = load_feedback_log()
    return {
        "total": len(log),
        "accepted": sum(1 for e in log if e["action"] == "accept"),
        "rejected": sum(1 for e in log if e["action"] == "reject"),
        "corrected": sum(1 for e in log if e["action"] == "correct"),
        "current_weights": load_rule_weights(),
    }
