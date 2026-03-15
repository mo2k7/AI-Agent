"""CLI tool to decrypt an encrypted audit log.

Usage::

    python -m agent_host.tools.decrypt_audit /path/to/audit.log
    python -m agent_host.tools.decrypt_audit /path/to/audit.log --output /tmp/decrypted.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from agent_host.memory.crypto import CryptoBox
from agent_host.memory.keychain import get_or_create_master_key


_AUDIT_AAD = b"audit-log-entry"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Decrypt an AES-256-GCM encrypted audit log"
    )
    parser.add_argument("input", type=Path, help="Path to the encrypted audit log")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Output path (defaults to stdout)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} does not exist", file=sys.stderr)
        sys.exit(1)

    master = get_or_create_master_key()
    box = CryptoBox(master.raw)

    out_handle = (
        open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    )
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    decrypted = box.decrypt_text(raw_line, aad=_AUDIT_AAD)
                    # Re-serialize to validate JSON and normalize formatting.
                    event = json.loads(decrypted)
                    out_handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                except Exception as exc:
                    print(
                        f"Warning: line {lineno}: {exc}",
                        file=sys.stderr,
                    )
    finally:
        if out_handle is not sys.stdout:
            out_handle.close()


if __name__ == "__main__":
    main()
