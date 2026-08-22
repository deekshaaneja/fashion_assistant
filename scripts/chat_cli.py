#!/usr/bin/env python3
"""Minimal, in-process dev harness for manually driving Phase 5's
conversational loop (product brief section 53 -- no production frontend,
just enough to run the 9-turn manual acceptance script interactively).

Usage:
    .venv/bin/python scripts/chat_cli.py [--mock]

Commands:
    !upload <path> [path...]   attach image file(s) to the NEXT message
    !quit                      exit
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.agent.loop import run_turn
from src.domain.models.session import DesignSession
from src.fashion_engine.fabric.vision_pipeline import UploadedFabricImage


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 conversational co-designer -- dev CLI")
    parser.add_argument(
        "--mock", action="store_true", help="force VISUALIZATION_ENABLED/AGENT_ENABLED off for a fully offline run"
    )
    args = parser.parse_args()

    if args.mock:
        import os

        os.environ["AGENT_ENABLED"] = "false"
        os.environ["VISUALIZATION_ENABLED"] = "false"
        os.environ["LLM_ENABLED"] = "false"
        os.environ["VISION_ENABLED"] = "false"

    session = DesignSession()
    print(f"session_id={session.session_id} (type !quit to exit, !upload <path> to attach a fabric photo)")

    pending_images: list[UploadedFabricImage] = []
    for line in sys.stdin if not sys.stdin.isatty() else _prompt_lines():
        line = line.rstrip("\n")
        if not line:
            continue
        if line.strip() == "!quit":
            break
        if line.startswith("!upload "):
            for path_str in line[len("!upload "):].split():
                path = Path(path_str)
                data = path.read_bytes()
                pending_images.append(UploadedFabricImage(image_id=path.name, data=data))
            print(f"(attached {len(pending_images)} image(s) for the next message)")
            continue

        result = run_turn(session, line, pending_images, persist=False)
        pending_images = []
        print(f"assistant> {result.message}")
        if result.artifacts:
            print(f"  artifacts: {result.artifacts}")
        if result.current_design_version:
            print(f"  current_design_version: {result.current_design_version}")


def _prompt_lines():
    while True:
        try:
            yield input("you> ")
        except EOFError:
            return


if __name__ == "__main__":
    main()
