# Rights Search Methods

Use this reference at the start of every real target assessment. The goal is to know what rights both sides hold before deciding whether trademark, unfair competition, patent, or copyright is the strongest route.

## 1. Required Search Order

1. Normalize names and clues:
   - Right holder company names, Chinese/English brands, product line, official store names, product names, package text, SKU/model, and logo variants.
   - Accused store name, company/operator, accused brand, product title, package text, manufacturer, invoice issuer, logistics sender, and any label names.
2. Search right holder rights:
   - Trademarks.
   - Patents, including invention/utility/design patents.
   - Copyright registrations, source files, packaging artwork, photos, videos, software, product copy, and design files.
3. Search accused-side rights:
   - Own trademarks or design patents that may be used as a defense.
   - Accused brand ownership, filing dates, classes, validity, and bad-faith filing clues.
4. Collect plaintiff and accused product/packaging images and compare visual features before route scoring.
5. Classify every result as `已核验`, `强推定`, or `待核验`; do not treat third-party databases as final proof when an official certificate or registry extract is needed.

## 2. Trademark Search

Primary official source:

- China Trademark Online Search: `https://sbj.cnipa.gov.cn/sbj/sbcx/`
- Use browser/manual access if curl is blocked. Search by mark name, applicant/registrant, registration/application number, and class.
- Capture: mark image/text, registration number, class, goods/services, applicant/registrant, status, application/registration dates, renewal, assignment/change, invalidation/cancellation, and official URL/screenshot.

International and fallback sources:

- WIPO Global Brand Database: `https://branddb.wipo.int/branddb/en/`
  - Current behavior observed: ALTCHA/human verification. Use browser/manual query; do not assume stable automated access.
- TMview: `https://www.tmdn.org/tmview/welcome`
  - Current behavior observed: SPA loads; frontend exposes search paths such as `/search/results`, filters under `/search/filter/...`, and fields including `basicSearch`, `appName`, `applicationNumber`, `registrationNumber`, `niceClass`, `tmStatus`, `tmType`.
  - Use browser query first. Treat direct API calls as experimental unless a tested request body is available.
- Search engine fallback:
  - `"brand" "商标" "申请人"`
  - `"brand" "申请/注册号"`
  - `"right holder" "brand" "商标"`
  - `"accused brand" "商标" "申请人"`

Trademark decision impact:

- Exact or similar mark on same/similar goods: trademark score rises.
- Accused owns a mark but copies plaintiff packaging: do not stop at trademark; evaluate unfair competition.
- Accused mark filing after plaintiff reputation or near-copy packaging: bad-faith and confusion evidence.

## 3. Patent And Design Search

Primary official sources:

- CNIPA patent search / China and Global Patent Examination Information: use CNIPA official browser access.
- Search by patent number, application number, publication number, patentee, inventor, product name, and package/product design words.
- Capture: patent type, application/publication/grant number, title, patentee, filing date, grant date, legal status, annuity, claims/drawings/design views, evaluation report if needed.

Fallback sources:

- Google Patents: `https://patents.google.com/`
  - Useful for bibliographic data, family members, PDFs, claims, and clue-level legal status.
  - Search by exact number, title words, applicant, and technology terms. Do not blindly convert application numbers into publication numbers.
  - Treat Google legal status and assignee fields as clues; confirm through CNIPA before filing.
- WIPO Global Design Database: `https://designdb.wipo.int/designdb/en/index.jsp`
  - Current behavior observed: page loads; frontend uses `/designdb/jsp/select.jsp`, with holder field `HOL`, product field `PROD`, number fields `ANS/RNS`, source filter including `CNID`.
  - Direct bare Solr-style parameters returned `INVALID_INPUT`; use browser query unless frontend request format is fully tested.
- Espacenet: `https://worldwide.espacenet.com/`
  - Current behavior observed: Cloudflare challenge in curl. Use browser if needed.
- WIPO PATENTSCOPE: `https://patentscope.wipo.int/search/en/search.jsf`
  - Current behavior observed: curl returned 403 in the tested environment. Use browser if needed.

Patent decision impact:

- Valid design patent plus product/packaging appearance comparison: patent may become primary or strong backup.
- Invention/utility patent on ingredients or structure: require product test, ingredient proof, or claim chart; do not use as main path from marketing copy alone.
- Accused owns a design patent: evaluate filing date, novelty, invalidation risk, and whether it is a shield or bad-faith filing clue.

## 4. Copyright Search

Primary evidence usually comes from the party, not public search:

- Copyright registration certificate, work sample, source files, drafts, PSD/AI files, photo EXIF/raw files, video project files, software source, publication/launch records, author employment or assignment contracts.
- For product packaging, collect packaging artwork, label design, official product images, detail-page images, and advertising materials.

Public and official lookup routes:

- China Copyright Protection Center / CPCC and local copyright registration platforms, where available.
- National Copyright Administration pages and registration agency directories.
- Software copyright registration announcements where available.
- Search engine fallback:
  - `"work name" "作品登记"`
  - `"registration number" "著作权"`
  - `"right holder" "作品著作权"`
  - `"software name" "软著"`

Known limitation:

- Copyright registries are fragmented and public query access may be incomplete or blocked. If no public result is found, ask for certificates/source files instead of treating copyright as unavailable.

Copyright decision impact:

- Packaging artwork/detail images copied with source files or registration: copyright backup improves.
- Only generic product photos or short functional copy: copyright damages are usually weak.
- Bulk image/video/software copying or high license price: copyright may become primary.

## 5. Packaging And Product Visual Comparison

For physical goods, build a side-by-side comparison after rights search:

| Feature | Plaintiff | Accused | Importance |
|---|---|---|---|
| Container shape |  |  | source impression/design |
| Color system |  |  | trade dress |
| Logo position |  |  | confusion |
| Typography hierarchy |  |  | overall impression |
| Product-name placement |  |  | trade dress |
| Icons/seals/claims |  |  | bad faith/copying |
| Model/scene images |  |  | detail-page copying |
| Package/product structure |  |  | design patent/trade dress |

If the accused product uses its own mark but preserves the plaintiff's distinctive visual system, evaluate unfair competition first and trademark second.

## 6. Minimum Rights Inventory Table

Output this table before path scoring:

| Side | Right type | Mark/patent/work | No./identifier | Class/type | Holder | Status | Source | Fact level | Route impact |
|---|---|---|---|---|---|---|---|---|---|
| Right holder | Trademark |  |  |  |  |  |  |  |  |
| Right holder | Patent/design |  |  |  |  |  |  |  |  |
| Right holder | Copyright |  |  |  |  |  |  |  |  |
| Accused | Trademark |  |  |  |  |  |  |  |  |
| Accused | Patent/design |  |  |  |  |  |  |  |  |
| Accused | Copyright |  |  |  |  |  |  |  |  |

## 7. Access Discipline

- If official sites block curl or require human verification, use visible browser/user-assisted access and record the barrier.
- Do not bypass CAPTCHA, login, or anti-bot measures.
- Use third-party databases as clues, then require official registry screenshots/certificates before filing.
- A failed public search is not proof that no right exists; it creates a certificate-request or official-browser verification task.
