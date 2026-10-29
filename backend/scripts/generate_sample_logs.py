"""
Write the synthetic sample logs (and their answer keys) to disk.

    python scripts/generate_sample_logs.py                 # writes into data/sample_logs
    python scripts/generate_sample_logs.py --seed 7 --out some/folder

The same seed always produces byte-identical files. Everything is invented demonstration data.
The "*_key.json" files are used only by scripts/evaluate_pipeline.py, never by the application.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.utils.sample_logs import generate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic sample logs.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=BACKEND_DIR / "data" / "sample_logs")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("application", "routing"):
        dataset = generate(name, args.seed)
        for filename, text in dataset.files.items():
            (args.out / filename).write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {args.out / filename}  ({len(text.splitlines()):,} lines)")
        key_path = args.out / f"{name}_key.json"
        key_path.write_text(json.dumps(dataset.key, indent=2), encoding="utf-8")
        print(f"wrote {key_path}  (answer key, used only by evaluation)")


if __name__ == "__main__":
    main()
