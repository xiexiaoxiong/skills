# Cross-host login coordination protocol

## 1. Purpose

This protocol lets an evidence workflow pause for authentication in a host-owned browser, ask the user only to complete the login action, verify that the same browser session is authenticated, and resume from the same checkpoint.

The protocol is transport-neutral. A desktop app may render a modal, while a terminal host may print plain text. Neither the protocol nor the CLI depends on a Codex-specific API.

## 2. Non-negotiable rules

- The only supported user authentication action is scanning the QR code visibly displayed by the platform in the current controlled browser.
- Before presenting QR, the host may first check whether the current controlled session is already authenticated; if so, resume directly.
- Never ask the user to take, upload, or send a screenshot.
- Never request or persist a password, one-time password, Cookie, authorization header, QR image, `localStorage`, or `sessionStorage` content.
- Never switch to password, OTP, copied QR image, exported authentication state, or a screenshot handoff when QR login is unavailable.
- The host owns the browser and authentication material. The protocol receives only an opaque `session_ref`.
- `session_ref`, `checkpoint`, and `correlation_id` stay unchanged from `LOGIN_REQUIRED` through `RESUME`.
- `LOGIN_CONFIRMED` means only that the user says the login action is complete. It is not proof of authentication.
- Emit `RESUME` only after the host verifies authentication in the same browser session.

The standard user instruction is:

> 请使用手机扫描当前已连接浏览器页面显示的登录二维码，完成后回复“已登录”。无需且请勿发送截图、二维码图片、密码、验证码、Cookie或浏览器存储内容。

## 3. State machine

```text
RUNNING
  -> LOGIN_REQUIRED
  -> WAITING_FOR_USER
  -> LOGIN_CONFIRMED
  -> VERIFYING_SESSION
  -> RESUME
  -> RUNNING

WAITING_FOR_USER or VERIFYING_SESSION
  -> LOGIN_FAILED
  -> FAILED (retryable) or BLOCKED (not retryable / attempts exhausted)
```

`LOGIN_CONFIRMED` never skips verification. If verification fails, emit `LOGIN_FAILED` with `VERIFICATION_FAILED` or `SESSION_LOST`.

## 4. Events

All events conform to [`login-event.schema.json`](./login-event.schema.json).

| Event | Producer | Meaning |
| --- | --- | --- |
| `LOGIN_REQUIRED` | Workflow | Authentication is required and the workflow is paused. |
| `LOGIN_CONFIRMED` | Host | The user completed the requested interaction; verification is still required. |
| `LOGIN_FAILED` | Host or protocol | Login cannot continue, expired, or verification failed. |
| `RESUME` | Host | The same session was verified and execution may continue at the checkpoint. |

Every event carries:

- `protocol`: `agent-login-coordination/1.0`
- `event_id`: immutable unique event identifier
- `correlation_id`: one login cycle, including retries
- `case_id` and `workflow_id`
- `checkpoint`: paused workflow checkpoint
- `attempt`: 1 through 3
- `issued_at` and `expires_at`
- `host_capabilities`
- `session.session_ref`: opaque host-generated label, never a credential
- `session.origin`, `session.target_url`, and `session.lease_expires_at`
- Event-specific `payload`

## 5. Presentation negotiation

`LOGIN_REQUIRED.payload.presentation` always declares:

```json
{
  "preferred": "HOST_MODAL",
  "fallback": "PLAIN_TEXT",
  "selected": "HOST_MODAL"
}
```

Select `HOST_MODAL` when the host exposes a user prompt surface. Otherwise select `PLAIN_TEXT`. Plain text is valid only when the host still controls a persistent browser session. If there is no controlled persistent browser, emit `LOGIN_FAILED` with `HOST_NO_BROWSER`; do not ask for a screenshot as a workaround.

## 6. Retry, timeout, and idempotency

- QR scan timeout: 180 seconds. Manual-login and OTP-flow handoffs are unsupported.
- Maximum attempts per `correlation_id`: 3.
- A retry keeps `correlation_id`, `session_ref`, and `checkpoint`, and increments `attempt`.
- Repeating `required` while the same request is waiting returns the original `LOGIN_REQUIRED` event without appending a duplicate.
- Repeating `confirmed`, `failed`, or `resume` after that transition returns the previously committed matching event.
- A duplicate `RESUME` is safe and does not run a second transition.
- A new login cycle must use a new `correlation_id`.

Recommended failure codes:

`TIMEOUT`, `USER_CANCELLED`, `CHALLENGE_EXPIRED`, `VERIFICATION_FAILED`, `SESSION_LOST`, `HOST_NO_BROWSER`, `AUTH_DENIED`, `NETWORK_ERROR`, `MFA_UNSUPPORTED`.

## 7. Local persistence

For a case directory `<case>`, the CLI writes only sanitized protocol data:

```text
<case>/work/login/state.json
<case>/work/login/events.jsonl
```

`state.json` is replaced atomically. `events.jsonl` is append-only. Both are written with owner-only permissions where supported. A short-lived local lock serializes writers.

URLs have user information, fragments, and known secret query parameters removed or redacted before persistence. Free-text diagnostics are redacted for password, OTP, Cookie, authorization, browser-storage, bearer-token, and JWT patterns.

## 8. CLI

The implementation is [`../scripts/login_protocol.py`](../scripts/login_protocol.py). Each command writes exactly one JSON object to stdout. Invalid command/state transitions return a JSON error object and a nonzero exit code.

Start a login pause:

```bash
python3 scripts/login_protocol.py required \
  --case-dir /path/to/case \
  --provider jd \
  --origin https://www.jd.com \
  --target-url https://item.jd.com/10220925150279.html \
  --session-ref chrome:tab:42 \
  --checkpoint defendant-product.seed \
  --browser-control \
  --session-persistence \
  --ui-prompt
```

Record the user's completion signal:

```bash
python3 scripts/login_protocol.py confirmed \
  --case-dir /path/to/case \
  --correlation-id CORRELATION_ID
```

After verification in the same browser session, resume:

```bash
python3 scripts/login_protocol.py resume \
  --case-dir /path/to/case \
  --correlation-id CORRELATION_ID \
  --session-ref chrome:tab:42 \
  --checkpoint defendant-product.seed \
  --session-verified \
  --verification-signal account-marker
```

Report a failure or inspect current state:

```bash
python3 scripts/login_protocol.py failed \
  --case-dir /path/to/case \
  --correlation-id CORRELATION_ID \
  --code VERIFICATION_FAILED

python3 scripts/login_protocol.py status --case-dir /path/to/case
```

Do not pass secrets through any CLI argument. The CLI intentionally provides no password, OTP, Cookie, QR-image, or browser-storage argument.
