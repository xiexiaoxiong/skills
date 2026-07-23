# Access Priority

Use this ladder when a live infringement page may be blocked, dynamic, login-only, App-only, or protected by platform risk controls. The goal is to see the page efficiently and lawfully before concluding that infringement cannot be verified.

## 0. Meaning Of Interactive Access And The Hard Stop

- Read `interactive-login-handoff.md` when a page may require authentication. `可见交互访问` only counts when the user can see and operate the same persistent browser/app session that the agent can inspect after login.
- Select by capability, not vendor: native browser/OpenClaw browser control, Computer Use, headed persistent Playwright, or an equivalent visible UI surface may qualify. Curl, web open, scraping, HTML fetches, search results, headless Playwright, and closed one-shot sessions do not.
- Before the first interactive action, load the applicable tool instructions and obtain a persistent page/window/session handle. Do not claim the tier was attempted without verifying visibility, user operability, persistence, and post-login reinspection.
- If no qualifying surface exists, record `可见交互表面不可用—需用户启用浏览器/Computer Use/有头 Playwright` and stop the full assessment. Ask the user to enable one or provide screenshots/App evidence.
- If login, QR scan, SMS, CAPTCHA, device check, or risk control appears, leave that page open, ask the user to complete the step, and wait for an explicit confirmation such as `已登录`. Do not close the tab and do not draft the route recommendation while waiting.
- If the user declines or cannot authenticate, offer only two lawful next steps: App/miniprogram notarization or an explicitly authorized `初步线索版`. A preliminary clue-only report must not score or decide packaging similarity from text descriptions.

## 1. Priority Ladder

Follow the tiers in order unless a higher tier is clearly unavailable.

| Priority | Method | Use when | Stop / move on when | Evidence to keep |
|---:|---|---|---|---|
| 1 | Parse the URL and seed fields | Always | Item ID, SKU, shop ID, title/query, share params extracted | Sanitized URL, IDs, decoded query terms |
| 2 | Direct web open / sanitized curl | Public PC/H5 page may render | Login redirect, x5/risk page, 403, empty shell, or no product fields | HTTP result, final URL, title/error |
| 3 | Exact public search | Direct page blocked | Exact ID/title/shop/company search has no useful result or only unrelated results | Search terms, result URLs/snippets |
| 4 | Platform variants and public endpoints | Taobao/Tmall/PDD/JD pages often expose fragments | Two or three targeted attempts show login/risk/403/404 | Endpoint tried, response type, useful JSON/text |
| 5 | Visible interactive access | Curl/search fail or page is JS-heavy | Prefer native/OpenClaw browser, Chrome DevTools MCP, or Playwright MCP; then use the bundled headed Playwright CDP handoff when its probe passes, then Computer Use. If authentication appears, immediately move to the hard-stop login step | Surface/tool, persistent session handle/state file, screenshot, visible text, title, final URL, main images |
| 6 | User-assisted login/session (pause gate) | The visible persistent surface reaches platform login/security, App-only, or risk-control state | Resume only after the user confirms authentication and the agent reinspects the same session; if the user cannot/declines, do not bypass and do not finalize a full assessment | Handoff prompt, user confirmation, post-login reinspection and capture, no credentials |
| 7 | App/miniprogram notarization | Web still cannot show details or litigation proof is needed | N/A | Notarized browsing, purchase, chat, payment, logistics, unpacking |
| 8 | Court/platform investigation | Sales/backend/owner data hidden | N/A | Requests for orders, GMV, refunds, account holder, link history |

## 2. Efficiency Rules

- Do not spend excessive time repeating curl once the same platform returns login/risk/403 twice.
- For Taobao/Tmall/Pinduoduo/Douyin-style pages, move to visible interactive access early after extracting item ID and trying exact search.
- Do not make Google a single point of failure. Use the platform's own search when permitted, then Baidu, Bing, Sogou/360 or another locally available public search surface; record which surface produced each clue. Search snippets remain clue-level evidence.
- Capability-probe configured Chrome DevTools MCP and Playwright MCP before falling back to the bundled adapter. Use headed mode and dedicated persistent task profiles. When those are unavailable across Codex/OpenClaw, run `scripts/headed_playwright_handoff.mjs probe`; if ready, use its task-specific headed Chrome/CDP state file so another agent can resume the same login session.
- Search exact IDs first (`itemId`, `goods_id`, `skuId`, shop ID), then title/product/store/company terms.
- Prefer logged-in normal browsing, user-assisted login, or App notarization over brittle unofficial scraping when the page is important.
- When the interactive surface reaches a platform login, QR scan, SMS, CAPTCHA, device check, or risk-control page, first focus/show the persistent window, then ask the user to complete that step before drafting the route recommendation.
- Asking is not enough: pause and wait for the user's confirmation. A later report cannot convert `未登录` into `浏览器已核验`.
- Never infer visual packaging features from titles, snippets, creator copy, or product descriptions. Record those only as textual clues.
- If browser access succeeds, immediately capture structured fields and visual evidence; do not keep browsing aimlessly.
- If visible sales exist, record them before scrolling because platform pages may change layout or lazy-load.
- Download or snapshot main product images when they determine trademark use, trade dress, or design similarity.

## 3. Legal And Safety Boundaries

- Do not bypass passwords, CAPTCHAs, SMS/face verification, device binding, or platform access controls.
- Do not use Playwright or another tool to evade a runtime's explicit URL/safety prohibition. The adapter expands compatible surfaces; it does not override policy.
- Do not extract stored credentials or cookies from a user profile without explicit user instruction.
- It is acceptable to use a browser session the user has opened or authenticated in, and to ask the user to complete login in the browser/App.
- Keep account identifiers out of the final report unless they are necessary and approved; focus on the product/store evidence.

## 4. Platform Hints

### Taobao/Tmall

Most efficient order:

1. Extract `id`, `skuId`, shop hints, title/search params.
2. Try sanitized PC/mobile links and exact ID search.
3. Try a small number of known detail endpoints; if x5/risk/login appears, stop repeating.
4. Use visible interactive access. If redirected to Taobao login/security verification, perform the login handoff or use an already authenticated visible persistent session.
5. Capture title, shop, brand field, model, producer, price, sold count, reviews, SKU options, main images, links, and screenshots.

### Pinduoduo

Most efficient order:

1. Extract `goods_id`, share title/query, shop hints.
2. Try sanitized mobile URL and exact ID search.
3. If H5 returns `needLogin` or a front-end shell, open it through a qualifying visible interactive surface. If login/security appears, perform the login handoff and pause.
4. If the page remains App-only after user-assisted browser access, switch to App/miniprogram notarization.
5. Capture title, shop, price, sold count/拼单, reviews, SKU, customer service, purchase, logistics, main images, and screenshots.

### JD

Most efficient order:

1. Try direct web page and exact SKU search.
2. If JD redirects to login or risk verification, open a visible browser window and ask the user to scan/login; do this before concluding that the product cannot be verified.
3. After user-assisted access, capture shop type, comments, price, invoice/seller, business license.
4. Use purchase/invoice/logistics to connect seller and source.

### Douyin/Kuaishou/Xiaohongshu

Most efficient order:

1. Capability-probe platform-native MCP tools under `platform-mcp-investigation.md`; use Xiaohongshu MCP for note/profile search after the visible login gate.
2. Search account/product card/title and external indexed pages.
3. Use visible Chrome DevTools MCP, headed Playwright MCP, native browser control, or App-side browsing for sales, live clips, store qualification, and follower data.
4. Preserve videos and product cards before takedown risk.

### Weibo

Most efficient order:

1. Use Weibo MCP content/user/topic search and preserve stable status IDs, account IDs, dates, engagement fields, and media URLs.
2. Open material results through a browser MCP or visible browser when the underlying page affects reputation, confusion, bad faith, or scale.
3. Treat keyword collisions and social engagement as clues; do not convert them into sales.

## 5. Required Working Access Record

For blocked or dynamic pages, keep a concise internal working record:

| Step | Surface / artifact | Result | What it proved | Next action |
|---|---|---|---|---|
| URL parse | Sanitized URL / IDs |  |  |  |
| Curl/web open | HTTP result / final URL |  |  |  |
| Search | Query / result URL |  |  |  |
| Endpoint/API | Endpoint / response type |  |  |  |
| Visible interactive access | Tool/surface + persistent session + screenshot |  |  |  |
| User login handoff | Prompt + user confirmation + same-session post-login capture |  |  |  |
| App/notarization | Evidence package |  |  |  |

Do not state "cannot verify" until the applicable steps have been tried or a specific user action is required.

Do not state `可见交互访问已尝试` unless the log identifies the tool/surface and proves the four-condition contract. If login remains unresolved, the next action is a user-facing pause, not report generation.

Do not insert this table as a standalone report section or appendix unless the user expressly requests it or a material conclusion must be qualified. The client report should state the resulting fact, evidence item, and any outcome-relevant limitation—not the operational retry history.
