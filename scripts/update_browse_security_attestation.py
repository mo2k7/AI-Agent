#!/usr/bin/env python3
"""Update browse security attestation timestamp after regression tests pass."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "agent_host"
        / "tools"
        / "data"
        / "browse_security_attestation.json"
    )
    payload = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    payload["last_security_tested_at"] = datetime.now(timezone.utc).isoformat()
    payload["status"] = "pass"
    payload["schedule"] = "weekly"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated attestation: {path}")


if __name__ == "__main__":
    main()
