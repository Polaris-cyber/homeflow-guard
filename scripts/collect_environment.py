"""Capture reproducibility metadata without collecting personal identifiers."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeflow.compiler import OllamaClient  # noqa: E402


OUTPUT = ROOT / "artifacts" / "environment.json"
MODELS = ["qwen3:14b-q4_K_M", "qwen3:8b-q4_K_M"]


def command_output(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        value = (completed.stdout or completed.stderr).strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    client = OllamaClient()
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "gpu": command_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
        ),
        "ollama_version": client.version(),
        "models": {model: {"digest": client.model_digest(model)} for model in MODELS},
        "privacy_note": "No username, hostname, IP address, token, or device inventory is collected.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
