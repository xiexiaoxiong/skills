# invoice-fetch：邮箱发票一键抓取

**干什么用**：自动登录你的新浪邮箱，把收件夹里的电子发票（PDF/图片）下载下来，按 `金额-项目-抬头-发票号` 重命名，并生成《发票清单.xlsx》（带总金额）和《发票_四拼一汇总.pdf》（一页 4 张，可直接打印报销）。

---

## 一、安装（二选一）

### 方式 A：一句话让 AI 帮你装（推荐，不会命令行也能用）

把下面这段话原样发给你的 AI agent（Kimi / Codex / 其他支持 skill 的 agent）：

```text
请帮我安装 invoice-fetch skill，GitHub 地址：
https://github.com/xiexiaoxiong/skills/tree/main/invoice-fetch
请把 SKILL.md 和 scripts/ 安装为你的 skill，并帮我装好依赖（Python 的 playwright 包和浏览器组件），装好后告诉我怎么调用。
```

### 方式 B：自己动手（3 条命令）

```bash
git clone https://github.com/xiexiaoxiong/skills.git
cp -R skills/invoice-fetch ~/.codex/skills/      # Codex 用户；Kimi 用户复制到自己约定的 skills 目录即可
python3 -m pip install playwright && python3 -m playwright install chromium
```

依赖说明：只需要 Python 3 和 playwright，处理库 `scripts/invoice_lib.py` 是纯标准库，无其他依赖。

---

## 二、使用（每次抓发票只需两步）

直接对 agent 说：**"抓一下我邮箱里的发票"**。接下来：

- **第 1 步（你动手）**：agent 会帮你打开一个专用浏览器窗口，你在里面登录新浪邮箱（mail.sina.com.cn），登录成功后回复"**好了**"。
- **第 2 步（agent 动手）**：自动扫描收件夹最近 30 天的发票邮件 → 下载发票（含邮件正文里税务平台链接的 PDF）→ 去重、重命名 → 生成清单和四拼一 PDF，并把结果汇报给你。

喜欢自己跑命令也可以：

```bash
python3 scripts/fetch_invoices.py open-login     # 第1步：打开登录窗口（你登录邮箱）
python3 scripts/fetch_invoices.py list           # 可选：预览匹配到的发票邮件（只看不下载）
python3 scripts/fetch_invoices.py collect --output-dir ~/Downloads/发票   # 第2步：抓取并生成产物
```

---

## 三、输出长什么样

输出目录里会有：

| 文件 | 说明 |
|---|---|
| `314.00-餐饮服务-北京德恒（深圳）律师事务所-26952...pdf` | 发票原件，已规范重命名 |
| `发票清单.xlsx` | 序号/金额/项目/抬头/发票号，末尾带**总金额**行 |
| `发票_四拼一汇总.pdf` | 横版 A4 一页 4 张，直接打印贴报销单 |
| `需要二次扫码/` | 如果抓到的是"开票二维码小票"（还不是发票），会放这里并提醒你**开票失效日期** |

---

## 四、固定规则（重要）

- **只下载 PDF 和图片**；OFD、XML 及其它格式一律跳过
- **不生成** `运行结果.json`
- 默认发票抬头：**北京德恒（深圳）律师事务所**（可用 `--default-title` 修改）
- 只读收件夹，默认最近 30 天（`--days` 修改）；关键词：发票/电子发票/增值税/开票/invoice
- 重复邮件（同一发票的多次通知）按文件内容自动去重

---

## 五、常见问题

**Q：每次都要重新登录吗？**
A：专用窗口有独立的浏览器配置，登录态一般会保留；过期了重新登一次即可。

**Q：那个专用浏览器窗口能关吗？**
A：抓取完成后随时可以关。

**Q：安全吗？会不会动我的邮件？**
A：脚本只**读**收件夹、只**下载**附件/链接中的文件，不删除、不移动、不发送任何邮件。

**Q：我不是新浪邮箱能用吗？**
A：这个版本只针对新浪邮箱（mail.sina.com.cn）的网页结构做了适配。
