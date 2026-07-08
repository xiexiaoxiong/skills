# Visual Evidence Portability

Use this reference when packaging, product appearance, page screenshots, artwork, or other visual expression affects route selection.

## 1. What The Skill Can And Cannot Provide

- The skill can provide a portable image-processing environment and scripts.
- The skill cannot make a non-multimodal agent visually understand images by itself.
- If the agent has a visual inspection tool, use it on the generated comparison sheet.
- If the agent lacks visual inspection, generate the comparison sheet, include it in the report, and mark the visual conclusion as `待人工/多模态复核`.

## 2. Environment Setup

After installing the skill, run:

```bash
bash scripts/setup_env.sh
```

This creates `ip-proposal/.venv`, installs `requirements.txt`, and self-tests the visual contact sheet script.

If network or package installation is blocked, continue the legal assessment but state that image handling is degraded. Ask the user or target agent to provide screenshots/contact sheets generated elsewhere.

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
