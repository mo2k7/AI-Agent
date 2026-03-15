#!/usr/bin/env python3
"""Validate and update browse_web anti-bot signatures.

Usage examples:
  python scripts/refresh_anti_bot_signatures.py --validate
  python scripts/refresh_anti_bot_signatures.py --source /tmp/new_signatures.json --bump-version
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


REQUIRED_PROVIDER_FIELDS = {
    "id",
    "error_class",
    "confidence",
    "min_signals",
}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_signature_path() -> Path:
    return _repo_root() / "agent_host" / "tools" / "data" / "anti_bot_signatures.json"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object at top level.")
    return value


def _validate_signatures(payload: dict[str, Any], source: str) -> None:
    if not isinstance(payload.get("version"), str) or not payload["version"].strip():
        raise ValueError(f"{source}: 'version' must be a non-empty string.")

    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ValueError(f"{source}: 'providers' must be a non-empty list.")

    provider_ids: set[str] = set()
    for idx, provider in enumerate(providers):
        if not isinstance(provider, dict):
            raise ValueError(f"{source}: provider index {idx} is not an object.")

        missing = REQUIRED_PROVIDER_FIELDS - set(provider.keys())
        if missing:
            raise ValueError(
                f"{source}: provider index {idx} missing required fields: {sorted(missing)}."
            )

        provider_id = str(provider["id"]).strip()
        if not provider_id:
            raise ValueError(f"{source}: provider index {idx} has empty id.")
        if provider_id in provider_ids:
            raise ValueError(f"{source}: duplicate provider id '{provider_id}'.")
        provider_ids.add(provider_id)

        confidence = str(provider["confidence"]).lower().strip()
        if confidence not in ALLOWED_CONFIDENCE:
            raise ValueError(
                f"{source}: provider '{provider_id}' has invalid confidence '{confidence}'."
            )

        try:
            min_signals = int(provider["min_signals"])
        except (TypeError, ValueError):
            raise ValueError(
                f"{source}: provider '{provider_id}' has non-integer min_signals."
            ) from None
        if min_signals < 1:
            raise ValueError(
                f"{source}: provider '{provider_id}' min_signals must be >= 1."
            )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=_default_signature_path(),
        help="Target anti_bot_signatures.json path.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional source JSON file to replace target payload before validation.",
    )
    parser.add_argument(
        "--bump-version",
        action="store_true",
        help="Set version to today's date (YYYY-MM-DD) after successful validation.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate only; do not write target.",
    )
    args = parser.parse_args()

    if args.source:
        payload = _load_json(args.source)
        source_label = str(args.source)
    else:
        payload = _load_json(args.target)
        source_label = str(args.target)

    _validate_signatures(payload, source_label)

    if args.bump_version:
        payload["version"] = dt.date.today().isoformat()

    if args.validate:
        print(f"OK: validated signatures from {source_label}")
        return

    _write_json(args.target, payload)
    print(
        "Updated anti-bot signatures:"
        f" target={args.target} version={payload.get('version', 'unknown')}"
    )


if __name__ == "__main__":
    main()
