"""Dispatch one collaboration tool call for a host-verified turn.

Identity comes from the host-signed turn file and process-private env, never
from tool arguments. This script is launched only by `buzz-acp collab-mcp`.
"""

from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_tools
import trusted_context


def _load_foundation():
    root = Path(os.environ["BUZZ_COLLAB_HELPER_ROOT"]).expanduser().resolve()
    if not (root / "config/local.json").is_file():
        raise PermissionError("协作工具未绑定融合层 helper root")
    return root


def _expected_turn(payload):
    recipient = payload.get("recipient") or {}
    return trusted_context.ExpectedTurn(
        provider=payload["provider"],
        authority=payload["authority"],
        project_id=payload["project_id"],
        agent_principal_id=os.environ["BUZZ_COLLAB_AGENT_PRINCIPAL"],
        agent_authority=os.environ["BUZZ_COLLAB_AGENT_AUTHORITY"],
        user_principal_id=payload["user_principal_id"],
        channel_id=payload["channel_id"],
        session_id=payload["session_id"],
        root_event_id=payload["root_event_id"],
        event_id=payload["event_id"],
        recipient_principal_id=recipient.get("principal_id"),
        recipient_authority=recipient.get("authority"),
    )


def _verified_context():
    key = bytes.fromhex(os.environ["BUZZ_COLLAB_HMAC_KEY"])
    envelope = json.loads(Path(os.environ["BUZZ_COLLAB_TURN_PATH"]).read_text(encoding="utf-8"))
    verifier = trusted_context.HostContextVerifier(key)
    return verifier.verify(envelope, expected_turn=_expected_turn(envelope["payload"]))


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: collab_invoke.py <tool-name>")
    arguments = json.loads(sys.stdin.read() or "{}")
    if arguments is None:
        arguments = {}
    context = _verified_context()
    surface = host_tools.HostToolSurface(context, _load_foundation())
    result = surface.call(sys.argv[1], arguments)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.stderr.write(str(error) + "\n")
        raise SystemExit(1)
