# Platform MCP And Browser Investigation

Use this reference for cross-agent platform investigation. It is capability-based so Codex, OpenClaw, and other MCP-capable agents can follow the same order without depending on Google or paid AgentKey credits.

## 1. Required Routing Order

Probe capabilities before searching. Use the first suitable read-only route and keep a fallback ready:

1. Purpose-built official database/API or configured Qichacha MCP for rights, company, judicial, and regulatory facts.
2. Platform-native MCP:
   - Xiaohongshu MCP for login status, note search, note detail, user profile, images, and engagement fields.
   - Weibo MCP for content/user/topic search, profiles, feeds, comments, and engagement fields.
3. Browser MCP:
   - Chrome DevTools MCP for a visible Chrome window, existing task profile, DOM/network inspection, screenshots, and login handoff.
   - Playwright MCP for a headed Chrome window, persistent task profile, screenshots, snapshots, network logs, and repeatable page navigation.
4. Native browser/OpenClaw browser control or permitted Computer Use.
5. Platform search, Baidu, Bing, Sogou/360, and other locally available public engines.
6. AgentKey only as optional enrichment when the user has credits and the result cannot be obtained through the routes above.

Do not make Google or AgentKey a single point of failure. Missing AgentKey credits are not a blocker and are not an investigation failure.

## 2. Capability Probe

At the start of a full assessment:

1. List configured MCP servers or available tools.
2. Look for capability names rather than exact vendor prefixes:
   - Xiaohongshu: login status, QR code, note/feed search, note detail, user profile.
   - Weibo: content search, user search, profile, feeds, topics, comments.
   - Chrome DevTools: list/new/select/navigate page, snapshot, screenshot, DOM evaluation, network requests.
   - Playwright: navigate, tabs, snapshot, screenshot, click/type/fill, network requests.
3. Run a read-only health check or `tools/list`.
4. Record the server name/version and probe result in working notes, not in the client report.
5. If a server is configured but unavailable, continue with the next route. Do not convert an auth, quota, startup, or transport error into `未检索到相关事实`.

## 3. Persistent Cross-Agent Configuration

Names may differ, but use stable logical names: `xiaohongshu`, `weibo`, `chrome-devtools`, and `playwright`.

Example local MCP declarations:

```toml
[mcp_servers.xiaohongshu]
url = "http://127.0.0.1:18060/mcp"

[mcp_servers.weibo]
command = "/absolute/path/to/mcp-server-weibo"
args = ["stdio"]

[mcp_servers.chrome-devtools]
command = "/absolute/path/to/npx"
args = ["-y", "chrome-devtools-mcp@<pinned-version>", "--user-data-dir=/absolute/task-profile/chrome", "--no-usage-statistics", "--no-performance-crux"]

[mcp_servers.playwright]
command = "/absolute/path/to/npx"
args = ["-y", "@playwright/mcp@<pinned-version>", "--browser=chrome", "--user-data-dir=/absolute/task-profile/playwright", "--output-mode=file", "--save-session", "--snapshot-mode=full"]
```

Cross-agent requirements:

- Pin tested package versions in durable machine configuration. Review updates intentionally instead of silently changing the investigation environment mid-case.
- Use a dedicated evidence profile, not the user's default Chrome profile.
- Use a different profile directory for Chrome DevTools MCP and Playwright MCP; a persistent profile can be held by only one browser process at a time.
- Keep output and profile directories outside the Git repository. Never commit cookies, login state, QR data, screenshots containing unrelated personal information, or browser profiles.
- For an HTTP Xiaohongshu MCP used by OpenClaw through MCPorter, add the local HTTP endpoint only after the service is running and test `tools/list`. Native MCP support is preferred when available.
- Never bind MCP HTTP or Chrome debugging ports to a LAN/public interface. Use `127.0.0.1` or the runtime's loopback-only equivalent.

## 4. Visible Login Hard Gate

Read `interactive-login-handoff.md` before authentication. The user must see and operate the same persistent session the agent will inspect afterward.

### Xiaohongshu MCP

1. Run the service in headed mode when supported, such as `-headless=false`, and prefer a visible local Chrome executable.
2. Call the read-only login-status tool.
3. If not logged in, call the QR/login tool.
4. If the MCP returns only a Base64 QR image, the agent must display that image in the conversation or open it in a visible local browser/window. A hidden tool payload does not count as a login handoff.
5. Ask the user to scan/confirm, wait, then call login status again in the same service session.
6. Only after successful reinspection may the agent search notes or profiles.

Xiaohongshu allows one web login for the same account at a time in common configurations. Do not open a competing web login that would invalidate the MCP session.

### Chrome DevTools MCP

- Leave headless mode off.
- Use a dedicated persistent `--user-data-dir`.
- Open/focus the target login page and retain the page identifier.
- If the runtime supports Chrome 144+ auto-connect, user permission must still be visible and explicit.
- Never expose or inspect unrelated tabs from a normal user profile.

### Playwright MCP

- Playwright MCP is headed by default; do not pass `--headless` for evidence login handoff.
- Use Chrome with a dedicated persistent `--user-data-dir`.
- Keep the browser process alive while waiting for the user.
- After `已登录`, reselect the same tab and capture a new snapshot/screenshot before continuing.

If an MCP client cannot preserve a visible browser or display a QR image, use native browser control, Computer Use, or the bundled `headed_playwright_handoff.mjs`. If none qualifies, pause instead of drafting a visually dependent conclusion.

## 5. Read-Only Investigation Workflow

### Xiaohongshu

Search exact and broad variants:

- right-holder brand;
- accused brand/store/product;
- both brands together;
- distinctive product or packaging phrase;
- product category plus accused brand;
- account/store names and company names.

For each relevant note, preserve:

- note ID and canonical URL;
- title/text excerpt as a paraphrase;
- author/account and profile ID;
- publication date;
- like, favorite, comment, and share counts;
- product/packaging images;
- whether the note is official promotion, paid/affiliate promotion, consumer commentary, or unrelated noise;
- access date and screenshot/evidence identifier.

### Weibo

Use content search, user search, topics, profiles, feeds, and comments as needed. For each relevant result, preserve:

- status/feed ID and canonical `https://m.weibo.cn/status/{id}` URL;
- text as a short paraphrase;
- account name and UID;
- publication date;
- repost, comment, and attitude counts;
- image/video URLs when material;
- whether the result supports reputation, promotion, accused-product sales, confusion, or merely a keyword collision.

### Browser MCPs

Use Chrome DevTools or Playwright to:

- open underlying posts/product pages instead of relying on snippets;
- capture visible title, account/store, price, sold units, reviews, SKU, producer, labels, and main images;
- preserve final URL, page title, timestamp, screenshot, and relevant network/DOM fields;
- recheck the page after login in the same persistent session.

Browser automation must stop before passwords, SMS, CAPTCHA, QR scanning, face verification, purchases, submissions, comments, likes, favorites, follows, posting, or account changes. Those actions require the user's direct action or separate authorization.

## 6. Fact-Level And Report Rules

- Platform MCP result with a stable ID/URL and visible fields: `已核验事实（公开平台数据）`, subject to preservation and later platform confirmation.
- Search result without the underlying page: `线索` or `强推定事实`, depending on specificity.
- Keyword collision, ambiguous account, or missing stable ID: `待核验`.
- Engagement counts are not sales.
- Reviews/comments are not sold units unless the platform expressly labels them as orders/sales.
- Store-wide totals cannot be attributed to one accused listing.
- Social posts may prove promotion, reputation, market presence, or confusion clues; they rarely prove transaction volume by themselves.

Keep tool health, login steps, retries, blocked pages, and session metadata in working notes/evidence artifacts. The client report should contain relevant findings, limitations, and sources, but no standalone `取证访问记录` or access-log appendix unless the user requests it or a material conclusion requires that explanation.

## 7. AgentKey Rule

AgentKey is optional and low priority for this skill:

- do not call it when platform-native MCPs, Chrome/Playwright, local browser control, official databases, or public engines can answer the question;
- do not ask the user to recharge merely to complete the standard workflow;
- if it is used, label the provider/source and independently open important underlying pages;
- never treat `insufficient credits`, auth failure, or provider unavailability as proof that no relevant result exists.
