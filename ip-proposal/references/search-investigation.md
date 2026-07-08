# Search Investigation

Use this reference before selecting the litigation route. The purpose is to turn sparse clues into a fact record: what exists online, what sales scale can be inferred, who controls the chain, and which right basis has the best damages upside.

For blocked live pages, first follow `access-priority.md`. Search results are useful, but they do not replace a successful page view, browser screenshot, App notarization, or platform backend data.

## 1. Seed Signal Extraction

Extract every searchable token from the user's clues and any provided file:

| Signal type | Examples | Why it matters |
|---|---|---|
| Right holder | company name, brand Chinese/English names, product line, official store | right chain, reputation, official price, first use |
| Target link | platform, item ID, URL parameters, share title, query parameter, snapshot count, shop ID | link preservation, platform backend request, search expansion |
| Product | product name, category, SKU, barcode, package text, specs, image features, packaging color/layout/container shape/logo placement | similarity, trade dress, price, profit proxy, comparable products |
| Store/account | shop name, account name, verified title, platform ID, customer service name | seller identity, repeated stores, jurisdiction |
| Suspected infringer | company names, individuals, addresses, phones, labels, logistics sender, invoice issuer | defendants, joint liability, collectability |
| Time | first review, launch date, share timestamp, complaint date, production date | priority, influence, bad faith, limitation period |
| Scale | sales, reviews, followers, rankings, stock, multi-platform listings, ads | high-damages feasibility |

If the live page is inaccessible, still extract item IDs, query terms, encoded titles, share timestamps, and platform clues from the URL.

## 2. Search Matrix

For a full assessment, search or propose searches in these buckets. Do not treat the user's existing scheme as a substitute for this step.

| Bucket | Search targets | Example query patterns | Result affects |
|---|---|---|---|
| Link preservation | direct URL, canonical URL, item ID, shop page, cache/share pages | `"item_id"`, `"goods_id"`, platform URL without share params | infringement existence, notarization scope |
| Platform product search | Pinduoduo, Taobao/Tmall, JD, Douyin, Kuaishou, 1688, Xiaohongshu, WeChat channels, Baidu/Bing indexed pages | `brand + product`, `infringer + product`, `shop name + SKU`, `barcode/spec + product` | whole-network scale, repeated conduct, defendant utility |
| Sales and traffic | sales count, reviews, followers, ranking, bestseller badges, ad pages, live commerce clips | `"shop name" "销量"`, `"product" "已拼"`, `"抖音" "销量"`, `"京东" "评价"` | damages model, high-award feasibility |
| Right holder reputation | official site, flagship stores, annual reports, media, awards, ads, product launch | `right holder + product + 上市`, `brand + 年报`, `brand + 销售额`, `brand + 广告` | influence/reputation, price/profit proxy |
| IP rights | CNIPA trademark/patent, copyright registration, product design materials | `brand + 商标`, `product + 专利`, `packaging + 作品登记` | route eligibility and backup claims |
| Accused-side rights | accused brand/company trademark, design patent, copyright/source claims | `accused brand + 商标`, `accused company + 专利`, `accused product + 外观设计` | defenses, bad-faith filing, invalidation needs |
| Company chain | National Enterprise Credit Information Publicity System, official filings, labels, third-party clues | `company + 法定代表人`, `company + 地址`, `company + 商标`, `company + 店铺` | defendants, shareholders, jurisdiction, collectability |
| Prior conduct | judgments, administrative penalties, platform complaints, repeated listings | `company + 商标侵权`, `company + 不正当竞争`, `brand + 投诉`, `shop + 下架` | bad faith, punitive/酌定 factors |
| Jurisdiction | defendant domicile, seller location, platform operator, centralized IP rules | `court + 知识产权 管辖`, `city + 知识产权案件 管辖` | court selection and objection risk |

## 3. Platform-Specific Sales Investigation

Use platform-native access where possible. Public search snippets are only clues; App/miniprogram notarization or platform backend data is stronger.

| Platform | What to capture | High-damages clues |
|---|---|---|
| Pinduoduo | goods ID, title, shop, price, sold count/拼单, reviews, SKU, share snapshot, customer service, order/payment/logistics | high public sold count, many SKUs, official/flagship naming, repeated links |
| Taobao/Tmall | title, shop operator, monthly sales, reviews, SKU price, Wangwang/chat, business license | flagship store, multiple hot listings, long review history |
| JD | shop name, self-operated/third-party, comments, SKU, business license, invoice | comments and SKU history, invoice issuer |
| Douyin/Kuaishou | product card, live/video sales, store, account followers, videos, shop qualification | live sales clips, follower scale, repeated campaigns |
| 1688 | manufacturer storefront, MOQ, monthly transactions, factory identity | source manufacturing, production capacity, wholesale scale |
| Xiaohongshu/WeChat/Baidu | promotion posts, consumer confusion, search results, official claims | confusion, publicity, traffic diversion |

When platform pages hide sales or require login, state the limitation and require:

- App-side notarized browsing and purchase.
- Trusted timestamp screenshots/videos where notarization is not immediately available.
- Court investigation order for backend orders, GMV, refunds, ads, traffic, account holder, and historical listings.

## 4. Sales Scale Table

Create a working table before choosing the amount:

| Channel/link | Seller/store | Product/SKU | Visible price | Visible sales/reviews | Time range | Evidence strength | GMV/profit inference |
|---|---|---|---:|---:|---|---|---|

Rules:

- Use visible public sales only as a medium-strength estimate.
- Deduplicate links that point to the same SKU/store when possible.
- Track whether the value is sales count, reviews, comments, "已拼", ranking, followers, or backend order data.
- Apply a conservative price if the platform shows a range.
- Separate gross sales, refunds, platform fees, and profit rate assumptions.
- If multiple platforms are found under the same controller, aggregate only after explaining the subject connection.

## 5. Result-To-Strategy Rules

Use search results to update the route, not merely decorate the report.

| Search result | Strategic effect |
|---|---|
| Target uses right holder's mark in title/brand field/package/store | trademark score rises; trademark may become primary |
| Target uses own brand but copies package/trade dress/product presentation | unfair competition score rises; trademark usually backup |
| Target omits the exact mark but visually imitates plaintiff packaging | do not downgrade on text search alone; build a side-by-side visual comparison and evaluate trade dress/unfair competition first |
| Valid patent found and accused product can be compared | patent becomes viable; require claim/design chart |
| Accused owns later trademark/design rights | evaluate defense, filing date, bad faith, invalidation/cancellation, and whether unfair competition remains stronger |
| Packaging artwork/detail images copied and source files exist | copyright backup improves |
| Multi-platform stores, wholesale source, high sales, long reviews | high-damages feasibility rises; add source defendants |
| Only one low-sales retail listing found | claim amount should be conservative; focus on evidence preservation |
| Official annual report/ads/sales prove right holder reputation | influence/reputation proof strengthens trademark or unfair competition |
| Company chain shows one-person companies, same controller, same address/phone | add shareholders/affiliates or plead joint liability |
| Platform inaccessible or hidden sales | do not invent facts; require notarization and platform data preservation |

## 6. Minimum Search Output

Every full assessment must include:

- Access priority steps attempted when live pages were blocked.
- Rights inventory for both right holder and accused side, including official searches completed or blocked.
- Search terms/targets actually used or that must be used next.
- Sources found, access date, and fact level.
- Sales/scale findings by channel.
- Searches that failed or were blocked.
- How the search results changed route score, defendants, jurisdiction, or amount.
