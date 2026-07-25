# Skills

这个仓库用于集中保存可复用的 AI Agent Skills。每个一级目录就是一个独立 skill，可以安装到 Codex、OpenClaw 或其他支持自定义提示词/知识包的 agent。

## 当前 Skills

- [`ip-proposal`](ip-proposal/README.md)：根据权利人和侵权链接，生成知识产权诉讼方案 `.docx` 报告，覆盖权利清单、包装/表达比对、案由选择、管辖、被告、赔偿模型和证据方案。
- [`evidence-collection`](evidence-collection/README.md)：基于疑似侵权链接进行重案证据清单取证，覆盖电商平台、商标/工商/监管、登录协作与证据目录生成。

### evidence-collection 技能介绍

`evidence-collection` 用于生成“侵权证据保全与取证清单”报告，适合知识产权案件中快速定位可公开抓取证据。它会：

- 输入权利人名与被告侵权链接后，自动生成结构化证据表；
- 给出每个检查项对应的平台与链接；
- 支持生成可复核的截图证据项，便于法务归档或导出到报表。

## 最简单安装方式

把下面这段话发给目标 agent，让它自己安装：

```text
请帮我安装 IP-Proposal skill 和 Evidence-Collection skill。
GitHub 地址：https://github.com/xiexiaoxiong/skills/tree/main/ip-proposal
GitHub 地址：https://github.com/xiexiaoxiong/skills/tree/main/evidence-collection

请你自行完成安装：
1. 如果你支持 Codex/OpenAI 风格的 skill，请把该目录安装为 ip-proposal，并确保我可以用 $ip-proposal 调用；
2. 如果你不支持这种 skill 机制，请把 SKILL.md 和 references/ 作为你的提示词包/知识包，并配置 $ip-proposal 别名；
3. 同理，evidence-collection 对应别名为 $evidence-collection，并确认安装成功；
4. 安装后告诉我具体调用方式，并确认：
   - $ip-proposal 会输出 DOCX 诉讼方案报告；
   - $evidence-collection 会输出重案证据清单与证据目录。
```

### evidence-collection 直接安装（适用于 Codex）

```bash
git clone https://github.com/xiexiaoxiong/skills.git
cd /Users/<你用户名>/Documents/skills
bash install/install.sh install evidence-collection
```

然后在 `~/.codex/skills/evidence-collection/` 下执行一次性依赖安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r evidence-collection/requirements.txt
```

如果你有统一部署脚本，也可改用 `cp` 方式安装：

```bash
cp -R evidence-collection ~/.codex/skills/
```

### evidence-collection 调用示例

```text
用 $evidence-collection 按照“重案证据清单”流程出报告。
权利人：珂润
侵权链接：https://item.jd.com/10220925150279.html
```

```text
用 $ip-proposal 生成诉讼方案报告。
权利人：珂润
被告侵权商品：https://item.jd.com/10220925150279.html
```

需要的输出：

- 一份可复核的证据清单（含检索项、平台、结果摘要、证据状态）
- 涉及证据截图/页面链接及跳转路径
- 完成度可直接打钩/打叉的核查表

### Codex 手动安装（包含 ip-proposal）

```bash
git clone https://github.com/xiexiaoxiong/skills.git
mkdir -p ~/.codex/skills
cp -R skills/ip-proposal skills/evidence-collection ~/.codex/skills/
```

调用：

```text
用 $ip-proposal 评估并生成诉讼方案报告。
用 $evidence-collection 进行重案证据清单与证据留痕。
权利人：某品牌/某公司
侵权链接：https://example.com/item/123
```
