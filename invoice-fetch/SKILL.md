---
name: invoice-fetch
description: 从用户的新浪邮箱（xiexiaoxiong@sina.com）收件夹抓取电子发票并生成报销材料。当用户说"抓发票/收发票/下载发票/整理发票/发票清单/报销发票/调用发票skill"或提到邮箱里的发票、电子发票、增值税发票时使用。流程：打开带 CDP 调试端口的专用浏览器让用户登录，然后枚举收件夹邮件、下载发票附件或正文税务交付链接中的 PDF、去重、按"金额-项目-抬头-发票号"重命名，生成 发票清单.xlsx（含总金额）和 发票_四拼一汇总.pdf。只下载 PDF 和图片，严格跳过 OFD 和 XML，不生成运行结果.json。
---

# 发票抓取（新浪邮箱 · CDP 直连版）

## 硬性规则（用户明确要求，不得违反）

1. **只下载 PDF 和图片**（.pdf/.png/.jpg/.jpeg/.gif/.bmp/.webp/.tif/.tiff）。**永远不下载 .ofd**，.xml 和其它扩展名也一律跳过。
2. **不生成 `运行结果.json`**。产物只有：发票文件、`发票清单.xlsx`、`发票_四拼一汇总.pdf`、`发票文件名清单.txt`、`需要二次扫码/`（如有）。
3. 默认发票抬头：**北京德恒（深圳）律师事务所**（提取不到抬头时的兜底）。
4. 只看收件夹（INBOX），默认最近 30 天，关键词：发票/电子发票/增值税/开票/invoice。

## 执行流程

脚本：`scripts/fetch_invoices.py`，处理库：`scripts/invoice_lib.py`（invoice_skill.py 的副本，纯标准库）。

**第一步 · 登录（需要用户配合，两轮交互）**

```bash
python3 scripts/fetch_invoices.py open-login
```

- 会打开一个带 `--remote-debugging-port=9222` 的专用 Chrome 窗口（配置目录独立，默认 `~/.invoice-fetch/profile`）。
- 请用户**在该窗口**登录 mail.sina.com.cn，用户回复"好了"之后再继续。
- 不要复用用户日常 Chrome 的配置目录：新浪会话 Cookie 是 session 级，新进程启动即失效，拷贝配置不可行。CDP 直连同一进程是唯一稳定路径。

**第二步 · 抓取**

```bash
python3 scripts/fetch_invoices.py collect --output-dir <输出目录>
```

可选先跑 `list` 子命令预览匹配邮件（只读，不下载）。

## 关键实现要点（都是踩过的坑，勿回退）

- **防残留 DOM**：新浪邮箱是 SPA，点邮件后阅读窗异步切换。必须等阅读窗确认切到目标邮件再提取——校验附件链接里的 `mid` 参数等于目标 mid；无附件邮件校验阅读窗主题文本。否则会把上一封邮件的附件当成这封的。
- **无附件发票邮件**：票慧通等平台的"你有一张电子发票待接收"邮件没有附件，发票在正文链接里——深圳税务 dppt 平台交付链接（`dppt.shenzhen.chinatax.gov.cn.../exportDzfpwjEwm?Wjgs=PDF&Fphm=<发票号>...`，同一邮件附 PDF/OFD/XML 三个链接，链接文本即真实 URL，可直接 GET，无需登录）。**只取 `Wjgs=PDF` 那个**。
- **去重**：票慧通/票通常发重复通知（同一附件）。下载后按文件 SHA1 去重。
- **字段提取**：环境缺 pdftotext/tesseract 时，PDF 用 pypdf 提取文本再正则取 发票号码/价税合计小写/`*类目*项目`；失败再回退 `invoice_lib.parse_invoice_fields`。
- **二维码小票**：图片经 `is_likely_qr_image` 判断（无 tesseract 时可能漏判，agent 可用 ReadMediaFile 目视确认），移入 `需要二次扫码/` 并在回复中提醒开票失效日期。
- **重命名**：`金额-项目-抬头-发票号.扩展名`（`invoice_lib.rename_invoice_file`）。

## 完成后

- 汇报：发票张数、总金额、每张的 金额/项目/销售方/发票号 表格、待扫码提醒。
- 回复中附 `发票清单.xlsx` 和 `发票_四拼一汇总.pdf` 的文件链接。
- 临时脚本和调试截图用完即删；专用浏览器窗口可提醒用户关闭。
