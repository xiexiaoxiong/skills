# Compact Inline Evidence Report

This is the default user-facing renderer contract for the 61-item heavy-case evidence checklist.

## Purpose

- Produce one compact `.docx` that can be reviewed row by row without a screenshot appendix.
- Render only normalized `results` plus `evidence_attachments`; never render browser-operation logs, raw timestamps, long URLs, or legacy appendix prose.
- Keep the defendant product as the investigation seed for every row except plaintiff reputation rows, as required by the parent skill.

## Fixed layout

- Preset: `compact_reference_guide`.
- Named page override: A4 landscape, `29.7 × 21.0 cm`.
- Margins: left/right `0.65 cm`, top/bottom `0.60 cm`.
- Header/footer distance: `0.30 cm`.
- First-page pattern: compact `memo_masthead` without a bottom rule; title and one metadata line only.
- Exactly one table, with five fixed DXA columns and no separate metadata table.
- Column widths: `1.35 / 5.15 / 4.55 / 12.25 / 5.10 cm`.
- Column order: identifier; evidence item; checked platforms/sites; investigation result and inline evidence; next-step focus.
- The table contains 61 task rows, five dimension-band rows, and one repeating header row.
- Rows use `cantSplit` but no fixed height.

## Cell content rules

### Checked platforms / sites

- Show the concrete platform or website name.
- Prefix a visited platform with `☑` and an unvisited platform with `☒`.
- If a platform URL is available, make the platform name clickable; never display its raw URL.

### Investigation result and evidence

- Start with a short status label and one compact conclusion.
- Use `compact_note`; fall back to `reason` or `findings` only when needed.
- Sanitize URLs, timestamps, hashes, newlines, and repeated punctuation.
- Truncate the visible conclusion to a compact reading length.
- Show no more than two inline thumbnails in a task row.
- Maximum dimensions are `5.65 × 3.35 cm` for each of two thumbnails and `6.40 × 3.60 cm` for a single thumbnail. The renderer intentionally uses smaller default dimensions to reduce page count.
- Every displayed image is clickable. The image links to its source when known, otherwise to the local original.
- Beneath each thumbnail, `原图` links to the local original and `来源` links to the public source when known.
- Never create a screenshot appendix.

### Image deduplication

- Compute SHA-256 from the original image bytes.
- The first displayed occurrence is the primary row for that SHA group.
- Suppress repeated insertions in later rows.
- Later rows show an internal `同图见 <row-id>` hyperlink to the primary row bookmark.
- Suppress a duplicate repeated within the same row.
- If a row has more than two unique attachments, expose compact `原图` links for the undisplayed remainder rather than adding more thumbnails.

### No-image reason

Every row without a newly displayed thumbnail carries a compact reason label, including:

- `无图｜公开查询无结果`
- `无图｜登录或技术受阻`
- `无图｜需线下或人工完成`
- `无图｜本项不适用`
- `无图｜附件文件缺失`
- `去重｜同图已在前行展示`

### Next-step focus

- Use at most the first two normalized `next_steps`.
- Label them `优先｜` and `补强｜`.
- Do not include investigation history or long procedural logs.

## Input contract

- Results may be a top-level array or an object containing `results`, `items`, or `rows`.
- Attachments may be a top-level array or an object containing `attachments`, `items`, or `rows`.
- Results must contain the exact canonical set of 61 `item_id` values.
- Attachment rows use `row_id`; missing attachment rows are allowed and produce a no-image label.
- Relative attachment paths are resolved against the attachments file directory, then its parent case directory.
- Legacy `appendix_note` may remain in input for compatibility but is never rendered.

## Command

```bash
/usr/bin/python3 scripts/render_compact_inline.py \
  --results /path/to/results.json \
  --attachments /path/to/evidence_attachments.json \
  --output /path/to/report.docx \
  --title '重案调查一般证据清单' \
  --rights-holder '权利人名称' \
  --defendant-product '从种子链接提取的被告商品完整名称' \
  --store-name '被告店铺' \
  --operator-name '被告经营主体' \
  --source-url 'https://item.example/seed' \
  --source-label '种子商品链接' \
  --investigation-date '2026-07-22'
```

## Atomic output and audit

The renderer writes a temporary `.docx` in the output directory, validates its OOXML, and only then uses an atomic rename. The audit rejects output unless it has:

- one fixed-width table with the exact five-column grid;
- A4 landscape page geometry;
- all 61 internal task-row bookmarks;
- at most two inline images per task row, only in column four;
- no floating image anchors;
- no visible raw URLs;
- no screenshot appendix.

Visual QA remains mandatory for a user deliverable: render the DOCX and inspect every page. QuickLook may be used as the macOS visual check requested by the operator; use the canonical document renderer for multipage inspection when available.
