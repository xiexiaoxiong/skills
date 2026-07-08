# Access Priority

Use this ladder when a live infringement page may be blocked, dynamic, login-only, App-only, or protected by platform risk controls. The goal is to see the page efficiently and lawfully before concluding that infringement cannot be verified.

## 1. Priority Ladder

Follow the tiers in order unless a higher tier is clearly unavailable.

| Priority | Method | Use when | Stop / move on when | Evidence to keep |
|---:|---|---|---|---|
| 1 | Parse the URL and seed fields | Always | Item ID, SKU, shop ID, title/query, share params extracted | Sanitized URL, IDs, decoded query terms |
| 2 | Direct web open / sanitized curl | Public PC/H5 page may render | Login redirect, x5/risk page, 403, empty shell, or no product fields | HTTP result, final URL, title/error |
| 3 | Exact public search | Direct page blocked | Exact ID/title/shop/company search has no useful result or only unrelated results | Search terms, result URLs/snippets |
| 4 | Platform variants and public endpoints | Taobao/Tmall/PDD/JD pages often expose fragments | Two or three targeted attempts show login/risk/403/404 | Endpoint tried, response type, useful JSON/text |
| 5 | Browser rendering | Curl/search fail or page is JS-heavy | Page loads, or reaches login/security verification; if login/security appears, immediately move to user-assisted login | Screenshot, visible text, title, URL, main images |
| 6 | User-assisted login/session | Browser reaches platform login/security page, App-only page, or risk-control page that a normal user can lawfully pass | User cannot or does not authenticate; do not bypass | Post-login page text, screenshots, no credentials |
| 7 | App/miniprogram notarization | Web still cannot show details or litigation proof is needed | N/A | Notarized browsing, purchase, chat, payment, logistics, unpacking |
| 8 | Court/platform investigation | Sales/backend/owner data hidden | N/A | Requests for orders, GMV, refunds, account holder, link history |

## 2. Efficiency Rules

- Do not spend excessive time repeating curl once the same platform returns login/risk/403 twice.
- For Taobao/Tmall/Pinduoduo/Douyin-style pages, move to browser rendering early after extracting item ID and trying exact search.
- Search exact IDs first (`itemId`, `goods_id`, `skuId`, shop ID), then title/product/store/company terms.
- Prefer logged-in normal browsing, user-assisted login, or App notarization over brittle unofficial scraping when the page is important.
- When browser rendering reaches a platform login, QR scan, SMS, CAPTCHA, device check, or risk-control page, ask the user to complete that step in the visible browser/App before drafting the route recommendation.
- If browser access succeeds, immediately capture structured fields and visual evidence; do not keep browsing aimlessly.
- If visible sales exist, record them before scrolling because platform pages may change layout or lazy-load.
- Download or snapshot main product images when they determine trademark use, trade dress, or design similarity.

## 3. Legal And Safety Boundaries

- Do not bypass passwords, CAPTCHAs, SMS/face verification, device binding, or platform access controls.
- Do not extract stored credentials or cookies from a user profile without explicit user instruction.
- It is acceptable to use a browser session the user has opened or authenticated in, and to ask the user to complete login in the browser/App.
- Keep account identifiers out of the final report unless they are necessary and approved; focus on the product/store evidence.

## 4. Platform Hints

### Taobao/Tmall

Most efficient order:

1. Extract `id`, `skuId`, shop hints, title/search params.
2. Try sanitized PC/mobile links and exact ID search.
3. Try a small number of known detail endpoints; if x5/risk/login appears, stop repeating.
4. Use browser rendering. If redirected to Taobao login/security verification, ask for user login or use an already authenticated browser session.
5. Capture title, shop, brand field, model, producer, price, sold count, reviews, SKU options, main images, links, and screenshots.

### Pinduoduo

Most efficient order:

1. Extract `goods_id`, share title/query, shop hints.
2. Try sanitized mobile URL and exact ID search.
3. If H5 returns `needLogin` or a front-end shell, switch to App/miniprogram notarization.
4. Capture title, shop, price, sold count/拼单, reviews, SKU, customer service, purchase, logistics.

### JD

Most efficient order:

1. Try direct web page and exact SKU search.
2. If JD redirects to login or risk verification, open a visible browser window and ask the user to scan/login; do this before concluding that the product cannot be verified.
3. After user-assisted access, capture shop type, comments, price, invoice/seller, business license.
4. Use purchase/invoice/logistics to connect seller and source.

### Douyin/Kuaishou/Xiaohongshu

Most efficient order:

1. Search account/product card/title and external indexed pages.
2. Use App-side browsing for sales, live clips, store qualification, follower data.
3. Preserve videos and product cards before takedown risk.

## 5. Required Access Log

For blocked or dynamic pages, output a concise log:

| Step | Result | What it proved | Next action |
|---|---|---|---|
| URL parse |  |  |  |
| Curl/web open |  |  |  |
| Search |  |  |  |
| Endpoint/API |  |  |  |
| Browser/login |  |  |  |
| App/notarization |  |  |  |

Do not state "cannot verify" until the applicable steps have been tried or a specific user action is required.
