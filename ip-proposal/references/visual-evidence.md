# Visual Evidence Portability

Use this reference when packaging, product appearance, page screenshots, artwork, or other visual expression affects route selection.

## 1. What The Skill Can And Cannot Provide

- The skill can provide a portable image-processing environment and scripts.
- The skill cannot make a non-multimodal agent visually understand images by itself.
- If the agent has a visual inspection tool, use it on the generated comparison sheet.
- If the agent lacks visual inspection, generate the comparison sheet, include it in the report, and mark the visual conclusion as `待人工/多模态复核`.
- If accused-product images were never obtained, a contact sheet cannot be generated and the packaging similarity question remains unresolved. Text descriptions or search snippets cannot replace the missing image.

## 2. Environment Setup

After installing the skill, run:

```bash
bash scripts/setup_env.sh
```

This creates `ip-proposal/.venv`, installs `requirements.txt`, and self-tests the visual contact sheet script.

If network or package installation is blocked, ask the user or target agent to provide screenshots/contact sheets generated elsewhere. Non-visual issues may still be investigated, but do not score or decide a packaging/trade-dress route until the images are inspectable. Only produce a preliminary clue-only report if the user expressly requests it after being told about the gap.

## 3. Visual Evidence Board

When plaintiff and accused images are available, create a side-by-side board:

```bash
.venv/bin/python scripts/make_visual_contact_sheet.py \
  --plaintiff /path/to/plaintiff-front.jpg \
  --plaintiff /path/to/plaintiff-side.jpg \
  --accused /path/to/accused-front.jpg \
  --accused /path/to/accused-side.jpg \
  --title "Plaintiff vs Accused Packaging" \
  --output /path/to/visual-contact-sheet.png
```

The script also writes a JSON manifest beside the PNG. Put the PNG into the DOCX report when visual similarity affects the route.

## 4. Minimum Visual Comparison

Record these features even if the agent can inspect images:

| Feature | What to compare |
|---|---|
| Container / shape | box, bottle, tube, bag, size ratio, silhouette |
| Color system | main colors, contrast, background blocks, accents |
| Layout hierarchy | brand position, product name position, claim blocks, grid |
| Typography | font style, weight, spacing, bilingual layout |
| Images / decorations | illustrations, ingredient photos, seals, icons, borders |
| Text claims | product line, function claims, slogans, ingredient claims |
| Overall impression | whether ordinary consumers would remember the same visual source |

Do not decide the litigation route from text search alone when product packaging is the user’s concern.

## 5. Minimum Provenance Record

For every plaintiff/accused image used in the report, record:

- side (`权利人` / `被诉方`), product and SKU;
- source URL, user-provided filename, or notarization package identifier;
- capture/access date;
- whether the page was viewed before or after login;
- screenshot or local evidence path;
- who/what inspected the image.

If these fields are unavailable, downgrade the image to a clue and state exactly what still needs to be captured.
