#!/usr/bin/env python3
"""Transport-neutral, local login coordination protocol CLI."""

from __future__ import annotations

import argparse
import contextlib
import datetime as datetime_module
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid


PROTOCOL = "agent-login-coordination/1.0"
AUTH_METHOD = "QR_SCAN_IN_CONTROLLED_BROWSER"
MAX_ATTEMPTS = 3
DEFAULT_QR_TIMEOUT = 180
DEFAULT_INTERACTIVE_TIMEOUT = DEFAULT_QR_TIMEOUT
DEFAULT_SESSION_LEASE = 600
LOCK_WAIT_SECONDS = 5.0
LOCK_STALE_SECONDS = 30.0

FAILURE_CODES = (
    "TIMEOUT",
    "USER_CANCELLED",
    "CHALLENGE_EXPIRED",
    "VERIFICATION_FAILED",
    "SESSION_LOST",
    "HOST_NO_BROWSER",
    "AUTH_DENIED",
    "NETWORK_ERROR",
    "MFA_UNSUPPORTED",
    "MAX_ATTEMPTS_EXCEEDED",
)
RETRYABLE_FAILURES = {
    "TIMEOUT",
    "CHALLENGE_EXPIRED",
    "VERIFICATION_FAILED",
    "SESSION_LOST",
    "NETWORK_ERROR",
}
ACTIVE_PHASES = {"WAITING_FOR_USER", "VERIFYING_SESSION"}
OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
SENSITIVE_KEY_PATTERN = re.compile(
    r"^(?:password|passwd|pwd|otp|one_?time_?password|cookie|cookies|"
    r"authorization|auth_?header|local_?storage|session_?storage)$",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|otp|one[-_ ]?time[-_ ]?password|cookie|"
    r"authorization|localstorage|local_storage|sessionstorage|session_storage)"
    r"\b\s*[:=]\s*([^\s,;]+)"
)
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
SECRET_QUERY_KEYS = {
    "password",
    "passwd",
    "pwd",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "cookie",
    "session",
    "sessionid",
    "session_id",
    "code",
}
FORBIDDEN_USER_MATERIALS = [
    "SCREENSHOT",
    "PASSWORD",
    "OTP_VALUE",
    "COOKIE",
    "AUTHORIZATION_HEADER",
    "QR_IMAGE",
    "LOCAL_STORAGE",
    "SESSION_STORAGE",
]
DEFAULT_INSTRUCTION = (
    "请使用手机扫描当前已连接浏览器页面显示的登录二维码，完成后回复“已登录”。"
    "无需且请勿发送截图、二维码图片、密码、验证码、Cookie或浏览器存储内容。"
)


class ProtocolError(Exception):
    def __init__(
        self, code: str, message: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def utc_now() -> datetime_module.datetime:
    return datetime_module.datetime.now(datetime_module.timezone.utc)


def isoformat(value: datetime_module.datetime) -> str:
    return value.astimezone(datetime_module.timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime_module.datetime:
    return datetime_module.datetime.fromisoformat(value.replace("Z", "+00:00"))


def sanitize_text(value: str) -> str:
    text = SENSITIVE_ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    text = BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = JWT_PATTERN.sub("[REDACTED_JWT]", text)
    return text[:1000]


def sanitize_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ProtocolError("INVALID_URL", "origin and target URL must be HTTP(S) URLs")

    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError as exc:
        raise ProtocolError("INVALID_URL", "URL contains an invalid port") from exc
    netloc = f"{host}:{port}" if port is not None else host

    query: List[Tuple[str, str]] = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SECRET_QUERY_KEYS:
            query.append((key, "[REDACTED]"))
        else:
            query.append((key, sanitize_text(item)))
    return urlunsplit(
        (parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), "")
    )


def sanitize(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY_PATTERN.match(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): sanitize(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def validate_opaque_identifier(label: str, value: str) -> str:
    if not OPAQUE_ID_PATTERN.fullmatch(value):
        raise ProtocolError(
            "INVALID_IDENTIFIER",
            f"{label} must be an opaque identifier, not authentication material",
        )
    return value


def login_paths(case_dir: str) -> Tuple[Path, Path, Path]:
    root = Path(case_dir).expanduser().resolve() / "work" / "login"
    return root, root / "state.json", root / "events.jsonl"


@contextlib.contextmanager
def protocol_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".protocol.lock"
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    descriptor: Optional[int] = None

    while descriptor is None:
        try:
            descriptor = os.open(
                str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise ProtocolError("LOCK_TIMEOUT", "login protocol state is busy")
            time.sleep(0.05)

    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_state(state_path: Path) -> Optional[Dict[str, Any]]:
    if not state_path.exists():
        return None
    try:
        with state_path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError("STATE_UNREADABLE", "stored login state is unreadable") from exc
    if not isinstance(state, dict) or state.get("protocol") != PROTOCOL:
        raise ProtocolError("STATE_INVALID", "stored login state uses an unsupported format")
    return state


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".state-", suffix=".tmp", dir=str(path.parent)
    )
    try:
        os.chmod(temporary_name, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def append_event(events_path: Path, event: Dict[str, Any]) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        str(events_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(event, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def make_event(state: Dict[str, Any], event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if event_name == "LOGIN_REQUIRED":
        payload = dict(payload)
        payload["instruction"] = DEFAULT_INSTRUCTION
        payload["authentication_contract"] = AUTH_METHOD
        payload["forbidden_user_materials"] = list(FORBIDDEN_USER_MATERIALS)
    return sanitize(
        {
            "protocol": PROTOCOL,
            "event": event_name,
            "event_id": str(uuid.uuid4()),
            "correlation_id": state["correlation_id"],
            "case_id": state["case_id"],
            "workflow_id": state["workflow_id"],
            "checkpoint": state["checkpoint"],
            "attempt": state["attempt"],
            "issued_at": isoformat(utc_now()),
            "expires_at": state["expires_at"],
            "host_capabilities": state["host_capabilities"],
            "session": state["session"],
            "payload": payload,
        }
    )


def commit_event(
    state_path: Path,
    events_path: Path,
    state: Dict[str, Any],
    event: Dict[str, Any],
    phase: str,
) -> Dict[str, Any]:
    clean_event = sanitize(event)
    append_event(events_path, clean_event)
    state["phase"] = phase
    state["updated_at"] = isoformat(utc_now())
    state["last_event"] = clean_event
    state.setdefault("last_events", {})[clean_event["event"]] = clean_event
    atomic_write_json(state_path, sanitize(state))
    return clean_event


def failure_message(code: str) -> str:
    messages = {
        "TIMEOUT": "Login coordination timed out.",
        "USER_CANCELLED": "The user cancelled the login action.",
        "CHALLENGE_EXPIRED": "The login challenge expired.",
        "VERIFICATION_FAILED": "The host could not verify authentication in the same session.",
        "SESSION_LOST": "The original browser session is no longer available.",
        "HOST_NO_BROWSER": "The host has no controlled persistent browser session.",
        "AUTH_DENIED": "The platform denied authentication.",
        "NETWORK_ERROR": "A network error interrupted login verification.",
        "MFA_UNSUPPORTED": "The host cannot complete the platform's MFA flow.",
        "MAX_ATTEMPTS_EXCEEDED": "The maximum of three login attempts was reached.",
    }
    return messages[code]


def emit_failure(
    state_path: Path,
    events_path: Path,
    state: Dict[str, Any],
    code: str,
    retryable: Optional[bool] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    can_retry = code in RETRYABLE_FAILURES if retryable is None else retryable
    can_retry = bool(can_retry and state["attempt"] < MAX_ATTEMPTS)
    event = make_event(
        state,
        "LOGIN_FAILED",
        {
            "code": code,
            "retryable": can_retry,
            "message": sanitize_text(note) if note else failure_message(code),
            "next_action": "RETRY_LOGIN" if can_retry else "STOP",
        },
    )
    state["retryable"] = can_retry
    return commit_event(
        state_path,
        events_path,
        state,
        event,
        "FAILED" if can_retry else "BLOCKED",
    )


def expire_if_needed(
    state_path: Path, events_path: Path, state: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if state.get("phase") not in ACTIVE_PHASES:
        return None
    try:
        expired = utc_now() >= parse_datetime(state["expires_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtocolError("STATE_INVALID", "stored login expiry is invalid") from exc
    if not expired:
        return None
    return emit_failure(state_path, events_path, state, "TIMEOUT")


def assert_correlation(state: Dict[str, Any], correlation_id: str) -> None:
    if state.get("correlation_id") != correlation_id:
        raise ProtocolError(
            "CORRELATION_MISMATCH",
            "correlation_id does not match the active login cycle",
        )


def state_or_error(state_path: Path) -> Dict[str, Any]:
    state = load_state(state_path)
    if state is None:
        raise ProtocolError("STATE_NOT_FOUND", "no login protocol state exists for this case")
    return state


def command_required(args: argparse.Namespace) -> Dict[str, Any]:
    root, state_path, events_path = login_paths(args.case_dir)
    with protocol_lock(root):
        state = load_state(state_path)

        session_ref = validate_opaque_identifier("session_ref", args.session_ref)
        checkpoint = validate_opaque_identifier("checkpoint", args.checkpoint)
        supplied_correlation = (
            validate_opaque_identifier("correlation_id", args.correlation_id)
            if args.correlation_id
            else None
        )
        origin = sanitize_url(args.origin)
        target_url = sanitize_url(args.target_url)

        if state is not None:
            expire_if_needed(state_path, events_path, state)

        same_seed = bool(
            state
            and state.get("session", {}).get("session_ref") == session_ref
            and state.get("checkpoint") == checkpoint
            and state.get("provider") == args.provider
        )
        correlation_id = supplied_correlation
        if correlation_id is None and state and same_seed and state.get("phase") in {
            "WAITING_FOR_USER",
            "VERIFYING_SESSION",
            "FAILED",
        }:
            correlation_id = state["correlation_id"]
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        if state and state.get("phase") in ACTIVE_PHASES and state.get("correlation_id") != correlation_id:
            raise ProtocolError(
                "ACTIVE_LOGIN_EXISTS",
                "another login cycle is already active for this case",
            )

        if state and state.get("correlation_id") == correlation_id:
            if not same_seed:
                raise ProtocolError(
                    "FLOW_REFERENCE_MISMATCH",
                    "retry must keep session_ref, checkpoint, and provider unchanged",
                )
            if state.get("phase") == "WAITING_FOR_USER":
                previous = state.get("last_events", {}).get("LOGIN_REQUIRED")
                if previous:
                    return previous
            if state.get("phase") == "VERIFYING_SESSION":
                raise ProtocolError(
                    "VERIFICATION_PENDING",
                    "login was confirmed and must be verified before another attempt",
                )
            if state.get("phase") == "RUNNING":
                raise ProtocolError("FLOW_COMPLETE", "this login cycle already resumed")
            if state.get("phase") == "BLOCKED":
                raise ProtocolError(
                    "MAX_ATTEMPTS_EXCEEDED",
                    "this login cycle is blocked; start a new cycle only if policy permits",
                )
            if state.get("phase") == "FAILED":
                if not state.get("retryable") or state.get("attempt", 0) >= MAX_ATTEMPTS:
                    raise ProtocolError(
                        "MAX_ATTEMPTS_EXCEEDED",
                        "this login cycle cannot be retried",
                    )
                attempt = int(state["attempt"]) + 1
                created_at = state.get("created_at", isoformat(utc_now()))
                last_events = state.get("last_events", {})
            else:
                attempt = int(state.get("attempt", 0)) or 1
                created_at = state.get("created_at", isoformat(utc_now()))
                last_events = state.get("last_events", {})
        else:
            attempt = 1
            created_at = isoformat(utc_now())
            last_events = {}

        methods = list(dict.fromkeys(args.method or ["QR"]))
        timeout_seconds = args.ttl
        if timeout_seconds is None:
            timeout_seconds = (
                DEFAULT_QR_TIMEOUT
                if methods == ["QR"]
                else DEFAULT_INTERACTIVE_TIMEOUT
            )
        if not 1 <= timeout_seconds <= 3600:
            raise ProtocolError("INVALID_TIMEOUT", "ttl must be between 1 and 3600 seconds")
        if args.session_lease_seconds < timeout_seconds:
            raise ProtocolError(
                "INVALID_SESSION_LEASE",
                "session lease must be at least as long as the login timeout",
            )

        now = utc_now()
        expires_at = isoformat(now + datetime_module.timedelta(seconds=timeout_seconds))
        lease_expires_at = isoformat(
            now + datetime_module.timedelta(seconds=args.session_lease_seconds)
        )
        capabilities = {
            "ui_prompt": bool(args.ui_prompt),
            "browser_control": bool(args.browser_control),
            "session_persistence": bool(args.session_persistence),
            "async_resume": bool(args.async_resume),
        }
        state = {
            "protocol": PROTOCOL,
            "case_id": sanitize_text(args.case_id or Path(args.case_dir).resolve().name or "case"),
            "workflow_id": sanitize_text(args.workflow_id),
            "provider": sanitize_text(args.provider),
            "phase": "INITIALIZING",
            "correlation_id": correlation_id,
            "checkpoint": checkpoint,
            "attempt": attempt,
            "created_at": created_at,
            "updated_at": isoformat(now),
            "expires_at": expires_at,
            "host_capabilities": capabilities,
            "session": {
                "session_ref": session_ref,
                "origin": origin,
                "target_url": target_url,
                "lease_expires_at": lease_expires_at,
            },
            "retryable": False,
            "last_events": last_events,
        }

        if not capabilities["browser_control"] or not capabilities["session_persistence"]:
            return emit_failure(
                state_path,
                events_path,
                state,
                "HOST_NO_BROWSER",
                retryable=False,
            )

        selected_presentation = "HOST_MODAL" if capabilities["ui_prompt"] else "PLAIN_TEXT"
        event = make_event(
            state,
            "LOGIN_REQUIRED",
            {
                "provider": state["provider"],
                "reason_code": sanitize_text(args.reason_code),
                "allowed_methods": methods,
                "instruction": DEFAULT_INSTRUCTION,
                "forbidden_user_materials": FORBIDDEN_USER_MATERIALS,
                "presentation": {
                    "preferred": "HOST_MODAL",
                    "fallback": "PLAIN_TEXT",
                    "selected": selected_presentation,
                },
                "verification": {
                    "same_session_required": True,
                    "expected_url_patterns": [
                        sanitize_text(pattern)
                        for pattern in (args.expected_url_pattern or [])
                    ],
                    "required_signals": ["authenticated-page-or-account-marker"],
                },
                "retry_policy": {
                    "timeout_seconds": timeout_seconds,
                    "max_attempts": MAX_ATTEMPTS,
                    "current_attempt": attempt,
                },
            },
        )
        return commit_event(
            state_path, events_path, state, event, "WAITING_FOR_USER"
        )


def command_confirmed(args: argparse.Namespace) -> Dict[str, Any]:
    root, state_path, events_path = login_paths(args.case_dir)
    with protocol_lock(root):
        state = state_or_error(state_path)
        correlation_id = validate_opaque_identifier("correlation_id", args.correlation_id)
        assert_correlation(state, correlation_id)
        expired_event = expire_if_needed(state_path, events_path, state)
        if expired_event:
            return expired_event

        if state.get("phase") in {"VERIFYING_SESSION", "RUNNING"}:
            previous = state.get("last_events", {}).get("LOGIN_CONFIRMED")
            if previous:
                return previous
        if state.get("phase") != "WAITING_FOR_USER":
            raise ProtocolError(
                "INVALID_TRANSITION",
                f"confirmed is not valid from phase {state.get('phase')}",
            )

        event = make_event(
            state,
            "LOGIN_CONFIRMED",
            {
                "source": args.source,
                "user_action_completed": True,
                "authentication_verified": False,
                "secret_received": False,
                "next_action": "VERIFY_SAME_SESSION",
            },
        )
        return commit_event(
            state_path, events_path, state, event, "VERIFYING_SESSION"
        )


def command_failed(args: argparse.Namespace) -> Dict[str, Any]:
    root, state_path, events_path = login_paths(args.case_dir)
    with protocol_lock(root):
        state = state_or_error(state_path)
        correlation_id = validate_opaque_identifier("correlation_id", args.correlation_id)
        assert_correlation(state, correlation_id)
        expired_event = expire_if_needed(state_path, events_path, state)
        if expired_event:
            return expired_event

        previous = state.get("last_events", {}).get("LOGIN_FAILED")
        if state.get("phase") in {"FAILED", "BLOCKED"} and previous:
            if previous.get("payload", {}).get("code") == args.code:
                return previous
        if state.get("phase") not in ACTIVE_PHASES:
            raise ProtocolError(
                "INVALID_TRANSITION",
                f"failed is not valid from phase {state.get('phase')}",
            )
        return emit_failure(
            state_path,
            events_path,
            state,
            args.code,
            retryable=args.retryable,
            note=args.note,
        )


def command_resume(args: argparse.Namespace) -> Dict[str, Any]:
    root, state_path, events_path = login_paths(args.case_dir)
    with protocol_lock(root):
        state = state_or_error(state_path)
        correlation_id = validate_opaque_identifier("correlation_id", args.correlation_id)
        session_ref = validate_opaque_identifier("session_ref", args.session_ref)
        checkpoint = validate_opaque_identifier("checkpoint", args.checkpoint)
        assert_correlation(state, correlation_id)

        if state.get("phase") == "RUNNING":
            previous = state.get("last_events", {}).get("RESUME")
            if previous:
                if (
                    state.get("session", {}).get("session_ref") != session_ref
                    or state.get("checkpoint") != checkpoint
                ):
                    raise ProtocolError(
                        "FLOW_REFERENCE_MISMATCH",
                        "duplicate resume must keep session_ref and checkpoint unchanged",
                    )
                return previous

        expired_event = expire_if_needed(state_path, events_path, state)
        if expired_event:
            return expired_event
        if state.get("phase") != "VERIFYING_SESSION":
            raise ProtocolError(
                "INVALID_TRANSITION",
                f"resume is not valid from phase {state.get('phase')}",
            )
        if (
            state.get("session", {}).get("session_ref") != session_ref
            or state.get("checkpoint") != checkpoint
        ):
            return emit_failure(
                state_path,
                events_path,
                state,
                "SESSION_LOST",
                note="The verified browser session or checkpoint did not match the paused flow.",
            )
        if not args.session_verified:
            return emit_failure(
                state_path,
                events_path,
                state,
                "VERIFICATION_FAILED",
                note="Resume was requested without verified authentication in the same session.",
            )

        signals = [sanitize_text(item) for item in (args.verification_signal or [])]
        signals = [item for item in signals if item]
        if not signals:
            raise ProtocolError(
                "VERIFICATION_SIGNAL_REQUIRED",
                "at least one non-secret verification signal name is required",
            )
        event = make_event(
            state,
            "RESUME",
            {
                "session_verified": True,
                "verification_signals": signals,
                "resume_ref": str(uuid.uuid4()),
                "next_state": "RUNNING",
            },
        )
        state["retryable"] = False
        state["completed_login_cycle"] = True
        return commit_event(state_path, events_path, state, event, "RUNNING")


def command_status(args: argparse.Namespace) -> Dict[str, Any]:
    root, state_path, events_path = login_paths(args.case_dir)
    with protocol_lock(root):
        state = load_state(state_path)
        if state is None:
            return {
                "protocol": PROTOCOL,
                "response": "STATUS",
                "state": {"phase": "NONE"},
            }
        if args.correlation_id:
            correlation_id = validate_opaque_identifier(
                "correlation_id", args.correlation_id
            )
            assert_correlation(state, correlation_id)
        expire_if_needed(state_path, events_path, state)
        last_event = state.get("last_event", {})
        return sanitize(
            {
                "protocol": PROTOCOL,
                "response": "STATUS",
                "state": {
                    "case_id": state.get("case_id"),
                    "workflow_id": state.get("workflow_id"),
                    "phase": state.get("phase"),
                    "correlation_id": state.get("correlation_id"),
                    "checkpoint": state.get("checkpoint"),
                    "attempt": state.get("attempt"),
                    "expires_at": state.get("expires_at"),
                    "session_ref": state.get("session", {}).get("session_ref"),
                    "retryable": state.get("retryable", False),
                    "last_event": last_event.get("event"),
                    "last_event_id": last_event.get("event_id"),
                    "last_failure_code": (
                        last_event.get("payload", {}).get("code")
                        if last_event.get("event") == "LOGIN_FAILED"
                        else None
                    ),
                },
                "storage": {
                    "state": str(state_path),
                    "events": str(events_path),
                },
            }
        )


def add_common_case_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-dir", required=True, help="Case root directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-host login coordination protocol"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    required_parser = subparsers.add_parser(
        "required", help="Pause a workflow and request browser login"
    )
    add_common_case_argument(required_parser)
    required_parser.add_argument("--provider", required=True)
    required_parser.add_argument("--origin", required=True)
    required_parser.add_argument("--target-url", required=True)
    required_parser.add_argument("--session-ref", required=True)
    required_parser.add_argument("--checkpoint", required=True)
    required_parser.add_argument("--correlation-id")
    required_parser.add_argument("--case-id")
    required_parser.add_argument("--workflow-id", default="evidence-investigation")
    required_parser.add_argument("--reason-code", default="AUTH_REQUIRED")
    required_parser.add_argument(
        "--method",
        action="append",
        choices=("QR", "OTP", "MANUAL_SIGN_IN"),
        help="Allowed login method; repeat for more than one",
    )
    required_parser.add_argument("--ttl", type=int)
    required_parser.add_argument(
        "--session-lease-seconds", type=int, default=DEFAULT_SESSION_LEASE
    )
    required_parser.add_argument("--expected-url-pattern", action="append")
    required_parser.add_argument("--ui-prompt", action="store_true")
    required_parser.add_argument("--browser-control", action="store_true")
    required_parser.add_argument("--session-persistence", action="store_true")
    required_parser.add_argument("--async-resume", action="store_true")
    required_parser.set_defaults(handler=command_required)

    confirmed_parser = subparsers.add_parser(
        "confirmed", help="Record that the user completed the login action"
    )
    add_common_case_argument(confirmed_parser)
    confirmed_parser.add_argument("--correlation-id", required=True)
    confirmed_parser.add_argument(
        "--source",
        choices=("USER_TEXT", "HOST_MODAL", "BROWSER_SIGNAL"),
        default="USER_TEXT",
    )
    confirmed_parser.set_defaults(handler=command_confirmed)

    failed_parser = subparsers.add_parser("failed", help="Record login failure")
    add_common_case_argument(failed_parser)
    failed_parser.add_argument("--correlation-id", required=True)
    failed_parser.add_argument("--code", choices=FAILURE_CODES, required=True)
    retry_group = failed_parser.add_mutually_exclusive_group()
    retry_group.add_argument("--retryable", dest="retryable", action="store_true")
    retry_group.add_argument("--no-retryable", dest="retryable", action="store_false")
    failed_parser.set_defaults(retryable=None)
    failed_parser.add_argument(
        "--note", help="Sanitized non-secret diagnostic; never pass credentials"
    )
    failed_parser.set_defaults(handler=command_failed)

    resume_parser = subparsers.add_parser(
        "resume", help="Resume after same-session authentication verification"
    )
    add_common_case_argument(resume_parser)
    resume_parser.add_argument("--correlation-id", required=True)
    resume_parser.add_argument("--session-ref", required=True)
    resume_parser.add_argument("--checkpoint", required=True)
    resume_parser.add_argument("--session-verified", action="store_true")
    resume_parser.add_argument("--verification-signal", action="append")
    resume_parser.set_defaults(handler=command_resume)

    status_parser = subparsers.add_parser("status", help="Inspect current login state")
    add_common_case_argument(status_parser)
    status_parser.add_argument("--correlation-id")
    status_parser.set_defaults(handler=command_status)

    return parser


def print_json(value: Dict[str, Any]) -> None:
    json.dump(
        sanitize(value),
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except ProtocolError as exc:
        print_json(
            {
                "protocol": PROTOCOL,
                "response": "ERROR",
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        )
        return 2
    except OSError as exc:
        print_json(
            {
                "protocol": PROTOCOL,
                "response": "ERROR",
                "code": "IO_ERROR",
                "message": sanitize_text(str(exc)),
                "details": {},
            }
        )
        return 2
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
