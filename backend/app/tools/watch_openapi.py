"""Watch Python source; export in a fresh process so Python never caches old schemas."""

from __future__ import annotations

import subprocess
import sys

from watchfiles import watch

from backend.app.tools.export_openapi import ROOT


def main() -> None:
    for _changes in watch(ROOT / "backend" / "app"):
        result = subprocess.run(
            [sys.executable, "-m", "backend.app.tools.export_openapi"], cwd=ROOT, check=False
        )
        if result.returncode:
            print("Schema export failed. Fix the Python error; watching continues.", flush=True)


if __name__ == "__main__":
    main()
