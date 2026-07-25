# Host login adapter

## Contract

The adapter connects protocol events to a host's browser and UI. It must not expose authentication material to the workflow.

```text
capabilities() -> {
  ui_prompt: boolean,
  browser_control: boolean,
  session_persistence: boolean,
  async_resume: boolean
}

present_login(login_required_event) -> user completion or cancellation
verify_login(session_ref, verification_spec) -> verification result
resume_workflow(resume_event) -> idempotent acknowledgement
```

The host generates `session_ref` as an opaque local identifier for an already controlled browser/profile/tab. It must not be a Cookie, access token, browser-storage value, or serialized authentication state.

## Required host behavior

1. Keep the same browser session and tab context alive from `LOGIN_REQUIRED` through verification.
2. Render `HOST_MODAL` when `ui_prompt=true`; otherwise use `PLAIN_TEXT`.
3. First, check whether the current controlled browser session is already authenticated on the target domain. If authenticated, emit `RESUME` directly. If still unauthenticated, show the platform QR code in the controlled browser and tell the user only to scan it with a phone, then reply or click “已登录”.
4. Never ask for a screenshot, password, OTP value, Cookie, QR image, authorization header, or browser-storage export.
5. If the platform does not present a usable QR challenge, stop the login cycle; do not switch to a password/OTP workflow or screenshot handoff.
6. Treat the user signal as `LOGIN_CONFIRMED`, not as proof of authentication.
7. Verify login in the same `session_ref`, using non-secret observations such as an authenticated account marker, disappearance of the login wall, or an expected authenticated URL.
8. Call `resume` with the original `correlation_id`, `session_ref`, and `checkpoint` only after verification succeeds.
9. Make workflow resumption idempotent by `event_id` or `payload.resume_ref`.

## Presentation adapters

### Modal-capable host

Map `LOGIN_REQUIRED.payload` to a blocking or asynchronous host modal:

- Title: `<provider> 登录`
- Body: `payload.instruction` plus the statement that only the QR code visible in the controlled browser may be scanned.
- Primary action: `已登录`
- Secondary action: `取消`
- Timeout: `payload.retry_policy.timeout_seconds`

The modal must not contain fields for credentials, OTP values, screenshots, file upload, cookies, or browser storage.

Primary action emits `LOGIN_CONFIRMED` with `source=HOST_MODAL`. Secondary action emits `LOGIN_FAILED` with `USER_CANCELLED`.

### Plain-text host

Print `payload.instruction` while the QR code remains visible in the controlled browser, and wait for a semantic confirmation equivalent to “已登录”. Do not ask the user to paste any authentication data or send a screenshot. Emit `LOGIN_CONFIRMED` with `source=USER_TEXT`.

Plain-text fallback requires both `browser_control=true` and `session_persistence=true`. Without them, emit `LOGIN_FAILED/HOST_NO_BROWSER` instead of inventing a screenshot-based handoff.

## Verification adapter

Verification stays inside the host-controlled browser:

```text
on LOGIN_CONFIRMED:
  assert current_session_ref == event.session.session_ref
  result = inspect_current_page_without_exporting_credentials()

  if session was replaced or lost:
      emit LOGIN_FAILED(code=SESSION_LOST)
  else if authenticated marker and URL checks pass:
      emit RESUME(
        correlation_id=original correlation_id,
        checkpoint=original checkpoint,
        session_ref=original session_ref,
        verification_signals=[non-secret signal names]
      )
  else:
      emit LOGIN_FAILED(code=VERIFICATION_FAILED)
```

Verification signals are labels such as `account-marker`, `login-wall-absent`, or `authenticated-url`. Do not put DOM dumps, headers, cookies, tokens, or storage values in a signal.

## CLI mapping

The host may invoke `scripts/login_protocol.py` as a subprocess and parse the single JSON object written to stdout.

| Host action | CLI command |
| --- | --- |
| Authentication wall detected | `required` |
| User clicks or replies “已登录” | `confirmed` |
| User cancels or verification fails | `failed` |
| Same browser session verifies successfully | `resume --session-verified` |
| Host recovers after restart | `status` |

Use `state.json` only for protocol recovery. The browser session remains host-owned; the CLI cannot recreate it. If the host restarts and loses the session, report `SESSION_LOST`.

## Retry ownership

The protocol enforces at most three attempts for a `correlation_id`. After a retryable `LOGIN_FAILED`, the host may invoke `required` again with the same correlation and same session/checkpoint. Attempt four is rejected. A non-retryable failure transitions to `BLOCKED`.

## Security boundary

The adapter may only let the user scan the platform QR code shown in the controlled browser. It must not solicit or handle passwords, OTP values, screenshots, copied QR images, or exported authentication state, and it must never place authentication material in:

- Event JSON
- CLI arguments
- `state.json`
- `events.jsonl`
- Logs or diagnostic messages

If a host receives a secret through an unintended channel, discard it and emit only a sanitized failure description. Do not echo it back.
