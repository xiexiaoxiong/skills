---
name: invoice-fetch
description: 从用户任意邮箱（新浪/163/126/QQ/Gmail/Outlook 等）的收件夹抓取电子发票并生成报销材料。当用户说"抓发票/收发票/下载发票/整理发票/发票清单/报销发票/调用发票skill"或提到邮箱里的发票、电子发票、增值税发票时使用。流程：按用户给的邮箱打开对应登录页（带 CDP 调试端口的专用浏览器），用户登录后枚举收件夹、下载发票附件；发票若以链接形式提供则点开链接下载 PDF。去重后按"金额-项目-抬头-发票号"重命名，生成 发票清单.xlsx（含总金额）和 发票_四拼一汇总.pdf。只下载 PDF 和图片，严格跳过 OFD 和 XML，不生成运行结果.json，默认最近 31 天。
---

# 发票抓取（任意邮箱 · CDP 直连版）

## 硬性规则（用户明确要求，不得违反）

1. **任意邮箱**：用户输入什么邮箱，就打开什么邮箱的登录页（`--email` 决定登录 URL），登录后的流程完全一致。不是新浪专用。
2. **只下载 PDF 和图片**（.pdf/.png/.jpg/.jpeg/.gif/.bmp/.webp/.tif/.tiff）。**永远不下载 .ofd**，.xml 和其它扩展名也一律跳过。
3. **链接形式的发票必须跟进**：邮件没有附件但正文有发票链接时，点开链接，下载 **PDF 格式**的电子发票（税务平台链接只取 `Wjgs=PDF`；直链 .pdf 直接下；其它发票链接打开落地页找 PDF 下载入口）。
4. **不生成 `运行结果.json`**。产物只有：发票文件、`发票清单.xlsx`、`发票_四拼一汇总.pdf`、`发票文件名清单.txt`、`需要二次扫码/`（如有）。
5. 默认范围：**最近 31 天**；关键词：发票/电子发票/增值税/开票/invoice。默认发票抬头：**北京德恒（深圳）律师事务所**。

## 执行流程

脚本：`scripts/fetch_invoices.py`，处理库：`scripts/invoice_lib.py`（invoice_skill.py 的副本，纯标准库）。

**第一步 · 登录（需要用户配合，两轮交互）**

```bash
python3 scripts/fetch_invoices.py open-login --email 用户输入的邮箱
```

- 按邮箱域名推断登录页（sina/163/126/qq/foxmail/gmail/outlook/yeah/139/aliyun 已内置；**dehenglaw.com 用特殊路径 `https://mail.dehenglaw.com/webmail/cgi/index.cgi`**；其它域名回退 `mail.<域名>`；推断不对时用 `--login-url` 手动指定），打开带 `--remote-debugging-port=9222` 的专用浏览器窗口（配置目录独立，默认 `~/.invoice-fetch/profile`，与日常浏览器互不影响）。
- 请用户**在该窗口**完成登录，回复"好了"之后再继续。
- 不要复用用户日常浏览器的配置目录：会话 Cookie 多为 session 级，新进程启动即失效，拷贝配置不可行。CDP 直连同一进程是唯一稳定路径。

**第二步 · 抓取**

```bash
python3 scripts/fetch_invoices.py collect --email 用户邮箱 --output-dir <输出目录>
```

可选先跑 `list` 预览匹配邮件（只读；目前仅新浪网页版支持列表枚举）。

## 关键实现要点（都是踩过的坑，勿回退）

- **防残留 DOM**：网页邮箱多为 SPA，点邮件后阅读窗异步切换。必须确认阅读窗已切到目标邮件再提取——新浪校验附件链接的 `mid` 参数等于目标 mid；无附件邮件校验阅读窗主题文本。否则会把上一封邮件的附件当成这封的。
- **税务平台交付链接**：票慧通等平台的"你有一张电子发票待接收"邮件无附件，正文给 PDF/OFD/XML 三个链接（如 `dppt.<城市>.chinatax.gov.cn.../exportDzfpwjEwm?Wjgs=PDF&Fphm=<发票号>...`，链接文本即真实 URL，可直接 GET，无需登录），**只取 PDF**。
- **去重**：发票平台的重复通知邮件很多，下载后按文件 SHA1 去重。
- **字段提取**：环境缺 pdftotext/tesseract 时，PDF 用 pypdf 提取文本再正则取 发票号码/价税合计小写/`*类目*项目`；失败再回退 `invoice_lib.parse_invoice_fields`。
- **二维码小票**：图片经 `is_likely_qr_image` 判断（无 tesseract 时可能漏判，agent 可用 ReadMediaFile 目视确认），移入 `需要二次扫码/` 并在回复中提醒开票失效日期。
- **重命名**：`金额-项目-抬头-发票号.扩展名`（`invoice_lib.rename_invoice_file`）。

## 适配状态

- **新浪邮箱（mail.sina.com.cn）**：完整适配（列表枚举、阅读窗校验、附件直链、正文链接）。
- **其它邮箱**：登录与 CDP 流程相同；抓取走通用模式——agent 引导用户在已登录窗口打开目标发票邮件后执行 collect，脚本扫描当前页面的附件与发票链接。如需完整适配某个邮箱的列表结构，参照 `list_rows_sina` / `wait_mail_open_sina` 增加对应适配器。

## 完成后

- 汇报：发票张数、总金额、每张的 金额/项目/销售方/发票号 表格、待扫码提醒。
- 回复中附 `发票清单.xlsx` 和 `发票_四拼一汇总.pdf` 的文件链接。
- 临时脚本和调试截图用完即删；专用浏览器窗口可提醒用户关闭。
