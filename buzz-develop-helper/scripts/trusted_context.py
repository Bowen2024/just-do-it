"""Verified Buzz host event context for capability-bearing tool calls.

The model never supplies these claims.  A Buzz host signs one short-lived
envelope for the admitted event; the tool host verifies it once and keeps the
result in memory for the lifetime of the turn.  Tool request dictionaries do
not contain principals, roles, projects, channels, messages, or recipients.

This module deliberately contains verification only.  Production signing
belongs in Buzz's event-admission boundary, before prompt construction.  Tests
construct envelopes with the standard-library HMAC primitive directly.
"""

from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import threading
import time


SCHEMA_VERSION = 1
MAX_LIFETIME_SECONDS = 300
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_VERIFIED_SEAL = object()

READ_TOOLS = frozenset({
    "artifact.inspect",
    "artifact.preview-register",
    "collaboration.inspect",
})
MAIN_TOOLS = frozenset({
    "artifact.register",
    "confirmation.confirm-current",
    "handoff.prepare",
    "handoff.record-sent",
})
REQUIREMENTS_TOOLS = frozenset({
    "requirements.context",
    "requirements.save-draft",
    "requirements.inspect-prd",
    "requirements.save-prd-draft",
})
SOLUTION_TOOLS = frozenset({
    "solution.context",
    "solution.inspect",
    "solution.save-tech-spec-draft",
})
RECIPIENT_TOOLS = frozenset({"handoff.verify-receipt"})

ROLE_TOOL_CEILINGS = {
    "main": READ_TOOLS | MAIN_TOOLS,
    "requirements": READ_TOOLS | REQUIREMENTS_TOOLS,
    "solution": READ_TOOLS | SOLUTION_TOOLS,
    "ui": READ_TOOLS,
    "recipient": READ_TOOLS | RECIPIENT_TOOLS,
}

PAYLOAD_FIELDS = frozenset({
    "schema_version",
    "provider",
    "authority",
    "project_id",
    "agent_principal_id",
    "agent_authority",
    "agent_role",
    "channel_id",
    "session_id",
    "root_event_id",
    "event_id",
    "user_principal_id",
    "event_time",
    "statement",
    "recipient",
    "tools",
    "issued_at",
    "expires_at",
    "nonce",
})


def canonical_payload(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


_STATEMENT_WHITESPACE = frozenset("\n\r\t")


def _required_text(value, label):
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError(f"{label} 必须是非空单行文本")
    return value.strip()


def required_statement(value, label="statement"):
    """Keep the admitted event body. Newlines are valid; other controls are not."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空文本")
    if any(ord(char) < 32 and char not in _STATEMENT_WHITESPACE for char in value):
        raise ValueError(f"{label} 含有非法控制字符")
    return value.strip()


@dataclass(frozen=True)
class RecipientBinding:
    principal_id: str
    authority: str


@dataclass(frozen=True)
class ExpectedTurn:
    """Host-owned call-site fence; never populate it from tool arguments."""

    provider: str
    authority: str
    project_id: str
    agent_principal_id: str
    agent_authority: str
    user_principal_id: str
    channel_id: str
    session_id: str
    root_event_id: str
    event_id: str
    recipient_principal_id: str | None = None
    recipient_authority: str | None = None


@dataclass(frozen=True)
class TrustedEventContext:
    provider: str
    authority: str
    project_id: str
    agent_principal_id: str
    agent_authority: str
    agent_role: str
    channel_id: str
    session_id: str
    root_event_id: str
    event_id: str
    user_principal_id: str
    event_time: str
    statement: str
    recipient: RecipientBinding | None
    tools: frozenset
    issued_at: int
    expires_at: int
    nonce: str
    _seal: object

    def __post_init__(self):
        if self._seal is not _VERIFIED_SEAL:
            raise PermissionError("可信事件上下文必须由宿主验签器产生")

    @property
    def message_id(self):
        return self.event_id

    def require_tool(self, tool_name):
        if tool_name not in self.tools:
            raise PermissionError(f"当前宿主身份未获工具 capability：{tool_name}")

    def require_main(self):
        if self.agent_role != "main":
            raise PermissionError("只有宿主绑定的 Main principal 可取得 Main capability")


def require_verified(context):
    if not isinstance(context, TrustedEventContext) or context._seal is not _VERIFIED_SEAL:
        raise PermissionError("操作只接受已验签的 Buzz 宿主事件上下文")
    return context


class HostContextVerifier:
    """Verify a host envelope with key material unavailable to tool requests."""

    def __init__(self, verification_key, *, clock=None):
        if not isinstance(verification_key, bytes) or len(verification_key) < 32:
            raise ValueError("宿主上下文验签密钥至少需要 32 字节")
        self._key = verification_key
        self._clock = clock or (lambda: int(time.time()))
        self._seen_nonces = {}
        self._nonce_lock = threading.Lock()

    def verify(self, envelope, *, expected_turn):
        if not isinstance(expected_turn, ExpectedTurn):
            raise PermissionError("expected_turn 必须来自 Buzz 宿主调用边界")
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            raise PermissionError("宿主事件信封格式无效")
        payload = envelope.get("payload")
        signature = envelope.get("signature")
        if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS:
            raise PermissionError("宿主事件声明字段不完整或包含未知字段")
        if not isinstance(signature, str) or not SHA256_RE.fullmatch(signature):
            raise PermissionError("宿主事件签名格式无效")
        actual = hmac.new(self._key, canonical_payload(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual, signature):
            raise PermissionError("宿主事件签名不匹配")

        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("不支持的宿主事件 schema_version")
        issued_at, expires_at = payload.get("issued_at"), payload.get("expires_at")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise ValueError("宿主事件有效期必须是整数时间戳")
        if expires_at <= issued_at or expires_at - issued_at > MAX_LIFETIME_SECONDS:
            raise ValueError("宿主事件有效期无效或超过 5 分钟")
        now = int(self._clock())
        if now < issued_at or now > expires_at:
            raise PermissionError("宿主事件上下文尚未生效或已经过期")
        if not NONCE_RE.fullmatch(str(payload.get("nonce", ""))):
            raise ValueError("宿主事件 nonce 无效")

        text_fields = (
            "provider", "authority", "project_id", "agent_principal_id",
            "agent_authority", "agent_role", "channel_id", "session_id",
            "root_event_id", "event_id", "user_principal_id", "event_time",
        )
        normalized = {field: _required_text(payload.get(field), field) for field in text_fields}
        normalized["statement"] = required_statement(payload.get("statement"))
        if not TIMESTAMP_RE.fullmatch(normalized["event_time"]):
            raise ValueError("event_time 必须是 UTC ISO-8601 时间")
        role = normalized["agent_role"]
        ceiling = ROLE_TOOL_CEILINGS.get(role)
        tools = payload.get("tools")
        if ceiling is None or not isinstance(tools, list) or len(set(tools)) != len(tools):
            raise PermissionError("宿主角色或工具集合无效")
        if any(not isinstance(tool, str) or tool not in ceiling for tool in tools):
            raise PermissionError("宿主为当前角色签发了越权工具")

        recipient_value = payload.get("recipient")
        recipient = None
        if recipient_value is not None:
            if not isinstance(recipient_value, dict) or set(recipient_value) != {
                "principal_id", "authority"
            }:
                raise ValueError("指定接收者绑定无效")
            recipient = RecipientBinding(
                _required_text(recipient_value.get("principal_id"), "recipient principal_id"),
                _required_text(recipient_value.get("authority"), "recipient authority"),
            )
        if any(tool in tools for tool in ("handoff.prepare", "handoff.record-sent")) and recipient is None:
            raise PermissionError("交接 capability 必须绑定指定接收者")

        comparisons = {
            "provider": expected_turn.provider,
            "authority": expected_turn.authority,
            "project_id": expected_turn.project_id,
            "agent_principal_id": expected_turn.agent_principal_id,
            "agent_authority": expected_turn.agent_authority,
            "user_principal_id": expected_turn.user_principal_id,
            "channel_id": expected_turn.channel_id,
            "session_id": expected_turn.session_id,
            "root_event_id": expected_turn.root_event_id,
            "event_id": expected_turn.event_id,
        }
        for field, expected in comparisons.items():
            if normalized[field] != expected:
                raise PermissionError(f"宿主事件与当前调用边界不匹配：{field}")
        actual_recipient = (
            (recipient.principal_id, recipient.authority) if recipient is not None else (None, None)
        )
        expected_recipient = (
            expected_turn.recipient_principal_id, expected_turn.recipient_authority
        )
        if actual_recipient != expected_recipient:
            raise PermissionError("宿主事件与当前指定接收者不匹配")

        nonce_key = (normalized["provider"], normalized["authority"], payload["nonce"])
        with self._nonce_lock:
            self._seen_nonces = {
                key: expiry for key, expiry in self._seen_nonces.items() if expiry >= now
            }
            if nonce_key in self._seen_nonces:
                raise PermissionError("宿主事件 nonce 已被使用")
            self._seen_nonces[nonce_key] = expires_at

        return TrustedEventContext(
            **normalized,
            recipient=recipient,
            tools=frozenset(tools),
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=payload["nonce"],
            _seal=_VERIFIED_SEAL,
        )
