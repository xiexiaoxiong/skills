#!/usr/bin/env python3
"""Portable heavy-case evidence package builder.

Uses only the Python standard library. It does not decide infringement or
damages. Public captures are evidence leads unless separately notarized.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

TOOL_VERSION = "1.1.0"
SCHEMA_VERSION = "1.1"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 20

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
XSI = "http://www.w3.org/2001/XMLSchema-instance"

GROUPS = {
    1: {
        "name": "第一组  权属及原告资格类证据",
        "common": "共同证明：权利人主体、权利取得及授权链完整；涉案商标、作品、专利或包装装潢在相关期间具有可主张的权利基础；权利客体、保护范围和拟提交主体能够对应。",
    },
    2: {
        "name": "第二组  知名度、贡献率及利润类证据",
        "common": "共同证明：涉案权利的持续使用、宣传、销量、市场影响及识别力；合理利润率、权利贡献率和可比经营数据的来源、期间及口径；相关公众对权利客体的认知。",
    },
    3: {
        "name": "第三组  侵权行为、渠道、规模、地域及销量类证据",
        "common": "共同证明：被诉对象、页面、实物及交易链；实施主体、店铺、收款、发货、生产或组织生产的连接；线上线下渠道、地区、数量、价格、销量、金额、产能和持续期间。",
    },
    4: {
        "name": "第四组  混淆、主观故意及明知类证据",
        "common": "共同证明：消费者混淆或市场替代后果；被告接触权利的机会、警告或既往处理；重复侵权、多权利叠加、仿冒申请、继续实施等主观故意和情节线索。",
    },
    5: {
        "name": "第五组  主体关联、参照赔偿、合理开支及特殊因素类证据",
        "common": "共同证明：经营主体、控制人、关联公司、付款发票物流等共同实施链；同权利关联案件的可比判赔；本案合理维权费用；地区经营、偿付能力及依法需要考虑的特殊因素。",
    },
}

FACT_STATUSES = {
    "VERIFIED",
    "STRONG_INFERENCE",
    "LEAD",
    "NEEDS_HUMAN",
    "NOT_FOUND",
    "BLOCKED",
    "LEGAL_ASSESSMENT",
}
LITIGATION_STATUSES = {
    "PUBLIC_CAPTURE",
    "FIXED",
    "NEEDS_NOTARIZATION",
    "NEEDS_DISCLOSURE",
    "NEEDS_COURT_ORDER",
}
TASK_STATUSES = {
    "PENDING",
    "IN_PROGRESS",
    "DONE",
    "NEEDS_HUMAN",
    "NOT_FOUND",
    "BLOCKED",
    "NOT_APPLICABLE",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str, limit: int = 48) -> str:
    value = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", "_", value.strip())
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._")
    return (value or "材料")[:limit]


def validate_input_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("URL必须使用http或https")
    if not parsed.hostname:
        raise ValueError("URL缺少主机名")
    if parsed.username or parsed.password:
        raise ValueError("URL不得包含明文账号或密码")
    return parsed


SANDBOX_EGRESS_PROXY = ipaddress.ip_network("198.18.0.0/15")


def _reject_non_public_ip(value: str, *, allow_sandbox_proxy: bool = False) -> None:
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    if allow_sandbox_proxy and ip in SANDBOX_EGRESS_PROXY:
        return
    if not ip.is_global:
        raise ValueError(f"拒绝访问非公网地址：{ip}")


def validate_public_url(url: str) -> urllib.parse.SplitResult:
    parsed = validate_input_url(url)
    host = parsed.hostname or ""
    try:
        _reject_non_public_ip(host)
        return parsed
    except ValueError:
        if re.fullmatch(r"[0-9a-fA-F:.%]+", host):
            raise
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("域名未解析到地址")
    for info in infos:
        _reject_non_public_ip(info[4][0], allow_sandbox_proxy=True)
    return parsed


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS:
            raise urllib.error.HTTPError(newurl, code, "重定向次数过多", headers, fp)
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def matrix_path() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "evidence-matrix.json"


def load_matrix() -> dict[str, Any]:
    return json_load(matrix_path())


def case_files(case_dir: Path) -> tuple[Path, Path, Path]:
    return (
        case_dir / "case.json",
        case_dir / "search_tasks.json",
        case_dir / "evidence_manifest.json",
    )


def ensure_case(case_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    case_path, tasks_path, manifest_path = case_files(case_dir)
    missing = [str(p) for p in (case_path, tasks_path, manifest_path) if not p.is_file()]
    if missing:
        raise FileNotFoundError("案件目录缺少文件：" + "，".join(missing))
    return json_load(case_path), json_load(tasks_path), json_load(manifest_path)


def build_queries(holder: str, defendant_seed: str, host: str, item: dict[str, Any]) -> list[str]:
    proof = item["proof"]
    sources = item.get("sources", "")
    reputation_task = bool(re.fullmatch(r"2-3-[1-5]", str(item.get("id") or "")))
    subject = holder if reputation_task else defendant_seed
    if not subject:
        return []
    queries = [f'"{subject}" "{proof}"']
    if host:
        queries.append(f'site:{host} "{subject}" "{proof}"')
    source_hint = re.split(r"[、，,/]", sources)[0].strip()
    if source_hint:
        queries.append(f'"{subject}" {source_hint} {proof}')
    return queries[:3]


def cmd_init(args: argparse.Namespace) -> int:
    holder = args.rights_holder.strip()
    if not holder:
        raise ValueError("权利人信息不能为空")
    parsed = validate_input_url(args.url)
    defendant_seed = str(args.defendant_seed or "").strip()
    output = Path(args.output).expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"输出目录非空：{output}")
    output.mkdir(parents=True, exist_ok=True)
    for rel in (
        "evidence/original",
        "evidence/metadata",
        "evidence/derived",
        "logs",
        "work",
    ):
        (output / rel).mkdir(parents=True, exist_ok=True)

    created = now_iso()
    digest = hashlib.sha256(f"{holder}|{args.url}|{created}".encode("utf-8")).hexdigest()[:10]
    case_id = f"HC-{datetime.now().strftime('%Y%m%d')}-{digest}"
    case_name = args.case_name.strip() if args.case_name else f"{holder}重案证据调查"
    case = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "created_at": created,
        "timezone": datetime.now().astimezone().tzname(),
        "case_name": case_name,
        "rights_holder": {"raw_input": holder},
        "defendant_seed": {
            "status": "READY" if defendant_seed else "MISSING",
            "product_name": defendant_seed,
            "seeds": (
                [{"id": "D-PRODUCT-001", "kind": "PRODUCT", "value": defendant_seed}]
                if defendant_seed
                else []
            ),
        },
        "suspected_infringement_url": args.url.strip(),
        "plaintiff": args.plaintiff or holder,
        "defendants": args.defendants or "待核验",
        "cause": args.cause or "知识产权侵权/不正当竞争纠纷（待律师定性）",
        "court": args.court or "待核验",
        "case_number": args.case_number or "待立案",
        "disclaimer": "本目录为公开调查与证据管理工具输出，不构成侵权、赔偿或诉讼结论；自动固定材料不等于公证证据。",
        "tool_version": TOOL_VERSION,
    }

    matrix = load_matrix()
    tasks: list[dict[str, Any]] = []
    host = parsed.hostname or ""
    for item in matrix["items"]:
        tasks.append(
            {
                "id": item["id"],
                "section": item["section"],
                "dimension": item["dimension"],
                "title": item["proof"],
                "priority": item["priority"],
                "automation": item["automation"],
                "target_url": args.url.strip() if item["id"] == "B07" else "",
                "queries": build_queries(holder, defendant_seed, host, item),
                "status": "PENDING",
                "result_urls": [],
                "notes": (
                    item.get("warning", "")
                    if defendant_seed or re.fullmatch(r"2-3-[1-5]", str(item.get("id") or ""))
                    else "被告商品种子尚未提取；不得用权利人名称替代被告检索。"
                ),
                "updated_at": created,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "created_at": created,
        "groups": [{"id": key, **value} for key, value in GROUPS.items()],
        "evidence": [],
        "tool_version": TOOL_VERSION,
    }
    json_dump(output / "case.json", case)
    json_dump(output / "search_tasks.json", {"schema_version": SCHEMA_VERSION, "tasks": tasks})
    json_dump(output / "evidence_manifest.json", manifest)
    (output / "logs" / "access_log.jsonl").touch()
    (output / "logs" / "search_log.jsonl").touch()
    result = {
        "ok": True,
        "case_dir": str(output),
        "case_id": case_id,
        "task_count": len(tasks),
        "next": (
            "按被告商品种子执行search_tasks.json任务。"
            if defendant_seed
            else "先固定疑似侵权URL并提取被告商品完整名称；非知名度任务不得用权利人名称替代。"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def next_evidence_id(manifest: dict[str, Any]) -> str:
    numbers = []
    for item in manifest.get("evidence", []):
        match = re.fullmatch(r"E(\d+)", str(item.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"E{(max(numbers, default=0) + 1):03d}"


def register_file(
    case_dir: Path,
    source_file: Path,
    *,
    title: str,
    source_org: str,
    source_type: str,
    group_id: int,
    proof_points: list[str],
    url: str,
    final_url: str,
    acquisition_method: str,
    fact_status: str,
    litigation_status: str,
    page_range: str,
    limitations: str,
    task_ids: list[str],
    mime_type: str | None = None,
    copy_source: bool = True,
) -> dict[str, Any]:
    _, _, manifest = ensure_case(case_dir)
    if group_id not in GROUPS:
        raise ValueError("group-id必须为1至5")
    if fact_status not in FACT_STATUSES:
        raise ValueError(f"无效事实状态：{fact_status}")
    if litigation_status not in LITIGATION_STATUSES:
        raise ValueError(f"无效诉讼状态：{litigation_status}")
    if not source_file.is_file():
        raise FileNotFoundError(f"材料不存在：{source_file}")

    eid = next_evidence_id(manifest)
    suffix = source_file.suffix.lower() or ".bin"
    dest = case_dir / "evidence" / "original" / f"{eid}_{safe_name(title)}{suffix}"
    if copy_source:
        shutil.copy2(source_file, dest)
    else:
        if source_file.resolve() != dest.resolve():
            shutil.move(str(source_file), str(dest))
    digest = sha256_file(dest)
    accessed = now_iso()
    guessed = mime_type or mimetypes.guess_type(dest.name)[0] or "application/octet-stream"
    item = {
        "id": eid,
        "group_id": group_id,
        "title": title.strip(),
        "source_org": source_org.strip() or "待核验",
        "source_type": source_type.strip() or "其他",
        "url": url.strip(),
        "final_url": (final_url or url).strip(),
        "accessed_at": accessed,
        "timezone": datetime.now().astimezone().tzname(),
        "acquisition_method": acquisition_method,
        "fact_status": fact_status,
        "litigation_status": litigation_status,
        "file_path": dest.relative_to(case_dir).as_posix(),
        "sha256": digest,
        "size_bytes": dest.stat().st_size,
        "mime_type": guessed,
        "page_range": page_range.strip() or "对应电子文件",
        "proof_points": [p.strip() for p in proof_points if p.strip()],
        "limitations": limitations.strip(),
        "linked_task_ids": [x for x in task_ids if x],
        "derived_files": [],
        "contains_personal_data": False,
        "privacy_redactions": [],
        "tool_version": TOOL_VERSION,
    }
    manifest["evidence"].append(item)
    json_dump(case_dir / "evidence_manifest.json", manifest)
    json_dump(case_dir / "evidence" / "metadata" / f"{eid}.json", item)
    return item


def cmd_add(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    item = register_file(
        case_dir,
        Path(args.file).expanduser().resolve(),
        title=args.title,
        source_org=args.source,
        source_type=args.source_type,
        group_id=args.group_id,
        proof_points=args.proof_point,
        url=args.url or "",
        final_url=args.final_url or "",
        acquisition_method=args.acquisition_method,
        fact_status=args.fact_status,
        litigation_status=args.litigation_status,
        page_range=args.page_range or "",
        limitations=args.limitations or "",
        task_ids=args.task_id or [],
        copy_source=True,
    )
    print(json.dumps({"ok": True, "evidence": item}, ensure_ascii=False, indent=2))
    return 0


def extension_for_content_type(content_type: str, url: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    mapping = {
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "text/plain": ".txt",
        "application/json": ".json",
    }
    if media_type in mapping:
        return mapping[media_type]
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return ".bin"


def public_capture(url: str) -> tuple[bytes, dict[str, Any]]:
    validate_public_url(url)
    handler = SafeRedirectHandler()
    opener = urllib.request.build_opener(handler)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "HeavyCaseEvidenceBuilder/1.0 (+public evidence preservation)",
            "Accept": "text/html,application/xhtml+xml,application/pdf,image/*;q=0.9,*/*;q=0.5",
        },
    )
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        validate_public_url(final_url)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("响应体超过25MB上限")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("响应体超过25MB上限")
            chunks.append(chunk)
        data = b"".join(chunks)
        meta = {
            "final_url": final_url,
            "http_status": getattr(response, "status", None),
            "content_type": response.headers.get("Content-Type", "application/octet-stream"),
            "headers": {k: v for k, v in response.headers.items()},
            "bytes": len(data),
            "redirects": handler.count,
        }
        return data, meta


def cmd_capture(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    ensure_case(case_dir)
    started = now_iso()
    try:
        data, response_meta = public_capture(args.url)
        suffix = extension_for_content_type(response_meta["content_type"], response_meta["final_url"])
        temp = case_dir / "work" / f"capture_{hashlib.sha256((args.url + started).encode()).hexdigest()[:12]}{suffix}"
        temp.write_bytes(data)
        item = register_file(
            case_dir,
            temp,
            title=args.title,
            source_org=args.source or (urllib.parse.urlsplit(response_meta["final_url"]).hostname or "网络公开页面"),
            source_type=args.source_type,
            group_id=args.group_id,
            proof_points=args.proof_point,
            url=args.url,
            final_url=response_meta["final_url"],
            acquisition_method="PUBLIC_HTTP_CAPTURE",
            fact_status=args.fact_status,
            litigation_status=args.litigation_status,
            page_range=args.page_range or "",
            limitations=args.limitations or "公开HTTP自动固定，未经公证或可信时间戳认证；动态内容可能未完整加载。",
            task_ids=args.task_id or [],
            mime_type=response_meta["content_type"].split(";", 1)[0],
            copy_source=False,
        )
        append_jsonl(
            case_dir / "logs" / "access_log.jsonl",
            {
                "timestamp": started,
                "url": args.url,
                "action": "capture",
                "status": "SUCCESS",
                "final_url": response_meta["final_url"],
                "http_status": response_meta["http_status"],
                "content_type": response_meta["content_type"],
                "bytes": response_meta["bytes"],
                "sha256": item["sha256"],
                "error": "",
                "evidence_id": item["id"],
            },
        )
        print(json.dumps({"ok": True, "evidence": item, "response": response_meta}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        append_jsonl(
            case_dir / "logs" / "access_log.jsonl",
            {
                "timestamp": started,
                "url": args.url,
                "action": "capture",
                "status": "BLOCKED",
                "final_url": "",
                "http_status": getattr(exc, "code", None),
                "content_type": "",
                "bytes": 0,
                "sha256": "",
                "error": f"{type(exc).__name__}: {exc}",
                "evidence_id": "",
            },
        )
        print(json.dumps({"ok": False, "status": "BLOCKED", "url": args.url, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 2


def cmd_task(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    _, tasks_doc, _ = ensure_case(case_dir)
    if args.status not in TASK_STATUSES:
        raise ValueError("无效任务状态")
    found = None
    for task in tasks_doc.get("tasks", []):
        if task.get("id") == args.task_id:
            task["status"] = args.status
            task["notes"] = args.notes or task.get("notes", "")
            if args.result_url and args.result_url not in task["result_urls"]:
                task["result_urls"].append(args.result_url)
            task["updated_at"] = now_iso()
            found = task
            break
    if found is None:
        raise KeyError(f"未找到任务：{args.task_id}")
    json_dump(case_dir / "search_tasks.json", tasks_doc)
    print(json.dumps({"ok": True, "task": found}, ensure_ascii=False, indent=2))
    return 0


def cmd_log_search(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    ensure_case(case_dir)
    entry = {
        "timestamp": now_iso(),
        "task_id": args.task_id,
        "query": args.query,
        "source": args.source,
        "result_url": args.result_url or "",
        "result_status": args.result_status,
        "notes": args.notes or "",
    }
    append_jsonl(case_dir / "logs" / "search_log.jsonl", entry)
    print(json.dumps({"ok": True, "entry": entry}, ensure_ascii=False, indent=2))
    return 0


def x(value: Any) -> str:
    return escape(str(value if value is not None else ""))


def run_xml(text: str, *, bold: bool = False, size: int = 21, font: str = "仿宋", color: str = "000000") -> str:
    props = (
        f'<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
        f'w:eastAsia="{x(font)}"/><w:color w:val="{color}"/><w:sz w:val="{size}"/>'
        f'<w:szCs w:val="{size}"/>{"<w:b/><w:bCs/>" if bold else ""}</w:rPr>'
    )
    pieces = str(text).split("\n")
    content = []
    for idx, piece in enumerate(pieces):
        if idx:
            content.append("<w:br/>")
        content.append(f'<w:t xml:space="preserve">{x(piece)}</w:t>')
    return f"<w:r>{props}{''.join(content)}</w:r>"


def paragraph_xml(
    text: str = "",
    *,
    align: str = "left",
    bold: bool = False,
    size: int = 21,
    font: str = "仿宋",
    style: str | None = None,
    keep_next: bool = False,
    page_break_before: bool = False,
    num: bool = False,
    bookmark: str | None = None,
    bookmark_id: int = 1,
    spacing: int = 276,
) -> str:
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{x(style)}"/>')
    if keep_next:
        ppr.append("<w:keepNext/>")
    if page_break_before:
        ppr.append("<w:pageBreakBefore/>")
    ppr.append(f'<w:jc w:val="{align}"/>')
    ppr.append(f'<w:spacing w:after="0" w:line="{spacing}" w:lineRule="auto"/>')
    if num:
        ppr.append('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
    start = f'<w:bookmarkStart w:id="{bookmark_id}" w:name="{x(bookmark)}"/>' if bookmark else ""
    end = f'<w:bookmarkEnd w:id="{bookmark_id}"/>' if bookmark else ""
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{start}{run_xml(text, bold=bold, size=size, font=font)}{end}</w:p>"


def page_break_xml() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def cell_xml(
    text: str,
    width: int,
    *,
    fill: str | None = None,
    span: int = 1,
    align: str = "left",
    bold: bool = False,
    size: int = 21,
    font: str = "仿宋",
    num: bool = False,
    bookmark: str | None = None,
    bookmark_id: int = 1,
) -> str:
    tcpr = [f'<w:tcW w:w="{width}" w:type="dxa"/>', '<w:vAlign w:val="center"/>']
    if span > 1:
        tcpr.append(f'<w:gridSpan w:val="{span}"/>')
    if fill:
        tcpr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    p = paragraph_xml(
        text,
        align=align,
        bold=bold,
        size=size,
        font=font,
        num=num,
        bookmark=bookmark,
        bookmark_id=bookmark_id,
    )
    return f"<w:tc><w:tcPr>{''.join(tcpr)}</w:tcPr>{p}</w:tc>"


def row_xml(cells: list[str], *, repeat: bool = False, cant_split: bool = False) -> str:
    props = []
    if repeat:
        props.append("<w:tblHeader/>")
    if cant_split:
        props.append("<w:cantSplit/>")
    trpr = f"<w:trPr>{''.join(props)}</w:trPr>" if props else ""
    return f"<w:tr>{trpr}{''.join(cells)}</w:tr>"


def table_xml(widths: list[int], rows: list[str], *, no_borders: bool = False) -> str:
    if no_borders:
        borders = "".join(f'<w:{side} w:val="nil"/>' for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
    else:
        borders = "".join(
            f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="BEBEBE"/>'
            for side in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
    props = (
        f'<w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/>'
        '<w:tblLayout w:type="fixed"/>'
        f'<w:tblBorders>{borders}</w:tblBorders>'
        '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
        '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar>'
        "</w:tblPr>"
    )
    grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    return f"<w:tbl>{props}{grid}{''.join(rows)}</w:tbl>"


def styles_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="仿宋"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:rPr><w:rFonts w:eastAsia="黑体"/><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:keepNext/><w:qFormat/><w:rPr><w:rFonts w:eastAsia="黑体"/><w:b/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
</w:styles>'''


def numbering_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="{W}">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1"/><w:lvlJc w:val="center"/>
      <w:pPr><w:jc w:val="center"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="仿宋"/><w:sz w:val="21"/></w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>'''


def header_xml(lines: list[str]) -> str:
    paras = [paragraph_xml(line, align="right", size=18, font="仿宋", spacing=220) for line in lines]
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr xmlns:w="{W}" xmlns:r="{R}">{"".join(paras)}</w:hdr>'


def footer_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{W}" xmlns:r="{R}">
  <w:p><w:pPr><w:jc w:val="center"/></w:pPr>
    {run_xml("", size=18)}
    <w:fldSimple w:instr="PAGE">{run_xml("1", size=18)}</w:fldSimple>
    {run_xml(" / ", size=18)}
    <w:fldSimple w:instr="NUMPAGES">{run_xml("1", size=18)}</w:fldSimple>
  </w:p>
</w:ftr>'''


def document_xml(body: str, *, landscape: bool = True) -> str:
    if landscape:
        pg = '<w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
        mar = '<w:pgMar w:top="1800" w:right="1440" w:bottom="1800" w:left="1440" w:header="851" w:footer="992" w:gutter="0"/>'
    else:
        pg = '<w:pgSz w:w="11906" w:h="16838"/>'
        mar = '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>'
    sect = (
        '<w:sectPr><w:headerReference w:type="default" r:id="rId5"/>'
        '<w:footerReference w:type="default" r:id="rId6"/>'
        f'{pg}{mar}<w:cols w:space="425" w:num="1"/><w:docGrid w:type="lines" w:linePitch="312"/></w:sectPr>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}{sect}</w:body></w:document>'''


def write_docx(path: Path, body: str, header_lines: list[str], *, title: str, landscape: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''
    document_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>'''
    settings = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="{W}"><w:updateFields w:val="true"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="{W}" w:val="15"/></w:compat></w:settings>'''
    font_table = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:fonts xmlns:w="{W}"><w:font w:name="仿宋"/><w:font w:name="黑体"/><w:font w:name="Times New Roman"/></w:fonts>'''
    core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="{CP}" xmlns:dc="{DC}" xmlns:dcterms="{DCTERMS}" xmlns:xsi="{XSI}">
  <dc:title>{x(title)}</dc:title><dc:creator>重案证据自动取证 Skill</dc:creator>
  <cp:lastModifiedBy>重案证据自动取证 Skill</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{x(timestamp)}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{x(timestamp)}</dcterms:modified>
</cp:coreProperties>'''
    app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Heavy Case Evidence Builder</Application><AppVersion>1.0</AppVersion></Properties>'''
    members = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": root_rels,
        "docProps/core.xml": core,
        "docProps/app.xml": app,
        "word/document.xml": document_xml(body, landscape=landscape),
        "word/_rels/document.xml.rels": document_rels,
        "word/styles.xml": styles_xml(),
        "word/numbering.xml": numbering_xml(),
        "word/settings.xml": settings,
        "word/fontTable.xml": font_table,
        "word/header1.xml": header_xml(header_lines),
        "word/footer1.xml": footer_xml(),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content.encode("utf-8"))


def evidence_table(group_id: int, evidence: list[dict[str, Any]], bookmark_start: int) -> tuple[str, int]:
    widths = [681, 4956, 1086, 6080, 1371]
    rows = [
        row_xml(
            [cell_xml(GROUPS[group_id]["name"], sum(widths), fill="FEF2CC", span=5, align="center", bold=True)],
            repeat=True,
            cant_split=True,
        ),
        row_xml(
            [
                cell_xml("序号", widths[0], fill="ECECEC", align="center", bold=True),
                cell_xml("证据名称", widths[1], fill="ECECEC", align="center", bold=True),
                cell_xml("证据来源", widths[2], fill="ECECEC", align="center", bold=True),
                cell_xml("单独证明目的", widths[3], fill="ECECEC", align="center", bold=True),
                cell_xml("页码", widths[4], fill="ECECEC", align="center", bold=True),
            ],
            repeat=True,
            cant_split=True,
        ),
        row_xml([cell_xml(GROUPS[group_id]["common"], sum(widths), span=5, align="both")]),
    ]
    bookmark_id = bookmark_start
    if not evidence:
        rows.append(row_xml([cell_xml("本组暂无已固定证据；请查看报告后的待补证与人工闸门。", sum(widths), span=5, align="center")]))
    for item in evidence:
        bookmark_id += 1
        proof = ("；".join(item.get("proof_points", [])) or "待补充具体证明目的").rstrip("。； ")
        limitations = item.get("limitations", "").strip().rstrip("。； ")
        if limitations:
            proof += f"。局限：{limitations}"
        proof += f"。事实状态：{item.get('fact_status')}；诉讼状态：{item.get('litigation_status')}。"
        name = item.get("title", "未命名材料")
        source = item.get("source_org") or item.get("source_type") or "待核验"
        rows.append(
            row_xml(
                [
                    cell_xml("", widths[0], align="center", num=True, bookmark=item["id"], bookmark_id=bookmark_id),
                    cell_xml(name, widths[1], align="both"),
                    cell_xml(source, widths[2], align="center"),
                    cell_xml(proof, widths[3], align="both"),
                    cell_xml(item.get("page_range") or "对应电子文件", widths[4], align="center"),
                ]
            )
        )
    return table_xml(widths, rows), bookmark_id


def build_case_report(case_dir: Path, output: Path) -> dict[str, Any]:
    case, tasks_doc, manifest = ensure_case(case_dir)
    evidence = sorted(
        manifest.get("evidence", []),
        key=lambda e: int(re.sub(r"\D", "", str(e.get("id", "0"))) or 0),
    )
    info_widths = [14174]
    info_rows = [
        row_xml([cell_xml("证据清单", 14174, align="center", bold=True, size=32, font="黑体")]),
        row_xml([cell_xml(f"原告（证据提交人）：{case.get('plaintiff', '待核验')}", 14174)]),
        row_xml([cell_xml(f"被告：{case.get('defendants', '待核验')}", 14174)]),
        row_xml([cell_xml(f"案由：{case.get('cause', '待核验')}", 14174)]),
    ]
    body = [table_xml(info_widths, info_rows, no_borders=True)]
    body.append(paragraph_xml(f"疑似侵权链接：{case.get('suspected_infringement_url', '')}", size=18))
    body.append(paragraph_xml(case.get("disclaimer", ""), size=18, bold=True))
    body.append(paragraph_xml(f"生成时间：{now_iso()}；证据文件数：{len(evidence)}", size=18))

    bookmark_id = 100
    for group_id in range(1, 6):
        body.append(
            paragraph_xml(
                GROUPS[group_id]["name"],
                style="Heading1",
                bold=True,
                size=26,
                font="黑体",
                keep_next=True,
                page_break_before=group_id > 1,
            )
        )
        group_evidence = [e for e in evidence if e.get("group_id") == group_id]
        table, bookmark_id = evidence_table(group_id, group_evidence, bookmark_id)
        body.append(table)

    body.append(
        paragraph_xml(
            "待补证与人工闸门",
            style="Heading1",
            bold=True,
            size=26,
            font="黑体",
            keep_next=True,
            page_break_before=True,
        )
    )
    pending = [
        t for t in tasks_doc.get("tasks", [])
        if t.get("status") in {"PENDING", "IN_PROGRESS", "NEEDS_HUMAN", "NOT_FOUND", "BLOCKED"}
        and t.get("priority") in {"P0", "P1"}
    ]
    widths = [900, 3000, 1500, 4300, 4474]
    rows = [
        row_xml(
            [
                cell_xml("任务ID", widths[0], fill="ECECEC", align="center", bold=True),
                cell_xml("待补事项", widths[1], fill="ECECEC", align="center", bold=True),
                cell_xml("状态", widths[2], fill="ECECEC", align="center", bold=True),
                cell_xml("查询/获取路径", widths[3], fill="ECECEC", align="center", bold=True),
                cell_xml("备注与人工步骤", widths[4], fill="ECECEC", align="center", bold=True),
            ],
            repeat=True,
        )
    ]
    for task in pending:
        queries = "\n".join(task.get("queries", [])[:2])
        rows.append(
            row_xml(
                [
                    cell_xml(task.get("id", ""), widths[0], align="center", size=18),
                    cell_xml(task.get("title", ""), widths[1], size=18),
                    cell_xml(task.get("status", ""), widths[2], align="center", size=18),
                    cell_xml(queries or task.get("target_url", ""), widths[3], size=18),
                    cell_xml(task.get("notes", ""), widths[4], size=18),
                ]
            )
        )
    if len(rows) == 1:
        rows.append(row_xml([cell_xml("无P0/P1待处理任务。", sum(widths), span=5, align="center")]))
    body.append(table_xml(widths, rows))

    body.append(paragraph_xml("附件完整性记录", style="Heading1", bold=True, size=26, font="黑体", keep_next=True))
    widths2 = [900, 3700, 6574, 1600, 1400]
    rows2 = [
        row_xml(
            [
                cell_xml("编号", widths2[0], fill="ECECEC", align="center", bold=True),
                cell_xml("文件", widths2[1], fill="ECECEC", align="center", bold=True),
                cell_xml("SHA-256", widths2[2], fill="ECECEC", align="center", bold=True),
                cell_xml("获取时间", widths2[3], fill="ECECEC", align="center", bold=True),
                cell_xml("大小", widths2[4], fill="ECECEC", align="center", bold=True),
            ],
            repeat=True,
        )
    ]
    for item in evidence:
        rows2.append(
            row_xml(
                [
                    cell_xml(item["id"], widths2[0], align="center", size=16),
                    cell_xml(item["file_path"], widths2[1], size=16),
                    cell_xml(item["sha256"], widths2[2], size=14, font="Times New Roman"),
                    cell_xml(item["accessed_at"], widths2[3], align="center", size=14),
                    cell_xml(str(item["size_bytes"]), widths2[4], align="center", size=16),
                ]
            )
        )
    if len(rows2) == 1:
        rows2.append(row_xml([cell_xml("暂无附件。", sum(widths2), span=5, align="center")]))
    body.append(table_xml(widths2, rows2))

    header_lines = [
        f"案号：{case.get('case_number', '待立案')}",
        f"法院：{case.get('court', '待核验')}",
        f"原告：{case.get('plaintiff', '待核验')}",
        f"被告：{case.get('defendants', '待核验')}",
        f"案由：{case.get('cause', '待核验')}",
    ]
    write_docx(output, "".join(body), header_lines, title=f"{case.get('case_name')}证据清单", landscape=True)
    return {"output": str(output), "evidence_count": len(evidence), "pending_high_priority": len(pending)}


def cmd_report(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else case_dir / "案件证据报告.docx"
    result = build_case_report(case_dir, output)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


def build_checklist(output: Path) -> dict[str, Any]:
    matrix = load_matrix()
    section_names = {s["id"]: s["name"] for s in matrix["sections"]}
    order = [s["id"] for s in matrix["sections"]]
    body = [
        paragraph_xml("重案证据搜集操作清单", style="Title", bold=True, size=36, font="黑体", align="center"),
        paragraph_xml("适用人群：未系统学习法律但需要逐项寻找、保存和移交重案线索的项目人员。", align="center", size=20),
        paragraph_xml("使用方法：先做B和T；任一T项达标即进入五维深挖。每一行都填写状态和文件编号。网页材料同时保存原文件/截图、URL、访问时间、SHA-256和局限。自动截图不等于公证证据。", bold=True, size=20),
        paragraph_xml("状态：□未做  □已取得  □仅线索  □需人工  □需公证  □需平台披露  □需法院调取  □不适用", size=20),
    ]
    widths = [850, 2500, 4900, 2800, 3124]
    total_rows = 0
    for index, section_id in enumerate(order):
        section_items = [item for item in matrix["items"] if item["section"] == section_id]
        body.append(
            paragraph_xml(
                section_names[section_id],
                style="Heading1",
                bold=True,
                size=26,
                font="黑体",
                keep_next=True,
                page_break_before=index > 0,
            )
        )
        rows = [
            row_xml(
                [cell_xml(section_names[section_id], sum(widths), fill="FEF2CC", span=5, align="center", bold=True, size=22)],
                repeat=True,
                cant_split=True,
            ),
            row_xml(
                [
                    cell_xml("编号/优先级", widths[0], fill="ECECEC", align="center", bold=True, size=18),
                    cell_xml("要证明什么", widths[1], fill="ECECEC", align="center", bold=True, size=18),
                    cell_xml("照着做", widths[2], fill="ECECEC", align="center", bold=True, size=18),
                    cell_xml("去哪找", widths[3], fill="ECECEC", align="center", bold=True, size=18),
                    cell_xml("保存、达标与完成记录", widths[4], fill="ECECEC", align="center", bold=True, size=18),
                ],
                repeat=True,
                cant_split=True,
            ),
        ]
        for item in section_items:
            last = (
                f"保存：{item['save']}\n"
                f"达标：{item['pass']}\n"
                f"自动化：{item['automation']}\n"
                "状态：□未做 □已取得 □仅线索 □需人工 □需公证/披露/调取\n"
                "文件编号：________ 负责人：________ 日期：________"
            )
            proof = item["proof"]
            if item.get("warning"):
                proof += f"\n风险：{item['warning']}"
            rows.append(
                row_xml(
                    [
                        cell_xml(f"{item['id']}\n{item['priority']}", widths[0], align="center", size=17),
                        cell_xml(proof, widths[1], size=17),
                        cell_xml(item["actions"], widths[2], size=17),
                        cell_xml(item["sources"], widths[3], size=17),
                        cell_xml(last, widths[4], size=16),
                    ]
                )
            )
            total_rows += 1
        body.append(table_xml(widths, rows))

    body.append(
        paragraph_xml(
            "移交律师前的最后检查",
            style="Heading1",
            bold=True,
            size=26,
            font="黑体",
            keep_next=True,
            page_break_before=True,
        )
    )
    final_checks = [
        "每个清单编号都填写状态；未取得项有具体下一步。",
        "权利人、权利状态、授权链和拟原告资格已用当日官方/原始材料核验。",
        "页面、店铺、订单、付款、物流、发货、包装生产者和关联主体尽量闭环。",
        "销量、金额、产能和利润率均说明期间、口径、去重、刷单/退货和局限。",
        "原始件、派生件、URL、时间、哈希、证明目的和隐私处理一一对应。",
        "没有把搜索摘要、评论、AI评价或自动截图写成已证实侵权/公证证据。",
        "需登录、测购、公证、平台披露和法院调取事项已经形成负责人和截止时间。",
    ]
    for idx, check in enumerate(final_checks, 1):
        body.append(paragraph_xml(f"□ {idx}. {check}", size=22))
    write_docx(
        output,
        "".join(body),
        ["重案证据搜集操作清单", "依据：清单化挖掘重案线索-20260715", f"生成日期：{now_iso()}", "", ""],
        title="重案证据搜集操作清单",
        landscape=True,
    )
    return {"output": str(output), "item_count": total_rows, "section_count": len(order)}


def cmd_checklist(args: argparse.Namespace) -> int:
    result = build_checklist(Path(args.output).expanduser().resolve())
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


def issue(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def validate_report(report: Path, expected_ids: list[str]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    issues: list[dict[str, str]] = []
    metrics: dict[str, Any] = {"report": str(report), "report_bookmarks": 0}
    if not report.is_file():
        issues.append(issue("ERROR", "REPORT_MISSING", f"报告不存在：{report}"))
        return issues, metrics
    if not zipfile.is_zipfile(report):
        issues.append(issue("ERROR", "REPORT_NOT_DOCX", "报告不是有效DOCX压缩包"))
        return issues, metrics
    required = {
        "[Content_Types].xml",
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/header1.xml",
        "word/footer1.xml",
    }
    with zipfile.ZipFile(report) as zf:
        names = set(zf.namelist())
        for name in sorted(required - names):
            issues.append(issue("ERROR", "REPORT_PART_MISSING", f"DOCX缺少{name}"))
        if "word/document.xml" not in names:
            return issues, metrics
        doc_root = ET.fromstring(zf.read("word/document.xml"))
        ns = {"w": W}
        bookmarks = [
            node.attrib.get(f"{{{W}}}name", "")
            for node in doc_root.findall(".//w:bookmarkStart", ns)
        ]
        evidence_bookmarks = [name for name in bookmarks if re.fullmatch(r"E\d{3,}", name)]
        metrics["report_bookmarks"] = len(evidence_bookmarks)
        if evidence_bookmarks != expected_ids:
            issues.append(
                issue(
                    "ERROR",
                    "REPORT_EVIDENCE_MISMATCH",
                    f"报告书签{evidence_bookmarks}与清单{expected_ids}不一致",
                )
            )
        number_nodes = doc_root.findall(".//w:numPr/w:numId", ns)
        number_ids = [node.attrib.get(f"{{{W}}}val") for node in number_nodes]
        metrics["numbered_evidence_rows"] = len(number_ids)
        if len(number_ids) != len(expected_ids):
            issues.append(
                issue(
                    "ERROR",
                    "REPORT_NUMBER_COUNT",
                    f"编号段落数{len(number_ids)}与证据数{len(expected_ids)}不一致",
                )
            )
        if any(value != "1" for value in number_ids):
            issues.append(issue("ERROR", "REPORT_NUMBER_SEQUENCE", "证据行未统一使用numId=1连续编号"))
        tables = doc_root.findall(".//w:tbl", ns)
        expected_widths = ["681", "4956", "1086", "6080", "1371"]
        if len(tables) < 6:
            issues.append(issue("ERROR", "REPORT_TABLE_COUNT", "缺少案头表或五组证据表"))
        else:
            for index, table in enumerate(tables[1:6], 1):
                grid = [
                    node.attrib.get(f"{{{W}}}w")
                    for node in table.findall("./w:tblGrid/w:gridCol", ns)
                ]
                if grid != expected_widths:
                    issues.append(
                        issue(
                            "ERROR",
                            "REPORT_COLUMN_WIDTHS",
                            f"第{index}组列宽{grid}不符合样本基线{expected_widths}",
                        )
                    )
                repeat_rows = table.findall("./w:tr/w:trPr/w:tblHeader", ns)
                if len(repeat_rows) < 2:
                    issues.append(issue("ERROR", "REPORT_REPEAT_HEADER", f"第{index}组未设置组标题和列标题跨页重复"))
        all_text = "".join(node.text or "" for node in doc_root.findall(".//w:t", ns))
        for group in GROUPS.values():
            if group["name"] not in all_text:
                issues.append(issue("ERROR", "REPORT_GROUP_MISSING", f"缺少分组：{group['name']}"))
        for header in ("序号", "证据名称", "证据来源", "单独证明目的", "页码"):
            if header not in all_text:
                issues.append(issue("ERROR", "REPORT_HEADER_MISSING", f"缺少列标题：{header}"))
        sect = doc_root.find(".//w:sectPr", ns)
        if sect is None:
            issues.append(issue("ERROR", "REPORT_SECTION_MISSING", "缺少页面设置"))
        else:
            pg = sect.find("w:pgSz", ns)
            if pg is None or pg.attrib.get(f"{{{W}}}orient") != "landscape":
                issues.append(issue("ERROR", "REPORT_NOT_LANDSCAPE", "报告不是横向页面"))
            if pg is not None:
                if pg.attrib.get(f"{{{W}}}w") != "16838" or pg.attrib.get(f"{{{W}}}h") != "11906":
                    issues.append(issue("ERROR", "REPORT_PAGE_SIZE", "报告不是A4横向基线尺寸"))
        if "word/footer1.xml" in names:
            footer = zf.read("word/footer1.xml").decode("utf-8", errors="replace")
            if "PAGE" not in footer or "NUMPAGES" not in footer:
                issues.append(issue("ERROR", "REPORT_PAGE_FIELDS", "页脚缺少动态PAGE/NUMPAGES"))
    return issues, metrics


def validate_case(case_dir: Path, report: Path | None = None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    case, tasks_doc, manifest = ensure_case(case_dir)
    evidence = manifest.get("evidence", [])
    expected_ids = [f"E{i:03d}" for i in range(1, len(evidence) + 1)]
    actual_ids = [str(item.get("id", "")) for item in evidence]
    if actual_ids != expected_ids:
        issues.append(issue("ERROR", "EVIDENCE_SEQUENCE", f"证据编号应为{expected_ids}，实际为{actual_ids}"))

    seen_hashes: dict[str, str] = {}
    for item in evidence:
        eid = str(item.get("id", ""))
        rel = item.get("file_path", "")
        path = case_dir / rel
        if not path.is_file():
            issues.append(issue("ERROR", "ATTACHMENT_MISSING", f"{eid}附件不存在：{rel}"))
            continue
        digest = sha256_file(path)
        if digest != item.get("sha256"):
            issues.append(issue("ERROR", "HASH_MISMATCH", f"{eid}哈希不一致"))
        if not item.get("source_org"):
            issues.append(issue("ERROR", "SOURCE_MISSING", f"{eid}缺少证据来源"))
        if not item.get("accessed_at"):
            issues.append(issue("ERROR", "TIME_MISSING", f"{eid}缺少访问/取得时间"))
        if not item.get("proof_points"):
            issues.append(issue("ERROR", "PROOF_MISSING", f"{eid}缺少证明目的"))
        if item.get("fact_status") not in FACT_STATUSES:
            issues.append(issue("ERROR", "FACT_STATUS_INVALID", f"{eid}事实状态无效"))
        if item.get("litigation_status") not in LITIGATION_STATUSES:
            issues.append(issue("ERROR", "LITIGATION_STATUS_INVALID", f"{eid}诉讼状态无效"))
        if item.get("group_id") not in GROUPS:
            issues.append(issue("ERROR", "GROUP_INVALID", f"{eid}分组无效"))
        if digest in seen_hashes:
            issues.append(issue("WARNING", "DUPLICATE_HASH", f"{eid}与{seen_hashes[digest]}内容哈希相同"))
        else:
            seen_hashes[digest] = eid
        metadata = case_dir / "evidence" / "metadata" / f"{eid}.json"
        if not metadata.is_file():
            issues.append(issue("ERROR", "METADATA_MISSING", f"{eid}缺少元数据文件"))

    groups_present = {item.get("group_id") for item in evidence}
    if 1 not in groups_present:
        issues.append(issue("WARNING", "MISSING_RIGHTS_BASIS", "尚无第一组权属及原告资格附件"))
    if 3 not in groups_present:
        issues.append(issue("WARNING", "NO_DIRECT_INFRINGEMENT", "尚无第三组直接侵权行为附件"))
    if evidence and not any(item.get("fact_status") == "VERIFIED" for item in evidence):
        issues.append(issue("WARNING", "NO_VERIFIED_FACT", "现有材料均未达到VERIFIED"))
    if not evidence:
        issues.append(issue("WARNING", "NO_EVIDENCE", "案件目录尚无证据附件"))

    task_ids = {task.get("id") for task in tasks_doc.get("tasks", [])}
    for item in evidence:
        for task_id in item.get("linked_task_ids", []):
            if task_id not in task_ids:
                issues.append(issue("WARNING", "UNKNOWN_TASK_LINK", f"{item['id']}引用不存在任务{task_id}"))
    unresolved_statuses = {"PENDING", "IN_PROGRESS", "NEEDS_HUMAN", "NOT_FOUND", "BLOCKED"}
    high_pending = [
        task for task in tasks_doc.get("tasks", [])
        if task.get("priority") in {"P0", "P1"} and task.get("status") in unresolved_statuses
    ]
    if high_pending:
        issues.append(issue("WARNING", "HIGH_PRIORITY_PENDING", f"仍有{len(high_pending)}项P0/P1任务未完成"))

    report_path = report or (case_dir / "案件证据报告.docx")
    report_issues, report_metrics = validate_report(report_path, expected_ids)
    issues.extend(report_issues)
    errors = [i for i in issues if i["level"] == "ERROR"]
    warnings = [i for i in issues if i["level"] == "WARNING"]
    return {
        "ok": not errors,
        "case_id": case.get("case_id"),
        "evidence_count": len(evidence),
        "group_counts": {str(g): sum(1 for e in evidence if e.get("group_id") == g) for g in GROUPS},
        "high_priority_pending": len(high_pending),
        "errors": errors,
        "warnings": warnings,
        "report_metrics": report_metrics,
        "checked_at": now_iso(),
        "tool_version": TOOL_VERSION,
    }


def cmd_validate(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    report = Path(args.report).expanduser().resolve() if args.report else None
    result = validate_case(case_dir, report)
    output = case_dir / "validation_result.json"
    json_dump(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def add_common_case_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-dir", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="重案证据包初始化、固定、登记、成册和校验")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="初始化案件目录和搜索任务")
    p.add_argument("--rights-holder", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--case-name")
    p.add_argument("--plaintiff")
    p.add_argument("--defendants")
    p.add_argument("--defendant-seed", help="从疑似侵权页提取的被告商品完整名称")
    p.add_argument("--cause")
    p.add_argument("--court")
    p.add_argument("--case-number")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("capture", help="安全固定公开静态URL")
    add_common_case_args(p)
    p.add_argument("--url", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--source")
    p.add_argument("--source-type", default="网络公开页面")
    p.add_argument("--group-id", required=True, type=int)
    p.add_argument("--proof-point", action="append", required=True)
    p.add_argument("--fact-status", choices=sorted(FACT_STATUSES), default="LEAD")
    p.add_argument("--litigation-status", choices=sorted(LITIGATION_STATUSES), default="PUBLIC_CAPTURE")
    p.add_argument("--page-range")
    p.add_argument("--limitations")
    p.add_argument("--task-id", action="append")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("add", help="登记浏览器、官方下载、用户或测购材料")
    add_common_case_args(p)
    p.add_argument("--file", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--source-type", default="其他")
    p.add_argument("--group-id", required=True, type=int)
    p.add_argument("--proof-point", action="append", required=True)
    p.add_argument("--url")
    p.add_argument("--final-url")
    p.add_argument("--acquisition-method", default="USER_OR_BROWSER_FILE")
    p.add_argument("--fact-status", choices=sorted(FACT_STATUSES), required=True)
    p.add_argument("--litigation-status", choices=sorted(LITIGATION_STATUSES), required=True)
    p.add_argument("--page-range")
    p.add_argument("--limitations")
    p.add_argument("--task-id", action="append")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("task", help="更新取证任务状态")
    add_common_case_args(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--status", choices=sorted(TASK_STATUSES), required=True)
    p.add_argument("--notes")
    p.add_argument("--result-url")
    p.set_defaults(func=cmd_task)

    p = sub.add_parser("log-search", help="记录一次搜索")
    add_common_case_args(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--result-url")
    p.add_argument("--result-status", required=True)
    p.add_argument("--notes")
    p.set_defaults(func=cmd_log_search)

    p = sub.add_parser("report", help="生成五组连续编号Word证据目录")
    add_common_case_args(p)
    p.add_argument("--output")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("validate", help="校验证据、哈希、元数据和Word目录")
    add_common_case_args(p)
    p.add_argument("--report")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("checklist", help="生成普通人逐项操作清单Word")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_checklist)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中断"}, ensure_ascii=False))
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
