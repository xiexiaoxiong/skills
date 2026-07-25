#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发票 skill（本地版）
------------------
1. 指导用户完成邮箱登录（不替代用户输入账号密码）。
2. 只扫描 INBOX，不扫描其他文件夹。
3. 下载邮件中“图片或 PDF”附件；若正文含 PDF 链接也会尝试下载。
4. 所有命中文件保存在同一个本地文件夹。
5. 按规则重命名：发票金额-发票项目-发票抬头-发票号。
6. 生成 Excel 清单（.xlsx）。
7. 按 4 拼 1 布局生成横版 A4 PDF 汇总。

说明：
- 仅使用标准库 + 系统工具（可选）：tesseract / pdftotext / sips。
- 若环境里未安装某些系统工具，相关功能会自动降级并给出提示。
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import imaplib
import json
import re
import shutil
import ssl
import os
import subprocess
from datetime import datetime, timedelta
from email import policy
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED


ALLOWED_ATTACH_EXTS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
DEFAULT_KEYWORDS = ("发票", "电子发票", "增值税", "invoice", "开票")
QR_TEXT_HINTS = ("扫码", "二维码", "二维码支付", "微信", "支付宝", "打开二维码", "扫码后")
QR_FILENAME_HINTS = ("qrcode", "qr", "二维码", "scan", "扫码")
URL_RE = re.compile(r"https?://[^\s\"'<>()]+", flags=re.I)


A4_LANDSCAPE = (842.0, 595.0)
MARGIN = 20.0


def _safe(v: str, fallback: str = "未知") -> str:
    if not v:
        return fallback
    v = str(v).strip().replace("\r", " ").replace("\n", " ")
    v = re.sub(r"\s+", " ", v).strip()
    return v if v else fallback


def _component(v: str, max_len: int = 48) -> str:
    v = _safe(v, "未知")
    v = re.sub(r'[\\/:*?"<>|]+', "_", v)
    v = re.sub(r"[\x00-\x1f]", "_", v)
    v = re.sub(r"\s+", "", v)
    v = v.strip(" ._-")
    return (v[:max_len] or "未知")


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    stem = path.stem
    suffix = path.suffix
    while True:
        candidate = path.with_name(f"{stem}_{i:02d}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def run_cmd(cmd: List[str], timeout: int = 30) -> Tuple[int, str]:
    try:
        cp = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        return cp.returncode, (cp.stdout or "").strip()
    except Exception as e:
        return 1, str(e)


def _read_file_trimmed(path: str) -> Optional[str]:
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return text or None


def parse_disposition_filename(header: str) -> str:
    if not header:
        return ""
    m = re.search(r"filename\*?=(?:UTF-8''|UTF-8'')?\"?([^\";]+)", header, flags=re.I)
    if not m:
        return ""
    return decode_mime_value(m.group(1).strip().strip("\"'"))


def decode_mime_value(value: Optional[str]) -> str:
    if not value:
        return ""
    out = []
    for piece, enc in decode_header(value):
        if isinstance(piece, bytes):
            out.append(piece.decode(enc or "utf-8", errors="ignore"))
        else:
            out.append(piece)
    return "".join(out)


def infer_imap(email_addr: str) -> Tuple[str, int]:
    domain = email_addr.split("@", 1)[-1].lower()
    mapping = {
        "gmail.com": ("imap.gmail.com", 993),
        "outlook.com": ("outlook.office365.com", 993),
        "hotmail.com": ("outlook.office365.com", 993),
        "qq.com": ("imap.qq.com", 993),
        "163.com": ("imap.163.com", 993),
        "126.com": ("imap.126.com", 993),
        "yeah.net": ("imap.yeah.net", 993),
        "sina.com": ("imap.sina.com.cn", 993),
        "sina.com.cn": ("imap.sina.com.cn", 993),
    }
    return mapping.get(domain, (f"imap.{domain}", 993))


def web_login_hint(email_addr: str) -> str:
    domain = email_addr.split("@", 1)[-1].lower()
    mapping = {
        "gmail.com": "https://mail.google.com",
        "outlook.com": "https://outlook.office.com",
        "hotmail.com": "https://outlook.live.com",
        "qq.com": "https://mail.qq.com",
        "sina.com": "https://mail.sina.com.cn",
        "sina.com.cn": "https://mail.sina.com.cn",
        "163.com": "https://mail.163.com",
        "126.com": "https://mail.126.com",
        "yahoo.com": "https://mail.yahoo.com",
    }
    return mapping.get(domain, f"https://mail.{domain}")


def open_browser(url: str) -> None:
    # macOS 打开网页；在受限环境下会静默失败。
    try:
        subprocess.run(["open", url], check=False, capture_output=True)
    except Exception:
        pass


def _looks_invoice_like(text: str, keywords: Iterable[str]) -> bool:
    merged = text.lower()
    return any(k.lower() in merged for k in keywords)


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def _image_size_from_file(path: Path) -> Tuple[Optional[int], Optional[int]]:
    # 优先快速用 sips（macOS 自带）
    rc, out = run_cmd(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    if rc != 0:
        return None, None
    w = h = None
    for line in out.splitlines():
        m = re.match(r"\s*pixelWidth:\s*(\d+)", line)
        if m:
            w = int(m.group(1))
            continue
        m = re.match(r"\s*pixelHeight:\s*(\d+)", line)
        if m:
            h = int(m.group(1))
    if w and h:
        return w, h
    return None, None


def _ocr_text_is_sparse(text: str) -> bool:
    no_space = re.sub(r"\s+", "", text or "")
    if not no_space:
        return True
    # 发票通常会出现金额符号、金额数字和发票代码
    if re.search(r"[¥￥0-9]{4,}", no_space):
        return False
    # 太短且内容像二维码噪点时归类到二维码
    return len(no_space) < 40


def is_likely_qr_image(path: Path, ocr_text: str = "") -> bool:
    name_low = path.stem.lower()
    if any(k in name_low for k in QR_FILENAME_HINTS):
        return True

    if ocr_text and any(k in ocr_text for k in QR_TEXT_HINTS):
        return True

    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff"}:
        w, h = _image_size_from_file(path)
        if w and h:
            ratio = w / float(h)
            # 常见二维码是近似正方形，且尺寸偏小
            if 0.8 <= ratio <= 1.25 and min(w, h) > 80 and max(w, h) < 3000:
                # 先按形态判定
                if _ocr_text_is_sparse(ocr_text):
                    return True

    return False


def extract_body_text(msg: Message) -> str:
    chunks = []
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        if ctype not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            txt = payload.decode(charset, errors="ignore")
        except Exception:
            txt = payload.decode("utf-8", errors="ignore")
        if "html" in ctype:
            txt = _strip_html(txt)
        chunks.append(txt)
    return "\n".join(chunks)


def _read_password_from_keychain(email_addr: str, imap_host: str) -> Optional[str]:
    """
    尝试从 macOS Keychain 自动读取 IMAP 密码。
    找不到时返回 None。
    """
    if shutil.which("security") is None:
        return None

    email_addr = (email_addr or "").strip()
    if not email_addr:
        return None

    domain = email_addr.split("@", 1)[-1].lower() if "@" in email_addr else email_addr.lower()
    candidates = []

    if imap_host:
        candidates.append(("generic", imap_host, email_addr))
        candidates.append(("internet", imap_host, email_addr))

    candidates.extend([
        ("generic", f"imap.{domain}", email_addr),
        ("internet", f"imap.{domain}", email_addr),
        ("generic", f"mail.{domain}", email_addr),
        ("generic", domain, email_addr),
    ])

    for family, service, user in candidates:
        if family == "generic":
            cmd = ["security", "find-generic-password", "-a", user, "-s", service, "-w"]
        else:
            cmd = ["security", "find-internet-password", "-a", user, "-s", service, "-w"]
        code, out = run_cmd(cmd)
        if code == 0:
            pwd = (out or "").strip()
            if pwd:
                return pwd

    cmd = ["security", "find-generic-password", "-a", email_addr, "-w"]
    code, out = run_cmd(cmd)
    if code == 0:
        pwd = (out or "").strip()
        if pwd:
            return pwd

    return None


def _iter_urls(text: str) -> List[str]:
    candidates = []
    for url in URL_RE.findall(text or ""):
        u = url.strip().strip(")];\"'<>")
        if not u:
            continue
        candidates.append(u)
        # 兼容很多邮件在 query 前面还有追踪参数，允许保存原链接优先
        if "?" in u:
            base = u.split("?", 1)[0]
            candidates.append(base)
    # 去重
    uniq = []
    seen = set()
    for u in candidates:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _safe_ext_name_from_url(url: str, fallback: str = "", default_ext: str = ".pdf") -> str:
    name = Path(urlsplit(url).path).name.strip()
    if not name:
        return fallback
    name = decode_mime_value(name)
    ext = Path(name).suffix.lower()
    if ext in ALLOWED_ATTACH_EXTS:
        return name
    if default_ext:
        return f"{Path(name).stem}{default_ext}"
    return name


def _looks_pdf_like_url(url: str) -> bool:
    low = url.lower()
    if low.endswith(".pdf") or ".pdf" in low:
        return True
    return "invoice" in low or "fapiao" in low or "invoicefile" in low


def _looks_like_invoice_attachment(url: str, text: str, keywords: Iterable[str]) -> bool:
    return _looks_pdf_like_url(url) or _looks_invoice_like(f"{url} {text}", keywords)


def _looks_like_downloadable_file_url(url: str) -> bool:
    low = (url or "").lower()
    if not low.startswith("http"):
        return False
    if any(x in low for x in [".xml", ".zip", ".js", ".css", ".js?"]):
        return False
    if _looks_pdf_like_url(low):
        return True
    if urlsplit(low).path and any(urlsplit(low).path.lower().endswith(ext) for ext in ALLOWED_ATTACH_EXTS):
        return True
    return False


def _save_http_bytes(target_dir: Path, url: str, data: bytes, headers: Dict[str, str], idx: int) -> Optional[Path]:
    cd = headers.get("content-disposition", headers.get("Content-Disposition", "")) or ""
    name = parse_disposition_filename(cd)
    ext = ""
    if not name:
        name = _safe_ext_name_from_url(url, fallback=f"attachment_{idx}.pdf")
    if not name:
        return None
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_ATTACH_EXTS:
        ctype = (headers.get("content-type") or headers.get("Content-Type") or "").lower()
        if ctype.startswith("application/pdf"):
            ext = ".pdf"
            name = f"{Path(name).stem}.pdf"
        elif ctype.startswith("image/"):
            ext = ".jpg"
            name = f"{Path(name).stem}.jpg"
        elif ".pdf" in (url.lower()):
            ext = ".pdf"
            if not name.lower().endswith(".pdf"):
                name = f"{name}.pdf"
        else:
            return None
    if name.lower().endswith(".xml"):
        return None
    target = _unique(target_dir / name)
    target.write_bytes(data)
    final_ext = target.suffix.lower()
    if final_ext not in ALLOWED_ATTACH_EXTS:
        return None
    return target


def _valid_content_type_for_attachment(ct: Optional[str]) -> bool:
    if not ct:
        return False
    ct = ct.lower()
    return ct.startswith("application/pdf") or ct.startswith("image/")


def _file_ext_from_name(filename: str) -> str:
    name = Path(filename).name
    return Path(name).suffix.lower()


def _filename_from_message_part(part, fallback: str) -> str:
    raw = part.get_filename() or ""
    name = decode_mime_value(raw)
    if name:
        return name
    ext = ""
    ctype = (part.get_content_type() or "").lower()
    if "pdf" in ctype:
        ext = ".pdf"
    elif ctype.startswith("image/"):
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/webp": ".webp",
            "image/tiff": ".tif",
        }.get(ctype, ".jpg")
    return f"{fallback}{ext}"


def save_message_attachments(msg: Message, source_tag: str, target_dir: Path) -> List[Path]:
    saved: List[Path] = []
    idx = 1
    for part in msg.iter_attachments():
        if not _valid_content_type_for_attachment(part.get_content_type()):
            continue
        filename = _filename_from_message_part(part, f"{source_tag}_{idx:04d}")
        ext = _file_ext_from_name(filename)
        if ext == ".xml":
            continue
        if ext not in ALLOWED_ATTACH_EXTS:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        target = _unique(target_dir / filename)
        target.write_bytes(payload)
        saved.append(target)
        idx += 1
    return saved


def download_linked_pdf(url: str, target_dir: Path, idx: int, headers: Dict[str, str]) -> Optional[Path]:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if any(x in (parsed.path or "").lower() for x in [".xml", ".zip", ".exe", ".js", ".css"]):
        return None
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=60, context=ssl.create_default_context()) as r:
        ctype = (r.headers.get_content_type() or "").lower()
        cd = r.headers.get("Content-Disposition") or ""
        m = re.search(r'filename\\*?=(?:UTF-8\\x27\\x27)?\"?([^\";]+)', cd, flags=re.I)
        filename = _safe(m.group(1), "") if m else ""
        if not filename:
            filename = Path(parsed.path).name
        if not filename:
            filename = f"attachment_{idx}.pdf"
        filename = decode_mime_value(filename)
        ext = Path(filename).suffix.lower()
        if ext.lower() not in ALLOWED_ATTACH_EXTS:
            if ctype.startswith("application/pdf"):
                filename = f"{Path(filename).stem}.pdf"
            elif ctype.startswith("image/"):
                filename = f"{Path(filename).stem}.jpg"
            elif ".pdf" in (url.lower()):
                filename = f"{filename}.pdf"
            else:
                return None
        if filename.lower().endswith(".xml"):
            return None
        target = _unique(target_dir / filename)
        target.write_bytes(r.read())
        # 再做一次类型兜底校验
        final_ext = target.suffix.lower()
        if final_ext not in ALLOWED_ATTACH_EXTS and final_ext not in {".xml"}:
            return None
        return target


def extract_text_for_file(path: Path) -> str:
    text = ""
    if path.suffix.lower() == ".pdf":
        rc, out = run_cmd(["pdftotext", str(path), "-"])
        if rc == 0:
            text = out
    if not text and path.suffix.lower() in IMAGE_EXTS:
        rc, out = run_cmd([
            "tesseract",
            str(path),
            "stdout",
            "-l",
            "chi_sim+eng",
            "--dpi",
            "300",
        ])
        if rc == 0:
            text = out
    if not text and path.suffix.lower() == ".pdf":
        rc, out = run_cmd([
            "tesseract",
            str(path),
            "stdout",
            "-l",
            "chi_sim+eng",
            "--dpi",
            "300",
        ])
        if rc == 0:
            text = out
    return text


def _extract_first(text: str, patterns: List[str]) -> str:
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            raw = m.group(1) if m.groups() else m.group(0)
            value = _safe(raw.replace(" ", ""))
            if value:
                return value
    return ""


def parse_invoice_fields(path: Path, subject: str, sender: str, fallback_title: str = "", extracted_text: Optional[str] = None) -> Dict[str, str]:
    txt = extracted_text if extracted_text is not None else extract_text_for_file(path)
    combined = "\n".join([txt, subject, sender, path.stem])
    amount = _extract_first(combined, [
        r"(?:价税合计|发票金额|开票金额|合计金额|小写)\s*[:：]?\s*([0-9]+(?:\.[0-9]{1,2})?)",
        r"[¥￥]\s*([0-9]+(?:\.[0-9]{1,2})?)",
    ])
    if not amount:
        amount = "待补充"
    invoice_no = _extract_first(combined, [
        r"(?:发票号码?|发票号|发票代码|发票代码号码)\s*[:：]?\s*([0-9A-Za-z-]{6,})",
    ]) or "待补充"
    project = _extract_first(combined, [
        r"(?:开票项目|项目名称|商品名称|项目|货物\s*或\s*应税劳务、服务名称)\s*[:：]?\s*([^\r\n]{2,80})",
    ]) or "待补充"
    title = _extract_first(combined, [
        r"(?:购买方(?:名称|抬头)|发票抬头|客户名称|单位名称|公司名称)\s*[:：]?\s*([^\r\n]{2,80})",
    ])
    if not title:
        title = fallback_title or _safe(f"{parseaddr(sender)[0] or sender}", "待补充")
    return {
        "amount": amount,
        "project": project,
        "title": title,
        "invoice_no": invoice_no,
    }


def rename_invoice_file(path: Path, fields: Dict[str, str]) -> Path:
    new_name = (
        f"{_component(fields['amount'])}"
        f"-{_component(fields['project'])}"
        f"-{_component(fields['title'])}"
        f"-{_component(fields['invoice_no'])}"
        f"{path.suffix.lower()}"
    )
    target = _unique(path.with_name(new_name))
    path.rename(target)
    return target


def xml_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _col_letter(n: int) -> str:
    # 1-based
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _parse_amount_to_number(value: str) -> float:
    if not value:
        return 0.0
    if value in {"待补充", "未知"}:
        return 0.0

    normalized = str(value).replace("¥", "").replace("￥", "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+(?:\.\d{1,2})?", normalized)
    if not m:
        return 0.0
    try:
        return float(m.group(0))
    except Exception:
        return 0.0


def write_xlsx(path: Path, rows: List[Dict[str, str]]) -> None:
    headers = ["序号", "发票金额", "发票项目", "发票抬头", "发票号"]
    data_rows = [headers]
    total_amount = 0.0
    for idx, row in enumerate(rows, 1):
        total_amount += _parse_amount_to_number(row.get("amount", ""))
        data_rows.append([
            str(idx),
            row.get("amount", ""),
            row.get("project", ""),
            row.get("title", ""),
            row.get("invoice_no", ""),
        ])
    data_rows.append(["", f"{total_amount:.2f}", "总金额", "", ""])

    sheet_rows = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r, vals in enumerate(data_rows, 1):
        sheet_rows.append(f'<row r="{r}">')
        for c, val in enumerate(vals):
            col = _col_letter(c + 1)
            cell_ref = f"{col}{r}"
            text = xml_escape(_safe(val, ""))
            sheet_rows.append(f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        sheet_rows.append("</row>")
    sheet_rows.extend(["</sheetData>", "</worksheet>"])
    sheet_xml = "\n".join(sheet_rows).encode("utf-8")

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="发票清单" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    ).encode("utf-8")

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    ).encode("utf-8")

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="/docProps/core.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="/docProps/app.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="/xl/workbook.xml"/>'
        "</Relationships>"
    ).encode("utf-8")

    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>发票清单</dc:title>"
        f"<dcterms:created xsi:type=\"dcterms:W3CDTF\">{datetime.now().isoformat()}</dcterms:created>"
        "</cp:coreProperties>"
    ).encode("utf-8")

    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Invoice Skill</Application>"
        "<DocSecurity>0</DocSecurity>"
        "<ScaleCrop>false</ScaleCrop>"
        "<SharedDoc>false</SharedDoc>"
        "<HyperlinksChanged>false</HyperlinksChanged>"
        "<AppVersion>16.0000</AppVersion>"
        "</Properties>"
    ).encode("utf-8")

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    ).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("docProps/app.xml", app_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def parse_jpeg_dim(data: bytes) -> Tuple[int, int, int]:
    if len(data) < 4 or data[:2] != b"\xFF\xD8":
        return 0, 0, 3
    i = 2
    while i + 1 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if i + 7 > len(data):
                return 0, 0, 3
            seg_len = int.from_bytes(data[i:i + 2], "big")
            if i + seg_len - 2 > len(data):
                return 0, 0, 3
            h = int.from_bytes(data[i + 3:i + 5], "big")
            w = int.from_bytes(data[i + 5:i + 7], "big")
            comps = data[i + 7]
            return w, h, comps
        if i + 1 >= len(data):
            break
        seg_len = int.from_bytes(data[i:i + 2], "big")
        i += 2 + max(seg_len - 2, 0)
    return 0, 0, 3


def convert_to_jpeg(src: Path, dst: Path) -> Optional[Path]:
    if src.suffix.lower() in {".jpg", ".jpeg"}:
        return src
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    rc, _ = run_cmd([
        "sips",
        "-s",
        "format",
        "jpeg",
        str(src),
        "--out",
        str(dst),
    ])
    if rc == 0 and dst.exists() and dst.stat().st_size > 0:
        return dst
    return None


def build_four_up_pdf(image_or_pdf_paths: List[Path], out_pdf: Path) -> None:
    if not image_or_pdf_paths:
        print("无附件可用于四拼一合并。")
        return

    tmp_dir = out_pdf.parent / ".tmp_invoice_four_up"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    render_images: List[Path] = []
    for i, p in enumerate(image_or_pdf_paths, 1):
        dst = tmp_dir / f"page_{i:04d}.jpg"
        converted = convert_to_jpeg(p, dst)
        if converted:
            render_images.append(converted)

    if not render_images:
        print("四拼一：所有文件转图失败，跳过。")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    page_w, page_h = A4_LANDSCAPE
    cell_w = (page_w - 3 * MARGIN) / 2.0
    cell_h = (page_h - 3 * MARGIN) / 2.0
    cell_x = [MARGIN, MARGIN + cell_w + MARGIN]
    cell_y = [MARGIN, MARGIN + cell_h + MARGIN]
    # PDF 坐标系原点在左下角，注意 y 取反
    positions = [
        (cell_x[0], cell_y[1]),
        (cell_x[1], cell_y[1]),
        (cell_x[0], cell_y[0]),
        (cell_x[1], cell_y[0]),
    ]

    objects: List[bytes] = []

    def add_obj(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    page_ids: List[int] = []

    for page_start in range(0, len(render_images), 4):
        chunk = render_images[page_start:page_start + 4]
        xobj_names = []

        for local_i, src in enumerate(chunk):
            data = src.read_bytes()
            w, h, comps = parse_jpeg_dim(data)
            if w <= 0 or h <= 0:
                continue
            color = "/DeviceGray" if comps == 1 else "/DeviceRGB"
            img_obj_dict = (
                f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                f"/ColorSpace {color} /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>"
            )
            img_name = f"Im{local_i + 1}"
            xobj_id = add_obj(
                f"{len(objects) + 1} 0 obj\n".encode("utf-8")
                + img_obj_dict.encode("utf-8")
                + b"\nstream\n"
                + data
                + b"\nendstream\nendobj\n"
            )
            xobj_names.append((img_name, xobj_id, src, w, h))

        if not xobj_names:
            continue

        content_ops: List[str] = []
        for local_i, (_, _, _, w, h) in enumerate(xobj_names):
            px, py = positions[local_i]
            scale = min(cell_w / float(w), cell_h / float(h))
            draw_w = w * scale
            draw_h = h * scale
            x = px + (cell_w - draw_w) / 2.0
            y = py + (cell_h - draw_h) / 2.0
            img_name = f"Im{local_i + 1}"
            content_ops.append("q")
            content_ops.append(f"{draw_w:.4f} 0 0 {draw_h:.4f} {x:.4f} {y:.4f} cm")
            content_ops.append(f"/{img_name} Do")
            content_ops.append("Q")

        content = "\n".join(content_ops).encode("utf-8")
        content_id = add_obj(
            f"{len(objects) + 1} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode("utf-8")
            + content
            + b"\nendstream\nendobj\n"
        )

        resource_obj = "<< /XObject << "
        resource_obj += " ".join([f"/{name} {obj_id} 0 R" for name, obj_id, _, _, _ in xobj_names])
        resource_obj += " >> >>"
        page_obj = (
            f"{len(objects) + 1} 0 obj\n"
            f"<< /Type /Page /Parent __PARENT__ /MediaBox [0 0 {int(page_w)} {int(page_h)}] "
            f"/Resources {resource_obj} /Contents {content_id} 0 R >>\nendobj\n"
        ).encode("utf-8")
        page_id = add_obj(page_obj)
        page_ids.append(page_id)

    if not page_ids:
        print("四拼一：未生成任何PDF页。")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    pages_id = len(objects) + 1
    for pid in page_ids:
        raw = objects[pid - 1]
        objects[pid - 1] = raw.replace(b"__PARENT__", f"{pages_id} 0 R".encode("ascii"))

    pages_obj = (
        f"{pages_id} 0 obj\n"
        f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] >>\n"
        f"endobj\n"
    ).encode("utf-8")
    objects.append(pages_obj)
    catalog_id = len(objects) + 1
    catalog_obj = (
        f"{catalog_id} 0 obj\n"
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>\n"
        f"endobj\n"
    ).encode("utf-8")
    objects.append(catalog_obj)

    # 逐个写出并补 xref
    # PDF 标准头尾再加一个非 ASCII 注释，避免部分工具按文本处理
    out = bytearray(b"%PDF-1.4\n%\xE2\xE2\xA4\xA2\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(obj)
    xref_start = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, len(objects) + 1):
        out.extend(f"{offsets[i]:010d} 00000 n \n".encode("ascii"))
    trailer = (
        "trailer\n"
        f"<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    ).encode("ascii")
    out.extend(trailer)

    out_pdf.write_bytes(out)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def search_inbox_uids(imap_conn: imaplib.IMAP4_SSL, days: int) -> List[bytes]:
    if days > 0:
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        status, data = imap_conn.search(None, "SINCE", since)
    else:
        status, data = imap_conn.search(None, "ALL")
    if status != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _env_true(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "y", "on"}


def detect_source_mode() -> str:
    default_mode = os.environ.get("INVOICE_SOURCE_MODE", "auto").strip().lower()
    if default_mode not in {"auto", "imap", "browser"}:
        default_mode = "auto"
    return default_mode


def infer_email_domain(email_addr: str) -> str:
    if "@" not in (email_addr or ""):
        return ""
    return (email_addr.split("@", 1)[-1] or "").lower()


def prefer_browser_first_for_domain(domain: str) -> bool:
    return domain in {"sina.com", "sina.com.cn", "163.com", "126.com"}


def normalize_provider(raw: str) -> str:
    v = (raw or "").strip().lower()
    if not v:
        return ""
    replacements = {
        "sina": "sina",
        "sina邮箱": "sina",
        "新浪": "sina",
        "新浪邮箱": "sina",
        "德恒": "sina",
        "德恒邮箱": "sina",
        "126": "126",
        "126邮箱": "126",
        "163": "163",
        "163邮箱": "163",
    }
    if v in replacements:
        return replacements[v]
    return v


def infer_domain_from_provider(provider: str) -> str:
    p = normalize_provider(provider)
    mapping = {
        "sina": "sina.com.cn",
        "126": "126.com",
        "163": "163.com",
    }
    return mapping.get(p, "")


def should_prefer_browser(domain: str, provider: str) -> bool:
    if provider:
        provider = normalize_provider(provider)
        if provider in {"sina", "163", "126"}:
            return True
    return prefer_browser_first_for_domain(domain)


def has_any_imap_credential(args: argparse.Namespace, email_addr: str) -> bool:
    if args.password:
        return True
    if os.environ.get("INVOICE_IMAP_PASSWORD"):
        return True

    pw_file = args.password_file or os.environ.get("INVOICE_IMAP_PASSWORD_FILE", "").strip()
    if _read_file_trimmed(pw_file):
        return True

    imap_host, _ = infer_imap(email_addr)
    return bool(_read_password_from_keychain(email_addr, imap_host))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="发票Skill：从收件箱下载发票附件并生成清单+四拼一PDF")
    p.add_argument("--email", default="", help="邮箱账号。浏览器模式可选（IMAP 模式必填）；未传时可从 INVOICE_EMAIL 读取")
    p.add_argument("--password", help="IMAP 应用专用密码/登录密码（留空则提示输入）")
    p.add_argument("--password-file", default="", help="读取 IMAP 密码的文件路径（自动化场景）")
    p.add_argument("--imap-server", default="", help="IMAP 服务器，留空按域名自动推断")
    p.add_argument("--imap-port", type=int, default=993, help="IMAP 端口")
    p.add_argument("--output-dir", default=str(Path.home() / "Downloads" / "发票"), help="输出目录（发票文件 + 报表都放这里）")
    p.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS), help="邮件匹配关键词（英文逗号分隔）")
    p.add_argument("--days", type=int, default=30, help="只检索最近 N 天，默认30，0表示全部")
    p.add_argument("--max-emails", type=int, default=300, help="最多处理的邮件数，默认300")
    p.add_argument("--open-login", action="store_true", help="是否自动打开邮箱登录页")
    p.add_argument(
        "--provider",
        default=os.environ.get("INVOICE_PROVIDER", ""),
        help="可选：邮箱类型标识（如 sina、新浪、163、126），用于默认抓取策略。"
    )
    p.add_argument("--default-title", default="", help="未解析到抬头时的兜底抬头")
    p.add_argument("--skip-links", action="store_true", help="忽略正文中的图片/PDF链接下载")
    p.add_argument(
        "--source-mode",
        default=detect_source_mode(),
        choices=("auto", "imap", "browser"),
        help="提取来源：auto（先浏览器，失败回退IMAP）、imap、browser。",
    )
    p.add_argument(
        "--browser-profile-dir",
        default=os.environ.get("INVOICE_BROWSER_PROFILE_DIR", "").strip(),
        help="Playwright 持久化资料目录（复用已登录浏览器会话，可选）",
    )
    p.add_argument(
        "--browser-headless",
        action="store_true",
        default=_env_true("INVOICE_BROWSER_HEADLESS"),
        help="Playwright 无头模式启动（默认 false）",
    )
    p.add_argument(
        "--auto",
        action="store_true",
        default=_env_true("INVOICE_AUTO"),
        help="自动化模式：跳过人为确认提示，直接按参数执行",
    )
    return p.parse_args()


def _download_from_browser_url(
    context,
    page,
    url: str,
    headers: Dict[str, str],
    timeout: int = 60000,
) -> Tuple[Optional[bytes], Dict[str, str]]:
    try:
        response = page.request.get(url, headers=headers, timeout=timeout)
    except Exception:
        response = None
    if response is not None and response.status == 200:
        ctype = (response.headers.get("content-type", "") or "").lower()
        if ctype.startswith("application/pdf") or ctype.startswith("image/"):
            try:
                return response.body(), dict(response.headers)
            except Exception:
                pass

    # 对于需要点击/JS 触发的下载入口，回退到上下文页面导航取内容
    temp_page = None
    try:
        temp_page = context.new_page()
        response = temp_page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        if response is None or response.status != 200:
            return None, {}
        ctype = (response.headers.get("content-type", "") or "").lower()
        if (
            ctype.startswith("application/pdf")
            or ctype.startswith("image/")
            or ".pdf" in (url.lower())
        ):
            return response.body(), dict(response.headers)
    except Exception:
        return None, {}
    finally:
        if temp_page is not None:
            try:
                temp_page.close()
            except Exception:
                pass

    return None, {}


def collect_invoices_via_browser(
    email: str,
    keywords: List[str],
    max_emails: int,
    out_dir: Path,
    default_title: str,
    headers: Dict[str, str],
    args: argparse.Namespace,
    qr_dir: Path,
) -> Optional[Tuple[List[Dict[str, str]], List[Path], List[Path], int, int]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    domain = (email.split("@", 1)[-1] if "@" in email else "").lower()
    mail_url = web_login_hint(f"xx@{domain}")
    if not mail_url:
        return None

    print("第三步：尝试从浏览器会话抓取发票附件（实验路径）...")
    seen_hashes = set()
    rows: List[Dict[str, str]] = []
    downloaded_items: List[Dict[str, str]] = []
    qr_paths: List[Path] = []
    skipped_files = 0
    matched_links = 0
    attachment_seq = 1

    if not args.browser_profile_dir:
        default_profile = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
        args.browser_profile_dir = str(default_profile)

    launch_ok = False
    context = None
    page = None
    browser = None
    try:
        with sync_playwright() as pw:
            profile_dir = args.browser_profile_dir.strip()
            try:
                launch_kwargs = {
                    "headless": bool(args.browser_headless),
                    "args": ["--no-first-run", "--no-default-browser-check"],
                }
                if profile_dir:
                    context = pw.chromium.launch_persistent_context(
                        user_data_dir=profile_dir,
                        **launch_kwargs,
                    )
                else:
                    browser = pw.chromium.launch(**launch_kwargs)
                    context = browser.new_context()
                launch_ok = True
            except Exception:
                if not launch_kwargs["headless"]:
                    launch_kwargs["headless"] = True
                    try:
                        if profile_dir:
                            context = pw.chromium.launch_persistent_context(
                                user_data_dir=profile_dir,
                                **launch_kwargs,
                            )
                        else:
                            browser = pw.chromium.launch(**launch_kwargs)
                            context = browser.new_context()
                        launch_ok = True
                    except Exception:
                        launch_ok = False

            if not launch_ok or context is None:
                return None

            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = context.new_page()
            page.set_default_timeout(60000)
            page.goto(mail_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")

            # 先采集可疑附件链接：优先匹配 href/pdf/关键字
            if args.skip_links:
                return [] , [], [], matched_links, skipped_files
            candidate_pairs = []
            seen_urls = set()
            for frame in [page] + page.frames:
                try:
                    entries = frame.evaluate(
                        """() => {
                            const out = [];
                            for (const a of document.querySelectorAll('a[href]')) {
                                const href = a.getAttribute('href') || '';
                                const text = (a.innerText || a.textContent || '').trim();
                                if (href) { out.push({href, text}); }
                            }
                            return out;
                        }"""
                    )
                except Exception:
                    continue
                for entry in entries or []:
                    href = (entry.get("href") or "").strip()
                    text = (entry.get("text") or "").strip()
                    if not href:
                        continue
                    resolved = href
                    try:
                        resolved = urljoin(page.url, href)
                    except Exception:
                        resolved = href
                    if not _looks_like_downloadable_file_url(resolved):
                        if not _looks_like_invoice_attachment(resolved, text, keywords):
                            continue
                    if resolved in seen_urls:
                        continue
                    seen_urls.add(resolved)
                    candidate_pairs.append((resolved, text))
                    if max_emails > 0 and len(candidate_pairs) >= max_emails:
                        break

            if not candidate_pairs:
                print("未从当前浏览器会话发现明显的发票附件入口。")
                return None

            for url, hint_text in candidate_pairs:
                if matched_links >= max_emails and max_emails > 0:
                    break
                matched_links += 1
                body, fetched_headers = _download_from_browser_url(
                    context,
                    page,
                    url,
                    headers,
                    timeout=60000,
                )
                if not body:
                    skipped_files += 1
                    continue
                r_headers = fetched_headers or {}
                ctype = (r_headers.get("content-type", "") or "").lower()
                if not (ctype.startswith("application/pdf") or ctype.startswith("image/")):
                    if ".pdf" not in (url.lower()) and not _looks_like_downloadable_file_url(url):
                        skipped_files += 1
                        continue

                fp = _save_http_bytes(out_dir, url, body, {**r_headers}, attachment_seq)
                attachment_seq += 1
                if not fp:
                    skipped_files += 1
                    continue
                file_hash = hashlib.sha1(fp.read_bytes()).hexdigest()
                if file_hash in seen_hashes:
                    skipped_files += 1
                    fp.unlink(missing_ok=True)
                    continue
                seen_hashes.add(file_hash)

                file_text = ""
                if fp.suffix.lower() in IMAGE_EXTS:
                    file_text = extract_text_for_file(fp)

                if fp.suffix.lower() in IMAGE_EXTS and is_likely_qr_image(fp, file_text):
                    qr_target = move_to_qr_folder(fp, qr_dir)
                    qr_paths.append(qr_target)
                    continue

                fields = parse_invoice_fields(
                    fp,
                    subject=hint_text,
                    sender=email,
                    fallback_title=default_title,
                    extracted_text=file_text,
                )
                renamed = fp
                try:
                    renamed = rename_invoice_file(fp, fields)
                except Exception:
                    renamed = fp

                downloaded_items.append({
                    "file": str(renamed),
                    "amount": fields["amount"],
                    "project": fields["project"],
                    "title": fields["title"],
                    "invoice_no": fields["invoice_no"],
                })
                rows.append({
                    "amount": fields["amount"],
                    "project": fields["project"],
                    "title": fields["title"],
                    "invoice_no": fields["invoice_no"],
                })

            return rows, downloaded_items, qr_paths, skipped_files, matched_links
    except Exception:
        return None
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def move_to_qr_folder(src: Path, qr_dir: Path) -> Path:
    qr_dir.mkdir(parents=True, exist_ok=True)
    qr_name = f"需要二次扫码_{_component(src.stem, 70)}{src.suffix.lower()}"
    dst = _unique(qr_dir / qr_name)
    try:
        return src.rename(dst)
    except Exception:
        shutil.move(str(src), str(dst))
        return dst


def main() -> None:
    args = parse_args()
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    email_provided = bool(args.email)
    if not args.email:
        args.email = os.environ.get("INVOICE_EMAIL", "").strip()
    if not args.default_title:
        args.default_title = os.environ.get("INVOICE_DEFAULT_TITLE", "").strip()

    if not args.email and args.source_mode in {"auto", "browser"}:
        inferred_domain = infer_domain_from_provider(args.provider)
        if inferred_domain:
            args.email = f"auto@{inferred_domain}"
            email_provided = False
            print(f"未提供邮箱账号，已按供应商推断默认会话：{args.provider or inferred_domain}。")
    email_domain = infer_email_domain(args.email)

    if args.source_mode == "imap" and not args.email:
        raise SystemExit("IMAP 模式下请提供邮箱：--email 或 INVOICE_EMAIL。")
    if not args.email:
        raise SystemExit(
            "未提供邮箱信息。请在 browser/auto 模式补充邮箱或供应商（新浪邮箱/126邮箱/163邮箱/德恒邮箱），并确保已登录。"
        )

    browser_preferred = should_prefer_browser(email_domain, args.provider)

    # 已登录网页会话常用于这类场景（例如新浪）：默认先走浏览器抓取路径
    if args.source_mode == "auto" and browser_preferred:
        print("已识别为常见网页登录邮箱（如新浪），将默认优先尝试浏览器会话抓取。")

    # 对于“已登录邮箱+默认自动执行”场景，跳过任何手工确认，直接按默认 INBOX 流程执行
    if browser_preferred and not args.open_login:
        args.auto = True

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    qr_dir = out_dir / "需要二次扫码"

    print("第一步：准备登录")
    if args.auto and browser_preferred:
        print("检测到网页登录场景且当前为自动模式：默认只读收件箱，不做逐项确认。")
    if args.open_login:
        open_browser(web_login_hint(args.email))
        print("已打开邮箱登录页，请先在浏览器完成登录。")
        if not args.auto:
            input("邮箱登录完成后，按回车继续：")
    else:
        print("请确保你已在目标邮箱完成登录（若使用 IMAP 路径则会读取 INBOX）。")
        if not args.auto and args.source_mode != "browser":
            input("若已完成登录请按回车继续：")

    # 已知网页登录场景（如新浪/126/163）默认按“已登录+按默认规则”自动执行，不再等待人工确认。
    if browser_preferred and args.source_mode in {"auto", "browser"} and not args.open_login:
        args.auto = True

    if browser_preferred and not args.password and not os.environ.get("INVOICE_IMAP_PASSWORD"):
        args.auto = True

    if not args.password:
        if auto_pwd := os.environ.get("INVOICE_IMAP_PASSWORD"):
            args.password = auto_pwd
        else:
            pw_file = args.password_file or os.environ.get("INVOICE_IMAP_PASSWORD_FILE", "").strip()
            file_pwd = _read_file_trimmed(pw_file)
            if file_pwd:
                args.password = file_pwd

    # 如果邮箱是推断得来（auto@domain），不做 IMAP 回退，避免误用未知账号口令。
    has_imap_creds = has_any_imap_credential(args, args.email) if email_provided else False

    if not shutil.which("sips"):
        print("警告：未检测到 sips，PDF/图片转JPG无法使用，四拼一PDF可能失败。")
    if not shutil.which("tesseract"):
        print("提示：未检测到 tesseract，图片 OCR 会降级。")
    if not shutil.which("pdftotext"):
        print("提示：未检测到 pdftotext，PDF 文本提取会降级。")

    headers = {"User-Agent": "Mozilla/5.0"}

    rows: List[Dict[str, str]] = []
    downloaded_items: List[Dict[str, str]] = []
    qr_paths: List[Path] = []
    skipped_files = 0
    matched_mails = 0
    uids: List[bytes] = []
    used_source = args.source_mode

    # 第二步：先尝试浏览器抓取（仅在 auto/browser）
    browser_result = None
    attempted_browser = args.source_mode in {"auto", "browser"}
    if attempted_browser:
        print("第二步：尝试浏览器会话抓取发票附件")
        browser_result = collect_invoices_via_browser(
            email=args.email,
            keywords=keywords,
            max_emails=args.max_emails,
            out_dir=out_dir,
            default_title=args.default_title,
            headers=headers,
            args=args,
            qr_dir=qr_dir,
        )
        if browser_result is not None:
            rows, downloaded_items, qr_paths, skipped_files, matched_mails = browser_result
            used_source = "browser"
            if rows:
                uids = [b"browser"] * max(len(rows), 1)

    # fallback to IMAP
    fallback_to_imap = args.source_mode == "imap"
    if args.source_mode == "auto" and not rows:
        # auto 默认按配置自动回退 IMAP
        fallback_to_imap = True
    elif args.source_mode == "browser" and not rows and args.auto and has_imap_creds:
        # 若用户已走网页登录场景且我们默认自动执行，仍可以用 IMAP 兜底（不需要再次提问）
        fallback_to_imap = True
        print("浏览器会话未抓到可下载附件，检测到 IMAP 凭据，自动切换到 IMAP 路径（只读 INBOX）。")

    if args.source_mode == "browser" and not rows and not args.auto:
        print("浏览器模式未抓到可下载的发票附件（或当前未识别到可见入口）。")
        print("建议核对：1) 浏览器会话是否已登录且可见收件箱；2) Playwright/浏览器是否可访问该邮箱；3) 必要时改用 --source-mode imap。")

    if fallback_to_imap:
        used_source = "imap"
        if not args.password:
            keychain_pwd = _read_password_from_keychain(args.email, infer_imap(args.email)[0])
            if keychain_pwd:
                args.password = keychain_pwd
            elif not args.auto:
                args.password = getpass.getpass("IMAP 密码（推荐应用专用密码）：")
            else:
                fallback_to_imap = False
                print("自动化模式下未提供 IMAP 凭据，跳过 IMAP 分支。")

        if not fallback_to_imap:
            # keep browser result, do not block auto flow
            rows = list(rows)
            matched_mails = locals().get("matched_mails", 0)
            skipped_files = locals().get("skipped_files", 0)
        else:
            imap_server, inferred_port = infer_imap(args.email)
            if args.imap_server:
                imap_server = args.imap_server
                if args.imap_port == 993:
                    args.imap_port = inferred_port

            print(f"第二步：连接并读取 INBOX（仅 INBOX）=> {imap_server}:{args.imap_port}")
            try:
                imap_conn = imaplib.IMAP4_SSL(imap_server, args.imap_port)
                imap_conn.login(args.email, args.password)
                imap_conn.select("INBOX")
            except Exception as exc:
                if not args.auto:
                    raise SystemExit(f"IMAP 连接或登录失败：{exc}")
                fallback_to_imap = False
                print(f"IMAP 连接或登录失败，自动化模式下跳过 IMAP 分支：{exc}")
                rows = list(rows)

            if fallback_to_imap:
                uids = search_inbox_uids(imap_conn, args.days)
                if args.max_emails > 0 and len(uids) > args.max_emails:
                    uids = uids[-args.max_emails:]
                print(f"已在 INBOX 检索到 {len(uids)} 封待处理邮件。")

                seen_hashes = set()
                attachment_seq = 1
                rows = []
                downloaded_items = []
                qr_paths = []
                skipped_files = 0
                matched_mails = 0

                for uid in uids:
                    status, payload = imap_conn.fetch(uid, "(RFC822)")
                    if status != "OK" or not payload or not payload[0]:
                        continue

                    raw_msg = payload[0][1]
                    msg = BytesParser(policy=policy.default).parsebytes(raw_msg)
                    subject = decode_mime_value(msg.get("subject", ""))
                    sender = decode_mime_value(msg.get("from", ""))
                    body_text = extract_body_text(msg)

                    if not _looks_invoice_like(" ".join([subject, sender, body_text]), keywords):
                        continue
                    matched_mails += 1

                    tag = uid.decode()
                    files = save_message_attachments(msg, tag, out_dir)

                    if not args.skip_links:
                        for link in _iter_urls(body_text):
                            if not (_looks_like_downloadable_file_url(link) or _looks_like_invoice_attachment(link, body_text, keywords)):
                                continue
                            try:
                                fp = download_linked_pdf(link, out_dir, attachment_seq, headers)
                                attachment_seq += 1
                            except Exception:
                                fp = None
                            if fp:
                                files.append(fp)
                            else:
                                skipped_files += 1

                    for fp in files:
                        file_hash = hashlib.sha1(fp.read_bytes()).hexdigest()
                        if file_hash in seen_hashes:
                            skipped_files += 1
                            continue
                        seen_hashes.add(file_hash)

                        file_text = ""
                        if fp.suffix.lower() in IMAGE_EXTS:
                            file_text = extract_text_for_file(fp)

                        # 二维码识别：将疑似仅含二维码待开票的图片单独放到“需要二次扫码”目录
                        if fp.suffix.lower() in IMAGE_EXTS and is_likely_qr_image(fp, file_text):
                            qr_target = move_to_qr_folder(fp, qr_dir)
                            qr_paths.append(qr_target)
                            continue

                        fields = parse_invoice_fields(
                            fp,
                            subject=subject,
                            sender=sender,
                            fallback_title=args.default_title,
                            extracted_text=file_text,
                        )
                        renamed = fp
                        try:
                            renamed = rename_invoice_file(fp, fields)
                        except Exception:
                            renamed = fp

                        downloaded_items.append({
                            "file": str(renamed),
                            "amount": fields["amount"],
                            "project": fields["project"],
                            "title": fields["title"],
                            "invoice_no": fields["invoice_no"],
                        })
                        rows.append({
                            "amount": fields["amount"],
                            "project": fields["project"],
                            "title": fields["title"],
                            "invoice_no": fields["invoice_no"],
                        })

                imap_conn.logout()

    if not rows and not fallback_to_imap:
        print(
            "本次未抓到可下载附件；已按默认只看收件箱/链接下载处理。"
            "若你在登录后仍希望继续，请配置 IMAP 凭据并设置 --source-mode imap。"
        )

    invoice_paths = [Path(item["file"]) for item in downloaded_items if item.get("file")]
    xlsx_path = out_dir / "发票清单.xlsx"
    write_xlsx(xlsx_path, rows)
    four_up_pdf = out_dir / "发票_四拼一汇总.pdf"
    build_four_up_pdf(invoice_paths, four_up_pdf)

    report = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": str(out_dir),
        "source_mode": used_source,
        "inbox_searched": len(uids),
        "matched_mails": matched_mails,
        "matched_invoices": len(invoice_paths),
        "total_invoice_amount": f"{sum(_parse_amount_to_number(item.get('amount', '')) for item in downloaded_items):.2f}",
        "need_re_scan_qr": len(qr_paths),
        "skipped_files": skipped_files,
    }
    (out_dir / "运行结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "发票文件名清单.txt").write_text("\n".join([str(p) for p in invoice_paths]), encoding="utf-8")
    if qr_paths:
        (out_dir / "需要二次扫码清单.txt").write_text("\n".join([str(p) for p in qr_paths]), encoding="utf-8")

    print("\n执行完成。")
    print(f"输出目录：{out_dir}")
    print(f"匹配邮件：{matched_mails}")
    print(f"成功下载文件：{len(invoice_paths)}")
    print(f"跳过文件：{skipped_files}")
    print(f"待二次扫码文件：{len(qr_paths)}")
    if qr_paths:
        print(f"二维码待二次扫码目录：{qr_dir}")
    print(f"Excel 清单：{xlsx_path}")
    print(f"四拼一PDF：{four_up_pdf}")


if __name__ == "__main__":
    main()
