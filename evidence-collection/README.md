# evidence-collection

重案证据清单 Skill（原 `heavy-case-evidence-builder`）用于知识产权案件的“被告产品证据留存”场景。

- 输入：权利人 + 被告侵权链接
- 输出：结构化清单 + 关键页面证据 + 可复核链接
- 特征：支持电商平台、监管/工商平台、社媒、爬虫复核路径

## 给不会用的人（零门槛）

复制下面内容给你的 agent 即可（只填参数）：

```text
请直接帮我完成下面这件事，不需要我做命令行操作。
1) 安装：
   - 到仓库安装链接：https://github.com/xiexiaoxiong/skills/tree/main/evidence-collection
   - 确认安装后我可以用 $evidence-collection 调用
2) 代替我调用，参数如下：
   - 权利人：<填写权利人>
   - 被告侵权链接：<填写侵权链接>
3) 你需要输出一份“可直接交付”的证据清单报告：
   - 每行都要有“可点击链接”
   - 有截图核验的项要给出截图位置/说明
   - 结尾给我一句“任务完成”

请直接执行，不要让我再填其它参数。
```

示例（直接可发版本）：

```text
请直接帮我完成以下操作：
1) 安装仓库目录：https://github.com/xiexiaoxiong/skills/tree/main/evidence-collection
2) 确认 $evidence-collection 可调用
3) 按以下参数执行证据清单输出：
   权利人：珂润
   被告侵权链接：https://item.jd.com/10220925150279.html
4) 输出可复用报告，含可点击链接与截图核验项
```

## 安装与依赖

```bash
cd /Users/<你的用户名>/Documents/skills
bash install/install.sh install evidence-collection
```

安装后一次性安装 Python 依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r evidence-collection/requirements.txt
```

如果环境有统一迁移流程，可直接复制目录到技能路径：

```bash
cp -R evidence-collection ~/.codex/skills/
```

可选外部依赖：

- Chrome（页面复核与截图）
- qcc、xiaohongshu、weibo、chrome-devtools、playwright MCP

## 调用示例

```text
用 $evidence-collection 进行重案证据清单与证据留痕。
权利人：珂润
侵权链接：https://item.jd.com/10220925150279.html
```

```text
请按“平台 MCP 检索 → Chrome/Playwright 截图复核 → 表格超链接”方式输出报告。
```
