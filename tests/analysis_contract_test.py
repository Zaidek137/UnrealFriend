#!/usr/bin/env python3
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "apps" / "unreal-agent-web" / "server.py"
GOLDEN_ANALYSIS = ROOT / "tests" / "golden-blueprint-analysis" / "sample_analysis.json"


def load_server_module():
    spec = importlib.util.spec_from_file_location("unreal_agent_web_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load server module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    server = load_server_module()
    analysis = json.loads(GOLDEN_ANALYSIS.read_text(encoding="utf-8"))

    lint = server.build_analysis_lint(analysis)
    report = server.build_deterministic_analysis_report(analysis, lint)
    index = server.build_analysis_evidence_index(analysis)

    ok_validation = server.validate_analysis_report(
        report=report,
        evidence_index=index,
        require_citations=True,
        disallow_speculative=True,
    )
    assert_true(ok_validation.get("ok", False), f"Expected valid deterministic report, got {ok_validation}")

    bad_uncited = {
        "summary": "Bad",
        "claims": [{"claim": "It has one node", "confidence": 1.0, "unknown": False, "evidence": []}],
        "unknowns": [],
    }
    uncited_validation = server.validate_analysis_report(
        report=bad_uncited,
        evidence_index=index,
        require_citations=True,
        disallow_speculative=True,
    )
    assert_true(not uncited_validation.get("ok", True), "Expected uncited claims to fail validation")

    bad_speculative = {
        "summary": "Bad",
        "claims": [
            {
                "claim": "This likely runs every tick.",
                "confidence": 0.6,
                "unknown": False,
                "evidence": [{"graph_name": "EventGraph", "node_name": "K2Node_Event_BeginPlay"}],
            }
        ],
        "unknowns": [],
    }
    speculative_validation = server.validate_analysis_report(
        report=bad_speculative,
        evidence_index=index,
        require_citations=True,
        disallow_speculative=True,
    )
    assert_true(not speculative_validation.get("ok", True), "Expected speculative language to fail validation")

    print("Analysis contract tests passed.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Analysis contract tests failed: {exc}", file=sys.stderr)
        sys.exit(1)
