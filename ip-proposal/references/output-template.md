# Output Template

Use this structure for full assessments. The report must read like a lawyer-facing strategy memo, not a raw checklist.

## 1. Default Deliverable

For a full assessment, create a `.docx` report unless the user expressly asks for chat-only output.

DOCX requirements:

- Title format: `知识产权高判赔诉讼路径评估报告——{权利人/品牌} vs {被诉商品/店铺/平台}`.
- Use a formal business report style: clear headings, concise paragraphs, a few high-value tables, and appendices for dense investigation records.
- Put the recommendation, obstacles, and immediate actions on page 1.
- Keep the main text readable for clients and partners. Do not overload the body with every search attempt.
- Use appendices for the full search matrix, rights inventory details, sales worksheet, evidence checklist, and source list.
- Do not add a standalone `取证访问记录` section or access-log appendix by default. Keep access diagnostics in working notes/evidence artifacts; mention a limitation only where it qualifies a material finding.
- Classify facts as `已核验事实`, `强推定事实`, `待核验事实`, or `法律判断`.
- If visual product comparison is important, include side-by-side images when available; if images cannot be captured, include a feature-by-feature comparison table and state the gap.
- If plaintiff/accused images are available, generate a visual contact sheet with `scripts/make_visual_contact_sheet.py` and include the image in the DOCX. If the agent cannot visually inspect it, state `视觉结论待人工/多模态复核` rather than pretending to have inspected it.
- If the document toolchain is available, render the `.docx` to page images and visually inspect before delivery.
- Before delivery, run `scripts/check_docx_formal_errors.py {report.docx}`. The report must have zero hits for object-stringification or placeholder tokens such as `[object Object]`, `[object Promise]`, `[object Array]`, `undefined`, `null`, or `NaN`. If any hit appears, inspect the source field, expand the object into readable text, regenerate the DOCX, and scan again.

DOCX generation safety:

- Convert every paragraph, list item, heading, caption, and table cell to a string intentionally.
- For structured values, write named fields such as `状态：已注册` or `证据等级：待核验`; do not rely on JavaScript/Python default string conversion.
- For arrays, join readable item strings after mapping each item to text; never join raw objects.
- For missing data, use `待核验`, `未检索到公开结果`, or `需官方核验`, not `undefined`, `null`, or empty object output.

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
- If login/image access was unresolved, use `初步线索版（用户已明确选择暂不登录/暂不提供图片）`; do not label it a completed assessment. Record the user's decision date. Without that express decision, pause instead of generating the DOCX.

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

Evidence gate: the visual conclusion must name the screenshot/contact-sheet/evidence item actually inspected. If accused-product images were not obtained, write `视觉近似尚不能判断` and do not populate similarity findings from titles, snippets, creator copy, or product descriptions.

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
- A clear statement that receiving place, purchase place, payment place, or plaintiff-arranged notarized delivery place is not being used as an independent jurisdiction basis.
- Why platform is or is not a defendant.
- Whether shareholder, controller, manufacturer, seller, invoice issuer, logistics sender, or brand operator should be included.

Use short tables only where comparison helps.

### Damages And Claim Amount

Do not output a naked or generic number. If any reliable quantity or price exists, show case-specific arithmetic.

Required outputs:

1. `已见数据下限`:
   - identify every usable unit count and price;
   - show `quantity × low price` and `quantity × high price` as a visible-GMV envelope;
   - explain whether the quantity is sold units, orders, reviews, comments, followers, stock, or store-wide total;
   - exclude non-attributable values from the primary calculation.
2. `利润敏感性`:
   - show low/base/high profit assumptions or a supported unit-cost model;
   - provide the resulting numeric profit range.
3. `诉请与目标判赔`:
   - recommended economic-damages claim;
   - reasonable-expense claim;
   - total prayer;
   - target award/range;
   - whether the position is conservative, moderate, or aggressive.
4. `备位模型与升级触发`:
   - statutory/discretionary basis;
   - punitive-damages feasibility and why;
   - exact backend sales/GMV, multi-store, bad-faith, or reputation thresholds that would change the amount.

When figures are uncertain, write a transparent range instead of choosing a hidden midpoint. Reviews, comments, followers, and store-wide totals must not be silently converted into accused-product sales.

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

### Appendix B: Search Matrix

| Target | Query / channel | Result | Fact level | Impact | Next step |
|---|---|---|---|---|---|

Include blocked searches, especially login-only platform pages, App-only pages, hidden sales, and official registries requiring manual verification.

### Appendix C: Sales / Scale Worksheet

| Channel / link | Store / subject | Product / SKU | Visible price | Visible sales / reviews | Evidence strength | GMV / profit inference |
|---|---|---|---:|---:|---|---|

Explain deduplication, price assumptions, profit assumptions, and backend data requests.

The worksheet must contain the same arithmetic used in the body:

- low-price and high-price visible-GMV calculations;
- low/base/high profit sensitivity;
- values excluded from attribution and the reason;
- proposed economic-damages claim, reasonable expenses, total prayer, and upgrade triggers.

### Appendix D: Evidence Checklist

| Proof point | Current evidence | Needed evidence | Acquisition method | Priority |
|---|---|---|---|---|
| Rights basis |  |  |  | High |
| Infringement |  |  |  | High |
| Actor chain |  |  |  | High |
| Scale / amount |  |  |  | High |
| Bad faith |  |  |  | Medium |
| Reasonable expenses |  |  |  | Medium |

### Appendix E: Sources And Basis

List:

- Public sources searched, URLs, and access date.
- User-provided screenshots, documents, product images, or login-assisted observations.
- Official registry searches completed or blocked.
- Statistical or guide basis used for route scoring and award calibration.

Appendix E must not be empty. Important online factual claims must have an access date and a clickable source URL or a precisely identified user-provided/notarized evidence item.

## 4. Evidence And Completeness Release Gate

Before delivery:

1. Run `scripts/check_docx_formal_errors.py {report.docx}`.
2. Run `scripts/check_report_evidence_gates.py {report.docx}`. If login access mattered, add `--working-notes {internal-record.md}` so the gate can audit the handoff without adding an access-log section to the report.
3. Fix every failure. Do not waive a failure by adding a generic disclaimer.
4. Confirm the executive-summary fields, evidence plan, immediate-action list, route rationale, change-trigger facts, case-specific damages arithmetic, and Appendix E contain substantive content.
5. For product/packaging cases, confirm the DOCX contains the inspected screenshot/contact sheet. If it does not, the report must be an expressly authorized preliminary clue-only report and must not contain a decisive visual-similarity conclusion or visually dependent route score.
