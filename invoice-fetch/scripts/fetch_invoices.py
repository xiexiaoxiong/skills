#!/usr/bin/env python3
"""从任意已登录邮箱的网页会话抓取发票（仅 PDF/图片），并生成清单与四拼一汇总。

用法：
  python3 fetch_invoices.py open-login --email 你的邮箱 [--profile-dir DIR] [--port 9222]
  python3 fetch_invoices.py list       [--port 9222] [--days 31]
  python3 fetch_invoices.py collect    [--port 9222] [--days 31] [--output-dir DIR] [--default-title 抬头]

流程约定（用户修正后的规则，勿改）：
  - 任意邮箱：用户给什么邮箱，就打开什么邮箱的登录页；登录后流程一致
  - 只下载 PDF 和图片（.pdf/.png/.jpg/.jpeg/.gif/.bmp/.webp/.tif/.tiff）
  - 严格跳过 .xml 和 .ofd，其它扩展名也一律不下载
  - 不生成 运行结果.json
  - 发票若以链接形式提供：点开链接，下载 PDF 格式的电子发票
  - 打开邮件后必须校验阅读窗已切换到目标邮件，再提取附件/链接（防残留 DOM）
  - 文件按 SHA1 去重；二维码小票移入 需要二次扫码/
  - 默认范围：最近 31 天
"""
import argparse
import hashlib
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import invoice_lib  # noqa: E402  本 skill 自带的处理库（invoice_skill.py 副本）

CHROME_FOR_TESTING = "/Users/xiexiaoxiong/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app"
SYSTEM_CHROME = "/Applications/Google Chrome.app"

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
KEYWORDS = ("发票", "电子发票", "增值税", "开票", "invoice")
TAX_LINK_HINTS = ("chinatax", "dppt", "exportDzfpwjEwm")
INVOICE_LINK_TEXT_HINTS = ("发票", "invoice", "下载", "download", "查看")

LOGIN_URLS = {
    "sina.com": "https://mail.sina.com.cn",
    "sina.com.cn": "https://mail.sina.com.cn",
    "163.com": "https://mail.163.com",
    "126.com": "https://mail.126.com",
    "qq.com": "https://mail.qq.com",
    "foxmail.com": "https://mail.qq.com",
    "gmail.com": "https://mail.google.com",
    "outlook.com": "https://outlook.office.com",
    "hotmail.com": "https://outlook.office.com",
    "yeah.net": "https://mail.yeah.net",
    "139.com": "https://mail.139.com",
    "aliyun.com": "https://mail.aliyun.com",
    # 企业邮箱的特殊登录路径（非 mail.<域名> 根路径）在此单独登记
    "dehenglaw.com": "https://mail.dehenglaw.com/webmail/cgi/index.cgi",
}


def login_hint(email: str) -> str:
    domain = email.split("@", 1)[-1].lower() if "@" in email else ""
    if domain in LOGIN_URLS:
        return LOGIN_URLS[domain]
    return f"https://mail.{domain}" if domain else "https://mail.sina.com.cn"


def cmd_open_login(args):
    """打开专用浏览器窗口（带 CDP 调试端口），等用户手动登录邮箱。"""
    if not args.email:
        raise SystemExit("请提供邮箱：--email 你的邮箱（用户输入什么邮箱，就打开什么邮箱的登录页）")
    url = args.login_url or login_hint(args.email)
    profile = Path(args.profile_dir).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    app = CHROME_FOR_TESTING if Path(CHROME_FOR_TESTING).exists() else SYSTEM_CHROME
    subprocess.run([
        "open", "-na", app, "--args",
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={args.port}",
        "--no-first-run", "--no-default-browser-check",
        url,
    ], check=True)
    time.sleep(5)
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/json/version", timeout=5) as r:
            print("CDP 就绪:", r.read(120).decode(errors="ignore"))
    except Exception as e:
        print("警告：CDP 端口未就绪:", e)
    print(f"\n已打开 {url}\n请在该窗口登录 {args.email}，完成后告诉 agent『好了』，再执行 collect。")


def connect(port, email=""):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0]
    pages = [p for p in ctx.pages if p.url and not p.url.startswith("about:")]
    if email and "@" in email:
        domain = email.split("@", 1)[-1].lower()
        hit = [p for p in pages if domain in p.url]
        if hit:
            return pw, ctx, hit[0]
    mailish = [p for p in pages if re.search(r"mail|outlook|gmail", p.url, re.I)]
    page = (mailish or pages or [None])[0]
    if page is None:
        pw.stop()
        raise SystemExit("未找到邮箱标签页，请先 open-login 并登录。")
    page.set_default_timeout(30000)
    return pw, ctx, page


def open_inbox(page):
    for fr in [page] + page.frames:
        try:
            el = fr.query_selector("text=收件夹") or fr.query_selector("text=收件箱") or fr.query_selector("text=Inbox")
            if el:
                el.click()
                page.wait_for_timeout(5000)
                return True
        except Exception:
            continue
    return False


def is_sina(page) -> bool:
    return "sina.com" in page.url


def parse_row_date(text, today):
    head = text.split("|")[0].strip()
    if "小时前" in head or "分钟前" in head or "刚刚" in head:
        return today
    if head.startswith("昨天"):
        return today - timedelta(days=1)
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", head)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    m = re.match(r"^(\d{1,2})月(\d{1,2})日", head)
    if m:
        d = datetime(today.year, int(m.group(1)), int(m.group(2))).date()
        return d if d <= today else datetime(today.year - 1, int(m.group(1)), int(m.group(2))).date()
    return None


def list_rows_sina(page, days):
    frame = page.main_frame
    rows = frame.evaluate("""() => {
        const out = [];
        for (const el of document.querySelectorAll('div.listrow[mid]')) {
            const a = el.querySelector('a.subject');
            const parts = (el.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);
            out.push({
                mid: el.getAttribute('mid'),
                subject: a ? (a.getAttribute('title')||a.innerText||'').trim() : '',
                sender: parts.length > 1 ? parts[1] : '',
                dateText: parts.length ? parts[0] : ''
            });
        }
        return out;
    }""")
    today = datetime.now().date()
    cutoff = today - timedelta(days=days) if days > 0 else None
    matched = []
    for r in rows:
        if not any(k.lower() in (r["subject"] + r["sender"]).lower() for k in KEYWORDS):
            continue
        d = parse_row_date(r["dateText"], today)
        if cutoff and d and d < cutoff:
            continue
        matched.append(r)
    return matched


def wait_mail_open_sina(page, mid, subject, timeout=20):
    """确认阅读窗已切换到目标邮件（防止读到上一封的残留 DOM）。"""
    frame = page.main_frame
    deadline = time.time() + timeout
    while time.time() < deadline:
        att_mids = frame.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="base_download_att.php"]'))
                .map(a => { const m = a.href.match(/[?&]mid=([0-9A-F]+)/); return m ? m[1] : ''; })""")
        if att_mids and all(m.upper() == mid.upper() for m in att_mids if m):
            return True
        head = frame.evaluate("""() => {
            const cands = document.querySelectorAll('.subject, [class*=mailTitle], [class*=mail_subject], h1, h2');
            return Array.from(cands).filter(e => !e.closest('div.listrow')).map(e => (e.innerText||'').trim()).join(' ');
        }""")
        if subject and subject[:12] in head:
            return True
        if not att_mids:
            page.wait_for_timeout(1000)
        else:
            frame.evaluate(
                """(mid) => { const el = document.querySelector('div.listrow[mid="' + mid + '"] a.subject'); if (el) el.click(); }""",
                mid)
            page.wait_for_timeout(3000)
    return False


def save_file(body, out_dir, fname):
    ext = Path(urllib.parse.unquote(fname)).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return None, f"跳过（不允许的格式 {ext}）: {fname}"
    if ext == ".pdf" and body[:4] != b"%PDF":
        return None, f"非 PDF 内容: {fname}"
    safe = re.sub(r'[\\/:*?"<>|]', "_", urllib.parse.unquote(fname))
    target = out_dir / safe
    n = 1
    while target.exists():
        if hashlib.sha1(target.read_bytes()).hexdigest() == hashlib.sha1(body).hexdigest():
            return target, f"已存在（内容相同）: {safe}"
        target = out_dir / f"{Path(safe).stem}_{n}{Path(safe).suffix}"
        n += 1
    target.write_bytes(body)
    return target, f"已保存: {safe} ({len(body)} bytes)"


def download(ctx, url, out_dir, fname):
    try:
        resp = ctx.request.get(url, timeout=60000, max_redirects=10)
    except Exception as e:
        return None, f"下载异常: {e}"
    if not resp.ok:
        return None, f"下载失败 HTTP {resp.status}: {fname}"
    return save_file(resp.body(), out_dir, fname)


def filename_from_cd(resp, fallback):
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", cd, re.I)
    return urllib.parse.unquote(m.group(1)) if m else fallback


def collect_body_links(page):
    """收集当前打开邮件正文里的候选链接（文本或 href 含发票/下载语义的外部链接）。"""
    out = []
    for fr in page.frames:
        try:
            links = fr.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({t: (a.innerText||'').trim(), h: a.href}))
                .filter(x => x.h.startsWith('http'))""")
            out.extend(links)
        except Exception:
            continue
    # 链接文本本身就是 URL 的情况（如税务平台交付链接）
    for fr in page.frames:
        try:
            texts = fr.evaluate("""() => Array.from(document.querySelectorAll('a'))
                .map(a => (a.innerText||'').trim()).filter(t => t.startsWith('http'))""")
            out.extend({"t": t, "h": t} for t in texts)
        except Exception:
            continue
    seen, res = set(), []
    for x in out:
        key = x["h"]
        if key in seen:
            continue
        seen.add(key)
        res.append(x)
    return res


def fetch_pdf_from_link(ctx, page, link, out_dir):
    """点开正文链接，下载 PDF 格式电子发票。返回 (Path|None, msg)。"""
    href, text = link["h"], link["t"]
    candidates = []
    # 税务平台交付链接：只取 Wjgs=PDF
    for u in {href, text}:
        if any(h in u for h in TAX_LINK_HINTS):
            if "Wjgs=PDF" in u:
                candidates.append(u)
            continue
        path = urllib.parse.urlsplit(u).path.lower()
        if path.endswith(".pdf"):
            candidates.append(u)
    for url in dict.fromkeys(candidates):
        fphm = re.search(r"Fphm=(\d+)", url)
        fname = f"invoice_{fphm.group(1) if fphm else hashlib.sha1(url.encode()).hexdigest()[:8]}.pdf"
        fp, msg = download(ctx, url, out_dir, fname)
        if fp:
            return fp, msg
    # 其它发票链接：打开落地页找 PDF 下载入口
    if not any(h in text + href for h in INVOICE_LINK_TEXT_HINTS):
        return None, "非发票链接，未跟进"
    landing = None
    try:
        landing = ctx.new_page()
        landing.set_default_timeout(20000)
        landing.goto(href, wait_until="domcontentloaded", timeout=45000)
        landing.wait_for_timeout(5000)
        pdf_links = landing.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href).filter(h => h.toLowerCase().split('?')[0].endsWith('.pdf'))""")
        for url in dict.fromkeys(pdf_links):
            fp, msg = download(ctx, url, out_dir, url.split("/")[-1].split("?")[0] or "invoice.pdf")
            if fp:
                return fp, f"落地页 " + msg
        # 页面本身可能直接返回 PDF（跳转后）
        if landing.url.lower().split("?")[0].endswith(".pdf"):
            fp, msg = download(ctx, landing.url, out_dir, landing.url.split("/")[-1].split("?")[0])
            if fp:
                return fp, f"落地页直链 " + msg
        return None, "落地页未找到 PDF 下载入口"
    except Exception as e:
        return None, f"落地页打开失败: {e}"
    finally:
        if landing:
            try:
                landing.close()
            except Exception:
                pass


def process_files(files, subject, sender, args, out_dir, qr_dir, seen, downloaded, rows_out, qr_paths, preexisting=frozenset()):
    skipped = 0
    for fp in files:
        h = hashlib.sha1(fp.read_bytes()).hexdigest()
        if h in seen:
            if fp in preexisting:
                print(f"  已在库中（本轮跳过）: {fp.name}")
            else:
                print(f"  重复跳过: {fp.name}")
                fp.unlink()
            skipped += 1
            continue
        seen.add(h)
        if fp.suffix.lower() in invoice_lib.IMAGE_EXTS:
            text = invoice_lib.extract_text_for_file(fp)
            if invoice_lib.is_likely_qr_image(fp, text):
                tgt = invoice_lib.move_to_qr_folder(fp, qr_dir)
                qr_paths.append(tgt)
                print(f"  疑似二维码小票，移入待扫码: {tgt.name}")
                continue
        fields = extract_fields_pypdf(fp) if fp.suffix.lower() == ".pdf" else None
        if fields is None:
            fields = invoice_lib.parse_invoice_fields(
                fp, subject=subject, sender=sender, fallback_title=args.default_title)
        if fields.get("title") in ("", "待补充"):
            fields["title"] = args.default_title or "待补充"
        try:
            renamed = invoice_lib.rename_invoice_file(fp, fields)
        except Exception:
            renamed = fp
        print(f"  入账: {renamed.name}")
        downloaded.append(renamed)
        rows_out.append({"amount": fields["amount"], "project": fields["project"],
                         "title": fields["title"], "invoice_no": fields["invoice_no"]})
    return skipped


def extract_fields_pypdf(fp):
    try:
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(str(fp)).pages)
    except Exception:
        return None
    if "发票" not in text:
        return None
    no = re.findall(r"发票号码[：: ]*(\d{8,20})", text) or re.findall(r"\b(\d{20})\b", text)
    amt = re.findall(r"小写）[：: ]*¥?\s*(\d+\.\d{2})", text) or re.findall(r"¥\s*(\d+\.\d{2})", text)
    proj = re.findall(r"\*[^*\n]+\*([^\s\n|]+)", text)
    return {
        "invoice_no": no[0] if no else "待补充",
        "amount": amt[-1] if amt else "待补充",
        "project": proj[0] if proj else "待补充",
        "title": "",
    }


def cmd_list(args):
    pw, ctx, page = connect(args.port, args.email)
    try:
        if not is_sina(page):
            print("当前邮箱非新浪网页版，list 仅支持新浪；可直接 collect（通用模式会扫描当前打开页面）。")
            return
        open_inbox(page)
        rows = list_rows_sina(page, args.days)
        print(f"最近 {args.days} 天匹配发票关键词的邮件 {len(rows)} 封：")
        for r in rows:
            print(f"  [{r['dateText']}] {r['sender']} | {r['subject'][:50]} | mid={r['mid'][:8]}")
    finally:
        pw.stop()


def cmd_collect(args):
    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    qr_dir = out_dir / "需要二次扫码"
    qr_dir.mkdir(exist_ok=True)

    pw, ctx, page = connect(args.port, args.email)
    downloaded, rows_out, qr_paths = [], [], []
    seen = set()
    skipped = 0
    # 预置输出目录中已有文件的哈希，避免重复通知邮件把旧发票再入一次账
    preexisting = set()
    for old in out_dir.iterdir():
        if old.is_file() and old.suffix.lower() in ALLOWED_EXTS and "四拼一" not in old.name:
            seen.add(hashlib.sha1(old.read_bytes()).hexdigest())
            preexisting.add(old)
    try:
        if is_sina(page):
            open_inbox(page)
            mails = list_rows_sina(page, args.days)
            print(f"匹配邮件 {len(mails)} 封，开始处理…")
            frame = page.main_frame
            for mail in mails:
                mid, subject, sender = mail["mid"], mail["subject"], mail["sender"]
                print(f"\n=== {subject[:45]}")
                open_inbox(page)
                frame.evaluate(
                    """(mid) => { const el = document.querySelector('div.listrow[mid="' + mid + '"] a.subject'); if (el) el.click(); }""",
                    mid)
                page.wait_for_timeout(5000)
                if not wait_mail_open_sina(page, mid, subject):
                    print("  !! 阅读窗未确认切换，跳过以防误抓")
                    skipped += 1
                    continue
                files = []
                att_links = frame.evaluate(
                    """() => Array.from(document.querySelectorAll('a[href*="base_download_att.php"]')).map(a => a.href)""")
                for href in dict.fromkeys(att_links):
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    fname = qs.get("file_name", ["att.bin"])[0]
                    fp, msg = download(ctx, href, out_dir, fname)
                    print("  " + msg)
                    if fp:
                        files.append(fp)
                    else:
                        skipped += 1
                if not files:
                    found = False
                    for link in collect_body_links(page):
                        fp, msg = fetch_pdf_from_link(ctx, page, link, out_dir)
                        if fp:
                            print("  正文链接 " + msg)
                            files.append(fp)
                            found = True
                    if not found:
                        print("  未发现附件或可用的发票链接")
                skipped += process_files(files, subject, sender, args, out_dir, qr_dir,
                                         seen, downloaded, rows_out, qr_paths, preexisting)
        else:
            # 通用模式：扫描当前打开的页面（附件链接 + 正文发票链接）
            print("通用模式：扫描当前页面…（非新浪邮箱请先手动打开目标发票邮件）")
            files = []
            for fr in page.frames:
                try:
                    atts = fr.evaluate("""() => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({t:(a.innerText||'').trim(), h:a.href}))
                        .filter(x => /\\.(pdf|png|jpe?g|gif|bmp|webp|tiff?)(\\?|$)/i.test(x.h))""")
                    for a in atts:
                        fp, msg = download(ctx, a["h"], out_dir,
                                           a["h"].split("/")[-1].split("?")[0] or "file.pdf")
                        print("  " + msg)
                        if fp:
                            files.append(fp)
                        else:
                            skipped += 1
                except Exception:
                    continue
            if not files:
                for link in collect_body_links(page):
                    fp, msg = fetch_pdf_from_link(ctx, page, link, out_dir)
                    if fp:
                        print("  正文链接 " + msg)
                        files.append(fp)
            if not files:
                print("  当前页面未发现发票文件，请打开目标邮件后重试")
            skipped += process_files(files, "", "", args, out_dir, qr_dir,
                                     seen, downloaded, rows_out, qr_paths, preexisting)
    finally:
        pw.stop()

    invoice_lib.write_xlsx(out_dir / "发票清单.xlsx", rows_out)
    invoice_lib.build_four_up_pdf(downloaded, out_dir / "发票_四拼一汇总.pdf")
    (out_dir / "发票文件名清单.txt").write_text("\n".join(str(p) for p in downloaded), encoding="utf-8")
    if qr_paths:
        (out_dir / "需要二次扫码清单.txt").write_text("\n".join(str(p) for p in qr_paths), encoding="utf-8")

    total = sum(invoice_lib._parse_amount_to_number(r["amount"]) for r in rows_out)
    print(f"\n完成：{len(downloaded)} 张发票，总金额 {total:.2f} 元；跳过 {skipped}；待扫码 {len(qr_paths)}")
    print(f"输出目录：{out_dir}")


def main():
    p = argparse.ArgumentParser(description="邮箱发票抓取（任意邮箱，仅 PDF/图片）")
    p.add_argument("command", choices=["open-login", "list", "collect"])
    p.add_argument("--email", default="", help="用户邮箱；open-login 必填（给什么邮箱打开什么登录页）")
    p.add_argument("--login-url", default="", help="手动指定登录页 URL（企业邮箱特殊路径时用，优先级高于域名推断）")
    p.add_argument("--port", type=int, default=9222)
    p.add_argument("--profile-dir", default=str(Path.home() / ".invoice-fetch" / "profile"))
    p.add_argument("--days", type=int, default=31, help="只检索最近 N 天，默认 31，0 表示全部")
    p.add_argument("--output-dir", default=str(Path.home() / "Downloads" / "发票"))
    p.add_argument("--default-title", default="北京德恒（深圳）律师事务所")
    args = p.parse_args()
    {"open-login": cmd_open_login, "list": cmd_list, "collect": cmd_collect}[args.command](args)


if __name__ == "__main__":
    main()
