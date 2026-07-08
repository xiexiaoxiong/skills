# Evidence, Damages, And Defenses

## Evidence Modules By Path

### Trademark

- Rights: registration, renewal, assignment/change, class/goods/service coverage, authorization chain.
- Reputation: sales, advertising, awards, flagship stores, prior protection, official price.
- Infringement: mark use position, title/brand field/logo/package/store/customer service, goods similarity, notarized purchase.
- Scale: sales, GMV, reviews, orders, stock, platform backend, logistics, production capacity.
- Bad faith: counterfeit, prior cases, warning, complaint, repeated links, low price, refusal to provide accounts.

### Unfair Competition

- Protected interest: trade dress/product name/enterprise name/data/secret/traffic rule/service model.
- Influence/value: launch date, continuous use, sales, users, ads, rankings, media, awards.
- Improper conduct: confusion, passing off, traffic hijacking, data scraping, rule breaking, commercial disparagement, secret acquisition/use.
- Scale/value: transaction amount, traffic/ad revenue, project amount, substitute cost, avoided R&D, customer value.
- Bad faith: notice, repeated conduct, circumvention, employee access, deletion/relisting.

### Patent

- Rights: certificate, register, claims/design, annuity, evaluation report, invalidity/stability materials.
- Comparison: claim chart, design comparison, product disassembly, testing, appraisal, on-site inspection.
- Acts: manufacturing, selling, offering for sale, importing, using, project installation.
- Scale: contracts, tenders, invoices, orders, production records, capacity, stock.
- Damages: sales x profit x patent contribution; license fee; project amount.

### Copyright

- Rights: source file, draft, registration, publication, author/ownership, assignment/license chain.
- Protected expression: originality and expression/idea separation.
- Similarity: contact possibility, substantial similarity, copied fragments, same errors, expert comparison.
- Dissemination/commercialization: plays, downloads, users, ads, membership, software installations, sales, license price.
- Platform liability: notice, takedown, recommendation, revenue sharing, self-operation.

## Claim Amount Model

Use this sequence:

1. Determine the primary calculable basis:
   - Trademark: sales amount x profit rate, license fee, statutory/punitive fallback.
   - Unfair competition: transaction/traffic/project/secret value x profit or saved cost.
   - Patent: accused product sales x profit x patent contribution, or license fee/project amount.
   - Copyright: license fee x quantity/burden factor, dissemination revenue, software license price x installations.
2. Separate reasonable expenses:
   - Notarization, purchase, appraisal, attorney fee, investigation, preservation, travel, translation.
3. Add punitive damages only where facts support willfulness and serious circumstances; do not include reasonable expenses in punitive base.
4. Calibrate with empirical median award/claim ratios:
   - Trademark 60%.
   - Unfair competition 50%.
   - Patent 64.06%.
   - Copyright 41.67%.

Formula:

`recommended claim = max(calculable model, target award / empirical ratio)`

If evidence is weak, output a claim range and list the evidence needed before filing.

## Sales And Scale Investigation For Damages

Before setting the amount, build a channel-by-channel sales picture:

1. Start with the exact infringing link and item/account ID.
2. Search the same product, package text, brand/operator, company names, barcodes, SKU specs, and shop names across major e-commerce/content-commerce platforms.
3. Record visible prices, sales, reviews, comments, rankings, followers, live-commerce clips, SKU count, and first/last review time.
4. Distinguish sales metrics:
   - Backend orders/GMV/refunds: strong.
   - Notarized visible sales or monthly sales: medium to strong.
   - Search snippets, reviews, followers, rankings: medium or clue-only depending on source.
   - User estimates without source: `待核验`.
5. Deduplicate suspected repeated listings and aggregate only when seller/operator/control facts connect them.
6. Convert scale to damages with a stated model:
   - `visible sales x conservative average price`.
   - `GMV x reasonable profit rate`.
   - `platform backend GMV x profit rate` after court investigation.
   - `license fee / comparable transaction / substitute cost` where sales are hidden.
7. Use search gaps to draft investigation requests:
   - platform backend orders, GMV, refunds, ads, traffic, account holder, link history;
   - defendant ledgers, invoices, production records, purchase orders, warehouse/logistics records;
   - payment accounts and invoice issuers.

Do not let a single product page set the damages ceiling if search results show multi-platform stores, wholesale sources, live commerce, or repeated re-listing under related operators.

## Damages Strength Levels

- Strong: platform/backend/contract/accounting data + profit/fee/contribution model + bad faith.
- Medium: public sales/traffic data + price + reasonable profit or license proxy.
- Weak: only page existence or single purchase, no scale or fee evidence.

## Defense Matrix

### Trademark Defenses

- Own mark/authorization: check status, scope, actual use, deformation, authorization limits.
- No similarity/confusion: visual/phonetic/meaning comparison, actual confusion, product similarity.
- Descriptive/fair use: prove source-identifying use beyond necessity.
- Legitimate source/retailer: verify invoices, quantity, time, product match; prove knowledge.
- Low profit/false sales: request full backend, orders, refunds, logistics, accounts.

### Unfair Competition Defenses

- No protectable interest/no influence: prove continuous use, recognition, commercial value.
- No competition: prove user/traffic/customer/business opportunity overlap.
- No confusion: use overall impression, actual misrecognition, search/customer service evidence.
- Fair competition/public data: prove excessive, disruptive, circumvention, or commercial substitution.
- Platform/technical neutrality: prove active design, recommendation, revenue share, notice and failure.

### Patent Defenses

- Non-infringement: prepare claim chart, equivalence, testing, appraisal.
- Prior art/design: compare whether prior art discloses all disputed features.
- Invalidity: prepare stability opinion/evaluation report; address stay risk.
- Prior use: attack time, scope, evidence correspondence.
- Exhaustion/license: verify patent number, product, territory, term.
- Low contribution: prove patented feature is core selling point.

### Copyright Defenses

- No ownership/originality: source files, creation chain, registration, publication.
- Independent creation/no similarity: contact possibility, expression comparison, same errors.
- Fair use: commercial use, excessive taking, market substitution.
- Authorization/source: audit complete license chain and work list.
- Safe harbor: valid notice, obvious infringement, recommendation, revenue, delay.
- Low impact: use plays/downloads/ads/license price/bulk count.

## Evidence Orders And Investigation Requests

Common requests:

- Platform backend: orders, GMV, refunds, reviews, ads, traffic, account holder, history links.
- Defendant accounts: sales ledger, contracts, invoices, production records, software installs.
- Logistics/invoices/payment: sender, warehouse, invoice issuer, payee.
- Technical records: source code, server logs, API calls, product drawings, testing records.
- Administrative/criminal files when available.
