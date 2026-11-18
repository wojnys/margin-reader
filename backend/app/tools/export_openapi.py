"""Export the API contract without executing lifespan, settings, or database code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "contracts" / "openapi.json"


def export(target: Path = TARGET, *, check: bool = False) -> bool:
    app = create_app(background_jobs=False, serve_frontend=False)
    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target.exists() and target.read_text() == content:
        return True
    if check:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(content)
    temporary.replace(target)
    return True


class Arguments(argparse.Namespace):
    check: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(namespace=Arguments())
    if not export(check=args.check):
        raise SystemExit("OpenAPI contract is stale. Run npm run api:generate in frontend.")


if __name__ == "__main__":
    main()
