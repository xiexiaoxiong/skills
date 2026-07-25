#!/usr/bin/env python3
"""从已登录的新浪邮箱网页会话抓取发票（仅 PDF/图片），并生成清单与四拼一汇总。

用法：
  python3 fetch_invoices.py open-login [--profile-dir DIR] [--port 9222]
  python3 fetch_invoices.py list       [--port 9222] [--days 30]
  python3 fetch_invoices.py collect    [--port 9222] [--days 30] [--output-dir DIR] [--default-title 抬头]

流程约定（用户修正后的规则，勿改）：
  - 只下载 PDF 和图片（.pdf/.png/.jpg/.jpeg/.gif/.bmp/.webp/.tif/.tiff）
  - 严格跳过 .xml 和 .ofd，其它扩展名也一律不下载
  - 不生成 运行结果.json
  - 打开邮件后必须校验阅读窗已切换到目标邮件，再提取附件/链接（防残留 DOM）
  - 无附件的发票通知邮件，扫描正文里的税务平台交付链接（chinatax/dppt），只取 Wjgs=PDF
  - 文件按 SHA1 去重；二维码小票移入 需要二次扫码/
"""
import argparse
import hashlib
import json
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


def cmd_open_login(args):
    """打开专用浏览器窗口（带 CDP 调试端口），等用户手动登录邮箱。"""
    profile = Path(args.profile_dir).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    app = CHROME_FOR_TESTING if Path(CHROME_FOR_TESTING).exists() else SYSTEM_CHROME
    subprocess.run([
        "open", "-na", app, "--args",
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={args.port}",
        "--no-first-run", "--no-default-browser-check",
        "https://mail.sina.com.cn",
    ], check=True)
    time.sleep(5)
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/json/version", timeout=5) as r:
            print("CDP 就绪:", r.read(120).decode(errors="ignore"))
    except Exception as e:
        print("警告：CDP 端口未就绪:", e)
    print(f"\n请在打开的窗口登录邮箱，完成后告诉 agent『好了』，再执行 collect。")


def connect(port):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0]
    pages = [p for p in ctx.pages if "mail.sina" in p.url]
    if not pages:
        pw.stop()
        raise SystemExit("未找到新浪邮箱标签页，请先 open-login 并登录。")
    page = pages[0]
    page.set_default_timeout(30000)
    return pw, ctx, page


def open_inbox(page):
    for fr in [page] + page.frames:
        try:
            el = fr.query_selector("text=收件夹")
            if el:
                el.click()
                page.wait_for_timeout(5000)
                return True
        except Exception:
            continue
    return False


def parse_row_date(text, today):
    """从行文本首段解析日期：'11 小时前'/'昨天11:05'/'7月20日'/'2025年12月30日'。"""
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
    m = re.match(r"^周[一二三四五六日天]$", head)
    if m:
        return today  # 本周内，粗估
    return None


def list_rows(page, days):
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


def wait_mail_open(page, mid, subject, timeout=20):
    """确认阅读窗已切换到目标邮件（防止读到上一封的残留 DOM）。"""
    frame = page.main_frame
    deadline = time.time() + timeout
    while time.time() < deadline:
        att_mids = frame.evaluate(
            """() => Array.from(document.querySelectorAll('a[href*="base_download_att.php"]'))
                .map(a => { const m = a.href.match(/[?&]mid=([0-9A-F]+)/); return m ? m[1] : ''; })""")
        if att_mids and all(m.upper() == mid.upper() for m in att_mids if m):
            return True
        # 无附件邮件：校验阅读窗主题文本
        head = frame.evaluate("""() => {
            const cands = document.querySelectorAll('.subject, [class*=mailTitle], [class*=mail_subject], h1, h2');
            return Array.from(cands).map(e => (e.innerText||'').trim()).join(' ');
        }""")
        if subject and subject[:12] in head:
            return True
        if not att_mids:
            # 无附件链接时给主题校验更多机会
            page.wait_for_timeout(1000)
        else:
            # 有附件链接但 mid 不匹配 = 残留，重新点击
            frame.evaluate(
                """(mid) => { const el = document.querySelector('div.listrow[mid="' + mid + '"] a.subject'); if (el) el.click(); }""",
                mid)
            page.wait_for_timeout(3000)
    return False


def download(ctx, url, out_dir, fname):
    ext = Path(urllib.parse.unquote(fname)).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return None, f"跳过（不允许的格式 {ext}）: {fname}"
    resp = ctx.request.get(url, timeout=60000, max_redirects=10)
    if not resp.ok:
        return None, f"下载失败 HTTP {resp.status}: {fname}"
    body = resp.body()
    if ext == ".pdf" and not body[:4] == b"%PDF":
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


def extract_fields_pypdf(fp):
    """pypdf 提取发票字段；失败返回 None。"""
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
    }


def cmd_list(args):
    pw, ctx, page = connect(args.port)
    try:
        open_inbox(page)
        rows = list_rows(page, args.days)
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

    pw, ctx, page = connect(args.port)
    downloaded, rows_out, qr_paths, skipped = [], [], [], 0
    seen = set()
    try:
        open_inbox(page)
        mails = list_rows(page, args.days)
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
            if not wait_mail_open(page, mid, subject):
                print("  !! 阅读窗未确认切换，跳过以防误抓")
                skipped += 1
                continue

            files = []
            # 1) 附件（仅 PDF/图片，跳过 xml/ofd/其它）
            att_links = frame.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*="base_download_att.php"]')).map(a => a.href)""")
            for href in dict.fromkeys(att_links):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                fname = qs.get("file_name", ["att.bin"])[0]
                fp, msg = download(ctx, href, out_dir, fname)
                print("  " + msg)
                if fp:
                    files.append((fp, fname))
                else:
                    skipped += 1

            # 2) 无附件：扫正文税务平台交付链接（只取 PDF）
            if not files:
                links = frame.evaluate("""() => Array.from(document.querySelectorAll('a'))
                    .map(a => (a.innerText||'').trim())
                    .filter(t => t.startsWith('http'))""")
                pdf_urls = [t for t in dict.fromkeys(links)
                            if any(h in t for h in TAX_LINK_HINTS) and "Wjgs=PDF" in t]
                for url in pdf_urls:
                    fphm = re.search(r"Fphm=(\d+)", url)
                    fname = f"dppt_{fphm.group(1) if fphm else 'unknown'}.pdf"
                    fp, msg = download(ctx, url, out_dir, fname)
                    print("  正文链接 " + msg)
                    if fp:
                        files.append((fp, fname))
                    else:
                        skipped += 1
                if not pdf_urls:
                    print("  未发现附件或税务交付链接")

            # 3) 去重 + 处理
            for fp, fname in files:
                h = hashlib.sha1(fp.read_bytes()).hexdigest()
                if h in seen:
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
                        fp, subject=subject, sender=sender,
                        fallback_title=args.default_title)
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
    finally:
        pw.stop()

    # 4) 汇总产物（不生成 运行结果.json）
    invoice_lib.write_xlsx(out_dir / "发票清单.xlsx", rows_out)
    invoice_lib.build_four_up_pdf(downloaded, out_dir / "发票_四拼一汇总.pdf")
    (out_dir / "发票文件名清单.txt").write_text("\n".join(str(p) for p in downloaded), encoding="utf-8")
    if qr_paths:
        (out_dir / "需要二次扫码清单.txt").write_text("\n".join(str(p) for p in qr_paths), encoding="utf-8")

    total = sum(invoice_lib._parse_amount_to_number(r["amount"]) for r in rows_out)
    print(f"\n完成：{len(downloaded)} 张发票，总金额 {total:.2f} 元；跳过 {skipped}；待扫码 {len(qr_paths)}")
    print(f"输出目录：{out_dir}")


def main():
    p = argparse.ArgumentParser(description="新浪邮箱发票抓取（仅 PDF/图片）")
    p.add_argument("command", choices=["open-login", "list", "collect"])
    p.add_argument("--port", type=int, default=9222)
    p.add_argument("--profile-dir", default=str(Path.home() / ".invoice-fetch" / "profile"))
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--output-dir", default=str(Path.home() / "Downloads" / "发票"))
    p.add_argument("--default-title", default="北京德恒（深圳）律师事务所")
    args = p.parse_args()
    {"open-login": cmd_open_login, "list": cmd_list, "collect": cmd_collect}[args.command](args)


if __name__ == "__main__":
    main()
