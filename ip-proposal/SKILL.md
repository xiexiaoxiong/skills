---
name: ip-proposal
description: Generate a plaintiff-side PRC IP litigation proposal report from a right holder, infringement link/store/product/content, suspected infringer, platform, or evidence clues. Use when the user needs investigation-driven rights inventory, interactive login handoff for blocked platform pages across browser tools, Computer Use, or headed Playwright, packaging/expression comparison, trademark/unfair competition/patent/copyright path selection, damages, jurisdiction, defendants, evidence strategy, and a human-readable DOCX proposal.
---

# IP-Proposal

## Overview

Use this skill to convert sparse infringement clues into a plaintiff-side IP litigation proposal. The skill compares four rights bases: trademark, unfair competition, patent, and copyright.

The output must not merely list options. It must recommend a **primary path**, identify **backup paths**, and explain why other paths are weaker.

For a full case assessment, the default deliverable is a human-readable legal strategy report in `.docx` format, unless the user asks for another format. The chat response should be a short delivery note; put the substantive assessment in the document.

## Required References

For every full assessment, read these files before drafting the final scheme:

- `references/workflow.md`: investigation workflow and fact hierarchy.
- `references/access-priority.md`: priority ladder for accessing blocked platform pages and deciding when to move from curl/search to browser/login/notarization.
- `references/interactive-login-handoff.md`: tool-agnostic login handoff protocol for Codex, OpenClaw, Computer Use, headed Playwright, and other agents with a persistent visible UI.
- `references/rights-search-methods.md`: first-step trademark, patent, copyright, and accused-rights search methods, source priorities, and fallbacks.
- `references/search-investigation.md`: clue expansion, public search matrix, sales/scale investigation, and result-to-strategy rules.
- `references/platform-mcp-investigation.md`: cross-agent routing for Xiaohongshu, Weibo, Chrome DevTools MCP, Playwright MCP, visible login, and non-AgentKey fallbacks.
- `references/qcc-investigation.md`: Qichacha MCP/CLI entity anchoring, company-chain, intellectual-property, operating, risk, and key-person investigation; excludes Aiqicha.
- `references/path-selection.md`: four-rights scoring matrix, statistics, and selection rules.
- `references/jurisdiction-defendants.md`: court, defendant, and platform strategy.
- `references/evidence-damages-defenses.md`: evidence modules, claim amount model, and defense responses.
- `references/visual-evidence.md`: portable image-processing setup, visual contact sheet generation, and fallback rules for agents without image understanding.
- `references/output-template.md`: human-readable report structure, DOCX delivery rules, and appendix layout.

If the user asks only for a narrow sub-question, read only the relevant reference file(s).

## Core Inputs

Proceed with missing facts marked as `待核验`; do not stop unless the case cannot be identified at all.

Minimum useful inputs:

- 权利人名称
- 侵权链接、店铺、商品、内容、App、平台账号或线下销售线索
- 侵权人名称、店铺主体、生产商、销售商或关联主体

Helpful optional inputs:

- 目标赔偿额、目标法院、已取证材料、权利证书、产品图片、销售额/销量、是否已投诉或发函。

## Non-Negotiable Rules

1. Use current public investigation for live links, company status, platform pages, right status, and court jurisdiction rules when the user asks for a real target.
2. Separate `已核验事实`, `强推定事实`, `待核验事实`, and `法律判断`.
3. Do not finalize the route by reading only the user's existing方案 or screenshots. First build a search matrix from the clues, execute what can be searched, and state what remains unavailable.
4. Before choosing any cause of action, inventory the right holder's and suspected infringer's trademarks, patents, and copyright assets using `rights-search-methods.md`.
5. For product cases, compare plaintiff and accused product packaging/appearance after the rights inventory and before route scoring.
6. If a live platform page is blocked, follow `access-priority.md` before saying the infringement cannot be verified.
7. Recommend the route with the best combination of proof certainty, damages upside, procedural stability, and defendant collectability.
8. Do not assume trademark is always primary. If the target uses its own brand but copies packaging/trade dress, unfair competition may be primary.
9. Do not assume patent is primary merely because a product looks similar. Require a valid patent and infringement comparison.
10. Do not assume copyright is high-value for a single image or article. Require commercial scale, license price, bulk copying, software, audiovisual, or platform-scale evidence.
11. Do not use receiving place, purchase place, payment place, or plaintiff-arranged notarized delivery place as an independent jurisdiction basis. Treat purchase/delivery as evidence preservation, not a jurisdiction shortcut.
12. State evidence gaps and the next facts needed to upgrade the claim amount.
13. Do not promise litigation outcome.
14. When generating a `.docx`, never pass raw objects, arrays, promises, or tool result dictionaries into `TextRun`, template strings, table cells, or markdown-to-docx converters. Normalize every table cell and paragraph to a human-readable string first; object values must be expanded into named fields or summarized.
15. Do not skip visual comparison because the current agent lacks image-viewing ability. If images matter, use `references/visual-evidence.md` and `scripts/make_visual_contact_sheet.py` to create a comparison board; if no multimodal inspection is available, include the board and mark the visual conclusion as `待人工/多模态复核`.
16. Use the capability-adaptive protocol in `references/interactive-login-handoff.md`. `可见交互访问` means that the user can see and operate the same persistent browser/app session that the agent can inspect after login. Prefer native/OpenClaw control of the user's visible Chrome or another permitted local browser; otherwise probe and use the bundled headed Playwright CDP handoff so Codex/OpenClaw/CLI agents can resume the same task profile and state file. The adapter supports slow-start timeouts, host-targeted multi-tab capture/navigation, visible-text clicks, and selector-based search-field prefilling; use Computer Use when permitted. Curl, scraping, headless Playwright, HTML fetches, screenshots from a closed session, and search snippets do not qualify.
17. Treat login and interactive-surface availability as a hard gate. Open/focus the visible login page first, verify that the window is user-operable and will remain open, then ask the user to authenticate and wait for confirmation. If no qualifying surface exists, stop and ask the user to enable one or provide screenshots/App evidence. Do not continue to a full route recommendation merely because public snippets exist.
18. For packaging/trade-dress cases, text search cannot prove color, typography, container shape, layout hierarchy, decorations, or overall visual impression. If accused-product images were not actually captured and inspected, do not state that the packaging is `高度近似`, `完整保留`, `完全一致`, or that the unfair-competition elements are complete. At most deliver a clearly labeled `初步线索版` after the user expressly chooses to proceed without login evidence; the visual conclusion and route score must remain undecided.
19. Before delivering a full product/packaging report, run both `scripts/check_docx_formal_errors.py` and `scripts/check_report_evidence_gates.py`. When login access mattered, pass the internal UTF-8 working-note record with `--working-notes`; do not copy the access log into the client report merely to satisfy the audit. Fix every failure; an audit warning is not a substitute for missing evidence or user decision.
20. For corporate-chain work, use `references/qcc-investigation.md` when Qichacha MCP/CLI is configured. Capability-probe native QCC MCP tools first and the official QCC CLI second so Codex, OpenClaw, and other capable agents follow the same workflow. Anchor every fuzzy brand/store clue to a unique registered entity before downstream calls, treat QCC data as structured third-party evidence requiring official or litigation-proof confirmation, never turn quota/auth/tool failures into negative findings, and do not use Aiqicha as a source.
21. For platform and browser work, apply `references/platform-mcp-investigation.md`. Capability-probe Xiaohongshu MCP and Weibo MCP for platform-native search, then Chrome DevTools MCP and Playwright MCP for visible, persistent page work. Prefer Chrome or another user-visible local browser. AgentKey is an optional last-resort enrichment source only: do not make it a prerequisite, do not stop because it lacks credits, and do not spend credits when platform-native MCPs, local browser tools, public engines, or official sources can do the job.
22. Keep login/access diagnostics in working notes and the evidence folder. Do not add a standalone `取证访问记录` section or access-log appendix to the client report unless the user expressly requests it or an access limitation is necessary to qualify a material conclusion.
23. The damages section must use every reliable quantity and price actually found. Show the arithmetic for a public-data lower bound, a profit sensitivity range, the recommended claim, the target award, and reasonable expenses. Distinguish sold units from reviews, followers, store-wide totals, ranges, and unverified wholesale clues; never present a generic claim band when case-specific numbers are available.

## Working Method

1. Extract seed signals: right holder, brand, product category, infringement URL, item ID, title/search query, shop/account, suspected infringers, addresses, labels, packaging, price, sales/reviews, dates, and platform parameters.
2. Run a first-pass rights inventory using `rights-search-methods.md`: right holder marks/patents/copyrights and accused-party own marks/patents/copyrights.
3. Follow the access priority ladder in `access-priority.md` to obtain the live page or determine the next lawful access step.
   - If the ladder reaches login/security verification or reports that no qualifying visible interactive surface is available, read and apply `interactive-login-handoff.md`. Probe native/OpenClaw control, the bundled headed Playwright CDP adapter, and permitted Computer Use before declaring the surface unavailable; then pause. Resume only after the user confirms login/access, supplies inspectable images, or expressly requests a preliminary clue-only report.
4. For product cases, collect plaintiff and accused product images, create a visual contact sheet with `scripts/make_visual_contact_sheet.py` when images are available, and make a packaging/appearance comparison before route scoring. If the runtime lacks the image environment, run `scripts/setup_env.sh`; if setup is blocked, document the limitation and require user-assisted screenshots or manual review.
5. Build and execute a search matrix using `search-investigation.md` and `platform-mcp-investigation.md`: platform-native Xiaohongshu/Weibo searches, whole-web queries, platform-specific searches, right/status searches, company-chain searches, sales/scale searches, litigation/complaint searches, and jurisdiction searches. Use Chrome DevTools MCP, Playwright MCP, native browser control, or Computer Use for pages that require visible interaction. For company-chain, rights ownership, collectability, and related-party checks, apply `qcc-investigation.md` before relying on general web-search snippets.
6. Classify search results as `已核验事实`, `强推定事实`, or `待核验事实`, and identify which results change the route, defendants, court, or amount.
7. Map rights: trademark, trade dress/unfair competition, patents, copyright/software/game/content, and any combined route.
8. Map infringers: seller, producer, brand operator, platform account, uploader, software user, project user, shareholder, associated companies.
9. Score all four routes using `path-selection.md`.
10. Choose primary and backup routes.
11. Select candidate courts using `jurisdiction-defendants.md`.
12. Build claim amount using `evidence-damages-defenses.md`; use empirical ratio only as calibration, not as proof.
13. Predict defenses and prescribe counter-evidence.
14. Output using `output-template.md`. For full reports, generate a polished `.docx`, render-check it when the documents toolchain is available, run both `scripts/check_docx_formal_errors.py` and `scripts/check_report_evidence_gates.py` on the final file (adding `--working-notes {path}` when login access mattered), and return the final file path only after both scans pass.

## Source And Basis Requirements

When browsing or investigating:

- Cite source URLs and access date.
- Prefer official sources for right status, corporate status, court rules, laws, annual reports, and platform rules.
- Treat third-party corporate/search sites as clues unless verified by official registry or litigation evidence.
- For platform pages that cannot be fully crawled, say so and require App-side notarization or trusted timestamp preservation.

When giving the recommendation:

- Provide the search matrix and summarize what each search proved, failed to prove, or must be notarized.
- Preserve access attempts in working notes/evidence artifacts, but omit a standalone access log from the client report unless the user requests it or a material limitation must be explained.
- Provide a route score table.
- State the exact facts that caused the primary route to win.
- State what evidence could change the recommendation.
- Give the legal/evidentiary basis from the guide, not only intuitive reasoning.

## Claim Amount Discipline

Never output only one number without a model, and never omit case-specific arithmetic when reliable quantities or prices exist.

Use:

- 已见数据下限：for each reliable unit count and price, show `quantity × price = visible GMV`; explain what the number is and is not.
- 利润敏感性：show at least low/base/high profit-rate assumptions or a supported unit-cost model, with numeric outputs.
- 主位模型：sales/profit/license/contract/project/data/software/audiovisual model.
- 备位模型：statutory or discretionary damages using reputation, scale, bad faith, and obstruction.
- 合理开支：separate from economic damages and punitive base.
- 风险校准：compare with route empirical ratios and explain whether the claim is aggressive, moderate, or conservative.
- 量化诉请：state the recommended economic-damages claim, reasonable-expense claim, total prayer, target award, and upgrade triggers as numbers.

## Completion Checklist

Before finalizing a case assessment, confirm the output includes:

- A `.docx` report for full assessments unless the user requested plain text only.
- Best rights basis and backup paths.
- Candidate jurisdiction courts with connection facts and risks.
- Confirmation that the jurisdiction recommendation does not rely solely on receiving place, purchase place, payment place, or plaintiff-arranged delivery place.
- Defendant structure and why each defendant is included or excluded.
- Proposed claim amount/range with formula.
- Search matrix and current sales/scale findings.
- Rights inventory for the right holder and accused side: trademarks, patents/designs, copyright/source materials, source URLs, and fact level.
- Working-note/evidence proof that `可见交互访问` satisfied the four-condition contract (surface/tool, user-visible window, persistent session, post-login reinspection) plus final URL/title and screenshot/capture, or an explicit statement that the gate is unresolved and the report was not finalized as a full assessment. Keep this proof out of the client-facing report unless requested or materially necessary.
- Evidence collection plan by proof point.
- Visual comparison board path or a clear reason why image evidence could not be generated/inspected.
- Expected defendant defenses and counter-evidence.
- Public-source or evidence basis for important factual claims.
- Immediate action list.
- DOCX formal-error scan passed with zero hits for `[object Object]`, `[object Promise]`, `[object Array]`, `undefined`, `null`, and `NaN`; if it fails, fix the generation logic or regenerate the report before delivery.
- DOCX evidence-gate scan passed; in particular, no unresolved login wall, unsupported decisive visual conclusion, empty required section, or empty source appendix remains.
