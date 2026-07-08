# IP-Proposal Agent Contract

Use this file when an agent cannot automatically discover Codex-style skills.

## Display Name

Human-facing name: `IP-Proposal`

Codex/agent invocation name: `$ip-proposal`

Skill folder: `ip-proposal`

## Trigger

Invoke this skill when the user provides any of the following and asks for IP infringement assessment, litigation proposal, high-damages feasibility, evidence plan, jurisdiction, defendants, or a DOCX report:

- right holder, brand, product, copyrighted work, patent, trademark, or company;
- infringement link, store, platform account, product page, app, listing, content page, or screenshots;
- suspected infringer, producer, seller, uploader, store operator, or platform.

## Required Load Order

1. Read `SKILL.md`.
2. For a full assessment, read these references before drafting:
   - `references/workflow.md`
   - `references/access-priority.md`
   - `references/rights-search-methods.md`
   - `references/search-investigation.md`
   - `references/path-selection.md`
   - `references/jurisdiction-defendants.md`
   - `references/evidence-damages-defenses.md`
   - `references/output-template.md`
3. If the user asks only a narrow question, read only the relevant reference files.

## Minimum Input Handling

If the user gives only `权利人 + 侵权链接`, proceed. Extract all available facts from the link and public search. Mark missing items as `待核验`; do not ask for more information unless the target cannot be identified at all.

## Non-Skippable Steps

1. Search the right holder's trademarks, patents, copyright assets, and packaging/trade dress or expression basis.
2. Search the accused side's trademarks, patents, copyright assets, and operating entities.
3. Access or preserve the accused page using the access ladder.
4. Compare packaging / product appearance / expressive content when relevant. If images matter, use `references/visual-evidence.md` and generate a side-by-side contact sheet with `scripts/make_visual_contact_sheet.py`.
5. Score trademark, unfair competition, patent, and copyright paths.
6. Choose one primary path and backup paths.
7. Build jurisdiction, defendant, damages, evidence, and defense strategy.
8. Generate a human-readable `.docx` litigation proposal for full assessments.

## Other-Agent Installation

For OpenClaw or another non-Codex agent, the user should be able to paste this prompt and let the target agent install itself:

```text
请帮我安装 IP-Proposal skill。
GitHub 地址：https://github.com/xiexiaoxiong/skills/tree/main/ip-proposal

请你自行完成安装：
1. 如果你支持 Codex/OpenAI 风格的 skill，请把该目录安装为 ip-proposal，并确保我可以用 $ip-proposal 调用；
2. 如果你不支持这种 skill 机制，请把 SKILL.md 和 references/ 作为你的提示词包/知识包，并配置 $ip-proposal 别名；
3. 安装后运行 bash scripts/setup_env.sh，安装图片处理和 DOCX 生成依赖；
4. 安装后告诉我具体调用方式，并用一句话确认你会在完整评估时生成 DOCX 诉讼方案报告。
```

Manual fallback:

1. Copy this folder to the agent's skill/prompt directory.
2. Configure `$ip-proposal` as an alias for reading `SKILL.md` and following the required references.
3. Grant browser/search access for live links and public rights/company/court sources.
4. Grant local file output access for `.docx` reports.
5. Run `bash scripts/setup_env.sh` from the skill folder when the agent can install packages. This creates `.venv` and installs the portable image/DOCX helper dependencies.
6. Require the agent to record blocked pages and ask for lawful login/notarization support instead of bypassing CAPTCHA or platform risk controls.

## Visual Capability Fallback

The skill includes image-processing scripts, but it cannot give a non-visual model true image understanding. If the target agent has a vision tool, inspect the generated contact sheet. If not, generate the sheet, embed it into the report, and mark the visual conclusion as `待人工/多模态复核`.

## Final Response

Return a short delivery note with the report path. Do not paste the whole report into chat unless the user asks for chat-only output.
