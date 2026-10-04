"""Deterministic SE 3.0 quality gate evaluation script for CI/CD pipelines.

Inspects GAIN scorecard JSON telemetry and validates code health against
strict numerical thresholds without any non-deterministic or LLM reasoning.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gain.metrics.quality_gate import evaluate_quality_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate GAIN SE 3.0 Quality Gate")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="-",
        help="Path to GAIN scorecard JSON file (or '-' for stdin)",
    )
    parser.add_argument(
        "--max-bloat-pct",
        type=float,
        default=25.0,
        help="Max allowable percentage of bloat-flagged files",
    )
    parser.add_argument(
        "--min-refactor-ratio",
        type=float,
        default=0.10,
        help="Minimum required refactoring ratio",
    )
    parser.add_argument(
        "--max-friction-pct",
        type=float,
        default=30.0,
        help="Max percentage of reviews lingering >48h",
    )
    parser.add_argument(
        "--max-hotfix-pct",
        type=float,
        default=25.0,
        help="Max percentage of defect rework / hotfix PRs",
    )
    parser.add_argument(
        "--min-sample-size",
        type=int,
        default=5,
        help="Minimum PRs required before activating ratio thresholds",
    )

    args = parser.parse_args()

    if args.input == "-":
        content = sys.stdin.read()
    else:
        content = Path(args.input).read_text(encoding="utf-8")

    scorecard = json.loads(content)

    repo = scorecard.get("repository", "unknown")
    run_id = scorecard.get("scan_run_id", "unknown")

    print("\n" + "=" * 65)
    print("🛡️  GAIN AI-NATIVE SE 3.0 DETERMINISTIC QUALITY GATE")
    print(f"Target Repository: {repo}")
    print(f"Scan Run ID:       {run_id}")
    print("=" * 65)

    res = evaluate_quality_gate(
        scorecard,
        max_bloat_pct=args.max_bloat_pct,
        min_refactor_ratio=args.min_refactor_ratio,
        max_friction_pct=args.max_friction_pct,
        max_hotfix_pct=args.max_hotfix_pct,
        min_sample_size=args.min_sample_size,
    )

    if not res.passed:
        print("\n🚫 BUILD BROKEN — QUALITY GATE VIOLATIONS DETECTED:\n")
        for v in res.violations:
            print(f"::error title=SE 3.0 Gate Failure::{v}")
            print(f"   • {v}")
        print("\n" + "=" * 65 + "\n")
        return 1

    print("\n✅ ALL SE 3.0 QUALITY GATES PASSED")
    print(
        f"   • Code Bloat Gate:     PASSED ({res.bloat_percentage:.1f}% <= {args.max_bloat_pct}%)"
    )
    print(
        f"   • Refactor Ratio Gate: PASSED ({res.refactoring_ratio:.1%} >= "
        f"{args.min_refactor_ratio:.1%})"
    )
    print(
        f"   • Review Friction Gate:PASSED ({res.friction_percentage:.1f}% <= "
        f"{args.max_friction_pct}%)"
    )
    print(
        f"   • Defect Rework Gate:  PASSED ({res.hotfix_percentage:.1f}% <= {args.max_hotfix_pct}%)"
    )
    print("=" * 65 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
