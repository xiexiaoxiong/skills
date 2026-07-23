# Qichacha MCP Investigation

Use Qichacha (`企查查`, QCC) for company-chain, intellectual-property, operating, judicial-risk, and key-person checks when the MCP or the official QCC CLI is configured. Do not use Aiqicha (`爱企查`) in this workflow.

## 1. Access And Secrets

- Prefer the configured QCC MCP services: `qcc-company`, `qcc-ipr`, `qcc-operation`, `qcc-risk`, and `qcc-executive`.
- Capability-probe in this order for every runtime, including Codex, OpenClaw, and other agents:
  1. Native tools named for the five QCC services above.
  2. The official QCC CLI at `/opt/homebrew/bin/qcc`, which reaches the same QCC MCP backend.
  3. A user-visible, persistent browser session already supported by that runtime. If sign-in is required, follow `interactive-login-handoff.md`; do not substitute a search snippet for the blocked company page.
- If an agent runtime cannot expose the MCP tools but `/opt/homebrew/bin/qcc` is configured, use the CLI without treating that as a lower-quality data source.
- Run `qcc check` and refresh with `qcc update` before investigation when the cache is missing or stale.
- Store authentication only in QCC's credential store or an environment variable referenced by `bearer_token_env_var`. Never print, copy into a report, or commit the API key.
- Treat QCC as a third-party structured-data provider, not as an official certificate. Use official registries, certificates, platform disclosure, samples, or court/agency records for filing-critical proof.

### Authentication, quota, and failure semantics

- The skill may send a case-specific registered entity name and unified social credit code to QCC only when the user has authorized that disclosure or when it is plainly within the user's request.
- For a persistent MCP setup, declare all five services and keep the bearer token in the runtime environment or QCC credential store. Do not hard-code it in `SKILL.md`, `openai.yaml`, a report, shell history, or a project file.
- A direct MCP connection may require the agent runtime to restart after configuration. Until then, the official CLI is the approved same-provider fallback.
- `credit_balance_insufficient`, authentication failure, timeout, tool unavailability, or browser-login failure means `查询未完成`, not `无记录`.
- Do not retry a credit-exhausted paid call in a loop. Preserve successful calls, record the exact interruption, and place the unrun endpoints in a follow-up queue.
- Do not describe a company as having no trademark, patent, copyright, penalty, litigation, execution, freeze, serious-violation, online-store, or platform-account record unless the corresponding detail tool completed successfully and returned an empty result.
- If the browser adapter cannot attach to the user's browser, follow that adapter's supported recovery flow. Do not inspect cookie/profile files or launch an undisclosed headless replacement. Continue only with already valid QCC results, the official CLI, or a user-approved visible surface.

## 2. Entity Anchoring Gate

1. If the clue is a brand, store, abbreviation, or incomplete name, call `company/get_company_by_query`.
2. If QCC returns a unique exact match, record the full registered name and unified social credit code, then use that code for downstream calls.
3. If QCC returns several candidates, list every candidate and stop downstream entity-specific calls until the user or independent evidence selects one. Never choose the first result automatically.
4. If a full name and unified social credit code are both available, call `company/verify_company_accuracy`.
5. Do not merge entities merely because they share a brand keyword, legal representative, address, shareholder, phone number, or industry. Record each connection separately and explain what additional evidence is required to prove common control or joint conduct.

## 3. Investigation Sequence

For each locked plaintiff, defendant, producer, brand operator, and store operator:

1. Identity and domicile:
   - `company/get_company_registration_info`
   - `company/get_change_records` when historical identity or address matters
2. Control and related parties:
   - `company/get_shareholder_info`
   - `company/get_actual_controller`
   - `company/get_key_personnel`
   - `company/get_external_investments` only when relevant
3. Rights and online assets:
   - `ipr/get_trademark_info`
   - `ipr/get_patent_info`
   - `ipr/get_copyright_work_info`
   - `ipr/get_online_store`, `ipr/get_douyin_account`, or other account tools when platform linkage matters
4. Risk triage:
   - Call `risk/get_company_risk_scan` first.
   - Drill down only non-zero, case-relevant dimensions such as `get_administrative_penalty`, `get_judicial_documents`, `get_judgment_debtor_info`, `get_dishonest_info`, `get_terminated_cases`, `get_equity_freeze`, or `get_serious_violation`.
   - A scan count is a routing signal, not a merits conclusion. Do not characterize the risk until the matching detail tool has been called.
5. Key-person checks:
   - Use `executive` tools only after the person is anchored by company name plus exact person name.
   - Do not infer personal liability from a corporate role alone.

## 4. Case-Specific Use

- Plaintiff chain: prove which company owns the mark, commissioned or owns the packaging design, operates the brand/store, and received sales revenue.
- Defendant chain: distinguish store operator, brand owner, filer, manufacturer/OEM, invoice issuer, payee, and logistics sender.
- Related-party theory: use QCC links as investigation leads; require contracts, platform disclosure, samples, invoices, payment accounts, common staff/customer service, or other conduct evidence before alleging joint infringement.
- Jurisdiction: use current registered domicile as a candidate connection, then verify the court's centralized jurisdiction and obtain a registry extract or platform disclosure before filing.
- Collectability: use current execution, dishonesty, termination, freeze, serious-violation, and penalty details only after entity anchoring.

## 5. Report Record

For every QCC call, record:

- Service/tool name.
- Exact search key (full registered name or unified social credit code).
- Query date.
- Returned entity name and unified social credit code.
- Material fields used.
- Fact level: `企查查结构化线索，需官方/诉讼证据复核`.
- Whether the result changed defendants, jurisdiction, rights inventory, collectability, damages, or next evidence steps.

Do not cite an Aiqicha page, screenshot, snippet, or AI summary as a source in the report.
