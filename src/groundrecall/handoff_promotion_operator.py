"""Operator-only consumption receipt for quarantined handoff promotion actions."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .handoff import consume_handoff_promotion_action
from .policy import load_policy_plugins


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="groundrecall-handoff-promotion-operator")
    parser.add_argument("store_dir"); parser.add_argument("handoff_id"); parser.add_argument("action_id")
    parser.add_argument("--policy-config", required=True); parser.add_argument("--requester-subject-id", required=True)
    parser.add_argument("--project", required=True); parser.add_argument("--realm-id", required=True)
    parser.add_argument("--promotion-target", required=True); parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--idempotency-key", required=True); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        event = consume_handoff_promotion_action(args.store_dir, args.handoff_id, action_id=args.action_id, requester_subject_id=args.requester_subject_id, project=args.project, promotion_target=args.promotion_target, confirm=args.confirm, policy_provider=load_policy_plugins(args.policy_config), realm_id=args.realm_id, idempotency_key=args.idempotency_key)
    except (OSError, ValueError, PermissionError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr); return 1
    payload = {"ok": True, "canonical_effect": "none", "event_id": event.event_id}
    print(json.dumps(payload, sort_keys=True) if args.json else f"OK: event_id={event.event_id} canonical_effect=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
