# Output Template

Use this structure for full assessments. The report must read like a lawyer-facing strategy memo, not a raw checklist.

## 1. Default Deliverable

For a full assessment, create a `.docx` report unless the user expressly asks for chat-only output.

DOCX requirements:

- Title format: `知识产权高判赔诉讼路径评估报告——{权利人/品牌} vs {被诉商品/店铺/平台}`.
- Use a formal business report style: clear headings, concise paragraphs, a few high-value tables, and appendices for dense investigation records.
- Put the recommendation, obstacles, and immediate actions on page 1.
- Keep the main text readable for clients and partners. Do not overload the body with every search attempt.
- Use appendices for access logs, full search matrix, rights inventory details, evidence checklist, and source list.
- Classify facts as `已核验事实`, `强推定事实`, `待核验事实`, or `法律判断`.
- If visual product comparison is important, include side-by-side images when available; if images cannot be captured, include a feature-by-feature comparison table and state the gap.
- If the document toolchain is available, render the `.docx` to page images and visually inspect before delivery.

Chat response after generating the DOCX:

- Link only the final `.docx` unless the user asks for intermediate files.
- Mention only the core recommendation, the main caveat, and whether render QA succeeded.

## 2. Human-Friendly Report Structure

### Cover / Title Block

Include:

- Report title.
- Right holder / client.
- Accused platform, link, store or product.
- Suspected infringer(s).
- Report date.
- Status note, e.g. `初步公开检索版，待公证/官方权利核验/平台后台数据补强`.

### Executive Summary

Answer in short prose:

- Recommended primary cause of action.
- Backup causes of action.
- Recommended defendants.
- Recommended court.
- Recommended claim amount or claim range.
- Three reasons the route is strongest.
- Three evidence gaps that most affect filing value.

Do not bury the answer in tables.

### Key Facts And Current Verification Level

Use a compact table only for critical facts:

| Fact | Current level | Basis | Litigation impact |
|---|---|---|---|

Then add a short paragraph explaining the difference between what is already usable and what still needs notarization, official registry confirmation, purchase evidence, or platform data.

### Rights Inventory

Summarize both sides' rights before route selection:

- Right holder trademarks.
- Right holder patents/design patents.
- Right holder copyright/source-file assets.
- Accused-side trademarks.
- Accused-side patents/design patents.
- Accused-side copyright/source claims.

Use the detailed table in Appendix A. In the body, state which rights actually change the case strategy.

### Product / Packaging / Expression Comparison

For physical goods, this section is mandatory before route scoring.

Write a short visual conclusion first, then use a table:

| Feature | Right holder product | Accused product | Similarity and legal impact |
|---|---|---|---|
| Container / shape |  |  |  |
| Color system |  |  |  |
| Logo and brand placement |  |  |  |
| Typography and layout hierarchy |  |  |  |
| Product name and selling points |  |  |  |
| Icons / seals / claims |  |  |  |
| Images / scenes / decorations |  |  |  |
| Overall impression |  |  |  |

If the accused uses its own mark but preserves the plaintiff's distinctive visual system, state whether unfair competition should overtake trademark as the primary path.

### Route Selection

Provide a short comparative analysis of trademark, unfair competition, patent, and copyright.

Use a score table:

| Path | Score /12 | Position | Why | Main risk |
|---|---:|---|---|---|
| Trademark |  | Primary / backup / not recommended |  |  |
| Unfair competition |  | Primary / backup / not recommended |  |  |
| Patent |  | Primary / backup / not recommended |  |  |
| Copyright |  | Primary / backup / not recommended |  |  |

Then explain:

- Why the primary path wins.
- Why each backup path matters.
- What fact would change the recommendation.
- Whether claims should be parallel or primary/backup.

### Jurisdiction And Defendants

Recommend the most practical court and defendant combination.

Include:

- Candidate court A and B.
- Connection facts.
- Jurisdiction objection risk.
- Why platform is or is not a defendant.
- Whether shareholder, controller, manufacturer, seller, invoice issuer, logistics sender, or brand operator should be included.

Use short tables only where comparison helps.

### Damages And Claim Amount

Do not output a naked number. Use a model:

- Target award.
- Recommended claim amount / range.
- Primary model: sales, profit, license, contract, contribution, or statutory/discretionary basis.
- Backup model.
- Reasonable expenses.
- Punitive damages feasibility.
- Evidence needed to upgrade the amount.
- Whether the amount is aggressive, moderate, or conservative.

### Evidence Plan

Give the user a practical litigation workplan:

- What to preserve immediately.
- What to buy or notarize.
- What rights certificates/source files to request.
- What platform/backend data to seek.
- What documents to request from defendants through evidence orders.
- What expert comparison, appraisal, or test may be needed.

### Defendant Defenses And Responses

List the likely defenses and the counter-evidence:

| Defense | Likelihood | Counter-evidence | Risk after supplementation |
|---|---|---|---|

### Immediate Action List

Use time blocks:

1. Within 24 hours.
2. Within 3 days.
3. Within 1 week.
4. Before filing.
5. During litigation.

## 3. Appendices

### Appendix A: Rights Inventory Detail

| Side | Right type | Mark / patent / work | No. / identifier | Class / type | Holder | Status | Source | Fact level | Route impact |
|---|---|---|---|---|---|---|---|---|---|

State which official searches were completed, blocked, or require manual/browser verification.

### Appendix B: Access Log

| Step | Result | What it proved | Next action |
|---|---|---|---|
| URL parse |  |  |  |
| Direct open / curl |  |  |  |
| Exact search |  |  |  |
| Platform variant / endpoint |  |  |  |
| Browser / login |  |  |  |
| App / notarization |  |  |  |

If browser/login access succeeds, record visible fields: title, shop, brand field, producer, price, sales, reviews, SKU, images, and screenshots. If it fails, state the exact user action needed.

### Appendix C: Search Matrix

| Target | Query / channel | Result | Fact level | Impact | Next step |
|---|---|---|---|---|---|

Include blocked searches, especially login-only platform pages, App-only pages, hidden sales, and official registries requiring manual verification.

### Appendix D: Sales / Scale Worksheet

| Channel / link | Store / subject | Product / SKU | Visible price | Visible sales / reviews | Evidence strength | GMV / profit inference |
|---|---|---|---:|---:|---|---|

Explain deduplication, price assumptions, profit assumptions, and backend data requests.

### Appendix E: Evidence Checklist

| Proof point | Current evidence | Needed evidence | Acquisition method | Priority |
|---|---|---|---|---|
| Rights basis |  |  |  | High |
| Infringement |  |  |  | High |
| Actor chain |  |  |  | High |
| Scale / amount |  |  |  | High |
| Bad faith |  |  |  | Medium |
| Reasonable expenses |  |  |  | Medium |

### Appendix F: Sources And Basis

List:

- Public sources searched, URLs, and access date.
- User-provided screenshots, documents, product images, or login-assisted observations.
- Official registry searches completed or blocked.
- Statistical or guide basis used for route scoring and award calibration.
