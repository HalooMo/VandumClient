#!/usr/bin/env python3
"""CLI: OpenStack shelve / unshelve / status for SpeechLab GPU.

Usage (from repo root, with .venv and .env):

  python scripts/gpu_power.py status
  python scripts/gpu_power.py unshelve
  python scripts/gpu_power.py shelve
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.services.gpu_power import GpuPowerClient, GpuPowerError  # noqa: E402


def _print_server(srv: dict) -> None:
    addrs = srv.get("addresses") or {}
    print(
        json.dumps(
            {
                "id": srv.get("id"),
                "name": srv.get("name"),
                "status": srv.get("status"),
                "task_state": srv.get("OS-EXT-STS:task_state"),
                "power_state": srv.get("OS-EXT-STS:power_state"),
                "addresses": addrs,
                "updated": srv.get("updated"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_status(client: GpuPowerClient) -> int:
    client.authenticate()
    srv = client.server_show()
    _print_server(srv)
    ok, code, detail = client.check_health(timeout=5)
    print(f"\nhealth {client.speechlab_base}/health -> ok={ok} code={code}")
    if detail:
        print(detail)
    return 0


def cmd_unshelve(client: GpuPowerClient) -> int:
    client.authenticate()
    result = client.ensure_awake()
    print(
        json.dumps(
            {
                "already_up": result.get("already_up"),
                "elapsed_sec": result.get("elapsed_sec"),
                "status": (result.get("server") or {}).get("status"),
                "name": (result.get("server") or {}).get("name"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_shelve(client: GpuPowerClient) -> int:
    client.authenticate()
    srv = client.shelve()
    _print_server(srv)
    ok, code, detail = client.check_health(timeout=5)
    print(f"\nhealth after shelve -> ok={ok} code={code}")
    if detail and not ok:
        print("(expected unreachable while frozen)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SpeechLab GPU power (Selectel OpenStack)")
    parser.add_argument(
        "command",
        choices=("status", "unshelve", "shelve"),
        help="status | unshelve (wake+health) | shelve (freeze)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    client = GpuPowerClient()
    try:
        if args.command == "status":
            return cmd_status(client)
        if args.command == "unshelve":
            return cmd_unshelve(client)
        if args.command == "shelve":
            return cmd_shelve(client)
    except GpuPowerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logging.exception("Unexpected failure")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
