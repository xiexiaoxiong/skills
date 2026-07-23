# Interactive Login Handoff

Use this protocol whenever a target page reaches login, QR scan, SMS, CAPTCHA, device verification, security review, or another user-completable access control. It is capability-based so Codex, OpenClaw, and other agents can implement it with different tools.

## 1. Four-Condition Contract

An access surface qualifies only when all four conditions are true:

1. **Visible**: the user can see the browser/app window, not merely a screenshot or headless page.
2. **User-operable**: the user can click and type in that exact window.
3. **Persistent**: the window and page/session remain alive while the agent waits for the user's reply.
4. **Resumable**: after the user says `已登录`, the agent can inspect the same page/session and capture post-login evidence.

If any condition fails, do not call it browser rendering or interactive access.

## 2. Capability Selection

Use the first available qualifying option; tool names may differ by agent runtime.

| Order | Capability | Qualification rule |
|---:|---|---|
| 1 | Native browser control, Chrome extension, in-app browser, or OpenClaw browser tool | Must expose a user-visible tab/window and preserve a page/session handle across turns |
| 2 | Chrome DevTools MCP | Must run headed, use a dedicated persistent task profile, expose a visible Chrome page, and preserve the page/session for post-login reinspection |
| 3 | Playwright MCP | Must run headed, use Chrome or another visible local browser with a dedicated persistent task profile, and preserve the same tab/context |
| 4 | Headed Playwright or equivalent browser automation | Prefer the bundled CDP handoff adapter when MCP/native browser control is absent; it must use a task profile, visible local browser, loopback-only CDP, and a state file that another agent can resume |
| 5 | Computer Use / desktop UI control | Open or foreground the system browser/app, navigate to the URL, verify the visible login page, and leave the app open |
| 6 | System default browser launcher paired with UI observation | Valid only if the agent can later inspect/control the same window through Computer Use or an equivalent observer |

If only headless browsing, URL fetching, scraping, isolated screenshots, or a launcher without post-login readback is available, the interactive gate is unavailable. Stop and request another surface, screenshots, or App/notarization evidence.

## 3. Surface Adapters

### Native or OpenClaw browser control

- Select visible/show-UI mode when the tool exposes such an option.
- Open the target URL in a persistent tab and retain the browser/tab/session handle.
- Capture the visible login state before asking the user to act.
- Do not substitute a headless fetch merely because it returns page text.

### Computer Use

- Target a browser or platform app through the desktop UI.
- Navigate by using the visible address bar/UI and foreground the window.
- Reinspect the app state to verify that the login page is actually visible.
- Stop before credentials, QR scan, CAPTCHA, SMS, face verification, or device approval; the user performs those actions.
- Leave the app open and reuse the same window after the user confirms.

### Chrome DevTools MCP

- Leave headless mode off and use a dedicated `--user-data-dir`; never attach to the user's default Chrome profile.
- Open/focus the login page in visible Chrome, retain the page identifier, and capture the pre-login screenshot/snapshot.
- After `已登录`, select the same page and capture the post-login URL, title, visible fields, and screenshot.
- Keep any debugging connection loopback-only. Do not expose CDP to the LAN or internet.
- If the server can auto-connect to a user-opened Chrome, the user must see and approve the connection, and the agent must avoid unrelated tabs.

### Playwright MCP

- Playwright MCP is headed by default; do not add `--headless` for login handoff.
- Prefer `--browser=chrome` and a dedicated persistent `--user-data-dir`.
- Keep the MCP/browser process alive across the user's response, retain the tab identity, and capture a post-login snapshot/screenshot.
- Use separate profile directories for Playwright MCP and Chrome DevTools MCP to avoid profile locks and cross-session leakage.
- If the MCP client cannot keep the stdio process alive while waiting, it does not qualify; use native browser control, Computer Use, or the bundled detached CDP adapter.

### Headed Playwright

- Run `node scripts/headed_playwright_handoff.mjs probe` first. If Playwright is missing, run `bash scripts/setup_headed_playwright.sh` only when dependency installation is allowed, then probe again.
- Launch a visible local Chrome/Edge/Chromium instance with a task-specific profile and loopback-only CDP. Use `scripts/headed_playwright_handoff.mjs`; do not improvise a one-shot headless process.
- Use a task-specific profile directory unless the user explicitly authorizes an existing profile. Never inspect cookies, local storage, saved passwords, or profile files.
- Persist `state-file`, `profile-dir`, and `evidence-dir` paths in working notes. The state file contains only local connection metadata; never add cookies, storage state, credentials, or tokens.
- Keep the browser process open while waiting. Another Codex/OpenClaw/CLI agent may resume it by passing the same state file to `status`, `snapshot`, or `navigate`.
- Bind CDP only to `127.0.0.1`; never expose a debugging port to the LAN or internet.
- If the orchestrator cannot preserve a process and the detached CDP browser cannot be reached after the user's reply, this adapter does not qualify. Use Computer Use/native browser or stop.

Portable sequence from the skill root:

```bash
node scripts/headed_playwright_handoff.mjs probe
node scripts/headed_playwright_handoff.mjs start \
  --url 'https://target.example/' \
  --profile-dir '/absolute/task/profile' \
  --evidence-dir '/absolute/task/evidence' \
  --state-file '/absolute/task/handoff.json' \
  --startup-timeout-ms 45000

# Pause for the user. After the user says 已登录:
node scripts/headed_playwright_handoff.mjs status --state-file '/absolute/task/handoff.json'
node scripts/headed_playwright_handoff.mjs snapshot \
  --state-file '/absolute/task/handoff.json' \
  --page-host 'target.example' \
  --label post-login
```

The `start` command must return a `preLogin` screenshot/capture. The post-login `snapshot` must return a new title, URL, screenshot, and visible-text capture from the same CDP browser before the access gate is marked successful.

Chrome startup can take longer than 15 seconds on a busy Mac or a cold profile. The adapter therefore waits 45 seconds by default; `--startup-timeout-ms` accepts 5000–120000 milliseconds. Increase it only when the visible browser is still starting, not to mask a dead process or blocked CDP connection.

When the persistent browser contains several tabs or a click opens a new tab, first run `status`, then use `--page-host 'host.example'` with `snapshot`, `navigate`, `click-text`, or `fill-selector` so another agent targets the intended page instead of whichever tab was most recently active. The two interaction helpers are intentionally narrow and evidence-oriented:

```bash
node scripts/headed_playwright_handoff.mjs click-text \
  --state-file '/absolute/task/handoff.json' \
  --page-host 'target.example' \
  --text '商品评价' \
  --label reviews-opened

node scripts/headed_playwright_handoff.mjs fill-selector \
  --state-file '/absolute/task/handoff.json' \
  --page-host 'target.example' \
  --selector 'input[name="keyword"]' \
  --value '备案号' \
  --label query-prefilled
```

`click-text` defaults to exact visible text; pass `--exact false` only when a unique substring is safer. `fill-selector` may prefill an ordinary search field but must stop before CAPTCHA, SMS, QR, face verification, password, consent, purchase, submission, or another consequential step. Each command captures a screenshot and visible-text JSON after the action.

Some agent sandboxes deny loopback networking even though the visible Chrome process is still alive. If `status` reports `healthy: false` inside a restricted sandbox, rerun `status`/`snapshot` with the runtime's approved local-loopback or escalation mechanism before declaring the session lost. Never broaden CDP beyond `127.0.0.1` to work around that sandbox.

Use `navigate` only for ordinary read-only navigation after access is established. Do not use it to bypass a CAPTCHA, platform risk control, tool safety restriction, or an authentication wall. If a runtime explicitly forbids automation on a URL, do not switch to Playwright merely to evade that restriction; use another permitted evidence route or user-supplied/App-notarized evidence.

### System browser launcher

- Opening the URL in the user's default browser can create the popup, but it is not sufficient by itself.
- Pair it with Computer Use or another UI observer so the agent can verify the login page and resume the same window.
- Without post-login readback, treat any user screenshot as user-provided evidence and do not claim agent-verified page access.

## 4. Required Handoff Sequence

1. Open and foreground the visible login page.
2. Verify the four-condition contract and capture the pre-login state.
3. Send this message, adapted only for platform/surface names:

   `已在【{surface}】打开【{platform}】登录页，并会保持窗口不关闭。请在弹出的窗口中亲自完成登录/验证；完成后回复“已登录”，我再继续采集商品页面。请不要把密码或验证码发给我。`

4. Pause. Do not draft or score the visually dependent route while waiting.
5. After the user says `已登录`, inspect the same page/session.
6. If login is still shown, tell the user the verification has not completed and keep waiting.
7. If access succeeds, immediately capture final URL/title, product/store/price/sales/SKU fields, main images, and screenshots.

## 5. Safety Boundaries

- Never type, request, reveal, store, or extract passwords, SMS codes, face data, saved credentials, cookies, tokens, or browser profile secrets.
- Never solve or bypass CAPTCHA, QR, device binding, security warnings, or access controls. Hand those steps to the user.
- Never call `storageState()`, export cookies, copy a normal browser profile, or attach Playwright to the user's default Chrome profile.
- Do not accept unexpected permissions, terms, purchases, or other consequential actions as part of login.
- Keep account identifiers out of the report unless necessary and approved.

## 6. Required Working Access Record

Record these exact labeled fields in working notes/evidence artifacts:

- `登录交接方式：{native browser | OpenClaw browser | Chrome DevTools MCP | Playwright MCP | Computer Use | headed Playwright | other}`
- `可见窗口：是/否`
- `会话保持：是/否；session/tab/window identifier`
- `交接提示时间：{timestamp}`
- `用户确认：已登录/未登录/拒绝登录；{timestamp}`
- `登录后复核：成功/仍为登录页/会话丢失`
- `登录后证据：{screenshot/path/evidence identifier}`

Only `是 + 是 + 已登录 + 成功 + evidence` satisfies the gate.

Do not place this operational record in the client report by default. Include only the resulting evidence and any limitation that materially changes the recommendation; add a standalone access section only when the user expressly requests it.
