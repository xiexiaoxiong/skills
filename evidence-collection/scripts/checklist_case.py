#!/usr/bin/env python3
"""Audit-first, append-only investigation workflow for a user-owned DOCX checklist."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
NS = {"w": W_NS}

SCHEMA_VERSION = "1.1"
AI_HEADER = "AI调查说明（逐行留痕）"
DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "重案证据搜集操作清单_五维简化版.docx"
)

VALID_STATUSES = {
    "COMPLETE_VERIFIED",
    "PARTIAL_VERIFIED",
    "LEAD_ONLY",
    "NOT_FOUND",
    "BLOCKED",
    "NEEDS_HUMAN",
    "NOT_APPLICABLE",
    "CONFLICT",
    "ERROR",
}
VALID_OUTCOMES = {"FOUND", "NOT_FOUND", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE"}
VALID_GRADES = {"A", "B", "C", "D"}
STATUS_LABELS = {
    "COMPLETE_VERIFIED": "已找到并核验",
    "PARTIAL_VERIFIED": "部分找到",
    "LEAD_ONLY": "仅取得线索",
    "NOT_FOUND": "未找到",
    "BLOCKED": "访问受阻",
    "NEEDS_HUMAN": "需人工执行",
    "NOT_APPLICABLE": "不适用",
    "CONFLICT": "来源冲突",
    "ERROR": "执行错误",
}
OUTCOME_LABELS = {
    "FOUND": "找到",
    "NOT_FOUND": "未找到",
    "BLOCKED": "受阻",
    "NOT_RUN": "未执行",
    "NOT_APPLICABLE": "不适用",
}
TASK_ID_RE = re.compile(r"(?<!\d)([1-5](?:-\d+){1,2}[A-Z]?)(?!\d)")
PRIORITY_RE = re.compile(r"\b(P[0-3])\b")
CHECK_MARKERS_RE = re.compile(r"[□√×☐☑☒]")
FACT_STATUSES = {"COMPLETE_VERIFIED", "PARTIAL_VERIFIED", "CONFLICT"}
PLAINTIFF_REPUTATION_ITEMS = {"2-3-1", "2-3-2", "2-3-3", "2-3-4", "2-3-5"}
VALID_SUBJECT_ROLES = {"DEFENDANT", "PLAINTIFF_REPUTATION", "OFFLINE_MANUAL"}
VALID_EXECUTION_MODES = {"ONLINE", "OFFLINE_MANUAL"}
IMAGE_SEED_MARKER = "[IMAGE_SEED]"
AI_COLUMN_WIDTHS = [900, 2400, 3400, 1800, 3000, 4300]


class ChecklistError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_http_url(value: str, label: str = "URL") -> str:
    value = str(value or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ChecklistError(f"{label} 必须是有效的 HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ChecklistError(f"{label} 不得包含明文账号或密码")
    return value


def register_namespaces(xml_bytes: bytes) -> None:
    seen = set()
    try:
        for _, (prefix, uri) in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
            prefix = prefix or ""
            if (prefix, uri) in seen or prefix == "xml":
                continue
            seen.add((prefix, uri))
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                pass
    except ET.ParseError as exc:
        raise ChecklistError(f"DOCX XML 无法解析：{exc}") from exc


def load_document_xml(docx_path: Path) -> tuple[bytes, ET.Element]:
    if not docx_path.exists() or not docx_path.is_file():
        raise ChecklistError(f"DOCX 不存在：{docx_path}")
    if not zipfile.is_zipfile(docx_path):
        raise ChecklistError(f"不是合法 DOCX/OOXML 文件：{docx_path}")
    with zipfile.ZipFile(docx_path, "r") as archive:
        try:
            xml_bytes = archive.read("word/document.xml")
        except KeyError as exc:
            raise ChecklistError("DOCX 缺少 word/document.xml") from exc
    register_namespaces(xml_bytes)
    return xml_bytes, ET.fromstring(xml_bytes)


def package_inventory(docx_path: Path) -> dict:
    inventory = {}
    with zipfile.ZipFile(docx_path, "r") as archive:
        for info in archive.infolist():
            data = archive.read(info.filename)
            inventory[info.filename] = {
                "size": len(data),
                "sha256": sha256_bytes(data),
            }
    return inventory


def direct_rows(table: ET.Element) -> list[ET.Element]:
    return table.findall(f"{W}tr")


def direct_cells(row: ET.Element) -> list[ET.Element]:
    return row.findall(f"{W}tc")


def paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{W}t":
            parts.append(node.text or "")
        elif node.tag in {f"{W}br", f"{W}cr"}:
            parts.append("\n")
        elif node.tag == f"{W}tab":
            parts.append("\t")
    return "".join(parts).strip()


def cell_text(cell: ET.Element) -> str:
    paragraphs = [paragraph_text(p) for p in cell.findall(f".//{W}p")]
    return "\n".join(value for value in paragraphs if value)


def is_task_table(table: ET.Element) -> bool:
    rows = direct_rows(table)
    if not rows:
        return False
    headers = [cell_text(cell) for cell in direct_cells(rows[0])]
    if len(headers) < 5:
        return False
    return (
        "编号" in headers[0]
        and "优先级" in headers[0]
        and "关注什么" in headers[1]
        and "怎么做" in headers[2]
        and "去哪找" in headers[3]
        and "平台/网站核查" in headers[4]
    )


def extract_platforms(cell: ET.Element) -> list[str]:
    text = cell_text(cell)
    platforms = []
    for line in text.splitlines():
        cleaned = CHECK_MARKERS_RE.sub("", line, count=1).strip()
        if cleaned:
            platforms.append(cleaned)
    return platforms


def extract_tasks(root: ET.Element) -> list[dict]:
    tasks = []
    tables = root.findall(f".//{W}tbl")
    for table_index, table in enumerate(tables, start=1):
        if not is_task_table(table):
            continue
        rows = direct_rows(table)
        for row_index, row in enumerate(rows[1:], start=1):
            cells = direct_cells(row)
            if len(cells) < 5:
                continue
            original_cells = [cell_text(cell) for cell in cells[:5]]
            match = TASK_ID_RE.search(original_cells[0].replace("\n", " "))
            if not match:
                continue
            item_id = match.group(1)
            priority_match = PRIORITY_RE.search(original_cells[0].replace("\n", " "))
            row_key = f"T{table_index:02d}-R{row_index:03d}-{item_id}"
            tasks.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "row_key": row_key,
                    "item_id": item_id,
                    "priority": priority_match.group(1) if priority_match else "",
                    "table_index": table_index,
                    "row_index": row_index,
                    "manual_hint": "人类来做" in "\n".join(original_cells)
                    or "AI搞不了" in "\n".join(original_cells),
                    "original_cells": {
                        "编号 / 优先级": original_cells[0],
                        "关注什么": original_cells[1],
                        "怎么做": original_cells[2],
                        "去哪找": original_cells[3],
                        "平台/网站核查": original_cells[4],
                    },
                    "original_cells_sha256": sha256_bytes(
                        canonical_json(original_cells).encode("utf-8")
                    ),
                    "platforms": extract_platforms(cells[4]),
                }
            )
    return tasks


def case_paths(case_dir: Path) -> dict[str, Path]:
    return {
        "case": case_dir / "case.json",
        "manifest": case_dir / "checklist_manifest.json",
        "tasks": case_dir / "row_tasks.json",
        "results": case_dir / "row_results.jsonl",
        "search_log": case_dir / "logs" / "search_log.jsonl",
        "original": case_dir / "input" / "original_checklist.docx",
        "output_dir": case_dir / "output",
        "ledger": case_dir / "output" / "change_ledger.json",
        "validation": case_dir / "output" / "validation_result.json",
    }


def load_case(case_dir: Path) -> tuple[dict, dict[str, Path], list[dict]]:
    paths = case_paths(case_dir)
    missing = [str(path) for key, path in paths.items() if key in {"case", "manifest", "tasks", "original"} and not path.exists()]
    if missing:
        raise ChecklistError("案件目录不完整，缺少：" + "、".join(missing))
    case = read_json(paths["case"])
    task_doc = read_json(paths["tasks"])
    tasks = task_doc.get("tasks", [])
    return case, paths, tasks


def cmd_init(args) -> int:
    rights_holder = str(args.rights_holder or "").strip()
    if not rights_holder:
        raise ChecklistError("权利人信息不能为空")
    infringement_url = validate_http_url(args.url, "侵权链接")
    template = Path(args.checklist).expanduser().resolve() if args.checklist else DEFAULT_TEMPLATE
    case_dir = Path(args.output).expanduser().resolve()
    if case_dir.exists() and any(case_dir.iterdir()):
        raise ChecklistError(f"输出目录必须为空：{case_dir}")

    _, root = load_document_xml(template)
    tasks = extract_tasks(root)
    if not tasks:
        raise ChecklistError("模板中没有识别到五列调查任务表")
    duplicate_ids = sorted({task["item_id"] for task in tasks if sum(1 for row in tasks if row["item_id"] == task["item_id"]) > 1})
    if duplicate_ids:
        raise ChecklistError("模板存在重复任务编号：" + "、".join(duplicate_ids))

    paths = case_paths(case_dir)
    for directory in [
        case_dir / "input",
        case_dir / "output",
        case_dir / "logs",
        case_dir / "evidence" / "original",
        case_dir / "evidence" / "metadata",
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, paths["original"])
    paths["results"].write_text("", encoding="utf-8")
    paths["search_log"].write_text("", encoding="utf-8")

    template_hash = sha256_file(paths["original"])
    created_at = now_iso()
    case_id = "HC-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + template_hash[:8]
    case = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "rights_holder": rights_holder,
        "infringement_url": infringement_url,
        "created_at": created_at,
        "template_path": str(paths["original"]),
        "template_sha256": template_hash,
        "task_count": len(tasks),
        "workflow": "row_by_row_checklist_investigation",
        "defendant_seed": {
            "status": "MISSING",
            "product_name": "",
            "source_url": infringement_url,
            "captured_at": "",
            "seeds": [],
        },
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "template_source": str(template),
        "stored_template": str(paths["original"]),
        "sha256": template_hash,
        "task_count": len(tasks),
        "table_count": len(root.findall(f".//{W}tbl")),
        "package_parts": package_inventory(paths["original"]),
        "immutable_rule": "原始模板不得修改；输出只能在副本中更新方框并新增AI调查说明列",
    }
    write_json(paths["case"], case)
    write_json(paths["manifest"], manifest)
    write_json(
        paths["tasks"],
        {
            "schema_version": SCHEMA_VERSION,
            "template_sha256": template_hash,
            "task_count": len(tasks),
            "tasks": tasks,
        },
    )
    print(
        json.dumps(
            {
                "case_dir": str(case_dir),
                "case_id": case_id,
                "task_count": len(tasks),
                "template_sha256": template_hash,
                "next": f"python3 {Path(__file__).name} tasks --case-dir {case_dir} --pending",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_result_lines(path: Path, verify_chain: bool = True) -> tuple[list[dict], list[str]]:
    results = []
    errors = []
    previous_hash = ""
    if not path.exists():
        return results, errors
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"row_results.jsonl 第{line_number}行不是合法JSON：{exc}")
            continue
        if verify_chain:
            record_hash = record.get("record_hash", "")
            payload = dict(record)
            payload.pop("record_hash", None)
            expected = sha256_bytes(canonical_json(payload).encode("utf-8"))
            if record.get("prev_record_hash", "") != previous_hash:
                errors.append(f"第{line_number}行 prev_record_hash 不连续")
            if record_hash != expected:
                errors.append(f"第{line_number}行 record_hash 不匹配")
            previous_hash = record_hash
        results.append(record)
    return results, errors


def latest_results(records: list[dict]) -> dict[str, dict]:
    latest = {}
    for record in records:
        item_id = record.get("item_id")
        if item_id:
            latest[item_id] = record
    return latest


def normalize_platform(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def normalize_seed_text(value: str) -> str:
    return re.sub(r"[\s\"'“”‘’]+", "", str(value or "")).casefold()


def defendant_seed_map(case: dict) -> dict[str, dict]:
    bundle = case.get("defendant_seed", {})
    if not isinstance(bundle, dict) or bundle.get("status") != "READY":
        return {}
    seeds = bundle.get("seeds", [])
    if not isinstance(seeds, list):
        return {}
    return {
        str(seed.get("id") or "").strip(): seed
        for seed in seeds
        if isinstance(seed, dict)
        and str(seed.get("id") or "").strip()
        and str(seed.get("value") or "").strip()
    }


def build_defendant_seed_bundle(payload: dict, case: dict) -> dict:
    if not isinstance(payload, dict):
        raise ChecklistError("被告商品种子文件必须是JSON对象")
    product_name = str(payload.get("product_name") or "").strip()
    if not product_name:
        raise ChecklistError("被告商品种子缺少必填 product_name")
    source_url = str(payload.get("source_url") or case.get("infringement_url") or "").strip()
    if source_url:
        validate_http_url(source_url, "被告商品种子 source_url")
    captured_at = str(payload.get("captured_at") or now_iso()).strip()
    entries: list[dict] = []
    counts: dict[str, int] = {}
    seen_values: set[tuple[str, str]] = set()

    def add_seed(kind: str, raw_value, source_ref: str = "") -> None:
        value = str(raw_value or "").strip()
        if not value:
            return
        kind = re.sub(r"[^A-Z0-9]+", "_", str(kind or "ALIAS").upper()).strip("_") or "ALIAS"
        dedupe_key = (kind, normalize_seed_text(value))
        if dedupe_key in seen_values:
            return
        seen_values.add(dedupe_key)
        counts[kind] = counts.get(kind, 0) + 1
        entries.append(
            {
                "id": f"D-{kind}-{counts[kind]:03d}",
                "kind": kind,
                "value": value,
                "source_ref": str(source_ref or payload.get("source_ref") or source_url).strip(),
            }
        )

    add_seed("PRODUCT", product_name)
    for field_name, kind in [
        ("brand", "BRAND"),
        ("store_name", "STORE"),
        ("operator_name", "OPERATOR"),
        ("model", "MODEL"),
    ]:
        add_seed(kind, payload.get(field_name))
    for alias in payload.get("aliases", []) or []:
        if isinstance(alias, dict):
            add_seed(alias.get("kind", "ALIAS"), alias.get("value"), alias.get("source_ref", ""))
        else:
            add_seed("ALIAS", alias)
    for image_seed in payload.get("image_seeds", []) or []:
        if isinstance(image_seed, dict):
            add_seed("IMAGE", image_seed.get("value") or image_seed.get("sha256"), image_seed.get("source_ref", ""))
        else:
            add_seed("IMAGE", image_seed)
    return {
        "status": "READY",
        "product_name": product_name,
        "brand": str(payload.get("brand") or "").strip(),
        "store_name": str(payload.get("store_name") or "").strip(),
        "operator_name": str(payload.get("operator_name") or "").strip(),
        "model": str(payload.get("model") or "").strip(),
        "source_url": source_url,
        "captured_at": captured_at,
        "updated_at": now_iso(),
        "seeds": entries,
    }


def cmd_set_seed(args) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    case, paths, _ = load_case(case_dir)
    payload = read_json(Path(args.file).expanduser().resolve())
    bundle = build_defendant_seed_bundle(payload, case)
    case["schema_version"] = SCHEMA_VERSION
    case["defendant_seed"] = bundle
    write_json(paths["case"], case)
    print(
        json.dumps(
            {
                "case_id": case["case_id"],
                "status": bundle["status"],
                "product_name": bundle["product_name"],
                "seed_ids": [seed["id"] for seed in bundle["seeds"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def normalize_checked_platforms(value) -> list[dict]:
    if isinstance(value, dict):
        normalized = []
        for name, details in value.items():
            if isinstance(details, bool):
                normalized.append(
                    {
                        "name": name,
                        "checked": details,
                        "outcome": "FOUND" if details else "NOT_RUN",
                        "note": "",
                    }
                )
            elif isinstance(details, dict):
                normalized.append({"name": name, **details})
            else:
                raise ChecklistError(f"平台 {name} 的核查记录必须是布尔值或对象")
        return normalized
    if isinstance(value, list):
        return value
    raise ChecklistError("checked_platforms 必须是数组或对象")


def validate_result_record(
    raw: dict,
    task: dict,
    case: dict,
    add_defaults: bool,
    enforce_subject: bool = True,
) -> dict:
    if not isinstance(raw, dict):
        raise ChecklistError("每条行级结果必须是JSON对象")
    record = copy.deepcopy(raw)
    item_id = str(record.get("item_id") or record.get("task_id") or "").strip()
    if item_id != task["item_id"]:
        raise ChecklistError(f"任务编号不匹配：期望 {task['item_id']}，实际 {item_id or '空'}")
    record["item_id"] = item_id
    record["row_key"] = task["row_key"]
    status = str(record.get("status") or "").strip()
    if status not in VALID_STATUSES:
        raise ChecklistError(f"{item_id} 的 status 无效：{status}")
    record["status"] = status
    if add_defaults and not record.get("completed_at"):
        record["completed_at"] = now_iso()
    if not record.get("completed_at"):
        raise ChecklistError(f"{item_id} 缺少 completed_at")

    actions = record.get("actions", [])
    findings = record.get("findings", [])
    sources = record.get("sources", [])
    limitations = record.get("limitations", [])
    next_steps = record.get("next_steps", [])
    for field_name, value in [
        ("actions", actions),
        ("findings", findings),
        ("sources", sources),
        ("limitations", limitations),
        ("next_steps", next_steps),
    ]:
        if not isinstance(value, list):
            raise ChecklistError(f"{item_id} 的 {field_name} 必须是数组")

    source_by_id = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ChecklistError(f"{item_id} 的 source 必须是对象")
        source_id = str(source.get("id") or "").strip()
        if not source_id or source_id in source_by_id:
            raise ChecklistError(f"{item_id} 的来源ID为空或重复：{source_id}")
        source_grade = str(source.get("source_grade") or "").upper()
        if source_grade not in VALID_GRADES:
            raise ChecklistError(f"{item_id}/{source_id} 的 source_grade 必须为A/B/C/D")
        url = str(source.get("url") or "").strip()
        evidence_file = str(source.get("evidence_file") or "").strip()
        if url:
            validate_http_url(url, f"{item_id}/{source_id} 来源URL")
        elif not evidence_file:
            raise ChecklistError(f"{item_id}/{source_id} 必须提供URL或真实证据文件")
        if evidence_file and not Path(evidence_file).expanduser().exists():
            raise ChecklistError(f"{item_id}/{source_id} 证据文件不存在：{evidence_file}")
        if not str(source.get("title") or "").strip():
            raise ChecklistError(f"{item_id}/{source_id} 缺少页面或文件标题")
        if not str(source.get("accessed_at") or "").strip():
            raise ChecklistError(f"{item_id}/{source_id} 缺少访问或取得时间")
        source["source_grade"] = source_grade
        source_by_id[source_id] = source

    seeds_by_id = defendant_seed_map(case)
    valid_defendant_actions = []
    valid_reputation_actions = []
    for action in actions:
        if not isinstance(action, dict):
            raise ChecklistError(f"{item_id} 的 action 必须是对象")
        outcome = str(action.get("outcome") or "").upper()
        if outcome not in VALID_OUTCOMES:
            raise ChecklistError(f"{item_id} 的 action.outcome 无效：{outcome}")
        action["outcome"] = outcome
        if not str(action.get("accessed_at") or "").strip():
            raise ChecklistError(f"{item_id} 的每个 action 都必须记录 accessed_at")
        if not any(str(action.get(key) or "").strip() for key in ("query", "url", "platform")):
            raise ChecklistError(f"{item_id} 的 action 至少要记录 query、url 或 platform")
        if action.get("url"):
            validate_http_url(str(action["url"]), f"{item_id} action URL")
        if enforce_subject:
            subject_role = str(action.get("subject_role") or "").upper().strip()
            if subject_role not in VALID_SUBJECT_ROLES:
                raise ChecklistError(f"{item_id} 的每个 action 都必须提供有效 subject_role")
            seed_refs = action.get("seed_refs")
            if not isinstance(seed_refs, list):
                raise ChecklistError(f"{item_id} 的每个 action 都必须提供 seed_refs 数组")
            seed_refs = [str(ref).strip() for ref in seed_refs if str(ref).strip()]
            execution_mode = str(action.get("execution_mode") or "ONLINE").upper().strip()
            if execution_mode not in VALID_EXECUTION_MODES:
                raise ChecklistError(f"{item_id} action.execution_mode 无效：{execution_mode}")
            action["subject_role"] = subject_role
            action["seed_refs"] = seed_refs
            action["execution_mode"] = execution_mode
            if subject_role == "DEFENDANT":
                if not seed_refs:
                    raise ChecklistError(f"{item_id} 的 DEFENDANT action 必须引用至少一个被告种子")
                unknown_refs = [ref for ref in seed_refs if ref not in seeds_by_id]
                if unknown_refs:
                    raise ChecklistError(f"{item_id} 的 DEFENDANT action 引用了不存在的种子：{unknown_refs}")
                query = str(action.get("query") or "").strip()
                if query:
                    normalized_query = normalize_seed_text(query)
                    contains_seed = any(
                        normalize_seed_text(seeds_by_id[ref].get("value", "")) in normalized_query
                        for ref in seed_refs
                    )
                    image_marker = IMAGE_SEED_MARKER.casefold() in query.casefold()
                    if not contains_seed and not image_marker:
                        raise ChecklistError(
                            f"{item_id} 的 DEFENDANT query 必须包含被引用种子值或明确标记 {IMAGE_SEED_MARKER}"
                        )
                qualifies = (
                    execution_mode == "ONLINE"
                    and bool(query)
                    and outcome in {"FOUND", "NOT_FOUND", "BLOCKED"}
                )
                if qualifies:
                    valid_defendant_actions.append(action)
            elif subject_role == "PLAINTIFF_REPUTATION":
                if item_id not in PLAINTIFF_REPUTATION_ITEMS:
                    continue
                if execution_mode == "ONLINE" and outcome in {"FOUND", "NOT_FOUND", "BLOCKED"}:
                    valid_reputation_actions.append(action)

    if enforce_subject:
        seed_ready = bool(seeds_by_id)
        if not seed_ready and status not in {"BLOCKED", "NEEDS_HUMAN", "ERROR"}:
            raise ChecklistError(
                f"{item_id} 的被告商品种子尚未READY；只能记录 BLOCKED、NEEDS_HUMAN 或 ERROR"
            )
        if seed_ready and item_id not in PLAINTIFF_REPUTATION_ITEMS and not valid_defendant_actions:
            raise ChecklistError(
                f"{item_id} 必须至少包含一次联网、引用有效种子的 DEFENDANT action；"
                "PLAINTIFF_REPUTATION 或 OFFLINE_MANUAL action 不能替代"
            )
        if (
            seed_ready
            and item_id in PLAINTIFF_REPUTATION_ITEMS
            and actions
            and not valid_reputation_actions
            and not valid_defendant_actions
        ):
            raise ChecklistError(
                f"{item_id} 的联网调查必须使用 PLAINTIFF_REPUTATION 或有效 DEFENDANT action"
            )

    for finding in findings:
        if not isinstance(finding, dict) or not str(finding.get("statement") or "").strip():
            raise ChecklistError(f"{item_id} 的 finding 必须含非空 statement")
        refs = finding.get("source_refs", [])
        if not isinstance(refs, list) or not refs:
            raise ChecklistError(f"{item_id} 的每条 finding 必须引用 source_refs")
        unknown = [ref for ref in refs if ref not in source_by_id]
        if unknown:
            raise ChecklistError(f"{item_id} 的 finding 引用了不存在的来源：{unknown}")
        if status in FACT_STATUSES:
            grades = [source_by_id[ref]["source_grade"] for ref in refs]
            if all(grade == "D" for grade in grades):
                raise ChecklistError(f"{item_id} 的已核验事实不能只由D级线索支持")
            if all(grade == "C" for grade in grades):
                publishers = {
                    str(source_by_id[ref].get("publisher") or "").strip()
                    for ref in refs
                    if str(source_by_id[ref].get("publisher") or "").strip()
                }
                if len(publishers) < 2:
                    raise ChecklistError(f"{item_id} 的C级来源必须至少有两个独立发布主体相互印证")

    checked_platforms = normalize_checked_platforms(record.get("checked_platforms", []))
    expected_platforms = {normalize_platform(name): name for name in task.get("platforms", [])}
    covered = {}
    for platform in checked_platforms:
        if not isinstance(platform, dict):
            raise ChecklistError(f"{item_id} 的 checked_platforms 元素必须是对象")
        name = str(platform.get("name") or "").strip()
        normalized_name = normalize_platform(name)
        if normalized_name not in expected_platforms:
            raise ChecklistError(f"{item_id} 的平台不在原清单中：{name}")
        if normalized_name in covered:
            raise ChecklistError(f"{item_id} 重复记录平台：{name}")
        if not isinstance(platform.get("checked"), bool):
            raise ChecklistError(f"{item_id}/{name} 的 checked 必须是布尔值")
        outcome = str(platform.get("outcome") or "").upper()
        if outcome not in VALID_OUTCOMES:
            raise ChecklistError(f"{item_id}/{name} 的 outcome 无效：{outcome}")
        if platform["checked"] and outcome not in {"FOUND", "NOT_FOUND"}:
            raise ChecklistError(f"{item_id}/{name} 已查看时 outcome 只能为 FOUND 或 NOT_FOUND")
        if not platform["checked"] and outcome in {"FOUND", "NOT_FOUND"}:
            raise ChecklistError(f"{item_id}/{name} 未查看时不能写 FOUND 或 NOT_FOUND")
        if not platform["checked"] and not str(platform.get("note") or "").strip():
            raise ChecklistError(f"{item_id}/{name} 未查看时必须说明原因")
        platform["outcome"] = outcome
        platform["name"] = expected_platforms[normalized_name]
        covered[normalized_name] = platform
    missing_platforms = [original for key, original in expected_platforms.items() if key not in covered]
    if missing_platforms:
        raise ChecklistError(f"{item_id} 未逐项记录平台：{'、'.join(missing_platforms)}")
    record["checked_platforms"] = checked_platforms

    checked_names = {
        normalize_platform(platform["name"])
        for platform in checked_platforms
        if platform["checked"]
    }
    action_platforms = {
        normalize_platform(action.get("platform", ""))
        for action in actions
        if action.get("outcome") in {"FOUND", "NOT_FOUND"}
    }
    missing_actions = [
        expected_platforms[name]
        for name in checked_names
        if name not in action_platforms
    ]
    if missing_actions:
        raise ChecklistError(f"{item_id} 已勾选平台缺少对应 action：{'、'.join(missing_actions)}")

    if status in {"COMPLETE_VERIFIED", "PARTIAL_VERIFIED", "CONFLICT"} and not findings:
        raise ChecklistError(f"{item_id}/{status} 必须有带来源的 findings")
    if status == "LEAD_ONLY" and not findings:
        raise ChecklistError(f"{item_id}/LEAD_ONLY 必须写明线索及来源")
    if status == "NOT_FOUND":
        if findings:
            raise ChecklistError(f"{item_id}/NOT_FOUND 不得同时写已找到事实")
        if not actions or not str(record.get("searched_scope") or "").strip():
            raise ChecklistError(f"{item_id}/NOT_FOUND 必须记录 actions 和 searched_scope")
    if status == "BLOCKED" and not str(record.get("blocked_reason") or "").strip():
        raise ChecklistError(f"{item_id}/BLOCKED 必须写 blocked_reason")
    if status == "NEEDS_HUMAN" and not next_steps:
        raise ChecklistError(f"{item_id}/NEEDS_HUMAN 必须写 next_steps")
    if status == "NOT_APPLICABLE" and not str(record.get("reason") or "").strip():
        raise ChecklistError(f"{item_id}/NOT_APPLICABLE 必须逐行写明理由")
    if status == "ERROR" and not str(record.get("error_message") or "").strip():
        raise ChecklistError(f"{item_id}/ERROR 必须写 error_message")

    record["actions"] = actions
    record["findings"] = findings
    record["sources"] = sources
    record["limitations"] = limitations
    record["next_steps"] = next_steps
    return record


def append_results(case_dir: Path, raw_records: list[dict]) -> list[dict]:
    case, paths, tasks = load_case(case_dir)
    task_by_id = {task["item_id"]: task for task in tasks}
    existing, chain_errors = load_result_lines(paths["results"], verify_chain=True)
    if chain_errors:
        raise ChecklistError("既有结果日志哈希链损坏：" + "；".join(chain_errors))
    latest = latest_results(existing)
    previous_hash = existing[-1].get("record_hash", "") if existing else ""
    written = []
    with paths["results"].open("a", encoding="utf-8") as result_handle, paths["search_log"].open("a", encoding="utf-8") as log_handle:
        for raw in raw_records:
            item_id = str(raw.get("item_id") or raw.get("task_id") or "").strip()
            if item_id not in task_by_id:
                raise ChecklistError(f"未知任务编号：{item_id}")
            record = validate_result_record(raw, task_by_id[item_id], case, add_defaults=True)
            record["schema_version"] = SCHEMA_VERSION
            record["case_id"] = case["case_id"]
            record["template_sha256"] = case["template_sha256"]
            record["recorded_at"] = now_iso()
            record["revision"] = int(latest.get(item_id, {}).get("revision", 0)) + 1
            record["prev_record_hash"] = previous_hash
            payload_hash = sha256_bytes(canonical_json(record).encode("utf-8"))
            record["record_hash"] = payload_hash
            result_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            result_handle.flush()
            for action in record["actions"]:
                log_handle.write(
                    json.dumps(
                        {
                            "case_id": case["case_id"],
                            "item_id": item_id,
                            "row_key": record["row_key"],
                            "record_hash": payload_hash,
                            **action,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            log_handle.flush()
            previous_hash = payload_hash
            latest[item_id] = record
            written.append(record)
    return written


def cmd_record(args) -> int:
    if args.file:
        payload = read_json(Path(args.file).expanduser().resolve())
    elif args.json:
        payload = json.loads(args.json)
    else:
        payload = json.load(sys.stdin)
    records = payload if isinstance(payload, list) else [payload]
    written = append_results(Path(args.case_dir).expanduser().resolve(), records)
    print(
        json.dumps(
            {
                "recorded": len(written),
                "items": [record["item_id"] for record in written],
                "record_hashes": [record["record_hash"] for record in written],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_tasks(args) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    _, paths, tasks = load_case(case_dir)
    records, errors = load_result_lines(paths["results"], verify_chain=True)
    if errors:
        raise ChecklistError("结果日志损坏：" + "；".join(errors))
    latest = latest_results(records)
    output = []
    for task in tasks:
        if args.priority and task["priority"] != args.priority:
            continue
        result = latest.get(task["item_id"])
        if args.pending and result:
            continue
        output.append(
            {
                **task,
                "latest_status": result.get("status") if result else None,
                "latest_revision": result.get("revision") if result else None,
            }
        )
        if args.limit and len(output) >= args.limit:
            break
    print(json.dumps({"count": len(output), "tasks": output}, ensure_ascii=False, indent=2))
    return 0


def source_line(source: dict) -> str:
    pieces = [f"[{source.get('id')}] {source.get('title')}"]
    if source.get("publisher"):
        pieces.append(str(source["publisher"]))
    if source.get("url"):
        pieces.append(str(source["url"]))
    if source.get("evidence_file"):
        pieces.append(str(source["evidence_file"]))
    pieces.append(f"访问/取得：{source.get('accessed_at')}")
    pieces.append(f"来源级别：{source.get('source_grade')}")
    return "｜".join(pieces)


def build_ai_note(result: dict | None, task: dict) -> str:
    if not result:
        return "状态：未执行\nAI做了什么：尚未处理本行。\n限制：本行无调查记录，不能据此作事实判断。"
    status = result["status"]
    lines = [f"状态：{STATUS_LABELS[status]}"]
    actions = result.get("actions", [])
    if actions:
        lines.append("AI做了什么：")
        for index, action in enumerate(actions, start=1):
            details = []
            if action.get("platform"):
                details.append(str(action["platform"]))
            if action.get("subject_role"):
                details.append(f"对象：{action['subject_role']}")
            if action.get("seed_refs"):
                details.append("种子：" + "、".join(action["seed_refs"]))
            if action.get("query"):
                details.append(f"查询“{action['query']}”")
            if action.get("url"):
                details.append(str(action["url"]))
            details.append(OUTCOME_LABELS.get(action.get("outcome"), str(action.get("outcome"))))
            details.append(str(action.get("accessed_at")))
            if action.get("note"):
                details.append(str(action["note"]))
            lines.append(f"{index}. " + "｜".join(details))
    else:
        lines.append("AI做了什么：未进行公开网页操作。")

    findings = result.get("findings", [])
    if findings:
        lines.append("查到的内容：")
        for finding in findings:
            refs = "、".join(finding.get("source_refs", []))
            scope = str(finding.get("support_scope") or "").strip()
            value = f"- {finding['statement']}（来源：{refs}）"
            if scope:
                value += f"；证明边界：{scope}"
            lines.append(value)
    elif status == "NOT_FOUND":
        lines.append(
            "调查结果：截至"
            + str(result.get("completed_at"))
            + "，在"
            + str(result.get("searched_scope"))
            + "内未找到可核验公开材料。本结论仅表示本次公开检索未发现，不代表该事实不存在。"
        )
    elif status == "BLOCKED":
        lines.append("受阻原因：" + str(result.get("blocked_reason")))
    elif status == "NEEDS_HUMAN":
        lines.append("调查结果：该项不能由AI独立完成。")
    elif status == "NOT_APPLICABLE":
        lines.append("不适用理由：" + str(result.get("reason")))
    elif status == "ERROR":
        lines.append("错误：" + str(result.get("error_message")))

    sources = result.get("sources", [])
    if sources:
        lines.append("实际来源：")
        for source in sources:
            lines.append("- " + source_line(source))
    if result.get("limitations"):
        lines.append("未找到/局限：")
        lines.extend("- " + str(value) for value in result["limitations"])
    if result.get("next_steps"):
        lines.append("需人工补查：")
        lines.extend("- " + str(value) for value in result["next_steps"])
    return "\n".join(lines)


def set_cell_width(cell: ET.Element, width: int) -> None:
    tc_pr = cell.find(f"{W}tcPr")
    if tc_pr is None:
        tc_pr = ET.Element(f"{W}tcPr")
        cell.insert(0, tc_pr)
    tc_w = tc_pr.find(f"{W}tcW")
    if tc_w is None:
        tc_w = ET.SubElement(tc_pr, f"{W}tcW")
    tc_w.set(f"{W}w", str(width))
    tc_w.set(f"{W}type", "dxa")


def clone_cell_with_text(source: ET.Element, text: str, width: int) -> ET.Element:
    source_paragraph = source.find(f"{W}p")
    paragraph_props = copy.deepcopy(source_paragraph.find(f"{W}pPr")) if source_paragraph is not None and source_paragraph.find(f"{W}pPr") is not None else None
    source_run = source_paragraph.find(f"{W}r") if source_paragraph is not None else None
    run_props = copy.deepcopy(source_run.find(f"{W}rPr")) if source_run is not None and source_run.find(f"{W}rPr") is not None else None

    new_cell = copy.deepcopy(source)
    for child in list(new_cell):
        if child.tag != f"{W}tcPr":
            new_cell.remove(child)
    set_cell_width(new_cell, width)
    paragraph = ET.SubElement(new_cell, f"{W}p")
    if paragraph_props is not None:
        paragraph.append(paragraph_props)
    lines = str(text).split("\n")
    for index, line in enumerate(lines):
        run = ET.SubElement(paragraph, f"{W}r")
        if run_props is not None:
            run.append(copy.deepcopy(run_props))
        text_node = ET.SubElement(run, f"{W}t")
        text_node.set(XML_SPACE, "preserve")
        text_node.text = line
        if index < len(lines) - 1:
            ET.SubElement(run, f"{W}br")
    return new_cell


def set_table_widths(table: ET.Element, widths: list[int]) -> None:
    tbl_pr = table.find(f"{W}tblPr")
    if tbl_pr is None:
        tbl_pr = ET.Element(f"{W}tblPr")
        table.insert(0, tbl_pr)
    tbl_w = tbl_pr.find(f"{W}tblW")
    if tbl_w is None:
        tbl_w = ET.SubElement(tbl_pr, f"{W}tblW")
    tbl_w.set(f"{W}w", str(sum(widths)))
    tbl_w.set(f"{W}type", "dxa")
    grid = table.find(f"{W}tblGrid")
    if grid is None:
        grid = ET.Element(f"{W}tblGrid")
        insertion_index = 1 if table.find(f"{W}tblPr") is not None else 0
        table.insert(insertion_index, grid)
    for grid_col in list(grid):
        if grid_col.tag == f"{W}gridCol":
            grid.remove(grid_col)
    for width in widths:
        grid_col = ET.SubElement(grid, f"{W}gridCol")
        grid_col.set(f"{W}w", str(width))
    for row in direct_rows(table):
        for index, cell in enumerate(direct_cells(row)):
            set_cell_width(cell, widths[min(index, len(widths) - 1)])


def platform_was_checked(platform: str, result: dict | None) -> bool:
    if not result:
        return False
    target = normalize_platform(platform)
    return any(
        normalize_platform(item.get("name", "")) == target and item.get("checked") is True
        for item in result.get("checked_platforms", [])
    )


def update_platform_markers(cell: ET.Element, task: dict, result: dict | None, ledger: list[dict]) -> None:
    marker_nodes = [node for node in cell.iter(f"{W}t") if node.text and "□" in node.text]
    platforms = task.get("platforms", [])
    for index, node in enumerate(marker_nodes):
        platform = platforms[index] if index < len(platforms) else CHECK_MARKERS_RE.sub("", node.text, count=1).strip()
        replacement = "√" if platform_was_checked(platform, result) else "×"
        before = node.text
        node.text = node.text.replace("□", replacement, 1)
        ledger.append(
            {
                "item_id": task["item_id"],
                "location": "平台/网站核查",
                "before": before,
                "after": node.text,
                "reason": "已查看填√；未查看、无法查看或未找到入口填×",
                "result_record_hash": result.get("record_hash") if result else None,
            }
        )


def serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_patched_docx(original: Path, output: Path, document_xml: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(temporary, "w") as target:
        target.comment = source.comment
        for info in source.infolist():
            data = document_xml if info.filename == "word/document.xml" else source.read(info.filename)
            target.writestr(info, data)
    temporary.replace(output)


def build_filled_docx(case_dir: Path, output: Path, require_all_results: bool) -> dict:
    case, paths, tasks = load_case(case_dir)
    records, chain_errors = load_result_lines(paths["results"], verify_chain=True)
    if chain_errors:
        raise ChecklistError("结果日志哈希链损坏：" + "；".join(chain_errors))
    latest = latest_results(records)
    task_by_id = {task["item_id"]: task for task in tasks}
    missing = [task["item_id"] for task in tasks if task["item_id"] not in latest]
    if require_all_results and missing:
        raise ChecklistError("仍有未处理任务，不能严格生成：" + "、".join(missing))
    for item_id, result in latest.items():
        validate_result_record(
            result,
            task_by_id[item_id],
            case,
            add_defaults=False,
            enforce_subject=require_all_results,
        )

    _, root = load_document_xml(paths["original"])
    ledger = []
    task_tables = 0
    patched_tasks = set()
    for table_index, table in enumerate(root.findall(f".//{W}tbl"), start=1):
        if not is_task_table(table):
            continue
        task_tables += 1
        rows = direct_rows(table)
        header_cells = direct_cells(rows[0])
        if len(header_cells) < 5:
            raise ChecklistError(f"第{table_index}张任务表表头不足5列")
        header_cells[0].getparent if False else None
        rows[0].append(clone_cell_with_text(header_cells[4], AI_HEADER, AI_COLUMN_WIDTHS[5]))
        ledger.append(
            {
                "table_index": table_index,
                "row_index": 0,
                "location": "新增列",
                "before": None,
                "after": AI_HEADER,
                "reason": "按用户要求增加逐行AI调查说明列",
            }
        )
        for row_index, row in enumerate(rows[1:], start=1):
            cells = direct_cells(row)
            if len(cells) < 5:
                continue
            first_text = cell_text(cells[0])
            match = TASK_ID_RE.search(first_text.replace("\n", " "))
            if not match:
                row.append(clone_cell_with_text(cells[-1], "结构行，无独立调查任务。", AI_COLUMN_WIDTHS[5]))
                continue
            item_id = match.group(1)
            task = task_by_id.get(item_id)
            if not task:
                raise ChecklistError(f"输出阶段遇到未登记任务：{item_id}")
            result = latest.get(item_id)
            update_platform_markers(cells[4], task, result, ledger)
            note = build_ai_note(result, task)
            row.append(clone_cell_with_text(cells[4], note, AI_COLUMN_WIDTHS[5]))
            ledger.append(
                {
                    "item_id": item_id,
                    "table_index": table_index,
                    "row_index": row_index,
                    "location": AI_HEADER,
                    "before": None,
                    "after": note,
                    "reason": "追加本行调查动作、结果、来源、局限和人工补查",
                    "result_record_hash": result.get("record_hash") if result else None,
                }
            )
            patched_tasks.add(item_id)
        set_table_widths(table, AI_COLUMN_WIDTHS)
    if task_tables != 5:
        raise ChecklistError(f"应识别5张任务表，实际识别{task_tables}张")
    missing_in_doc = sorted(set(task_by_id) - patched_tasks)
    if missing_in_doc:
        raise ChecklistError("以下任务未写入输出DOCX：" + "、".join(missing_in_doc))

    write_patched_docx(paths["original"], output, serialize_xml(root))
    write_json(
        paths["ledger"],
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": case["case_id"],
            "template_sha256": case["template_sha256"],
            "output": str(output),
            "created_at": now_iso(),
            "changes": ledger,
        },
    )
    return {
        "output": str(output),
        "task_count": len(tasks),
        "result_count": len(latest),
        "missing_result_count": len(missing),
        "change_count": len(ledger),
    }


def cmd_fill(args) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    case, paths, _ = load_case(case_dir)
    default_name = Path(paths["original"]).stem + "_逐行调查_部分填充.docx"
    output = Path(args.output).expanduser().resolve() if args.output else paths["output_dir"] / default_name
    result = build_filled_docx(case_dir, output, require_all_results=args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def strip_check_markers(value: str) -> str:
    return CHECK_MARKERS_RE.sub("", value)


def validate_output(case_dir: Path, output: Path, strict: bool) -> dict:
    case, paths, tasks = load_case(case_dir)
    errors = []
    warnings = []
    if sha256_file(paths["original"]) != case["template_sha256"]:
        errors.append("原始模板SHA-256已变化")

    records, chain_errors = load_result_lines(paths["results"], verify_chain=True)
    errors.extend(chain_errors)
    latest = latest_results(records)
    task_by_id = {task["item_id"]: task for task in tasks}
    for item_id, record in latest.items():
        if item_id not in task_by_id:
            errors.append(f"结果日志含未知任务：{item_id}")
            continue
        try:
            validate_result_record(
                record,
                task_by_id[item_id],
                case,
                add_defaults=False,
                enforce_subject=strict,
            )
        except ChecklistError as exc:
            errors.append(str(exc))
    missing_results = [task["item_id"] for task in tasks if task["item_id"] not in latest]
    if strict and missing_results:
        errors.append("严格模式下仍有未处理任务：" + "、".join(missing_results))
    elif missing_results:
        warnings.append("仍有未处理任务：" + "、".join(missing_results))

    if not output.exists():
        errors.append(f"输出DOCX不存在：{output}")
    elif not zipfile.is_zipfile(output):
        errors.append("输出文件不是合法DOCX")
    else:
        original_inventory = package_inventory(paths["original"])
        output_inventory = package_inventory(output)
        if set(original_inventory) != set(output_inventory):
            errors.append("输出DOCX的ZIP部件集合与原模板不同")
        for name, details in original_inventory.items():
            if name == "word/document.xml" or name not in output_inventory:
                continue
            if output_inventory[name]["sha256"] != details["sha256"]:
                errors.append(f"不应修改的DOCX部件发生变化：{name}")

        _, original_root = load_document_xml(paths["original"])
        _, output_root = load_document_xml(output)
        original_tables = original_root.findall(f".//{W}tbl")
        output_tables = output_root.findall(f".//{W}tbl")
        if len(original_tables) != len(output_tables):
            errors.append("输出表格数量与原模板不一致")
        for table_index, (original_table, output_table) in enumerate(zip(original_tables, output_tables), start=1):
            original_rows = direct_rows(original_table)
            output_rows = direct_rows(output_table)
            if len(original_rows) != len(output_rows):
                errors.append(f"第{table_index}张表行数发生变化")
                continue
            main_table = is_task_table(original_table)
            for row_index, (original_row, output_row) in enumerate(zip(original_rows, output_rows)):
                original_cells = direct_cells(original_row)
                output_cells = direct_cells(output_row)
                expected_count = len(original_cells) + 1 if main_table else len(original_cells)
                if len(output_cells) != expected_count:
                    errors.append(f"第{table_index}张表第{row_index}行列数不符合追加式规则")
                    continue
                if not main_table:
                    if [cell_text(cell) for cell in original_cells] != [cell_text(cell) for cell in output_cells]:
                        errors.append(f"第{table_index}张非任务表内容发生变化")
                    continue
                for column_index in range(min(4, len(original_cells))):
                    if cell_text(original_cells[column_index]) != cell_text(output_cells[column_index]):
                        errors.append(f"任务表{table_index}第{row_index}行第{column_index + 1}列原文发生变化")
                if len(original_cells) >= 5 and strip_check_markers(cell_text(original_cells[4])) != strip_check_markers(cell_text(output_cells[4])):
                    errors.append(f"任务表{table_index}第{row_index}行平台名称或原文发生变化")
                if not cell_text(output_cells[-1]).strip():
                    errors.append(f"任务表{table_index}第{row_index}行AI调查说明为空")

    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case["case_id"],
        "strict": strict,
        "ok": not errors,
        "template_sha256": case["template_sha256"],
        "task_count": len(tasks),
        "result_count": len(latest),
        "missing_results": missing_results,
        "errors": errors,
        "warnings": warnings,
        "validated_at": now_iso(),
        "output": str(output),
    }
    write_json(paths["validation"], result)
    return result


def cmd_validate(args) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    _, paths, _ = load_case(case_dir)
    if args.output:
        output = Path(args.output).expanduser().resolve()
    else:
        candidates = sorted(paths["output_dir"].glob("*_逐行调查_部分填充.docx"))
        if not candidates:
            raise ChecklistError("没有找到待校验的部分填充DOCX，请用 --output 指定")
        output = candidates[-1]
    result = validate_output(case_dir, output, strict=args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def self_test_record(task: dict, timestamp: str) -> dict:
    reputation = task["item_id"] in PLAINTIFF_REPUTATION_ITEMS
    subject_role = "PLAINTIFF_REPUTATION" if reputation else "DEFENDANT"
    seed_refs = [] if reputation else ["D-PRODUCT-001"]
    query_subject = "自检权利人（非真实案件）" if reputation else "自检被告商品（非真实案件）"
    if task["manual_hint"]:
        return {
            "item_id": task["item_id"],
            "status": "NEEDS_HUMAN",
            "completed_at": timestamp,
            "actions": [
                {
                    "platform": "离线自检",
                    "query": f'"{query_subject}" 人工作业前置检索',
                    "accessed_at": timestamp,
                    "outcome": "NOT_FOUND",
                    "note": "仅验证对象与种子约束，不代表真实调查",
                    "subject_role": subject_role,
                    "seed_refs": seed_refs,
                    "execution_mode": "ONLINE",
                }
            ],
            "findings": [],
            "sources": [],
            "checked_platforms": [
                {
                    "name": platform,
                    "checked": False,
                    "outcome": "NOT_RUN",
                    "note": "自检：该行按模板标识交由人工执行",
                }
                for platform in task["platforms"]
            ],
            "limitations": ["自检不进行真实网络调查"],
            "next_steps": ["由人工完成模板载明的测购、支付、物流或实物核验动作"],
        }
    actions = [
        {
            "platform": platform,
            "query": f'"{query_subject}" SELF-TEST {task["item_id"]} {platform}',
            "accessed_at": timestamp,
            "outcome": "NOT_FOUND",
            "note": "仅用于验证数据契约，不代表真实调查",
            "subject_role": subject_role,
            "seed_refs": seed_refs,
            "execution_mode": "ONLINE",
        }
        for platform in task["platforms"]
    ]
    return {
        "item_id": task["item_id"],
        "status": "NOT_FOUND",
        "completed_at": timestamp,
        "actions": actions,
        "findings": [],
        "sources": [],
        "checked_platforms": [
            {
                "name": platform,
                "checked": True,
                "outcome": "NOT_FOUND",
                "note": "仅用于验证数据契约",
            }
            for platform in task["platforms"]
        ],
        "searched_scope": "离线自检范围（不代表真实公开网络检索）",
        "limitations": ["自检不进行真实网络调查，结果不得作为案件事实使用"],
        "next_steps": [],
    }


def cmd_self_test(args) -> int:
    with tempfile.TemporaryDirectory(prefix="checklist-case-self-test-") as temp:
        case_dir = Path(temp) / "case"
        init_args = argparse.Namespace(
            rights_holder="自检权利人（非真实案件）",
            url="https://example.com/self-test",
            checklist=str(DEFAULT_TEMPLATE),
            output=str(case_dir),
        )
        cmd_init(init_args)
        _, paths, tasks = load_case(case_dir)
        seed_file = Path(temp) / "defendant_seed.json"
        write_json(
            seed_file,
            {
                "product_name": "自检被告商品（非真实案件）",
                "brand": "自检被告品牌",
                "source_url": "https://example.com/self-test",
                "captured_at": now_iso(),
            },
        )
        cmd_set_seed(argparse.Namespace(case_dir=str(case_dir), file=str(seed_file)))
        case, paths, tasks = load_case(case_dir)
        timestamp = now_iso()
        ordinary_task = next(task for task in tasks if task["item_id"] not in PLAINTIFF_REPUTATION_ITEMS and not task["manual_hint"])
        bad_record = self_test_record(ordinary_task, timestamp)
        for action in bad_record["actions"]:
            action["subject_role"] = "PLAINTIFF_REPUTATION"
            action["seed_refs"] = []
            action["query"] = '"自检权利人（非真实案件）"'
        plaintiff_only_rejected = False
        try:
            validate_result_record(bad_record, ordinary_task, case, add_defaults=False)
        except ChecklistError:
            plaintiff_only_rejected = True
        if not plaintiff_only_rejected:
            raise ChecklistError("自检失败：普通任务只有原告查询时未被拒绝")
        reputation_task = next(task for task in tasks if task["item_id"] in PLAINTIFF_REPUTATION_ITEMS and not task["manual_hint"])
        validate_result_record(self_test_record(reputation_task, timestamp), reputation_task, case, add_defaults=False)
        append_results(case_dir, [self_test_record(task, timestamp) for task in tasks])
        output = paths["output_dir"] / "自检_逐行调查_部分填充.docx"
        build_filled_docx(case_dir, output, require_all_results=True)
        validation = validate_output(case_dir, output, strict=True)
        if not validation["ok"]:
            raise ChecklistError("自检失败：" + "；".join(validation["errors"]))
        print(
            json.dumps(
                {
                    "ok": True,
                    "task_count": len(tasks),
                    "result_count": validation["result_count"],
                    "checks": [
                        "原模板SHA-256未变化",
                        "61行逐项结果可记录",
                        "原五列文字保留",
                        "方框仅替换为√或×",
                        "每行新增AI调查说明",
                        "结果日志哈希链连续",
                        "普通任务只有原告查询时拒绝登记",
                        "知名度任务允许PLAINTIFF_REPUTATION查询",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="按用户DOCX清单逐行登记调查结果，并以追加方式输出部分填充清单"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="用权利人和侵权链接初始化逐行调查案件")
    init_parser.add_argument("--rights-holder", required=True)
    init_parser.add_argument("--url", required=True)
    init_parser.add_argument("--checklist", help="可选；缺省使用Skill内置的用户修改版清单")
    init_parser.add_argument("--output", required=True)
    init_parser.set_defaults(func=cmd_init)

    seed_parser = subparsers.add_parser("set-seed", help="登记从疑似侵权页提取的被告商品检索种子")
    seed_parser.add_argument("--case-dir", required=True)
    seed_parser.add_argument("--file", required=True, help="含必填 product_name 的JSON文件")
    seed_parser.set_defaults(func=cmd_set_seed)

    tasks_parser = subparsers.add_parser("tasks", help="列出逐行任务和当前状态")
    tasks_parser.add_argument("--case-dir", required=True)
    tasks_parser.add_argument("--pending", action="store_true")
    tasks_parser.add_argument("--priority", choices=["P0", "P1", "P2", "P3"])
    tasks_parser.add_argument("--limit", type=int)
    tasks_parser.set_defaults(func=cmd_tasks)

    record_parser = subparsers.add_parser("record", help="追加一条或一批有来源约束的行级结果")
    record_parser.add_argument("--case-dir", required=True)
    group = record_parser.add_mutually_exclusive_group()
    group.add_argument("--file", help="JSON文件，可为单个对象或对象数组")
    group.add_argument("--json", help="内联JSON；未提供时从stdin读取")
    record_parser.set_defaults(func=cmd_record)

    fill_parser = subparsers.add_parser("fill", help="复制原模板、填√/×并追加AI调查说明列")
    fill_parser.add_argument("--case-dir", required=True)
    fill_parser.add_argument("--output")
    fill_parser.add_argument("--strict", action="store_true", help="要求61项全部有行级结果")
    fill_parser.set_defaults(func=cmd_fill)

    validate_parser = subparsers.add_parser("validate", help="验证不删原文、结果有来源和逐行留痕")
    validate_parser.add_argument("--case-dir", required=True)
    validate_parser.add_argument("--output")
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    self_test_parser = subparsers.add_parser("self-test", help="离线验证模板解析、回填和硬校验")
    self_test_parser.set_defaults(func=cmd_self_test)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ChecklistError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
