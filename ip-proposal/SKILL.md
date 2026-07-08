---
name: ip-proposal
description: Generate a plaintiff-side PRC IP litigation proposal report from a right holder, infringement link/store/product/content, suspected infringer, platform, or evidence clues. Use when the user needs investigation-driven rights inventory, packaging/expression comparison, trademark/unfair competition/patent/copyright path selection, high-damages feasibility, jurisdiction, defendants, claim amount, evidence strategy, defendant defenses, and a human-readable DOCX proposal.
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
- `references/rights-search-methods.md`: first-step trademark, patent, copyright, and accused-rights search methods, source priorities, and fallbacks.
- `references/search-investigation.md`: clue expansion, public search matrix, sales/scale investigation, and result-to-strategy rules.
- `references/path-selection.md`: four-rights scoring matrix, statistics, and selection rules.
- `references/jurisdiction-defendants.md`: court, defendant, and platform strategy.
- `references/evidence-damages-defenses.md`: evidence modules, claim amount model, and defense responses.
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
11. State evidence gaps and the next facts needed to upgrade the claim amount.
12. Do not promise litigation outcome.

## Working Method

1. Extract seed signals: right holder, brand, product category, infringement URL, item ID, title/search query, shop/account, suspected infringers, addresses, labels, packaging, price, sales/reviews, dates, and platform parameters.
2. Run a first-pass rights inventory using `rights-search-methods.md`: right holder marks/patents/copyrights and accused-party own marks/patents/copyrights.
3. Follow the access priority ladder in `access-priority.md` to obtain the live page or determine the next lawful access step.
4. For product cases, collect plaintiff and accused product images and make a packaging/appearance comparison before route scoring.
5. Build and execute a search matrix using `search-investigation.md`: whole-web queries, platform-specific searches, right/status searches, company-chain searches, sales/scale searches, litigation/complaint searches, and jurisdiction searches.
6. Classify search results as `已核验事实`, `强推定事实`, or `待核验事实`, and identify which results change the route, defendants, court, or amount.
7. Map rights: trademark, trade dress/unfair competition, patents, copyright/software/game/content, and any combined route.
8. Map infringers: seller, producer, brand operator, platform account, uploader, software user, project user, shareholder, associated companies.
9. Score all four routes using `path-selection.md`.
10. Choose primary and backup routes.
11. Select candidate courts using `jurisdiction-defendants.md`.
12. Build claim amount using `evidence-damages-defenses.md`; use empirical ratio only as calibration, not as proof.
13. Predict defenses and prescribe counter-evidence.
14. Output using `output-template.md`. For full reports, generate a polished `.docx`, render-check it when the documents toolchain is available, and return the final file path.

## Source And Basis Requirements

When browsing or investigating:

- Cite source URLs and access date.
- Prefer official sources for right status, corporate status, court rules, laws, annual reports, and platform rules.
- Treat third-party corporate/search sites as clues unless verified by official registry or litigation evidence.
- For platform pages that cannot be fully crawled, say so and require App-side notarization or trusted timestamp preservation.

When giving the recommendation:

- Provide the search matrix and summarize what each search proved, failed to prove, or must be notarized.
- Provide an access-attempt log when the live page was blocked or required browser/login access.
- Provide a route score table.
- State the exact facts that caused the primary route to win.
- State what evidence could change the recommendation.
- Give the legal/evidentiary basis from the guide, not only intuitive reasoning.

## Claim Amount Discipline

Never output only one number without a model.

Use:

- 主位模型：sales/profit/license/contract/project/data/software/audiovisual model.
- 备位模型：statutory or discretionary damages using reputation, scale, bad faith, and obstruction.
- 合理开支：separate from economic damages and punitive base.
- 风险校准：compare with route empirical ratios and explain whether the claim is aggressive, moderate, or conservative.

## Completion Checklist

Before finalizing a case assessment, confirm the output includes:

- A `.docx` report for full assessments unless the user requested plain text only.
- Best rights basis and backup paths.
- Candidate jurisdiction courts with connection facts and risks.
- Defendant structure and why each defendant is included or excluded.
- Proposed claim amount/range with formula.
- Search matrix and current sales/scale findings.
- Rights inventory for the right holder and accused side: trademarks, patents/designs, copyright/source materials, source URLs, and fact level.
- Access attempts, blocked points, and whether browser/login/App notarization is needed.
- Evidence collection plan by proof point.
- Expected defendant defenses and counter-evidence.
- Public-source or evidence basis for important factual claims.
- Immediate action list.
