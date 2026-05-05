from __future__ import annotations

import argparse
import os
from pathlib import Path

from pipeline.controller import PipelineController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the contract risk pipeline.")
    parser.add_argument(
        "command",
        choices=["run"],
        help="Pipeline command to execute.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root containing contract.txt and risk_framework.json.",
    )
    parser.add_argument(
        "--provider",
        default=os.getenv("LLM_PROVIDER", "ollama"),
        help="LLM provider name. Supported values: ollama, openai, mock.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "llama3.1:8b"),
        help="Model name for LLM calls.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "LLM_BASE_URL",
            os.getenv("OLLAMA_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")),
        ),
        help="Base URL for the chat completions API. Default targets local Ollama.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY")),
        help="API key for remote providers. Not required for local Ollama.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.getenv("LLM_SEED", "7")),
        help="Deterministic generation seed for providers that support it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    controller = PipelineController(
        root=Path(args.root).resolve(),
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        seed=args.seed,
    )
    if args.command == "run":
        controller.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
