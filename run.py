"""Thin command-line entry point for TraceGuard."""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from uuid import uuid4

from traceguard.agent.graph import run_investigation
from traceguard.config import faults_from_environment, provider_from_environment, tracer_for_run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigate an order's payment history.")
    parser.add_argument("--events", required=True, help="Path to input events JSONL")
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--order", required=True, help="Order ID")
    parser.add_argument("--question", required=True, help="Investigation question")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Print exactly one JSON result, or a concise invocation error to stderr."""
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")
    args = _parser().parse_args(argv)
    try:
        run_id = str(uuid4())
        output = run_investigation(
            args.events,
            args.tenant,
            args.order,
            args.question,
            faults=faults_from_environment(),
            provider=provider_from_environment(),
            tracer=tracer_for_run(run_id),
            run_id=run_id,
        )
    except (OSError, ValueError) as exc:
        print(f"TraceGuard: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
