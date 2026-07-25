#!/usr/bin/env python3
"""Deterministic run-first queue for the 61-row heavy-case checklist.

This script never accesses the network. It compiles and dispatches action specs
for an Agent, then records the Agent's browser, MCP, search, or manual results.
"""

from __future__ import annotations

import urllib.parse
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA_VERSION = "1.0"
WAVE_ORDER = ["W0", "W1", "W2", "W3", "W4", "W5"]
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
ACTION_STATES = {
    "PLANNED",
    "WAITING_DEPENDENCY",
    "READY",
    "RUNNING",
    "WAITING_LOGIN",
    "WAITING_MANUAL",
    "RETRYABLE",
    "TERMINAL",
}
RESULT_STATUSES = {
    "COMPLETE_VERIFIED",
    "PARTIAL_VERIFIED",
    "LEAD_ONLY",
    "NOT_FOUND",
    "NEEDS_HUMAN",
    "NOT_APPLICABLE",
    "CONFLICT",
    "ERROR",
}
OUTCOMES = {
    "FOUND",
    "NOT_FOUND",
    "LOGIN_REQUIRED",
    "MANUAL_REQUIRED",
    "NOT_APPLICABLE",
    "ERROR",
}
CANONICAL_61 = (
    "1-1-1", "1-1-2", "1-1-3", "1-1-4", "1-1-5", "1-1-6", "1-1-7", "1-1-8",
    "1-2-1", "1-2-2", "1-2-3", "1-2-4", "1-2-5",
    "1-3-1", "1-3-2", "1-3-3", "1-3-4", "1-3-5", "1-3-6",
    "1-4-1", "1-4-2",
    "1-5-1", "1-5-2", "1-5-3", "1-5-4", "1-5-5",
    "2-1-1", "2-1-2",
    "2-2-1", "2-2-2", "2-2-3", "2-2-4", "2-2-5", "2-2-6", "2-2-7", "2-2-8",
    "2-3-1", "2-3-2", "2-3-3", "2-3-4", "2-3-5",
    "3-1-1", "3-1-2", "3-1-3", "3-1-4", "3-1-5", "3-1-6",
    "3-2-1", "3-2-2", "3-2-3", "3-2-4", "3-2-5", "3-2-6",
    "4-1", "4-2",
    "5-1", "5-2-1", "5-2-2", "5-2-3", "5-3-1", "5-3-2",
)
CANONICAL_SET = set(CANONICAL_61)
LEGACY_ID_RE = re.compile(r"^(?:B|T|Q)\d", re.IGNORECASE)
MATRIX_PATH = Path(__file__).resolve().parent.parent / "references" / "run-matrix-61.json"
MANUAL_TERMS = (
    "人工核查", "下单记录", "快递单号", "收款信息", "发货地址", "发货人",
    "权利人提供合同", "通知或警告信", "合同原件", "发票", "付款凭证",
    "专家", "问卷", "实物核验",
)
LOGIN_PLATFORMS = (
    "淘宝", "天猫", "京东", "拼多多", "1688", "抖音", "快手", "小红书",
    "微信", "视频号", "美团", "大众点评", "携程", "艺龙", "同程",
)
OFFICIAL_TERMS = (
    "国家", "政府", "法院", "裁判", "审判", "执行", "信用中国", "市场监督",
    "知识产权局", "WIPO", "海关", "统计局", "交易所", "巨潮", "公共资源",
    "药品监督", "认证认可", "标准信息", "生态环境", "公报", "行业协会",
)
PLATFORM_MCP_PROVIDERS = {
    "小红书": "xiaohongshu",
    "微博": "weibo",
}
PLATFORM_PAGE_VERIFIERS = {"chrome-devtools", "playwright"}
FORBIDDEN_TOOL_ROUTE = "agentkey"


class RunError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_load(path: Path) -> Any:
    if not path.is_file():
        raise RunError(f"缺少文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_jsonl_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        written = os.write(fd, data)
        if written != len(data):
            raise RunError(f"动作日志未完整写入：{written}/{len(data)}")
        os.fsync(fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def runtime_paths(run_dir: Path) -> dict[str, Path]:
    return {
        "state": run_dir / "run_state.json",
        "queue": run_dir / "action_queue.json",
        "log": run_dir / "action_runs.jsonl",
    }


def load_runtime(case_dir: Path, run_dir: Path) -> tuple[dict, dict, dict, dict[str, Path]]:
    paths = runtime_paths(run_dir)
    case = json_load(case_dir / "case.json")
    state = json_load(paths["state"])
    queue = json_load(paths["queue"])
    if state.get("case_id") != case.get("case_id") or queue.get("run_id") != state.get("run_id"):
        raise RunError("case、run_state 与 action_queue 标识不一致")
    return case, state, queue, paths


def save_runtime(state: dict, queue: dict, paths: dict[str, Path]) -> None:
    state["updated_at"] = now_iso()
    queue["updated_at"] = state["updated_at"]
    atomic_json(paths["queue"], queue)
    atomic_json(paths["state"], state)


def validate_authoritative_ids(tasks: list[dict], matrix_items: list[dict]) -> None:
    task_ids = [str(item.get("item_id") or "") for item in tasks]
    matrix_ids = [str(item.get("id") or "") for item in matrix_items]
    legacy = sorted(
        item_id for item_id in set(task_ids + matrix_ids)
        if LEGACY_ID_RE.match(item_id) or item_id == "1-1-1A"
    )
    if legacy:
        raise RunError("拒绝 legacy 任务编号：" + "、".join(legacy))
    for label, ids in (("row_tasks", task_ids), ("run_matrix", matrix_ids)):
        duplicates = sorted(item_id for item_id in set(ids) if ids.count(item_id) > 1)
        missing = sorted(CANONICAL_SET - set(ids))
        extra = sorted(set(ids) - CANONICAL_SET)
        if len(ids) != 61 or duplicates or missing or extra:
            raise RunError(
                f"{label} 必须精确等于权威61行；count={len(ids)}；"
                f"duplicates={duplicates}；missing={missing}；extra={extra}"
            )


def base_seed_list(case: dict, state: dict | None = None) -> list[dict]:
    seeds = case.get("defendant_seed", {}).get("seeds", [])
    output = [item for item in seeds if isinstance(item, dict) and item.get("id") and item.get("value")]
    if state:
        output.extend(
            item for item in state.get("discovered_seeds", [])
            if isinstance(item, dict) and item.get("id") and item.get("value")
        )
    deduped: dict[str, dict] = {}
    for seed in output:
        deduped[str(seed["id"])] = seed
    return list(deduped.values())


def pick_seeds(case: dict, profile: str, state: dict | None = None) -> list[dict]:
    seeds = base_seed_list(case, state)
    preferences = {
        "PRODUCT": ["PRODUCT_SHORT", "PRODUCT", "MODEL", "PLATFORM_SKU", "BRAND"],
        "ENTITY": ["PLATFORM_VENDOR_NAME", "BUSINESS_ENTITY", "OPERATOR", "STORE", "SHOP_ID", "BRAND"],
        "MIXED": ["PRODUCT_SHORT", "PLATFORM_VENDOR_NAME", "PRODUCT", "STORE", "MODEL", "BRAND"],
        "COMPARISON": ["PRODUCT_SHORT", "PLATFORM_VENDOR_NAME", "PRODUCT", "STORE", "BRAND"],
    }.get(profile, ["PRODUCT_SHORT", "PRODUCT", "PLATFORM_VENDOR_NAME", "STORE", "BRAND"])
    selected = []
    for kind in preferences:
        match = next((seed for seed in seeds if str(seed.get("kind", "")).upper() == kind), None)
        if match and match not in selected:
            selected.append(match)
        if len(selected) >= 3:
            break
    return selected or seeds[:1]


def requirements_met(requirements: list[str], case: dict, state: dict) -> bool:
    seeds = base_seed_list(case, state)
    kinds = {str(seed.get("kind", "")).upper() for seed in seeds}
    holder = str(case.get("rights_holder") or case.get("rights_holder", {}).get("raw_input") or "").strip()
    for requirement in requirements:
        if requirement == "PLAINTIFF" and not holder:
            return False
        if requirement == "DEFENDANT_ANY" and not seeds:
            return False
        if requirement == "PRODUCT_ANY" and not kinds.intersection(
            {"PRODUCT", "PRODUCT_SHORT", "MODEL", "PLATFORM_SKU", "BRAND", "VARIANT"}
        ):
            return False
        if requirement == "ENTITY_ANY" and not kinds.intersection(
            {"PLATFORM_VENDOR_NAME", "BUSINESS_ENTITY", "OPERATOR", "STORE", "SHOP_ID", "BRAND"}
        ):
            return False
    return True


def platform_mcp_provider(platform: str) -> str | None:
    return next(
        (provider for label, provider in PLATFORM_MCP_PROVIDERS.items() if label in platform),
        None,
    )


def classify_executor(platform: str, forced_manual: bool = False) -> tuple[str, str, str]:
    if forced_manual or any(term in platform for term in MANUAL_TERMS):
        return "MANUAL_HANDOFF", "USER_OR_COUNSEL", "MANUAL_ONLY"
    platform_provider = platform_mcp_provider(platform)
    if platform_provider:
        return "MCP_THEN_BROWSER", platform_provider, "QR_ONLY_PARK_ON_LOGIN"
    if "企查查" in platform:
        return "MCP", "QCC_MCP", "PUBLIC_FIRST"
    if "AI系统" in platform or "多个AI" in platform:
        return "AGENT_REASONING", "MODEL_COMPARISON", "NO_LOGIN"
    if platform == "新闻" or "媒体" in platform:
        return "WEB_SEARCH", "PUBLIC_SEARCH", "PUBLIC_FIRST"
    if any(term in platform for term in OFFICIAL_TERMS):
        return "BROWSER", "OFFICIAL_DATABASE", "PUBLIC_FIRST"
    if any(term in platform for term in LOGIN_PLATFORMS):
        return "BROWSER", "IN_APP_BROWSER", "PARK_ON_LOGIN"
    return "BROWSER", "PUBLIC_WEB", "PARK_ON_LOGIN"


def primary_role(required_subjects: list[str], index: int, manual: bool) -> str:
    if manual and "MANUAL" in required_subjects:
        return "MANUAL"
    roles = [role for role in required_subjects if role != "MANUAL"]
    if not roles:
        return "MANUAL" if manual else "DEFENDANT"
    return roles[min(index, len(roles) - 1)]


def query_for(case: dict, profile: str, platform: str, role: str, seeds: list[dict]) -> tuple[str, list[str]]:
    holder_raw = case.get("rights_holder")
    holder = holder_raw.get("raw_input", "") if isinstance(holder_raw, dict) else str(holder_raw or "")
    values: list[str] = []
    refs: list[str] = []
    if role in {"PLAINTIFF_REPUTATION", "RIGHTS_BASIS"}:
        values.append(holder)
        refs.append("P-RIGHTS-HOLDER-001")
    else:
        values.extend(str(seed.get("value") or "") for seed in seeds)
        refs.extend(str(seed.get("id") or "") for seed in seeds)
        if role == "COMPARISON":
            values.append(holder)
            refs.append("P-RIGHTS-HOLDER-001")
    values = [value for value in values if value]
    terms = " ".join(f'"{value}"' for value in values[:3])
    query = f"{terms} {platform}".strip()
    return query, [ref for ref in refs if ref]


def build_action(
    *,
    case: dict,
    row_task: dict,
    spec: dict,
    platform: str,
    index: int,
    ordinal: int,
    manual: bool,
    supplemental: bool = False,
) -> dict:
    executor, provider, login_policy = classify_executor(platform, forced_manual=manual)
    role = primary_role(spec.get("required_subjects", ["DEFENDANT"]), index, manual)
    seeds = pick_seeds(case, spec.get("query_profile", "MIXED"))
    query, seed_refs = query_for(case, spec.get("query_profile", "MIXED"), platform, role, seeds)
    objective = str(row_task.get("original_cells", {}).get("关注什么") or "").strip()
    action_id = f"{row_task['item_id']}-A{ordinal:03d}"
    initial_state = "WAITING_MANUAL" if manual else "WAITING_DEPENDENCY"
    initial_result = "NEEDS_HUMAN" if manual else None
    expected_artifacts = ["raw_result"]
    if executor in {"BROWSER", "MCP", "MCP_THEN_BROWSER"}:
        expected_artifacts.append("screenshot")
    if executor == "MCP_THEN_BROWSER":
        expected_artifacts.extend(["mcp_raw_result", "canonical_page"])
    platform_provider = platform_mcp_provider(platform)
    execution_plan = []
    if platform_provider:
        execution_plan = [
            {"step": "DISCOVERY", "tool": platform_provider, "mode": "READ_ONLY"},
            {"step": "VERIFY", "tool": "chrome-devtools", "mode": "CANONICAL_PAGE"},
            {
                "step": "PUBLIC_FALLBACK",
                "tool": "playwright",
                "mode": "PUBLIC_PAGE_ONLY_NO_LOGIN",
            },
        ]
    return {
        "action_id": action_id,
        "row_id": row_task["item_id"],
        "row_key": row_task["row_key"],
        "ordinal": ordinal,
        "wave": spec["wave"],
        "priority": row_task.get("priority", "P3"),
        "execution_class": spec["execution_class"],
        "execution_state": initial_state,
        "result_status": initial_result,
        "outcome": "MANUAL_REQUIRED" if manual else None,
        "attempt": 0,
        "max_attempts": 3,
        "started_at": None,
        "finished_at": None,
        "park_reason": "矩阵标记为人工或禁止自动处理" if manual else None,
        "seed_requirements": spec.get("seed_requirements", []),
        "depends_on_all": spec.get("depends_on_all", []),
        "depends_on_any": spec.get("depends_on_any", []),
        "public_first": not manual,
        "supplemental": supplemental,
        "action_spec": {
            "wave": spec["wave"],
            "executor": executor,
            "provider": provider,
            "platform": platform,
            "subject_role": role,
            "required_subjects": spec.get("required_subjects", []),
            "seed_refs": seed_refs,
            "query": query,
            "url": case.get("infringement_url", "") if platform in {"京东", "疑似侵权商品所在平台"} else "",
            "objective": objective,
            "login_policy": login_policy,
            "expected_artifacts": expected_artifacts,
            "execution_plan": execution_plan,
            "forbidden_routes": ["AgentKey"],
            "required_verification": (
                {
                    "discovery_tool": platform_provider,
                    "discovery_mode": "READ_ONLY",
                    "primary_page_tool": "chrome-devtools",
                    "public_fallback_tool": "playwright",
                    "canonical_url_required": True,
                    "agent_screenshot_required": True,
                    "user_login_method": "QR_SCAN_IN_CONTROLLED_BROWSER",
                }
                if platform_provider
                else None
            ),
            "completion_policy": {
                "found": (
                    "提交平台MCP原始结果、Chrome核验的规范页URL和AI截图"
                    if platform_provider
                    else "提交真实来源和原始文件/截图引用"
                ),
                "not_found": "仅在本action指定平台和查询范围实际执行完后提交",
                "error": "先按provider降级或重试；LOGIN_REQUIRED与MANUAL_REQUIRED只park",
            },
        },
        "findings": [],
        "sources": [],
        "raw_refs": [],
        "screenshot_refs": [],
        "limitations": [],
        "next_steps": [],
        "last_commit_id": None,
    }


def dependencies_met(action: dict, queue: dict) -> bool:
    rows = {row["row_id"]: row for row in queue["rows"]}
    all_ids = action.get("depends_on_all", [])
    any_ids = action.get("depends_on_any", [])
    if any(rows.get(row_id, {}).get("execution_state") != "TERMINAL" for row_id in all_ids):
        return False
    if any_ids and not any(rows.get(row_id, {}).get("execution_state") == "TERMINAL" for row_id in any_ids):
        return False
    return True


def comparison_evidence_met(action: dict, case: dict, state: dict, queue: dict) -> bool:
    if action.get("action_spec", {}).get("subject_role") != "COMPARISON":
        return True
    for candidate in queue.get("actions", []):
        if candidate.get("row_id") != action.get("row_id"):
            continue
        if candidate.get("action_spec", {}).get("subject_role") != "DEFENDANT":
            continue
        if (
            candidate.get("execution_state") == "TERMINAL"
            and candidate.get("outcome") == "FOUND"
            and (candidate.get("sources") or candidate.get("raw_refs"))
        ):
            return True
    referenced = set(action.get("action_spec", {}).get("seed_refs", []))
    return any(
        str(seed.get("id") or "") in referenced
        and str(seed.get("source_ref") or "").strip()
        for seed in base_seed_list(case, state)
    )


def normalize_searched_scope(value: Any, action: dict) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RunError("NOT_FOUND 必须提供结构化 searched_scope 对象")
    required = ("provider", "platform", "query", "executed_at")
    scope = {key: str(value.get(key) or "").strip() for key in required}
    missing = [key for key, item in scope.items() if not item]
    if missing:
        raise RunError("NOT_FOUND searched_scope 缺少：" + "、".join(missing))
    expected_provider = str(action.get("action_spec", {}).get("provider") or "").strip()
    expected_platform = str(action.get("action_spec", {}).get("platform") or "").strip()
    if expected_provider and scope["provider"] != expected_provider:
        raise RunError(
            f"NOT_FOUND provider 与动作不一致：{scope['provider']} != {expected_provider}"
        )
    if expected_platform and not platform_matches(scope["platform"], expected_platform):
        raise RunError(
            f"NOT_FOUND platform 与动作不一致：{scope['platform']} != {expected_platform}"
        )
    try:
        executed_at = datetime.fromisoformat(scope["executed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunError("NOT_FOUND searched_scope.executed_at 必须是 ISO 8601 时间") from exc
    if executed_at.tzinfo is None:
        raise RunError("NOT_FOUND searched_scope.executed_at 必须包含时区")
    return scope


def require_not_found_evidence(payload: dict, action: dict) -> tuple[list[str], dict[str, str]]:
    raw_value = payload.get("raw_refs")
    if not isinstance(raw_value, list):
        raise RunError("NOT_FOUND 必须提供非空 raw_refs 数组")
    raw_refs = [str(ref).strip() for ref in raw_value if str(ref).strip()]
    if not raw_refs:
        raise RunError("NOT_FOUND 必须提供至少一个实际检索原始记录 raw_ref")
    scope = normalize_searched_scope(payload.get("searched_scope"), action)
    return list(dict.fromkeys(raw_refs)), scope


def aggregate_result(actions: list[dict], execution_state: str) -> str | None:
    statuses = [action.get("result_status") for action in actions if action.get("result_status")]
    if not statuses:
        return "NEEDS_HUMAN" if execution_state == "WAITING_MANUAL" else None
    if execution_state != "TERMINAL":
        if any(status in {"COMPLETE_VERIFIED", "PARTIAL_VERIFIED"} for status in statuses):
            return "PARTIAL_VERIFIED"
        if "LEAD_ONLY" in statuses:
            return "LEAD_ONLY"
        if "NEEDS_HUMAN" in statuses:
            return "NEEDS_HUMAN"
        return statuses[-1]
    if all(status == "NOT_FOUND" for status in statuses):
        return "NOT_FOUND"
    if all(status == "NOT_APPLICABLE" for status in statuses):
        return "NOT_APPLICABLE"
    if all(status == "ERROR" for status in statuses):
        return "ERROR"
    if all(status == "COMPLETE_VERIFIED" for status in statuses):
        return "COMPLETE_VERIFIED"
    if any(status in {"COMPLETE_VERIFIED", "PARTIAL_VERIFIED"} for status in statuses):
        return "PARTIAL_VERIFIED"
    if "LEAD_ONLY" in statuses:
        return "LEAD_ONLY"
    if "NEEDS_HUMAN" in statuses:
        return "NEEDS_HUMAN"
    return statuses[-1]


def aggregate_rows(queue: dict) -> None:
    actions_by_row: dict[str, list[dict]] = {}
    for action in queue["actions"]:
        actions_by_row.setdefault(action["row_id"], []).append(action)
    for row in queue["rows"]:
        actions = actions_by_row.get(row["row_id"], [])
        states = {action["execution_state"] for action in actions}
        if "RUNNING" in states:
            execution = "RUNNING"
        elif states.intersection({"READY", "RETRYABLE"}):
            execution = "READY"
        elif "WAITING_LOGIN" in states:
            execution = "WAITING_LOGIN"
        elif "WAITING_MANUAL" in states:
            execution = "WAITING_MANUAL"
        elif "WAITING_DEPENDENCY" in states:
            execution = "WAITING_DEPENDENCY"
        elif actions and states == {"TERMINAL"}:
            execution = "TERMINAL"
        else:
            execution = "PLANNED"
        row["execution_state"] = execution
        row["result_status"] = aggregate_result(actions, execution)
        row["action_counts"] = dict(Counter(action["execution_state"] for action in actions))


def refresh_runtime(case: dict, state: dict, queue: dict) -> None:
    for _ in range(3):
        aggregate_rows(queue)
        changed = False
        for action in queue["actions"]:
            if action["execution_state"] != "WAITING_DEPENDENCY":
                continue
            if (
                requirements_met(action.get("seed_requirements", []), case, state)
                and dependencies_met(action, queue)
                and comparison_evidence_met(action, case, state, queue)
            ):
                action["execution_state"] = "READY"
                action["park_reason"] = None
                changed = True
        if not changed:
            break
    aggregate_rows(queue)
    action_counts = Counter(action["execution_state"] for action in queue["actions"])
    result_counts = Counter(
        row["result_status"] for row in queue["rows"] if row.get("result_status")
    )
    wave_counts = Counter(action["wave"] for action in queue["actions"])
    state["counts"] = {
        "actions": len(queue["actions"]),
        "rows": len(queue["rows"]),
        "by_execution_state": dict(sorted(action_counts.items())),
        "by_result_status": dict(sorted(result_counts.items())),
        "by_wave": {wave: wave_counts.get(wave, 0) for wave in WAVE_ORDER},
    }
    ready_count = action_counts.get("READY", 0) + action_counts.get("RETRYABLE", 0)
    running_count = action_counts.get("RUNNING", 0)
    if running_count:
        state["case_state"] = "RUNNING"
        state["execution_state"] = "RUNNING"
        state["pause_reason"] = None
    elif ready_count:
        state["case_state"] = "PLANNED" if state.get("last_sequence", 0) == 0 else "RUNNING"
        state["execution_state"] = "READY"
        state["pause_reason"] = None
    elif action_counts.get("WAITING_LOGIN", 0):
        state["case_state"] = "WAITING_LOGIN"
        state["execution_state"] = "WAITING_LOGIN"
        state["pause_reason"] = "READY队列已耗尽，存在需用户完成登录的动作"
    elif action_counts.get("WAITING_MANUAL", 0):
        state["case_state"] = "WAITING_MANUAL"
        state["execution_state"] = "WAITING_MANUAL"
        state["pause_reason"] = "READY队列已耗尽，存在人工或禁止自动处理动作"
    else:
        state["case_state"] = "QUIESCENT"
        state["execution_state"] = "QUIESCENT"
        state["pause_reason"] = None
        state["quiesced_at"] = state.get("quiesced_at") or now_iso()
    row_statuses = [row.get("result_status") for row in queue["rows"] if row.get("result_status")]
    if len(row_statuses) == 61 and all(status == "COMPLETE_VERIFIED" for status in row_statuses):
        state["result_status"] = "COMPLETE_VERIFIED"
    elif row_statuses:
        state["result_status"] = "PARTIAL_VERIFIED"
    else:
        state["result_status"] = None


def make_event(
    state: dict,
    action: dict,
    *,
    event_type: str,
    before: str,
    after: str,
    outcome: str | None,
    payload: dict | None = None,
) -> dict:
    payload = payload or {}
    sequence = int(state.get("last_sequence", 0)) + 1
    state["last_sequence"] = sequence
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    commit_id = hashlib.sha256(
        f"{state['run_id']}|{action['action_id']}|{action.get('attempt', 0)}|{event_type}|{canonical}".encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "case_id": state["case_id"],
        "sequence": sequence,
        "event_type": event_type,
        "commit_id": commit_id,
        "action_id": action["action_id"],
        "row_id": action["row_id"],
        "attempt": int(action.get("attempt", 0)),
        "recorded_at": now_iso(),
        "started_at": action.get("started_at"),
        "finished_at": action.get("finished_at"),
        "execution_before": before,
        "execution_after": after,
        "outcome": outcome,
        "result_status": action.get("result_status"),
        "action_spec": action["action_spec"],
        "findings": payload.get("findings", []),
        "sources": payload.get("sources", []),
        "raw_refs": payload.get("raw_refs", []),
        "screenshot_refs": payload.get("screenshot_refs", []),
        "limitations": payload.get("limitations", []),
        "next_steps": payload.get("next_steps", []),
        "seed_updates": payload.get("seed_updates", []),
        "searched_scope": payload.get("searched_scope"),
        "login_resume": payload.get("login_resume"),
        "error": payload.get("error"),
    }


def find_action(queue: dict, action_id: str) -> dict:
    action = next((item for item in queue["actions"] if item["action_id"] == action_id), None)
    if not action:
        raise RunError(f"未知 action_id：{action_id}")
    return action


def command_summary(state: dict, queue: dict, command: str) -> dict:
    return {
        "ok": True,
        "command": command,
        "run_id": state["run_id"],
        "case_id": state["case_id"],
        "case_state": state["case_state"],
        "execution_state": state["execution_state"],
        "result_status": state.get("result_status"),
        "active_action_id": state.get("active_action_id"),
        "pause_reason": state.get("pause_reason"),
        "counts": state["counts"],
        "row_execution_counts": dict(Counter(row["execution_state"] for row in queue["rows"])),
        "row_result_counts": dict(Counter(
            row["result_status"] for row in queue["rows"] if row.get("result_status")
        )),
    }


def cmd_compile(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    paths = runtime_paths(run_dir)
    occupied = [str(path) for path in paths.values() if path.exists()]
    if occupied:
        raise RunError("运行目录已有状态文件，拒绝覆盖：" + "、".join(occupied))
    case = json_load(case_dir / "case.json")
    task_doc = json_load(case_dir / "row_tasks.json")
    matrix = json_load(Path(args.matrix).expanduser().resolve() if args.matrix else MATRIX_PATH)
    tasks = task_doc.get("tasks", [])
    matrix_items = matrix.get("items", [])
    validate_authoritative_ids(tasks, matrix_items)
    matrix_by_id = {item["id"]: item for item in matrix_items}
    run_id = "RUN-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(
        f"{case.get('case_id')}|{run_dir}".encode("utf-8")
    ).hexdigest()[:8]
    created = now_iso()
    state = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case.get("case_id", ""),
        "case_dir": str(case_dir),
        "run_dir": str(run_dir),
        "case_state": "CREATED",
        "execution_state": "PLANNED",
        "result_status": None,
        "wave_order": WAVE_ORDER,
        "active_action_id": None,
        "pause_reason": None,
        "created_at": created,
        "started_at": None,
        "updated_at": created,
        "quiesced_at": None,
        "last_sequence": 0,
        "counts": {
            "actions": 0,
            "rows": 61,
            "by_execution_state": {},
            "by_result_status": {},
            "by_wave": {},
        },
        "discovered_seeds": [],
    }
    rows = []
    actions = []
    seed_ready = bool(base_seed_list(case)) and case.get("defendant_seed", {}).get("status") == "READY"
    seed_action = {
        "action_id": "CASE-SEED-A001",
        "row_id": "__SEED__",
        "row_key": "__SEED__",
        "ordinal": 0,
        "wave": "W0",
        "priority": "P0",
        "execution_class": "ONLINE",
        "execution_state": "TERMINAL" if seed_ready else "READY",
        "result_status": "COMPLETE_VERIFIED" if seed_ready else None,
        "outcome": "FOUND" if seed_ready else None,
        "attempt": 0,
        "max_attempts": 3,
        "started_at": None,
        "finished_at": created if seed_ready else None,
        "park_reason": None,
        "seed_requirements": [],
        "depends_on_all": [],
        "depends_on_any": [],
        "public_first": True,
        "supplemental": True,
        "action_spec": {
            "wave": "W0",
            "executor": "BROWSER",
            "provider": "IN_APP_BROWSER",
            "platform": "疑似侵权种子链接",
            "subject_role": "DEFENDANT",
            "required_subjects": ["DEFENDANT"],
            "seed_refs": [seed.get("id") for seed in base_seed_list(case)],
            "query": "",
            "url": case.get("infringement_url", ""),
            "objective": "固定疑似侵权页面并提取被告商品、SKU、店铺、平台展示供应商及主体种子",
            "login_policy": "PARK_ON_LOGIN",
            "expected_artifacts": ["raw_result", "screenshot", "seed_updates"],
            "completion_policy": {"found": "必须提交字段级seed_updates和页面证据引用"},
        },
        "findings": [],
        "sources": [],
        "raw_refs": [],
        "screenshot_refs": [],
        "limitations": [],
        "next_steps": [],
        "searched_scope": None,
        "last_commit_id": None,
    }
    actions.append(seed_action)
    for row_task in tasks:
        spec = matrix_by_id[row_task["item_id"]]
        action_ids = []
        platforms = list(row_task.get("platforms", []))
        ordinal = 1
        manual_only = spec["execution_class"] in {"MANUAL_ONLY", "PROHIBITED_AUTO"}
        for index, platform in enumerate(platforms):
            platform_manual = manual_only or any(term in platform for term in MANUAL_TERMS)
            action = build_action(
                case=case,
                row_task=row_task,
                spec=spec,
                platform=platform,
                index=index,
                ordinal=ordinal,
                manual=platform_manual,
            )
            actions.append(action)
            action_ids.append(action["action_id"])
            ordinal += 1
        if spec.get("qcc") and not any("企查查" in platform for platform in platforms):
            action = build_action(
                case=case,
                row_task=row_task,
                spec=spec,
                platform="企查查MCP",
                index=0,
                ordinal=ordinal,
                manual=False,
                supplemental=True,
            )
            actions.append(action)
            action_ids.append(action["action_id"])
            ordinal += 1
        if spec.get("manual_followup"):
            action = build_action(
                case=case,
                row_task=row_task,
                spec=spec,
                platform="人工补充材料",
                index=len(platforms),
                ordinal=ordinal,
                manual=True,
                supplemental=True,
            )
            action["action_spec"]["objective"] = spec["manual_followup"]
            action["next_steps"] = [spec["manual_followup"]]
            actions.append(action)
            action_ids.append(action["action_id"])
        rows.append({
            "row_id": row_task["item_id"],
            "row_key": row_task["row_key"],
            "priority": row_task.get("priority", "P3"),
            "wave": spec["wave"],
            "execution_class": spec["execution_class"],
            "required_subjects": spec.get("required_subjects", []),
            "execution_state": "PLANNED",
            "result_status": None,
            "action_ids": action_ids,
            "action_counts": {},
        })
    queue = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case.get("case_id", ""),
        "matrix_path": str(Path(args.matrix).expanduser().resolve() if args.matrix else MATRIX_PATH),
        "matrix_schema_version": matrix.get("schema_version"),
        "authoritative_task_count": 61,
        "created_at": created,
        "updated_at": created,
        "rows": rows,
        "actions": actions,
    }
    refresh_runtime(case, state, queue)
    run_dir.mkdir(parents=True, exist_ok=True)
    paths["log"].touch(exist_ok=False)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "compile")
    output["run_dir"] = str(run_dir)
    output["matrix_task_count"] = len(matrix_items)
    output["case_task_count"] = len(tasks)
    emit(output)
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    refresh_runtime(case, state, queue)
    if state.get("active_action_id"):
        active = find_action(queue, state["active_action_id"])
        output = command_summary(state, queue, "next")
        output["action"] = active
        output["already_running"] = True
        emit(output)
        return 0
    candidates = [
        action for action in queue["actions"]
        if action["execution_state"] in {"READY", "RETRYABLE"}
    ]
    if not candidates:
        save_runtime(state, queue, paths)
        output = command_summary(state, queue, "next")
        output["action"] = None
        emit(output)
        return 0
    candidates.sort(key=lambda action: (
        WAVE_ORDER.index(action["wave"]),
        PRIORITY_ORDER.get(action.get("priority", "P3"), 9),
        0 if action.get("public_first") else 1,
        action.get("row_id", ""),
        action.get("ordinal", 0),
    ))
    action = candidates[0]
    before = action["execution_state"]
    action["execution_state"] = "RUNNING"
    action["attempt"] = int(action.get("attempt", 0)) + 1
    action["started_at"] = now_iso()
    action["finished_at"] = None
    state["active_action_id"] = action["action_id"]
    state["started_at"] = state.get("started_at") or action["started_at"]
    event = make_event(
        state,
        action,
        event_type="DISPATCH",
        before=before,
        after="RUNNING",
        outcome=None,
    )
    append_jsonl_atomic(paths["log"], event)
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "next")
    output["action"] = action
    output["already_running"] = False
    output["agent_instruction"] = (
        "严格调用 action.action_spec 指定的 executor/provider 和 execution_plan；"
        "禁止AgentKey。小红书/微博先只读MCP发现，再用chrome-devtools核验规范页并由AI截图，"
        "playwright仅限无需登录的公开页。登录只让用户扫描当前受控浏览器二维码，绝不让用户截图。"
        "完成后用 commit 原子提交结果。"
    )
    emit(output)
    return 0


def read_commit_payload(args: argparse.Namespace) -> dict:
    if args.file:
        value = json_load(Path(args.file).expanduser().resolve())
    elif args.json:
        value = json.loads(args.json)
    else:
        value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise RunError("commit payload 必须是JSON对象")
    return value


def reject_agentkey_route(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    compact = re.sub(r"[^a-z0-9]+", "", serialized)
    if FORBIDDEN_TOOL_ROUTE in compact:
        raise RunError("禁止使用AgentKey或任何AgentKey后端")


def normalize_verified_canonical_url(value: Any, platform: str) -> str:
    raw = str(value or "").strip()
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError as exc:
        raise RunError("canonical_url 不是有效URL") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise RunError("canonical_url 必须是HTTP(S)规范页")
    host = parts.hostname.lower()
    path = parts.path or "/"
    if "小红书" in platform:
        if not host.endswith("xiaohongshu.com"):
            raise RunError("小红书规范页必须位于xiaohongshu.com")
        if "/search_result" in path or not any(
            marker in path for marker in ("/explore/", "/discovery/item/", "/user/profile/")
        ):
            raise RunError("小红书链接必须是账号、笔记或内容规范页，不能是搜索页")
    if "微博" in platform:
        if host == "s.weibo.com" or not (
            host == "weibo.com"
            or host.endswith(".weibo.com")
            or host == "m.weibo.cn"
            or host.endswith(".weibo.cn")
        ):
            raise RunError("微博规范页必须位于weibo.com或m.weibo.cn且不能是搜索页")
        if "/search" in path.lower() or path == "/":
            raise RunError("微博链接必须是账号或帖子规范页，不能是搜索入口")
    filtered_query = [
        (key, item)
        for key, item in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"spm", "source", "share", "share_source", "track_id"}
    ]
    return urllib.parse.urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc,
            path,
            urllib.parse.urlencode(filtered_query),
            "",
        )
    )


def validate_platform_execution(payload: dict, action: dict, outcome: str) -> None:
    reject_agentkey_route(payload)
    executor = str(action.get("action_spec", {}).get("executor") or "")
    if executor not in {"MANUAL_HANDOFF", "AGENT_REASONING"} and outcome not in {
        "LOGIN_REQUIRED",
        "MANUAL_REQUIRED",
    }:
        tool_route = payload.get("tool_route")
        trace = payload.get("execution_trace")
        if not str(tool_route or "").strip() and not isinstance(trace, dict):
            raise RunError("自动动作commit必须记录tool_route或execution_trace，且不得使用AgentKey")

    platform = str(action.get("action_spec", {}).get("platform") or "")
    expected_mcp = platform_mcp_provider(platform)
    if not expected_mcp or outcome not in {"FOUND", "NOT_FOUND"}:
        return
    trace = payload.get("execution_trace")
    if not isinstance(trace, dict):
        raise RunError("小红书/微博结果必须提供execution_trace")
    discovery = trace.get("discovery")
    if not isinstance(discovery, dict):
        raise RunError("小红书/微博结果缺少只读平台MCP discovery记录")
    if str(discovery.get("tool") or "") != expected_mcp:
        raise RunError(f"平台MCP必须为{expected_mcp}")
    if str(discovery.get("mode") or "").upper() != "READ_ONLY":
        raise RunError("小红书/微博MCP必须以READ_ONLY模式执行")
    if not str(discovery.get("raw_ref") or "").strip():
        raise RunError("平台MCP discovery必须提供raw_ref")
    if outcome == "NOT_FOUND":
        return

    verification = trace.get("verification")
    if not isinstance(verification, dict):
        raise RunError("FOUND必须提供Chrome/Playwright规范页核验记录")
    verification_tool = str(verification.get("tool") or "")
    if verification_tool not in PLATFORM_PAGE_VERIFIERS:
        raise RunError("页面核验工具只能是chrome-devtools或playwright")
    if verification_tool == "playwright" and (
        verification.get("public_page") is not True
        or verification.get("login_state_used") is True
    ):
        raise RunError("playwright仅可核验无需登录的公开页")
    if verification.get("page_verified") is not True:
        raise RunError("FOUND必须标记page_verified=true")
    if str(verification.get("capture_actor") or "").upper() != "AGENT":
        raise RunError("页面截图必须由AI通过浏览器生成，不接受用户截图")
    verified_at = str(verification.get("verified_at") or "").strip()
    if not verified_at:
        raise RunError("页面核验缺少verified_at")
    try:
        verified_time = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunError("verified_at必须是ISO 8601时间") from exc
    if verified_time.tzinfo is None:
        raise RunError("verified_at必须包含时区")
    canonical_url = normalize_verified_canonical_url(
        verification.get("canonical_url") or verification.get("final_url"),
        platform,
    )
    screenshot_ref = str(verification.get("screenshot_ref") or "").strip()
    screenshot_refs = [
        str(ref).strip() for ref in payload.get("screenshot_refs", []) if str(ref).strip()
    ]
    if not screenshot_ref or screenshot_ref not in screenshot_refs:
        raise RunError("FOUND必须提交与核验记录一致的AI截图引用")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not any(isinstance(source, dict) for source in sources):
        raise RunError("FOUND必须提供至少一个结构化来源")
    for source in sources:
        if not isinstance(source, dict):
            continue
        source["canonical_url"] = canonical_url
        source["page_verified"] = True
        source["page_verified_at"] = verified_at
        source["verification_tool"] = verification_tool
    payload["canonical_url"] = canonical_url
    payload["page_verified"] = True
    payload["page_verified_at"] = verified_at
    payload["verification_tool"] = verification_tool


def cmd_commit(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    payload = read_commit_payload(args)
    action_id = str(payload.get("action_id") or "")
    outcome = str(payload.get("outcome") or "").upper()
    if outcome not in OUTCOMES:
        raise RunError("outcome 必须为 FOUND/NOT_FOUND/LOGIN_REQUIRED/MANUAL_REQUIRED/NOT_APPLICABLE/ERROR")
    action = find_action(queue, action_id)
    if action["execution_state"] != "RUNNING":
        raise RunError(f"{action_id} 当前不是RUNNING，不能commit：{action['execution_state']}")
    validate_platform_execution(payload, action, outcome)
    result_status = payload.get("result_status")
    if result_status is not None and result_status not in RESULT_STATUSES:
        raise RunError(f"无效 result_status：{result_status}")
    if outcome == "NOT_FOUND":
        raw_refs, searched_scope = require_not_found_evidence(payload, action)
        payload["raw_refs"] = raw_refs
        payload["searched_scope"] = searched_scope
    before = action["execution_state"]
    action["finished_at"] = now_iso()
    action["outcome"] = outcome
    if outcome == "FOUND":
        action["execution_state"] = "TERMINAL"
        action["result_status"] = result_status or (
            "COMPLETE_VERIFIED" if action["row_id"] == "__SEED__" else "LEAD_ONLY"
        )
    elif outcome == "NOT_FOUND":
        action["execution_state"] = "TERMINAL"
        action["result_status"] = "NOT_FOUND"
    elif outcome == "NOT_APPLICABLE":
        action["execution_state"] = "TERMINAL"
        action["result_status"] = "NOT_APPLICABLE"
    elif outcome == "LOGIN_REQUIRED":
        action["execution_state"] = "WAITING_LOGIN"
        action["result_status"] = None
        action["park_reason"] = str(payload.get("note") or "平台要求用户登录")
    elif outcome == "MANUAL_REQUIRED":
        action["execution_state"] = "WAITING_MANUAL"
        action["result_status"] = "NEEDS_HUMAN"
        action["park_reason"] = str(payload.get("note") or "需要人工、律师或线下材料")
    else:
        error = payload.get("error") or {}
        retryable = bool(error.get("retryable", payload.get("retryable", False)))
        if retryable and int(action.get("attempt", 0)) < int(action.get("max_attempts", 3)):
            action["execution_state"] = "RETRYABLE"
            action["result_status"] = None
        else:
            action["execution_state"] = "TERMINAL"
            action["result_status"] = "ERROR"
    for field in ("findings", "sources", "raw_refs", "screenshot_refs", "limitations", "next_steps"):
        value = payload.get(field, [])
        if not isinstance(value, list):
            raise RunError(f"{field} 必须是数组")
        action[field] = value
    for field in (
        "tool_route",
        "execution_trace",
        "canonical_url",
        "page_verified",
        "page_verified_at",
        "verification_tool",
    ):
        if field in payload:
            action[field] = payload[field]
    if "searched_scope" in payload:
        action["searched_scope"] = payload["searched_scope"]
    seed_updates = payload.get("seed_updates", [])
    if not isinstance(seed_updates, list):
        raise RunError("seed_updates 必须是数组")
    existing_ids = {seed.get("id") for seed in state.get("discovered_seeds", [])}
    for seed in seed_updates:
        if not isinstance(seed, dict) or not seed.get("id") or not seed.get("kind") or not seed.get("value"):
            raise RunError("每个 seed_update 必须含 id/kind/value")
        if seed["id"] not in existing_ids:
            state["discovered_seeds"].append({
                "id": str(seed["id"]),
                "kind": str(seed["kind"]),
                "value": str(seed["value"]),
                "source_ref": str(seed.get("source_ref") or ""),
            })
            existing_ids.add(seed["id"])
    event = make_event(
        state,
        action,
        event_type="COMMIT",
        before=before,
        after=action["execution_state"],
        outcome=outcome,
        payload=payload,
    )
    action["last_commit_id"] = event["commit_id"]
    append_jsonl_atomic(paths["log"], event)
    state["active_action_id"] = None
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "commit")
    output["committed_action"] = {
        "action_id": action_id,
        "execution_state": action["execution_state"],
        "result_status": action["result_status"],
        "outcome": outcome,
        "commit_id": event["commit_id"],
    }
    emit(output)
    return 0


def normalize_match_text(value: Any) -> str:
    return re.sub(r"[\s:/_.?&=+\-]+", "", str(value or "")).casefold()


def platform_aliases(platform: str) -> list[str]:
    normalized = normalize_match_text(platform)
    aliases = [normalized]
    known = {
        "企查查": ["企查查", "qcc"],
        "京东": ["京东", "jdcom", "itemjd"],
        "淘宝": ["淘宝", "taobao"],
        "天猫": ["天猫", "tmall"],
        "拼多多": ["拼多多", "pinduoduo"],
        "1688": ["1688"],
        "抖音": ["抖音", "douyin"],
        "快手": ["快手", "kuaishou"],
        "小红书": ["小红书", "xiaohongshu"],
        "国家企业信用信息公示系统": ["国家企业信用信息公示", "gsxt"],
        "信用中国": ["信用中国", "creditchina"],
        "中国裁判文书网": ["中国裁判文书", "wenshu"],
        "人民法院案例库": ["人民法院案例库", "rmfyalk"],
        "中国执行信息公开网": ["中国执行信息公开", "zxgk"],
        "国家知识产权局": ["国家知识产权局", "cnipa"],
        "WIPO": ["wipo"],
        "Google Patents": ["googlepatents", "patentsgoogle"],
        "巨潮资讯网": ["巨潮资讯", "cninfo"],
    }
    for label, values in known.items():
        if label.casefold() in platform.casefold():
            aliases.extend(normalize_match_text(value) for value in values)
    trimmed = normalized
    for suffix in ("官方网站", "官网", "平台", "系统", "旗舰店", "mcp", "网"):
        suffix_normalized = normalize_match_text(suffix)
        if trimmed.endswith(suffix_normalized) and len(trimmed) > len(suffix_normalized) + 1:
            trimmed = trimmed[: -len(suffix_normalized)]
    if len(trimmed) >= 2:
        aliases.append(trimmed)
    return list(dict.fromkeys(alias for alias in aliases if alias))


def platform_matches(left: str, right: str) -> bool:
    left_aliases = platform_aliases(left)
    right_aliases = platform_aliases(right)
    return any(
        left_alias == right_alias
        or (len(left_alias) >= 3 and left_alias in right_alias)
        or (len(right_alias) >= 3 and right_alias in left_alias)
        for left_alias in left_aliases
        for right_alias in right_aliases
    )


def valid_result_sources(row: dict) -> list[dict]:
    return [
        source for source in row.get("sources", [])
        if isinstance(source, dict)
        and (str(source.get("url") or "").strip() or str(source.get("evidence_file") or "").strip())
    ]


def source_matches_platform(source: dict, platform: str) -> bool:
    haystack = normalize_match_text(" ".join(
        str(source.get(key) or "")
        for key in ("title", "publisher", "url", "evidence_file", "supports")
    ))
    return any(alias in haystack for alias in platform_aliases(platform) if len(alias) >= 2)


def cmd_reconcile(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    results = json_load(Path(args.results).expanduser().resolve())
    if isinstance(results, dict):
        results = results.get("results") or results.get("rows") or []
    if not isinstance(results, list):
        raise RunError("reconcile results 必须是61行数组或含results/rows数组的对象")
    rows_by_id = {
        str(row.get("item_id") or row.get("row_id") or ""): row
        for row in results
        if isinstance(row, dict)
    }
    unknown = sorted(set(rows_by_id) - CANONICAL_SET)
    if unknown:
        raise RunError("reconcile results 含非权威61行编号：" + "、".join(unknown))
    reconciled: list[dict] = []
    skipped_no_action = 0
    skipped_no_source = 0
    skipped_no_spec_match = 0
    skipped_terminal_or_running = 0
    for row_id in CANONICAL_61:
        row = rows_by_id.get(row_id)
        if not row:
            continue
        result_actions = [
            action for action in row.get("actions", [])
            if isinstance(action, dict)
            and str(action.get("platform") or "").strip()
            and str(action.get("outcome") or "").upper() in {"FOUND", "NOT_FOUND", "BLOCKED"}
        ]
        if not result_actions:
            skipped_no_action += 1
            continue
        sources = valid_result_sources(row)
        row_raw_refs = [
            str(ref) for ref in row.get("raw_refs", [])
            if str(ref).strip()
        ] if isinstance(row.get("raw_refs", []), list) else []
        candidates = [
            action for action in queue["actions"]
            if action["row_id"] == row_id
            and action["execution_state"] not in {"TERMINAL", "RUNNING"}
        ]
        for result_action in result_actions:
            platform = str(result_action.get("platform") or "")
            candidate = next(
                (
                    action for action in candidates
                    if platform_matches(platform, action["action_spec"]["platform"])
                    and (
                        not result_action.get("subject_role")
                        or result_action.get("subject_role") == action["action_spec"].get("subject_role")
                    )
                ),
                None,
            )
            if not candidate:
                skipped_no_spec_match += 1
                continue
            matched_sources = [
                source for source in sources
                if source_matches_platform(source, candidate["action_spec"]["platform"])
            ]
            if not matched_sources and len(result_actions) == 1:
                matched_sources = sources
            raw_refs = list(dict.fromkeys(
                row_raw_refs
                + [
                    str(source.get("evidence_file"))
                    for source in matched_sources
                    if str(source.get("evidence_file") or "").strip()
                ]
            ))
            outcome = str(result_action.get("outcome") or "").upper()
            searched_scope = None
            if outcome == "NOT_FOUND":
                raw_refs, searched_scope = require_not_found_evidence(
                    {
                        "raw_refs": raw_refs,
                        "searched_scope": result_action.get("searched_scope")
                        or row.get("searched_scope"),
                    },
                    candidate,
                )
            elif not matched_sources and not raw_refs:
                skipped_no_source += 1
                continue
            note = str(result_action.get("note") or "")
            if outcome == "BLOCKED":
                if not any(term in note for term in ("登录", "扫码", "验证码", "认证", "账户")):
                    skipped_no_spec_match += 1
                    continue
                normalized_outcome = "LOGIN_REQUIRED"
                after = "WAITING_LOGIN"
                result_status = None
            elif outcome == "FOUND":
                normalized_outcome = "FOUND"
                after = "TERMINAL"
                row_status = str(row.get("status") or "")
                result_status = row_status if row_status in RESULT_STATUSES else "LEAD_ONLY"
            else:
                normalized_outcome = "NOT_FOUND"
                after = "TERMINAL"
                result_status = "NOT_FOUND"
            before = candidate["execution_state"]
            candidate["attempt"] = max(1, int(candidate.get("attempt", 0)))
            candidate["started_at"] = str(result_action.get("accessed_at") or row.get("completed_at") or now_iso())
            candidate["finished_at"] = str(row.get("completed_at") or result_action.get("accessed_at") or now_iso())
            candidate["execution_state"] = after
            candidate["result_status"] = result_status
            candidate["outcome"] = normalized_outcome
            candidate["park_reason"] = note if normalized_outcome == "LOGIN_REQUIRED" else None
            candidate["findings"] = row.get("findings", []) if isinstance(row.get("findings", []), list) else []
            candidate["sources"] = matched_sources
            candidate["raw_refs"] = raw_refs
            candidate["screenshot_refs"] = [
                ref for ref in raw_refs
                if Path(ref).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            candidate["limitations"] = row.get("limitations", []) if isinstance(row.get("limitations", []), list) else []
            candidate["next_steps"] = row.get("next_steps", []) if isinstance(row.get("next_steps", []), list) else []
            candidate["searched_scope"] = searched_scope
            payload = {
                "findings": candidate["findings"],
                "sources": matched_sources,
                "raw_refs": raw_refs,
                "screenshot_refs": candidate["screenshot_refs"],
                "limitations": candidate["limitations"],
                "next_steps": candidate["next_steps"],
                "searched_scope": searched_scope,
            }
            event = make_event(
                state,
                candidate,
                event_type="COMMIT",
                before=before,
                after=after,
                outcome=normalized_outcome,
                payload=payload,
            )
            event["reconciled"] = True
            event["reconcile_source"] = str(Path(args.results).expanduser().resolve())
            candidate["last_commit_id"] = event["commit_id"]
            append_jsonl_atomic(paths["log"], event)
            reconciled.append({
                "action_id": candidate["action_id"],
                "row_id": row_id,
                "platform": candidate["action_spec"]["platform"],
                "outcome": normalized_outcome,
            })
            candidates.remove(candidate)
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "reconcile")
    output["results_file"] = str(Path(args.results).expanduser().resolve())
    output["reconciled_count"] = len(reconciled)
    output["reconciled"] = reconciled
    output["skipped"] = {
        "rows_without_real_actions": skipped_no_action,
        "actions_without_source_or_raw_ref": skipped_no_source,
        "actions_without_spec_match": skipped_no_spec_match,
        "terminal_or_running": skipped_terminal_or_running,
    }
    emit(output)
    return 0


def selected_actions(queue: dict, args: argparse.Namespace, allowed_states: set[str] | None = None) -> list[dict]:
    action_ids = set(args.action_id or [])
    row_ids = set(args.row_id or [])
    if not action_ids and not row_ids:
        raise RunError("至少提供一个 --action-id 或 --row-id")
    selected = [
        action for action in queue["actions"]
        if action["action_id"] in action_ids or action["row_id"] in row_ids
    ]
    unknown_actions = action_ids - {action["action_id"] for action in selected}
    unknown_rows = row_ids - {action["row_id"] for action in selected}
    if unknown_actions or unknown_rows:
        raise RunError(f"未知选择：actions={sorted(unknown_actions)} rows={sorted(unknown_rows)}")
    if allowed_states is not None:
        selected = [action for action in selected if action["execution_state"] in allowed_states]
    return selected


def cmd_park_manual(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    selected = selected_actions(queue, args)
    if not selected:
        raise RunError("没有可park的动作")
    parked = []
    for action in selected:
        if action["execution_state"] in {"TERMINAL", "RUNNING"}:
            raise RunError(f"{action['action_id']} 为 {action['execution_state']}，不能park-manual")
        before = action["execution_state"]
        action["execution_state"] = "WAITING_MANUAL"
        action["result_status"] = "NEEDS_HUMAN"
        action["outcome"] = "MANUAL_REQUIRED"
        action["park_reason"] = args.reason
        action["next_steps"] = [args.next_step] if args.next_step else []
        payload = {"next_steps": action["next_steps"], "limitations": [args.reason]}
        event = make_event(
            state,
            action,
            event_type="PARK_MANUAL",
            before=before,
            after="WAITING_MANUAL",
            outcome="MANUAL_REQUIRED",
            payload=payload,
        )
        action["last_commit_id"] = event["commit_id"]
        append_jsonl_atomic(paths["log"], event)
        parked.append(action["action_id"])
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "park-manual")
    output["parked_actions"] = parked
    emit(output)
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    state_map = {
        "LOGIN_REQUIRED": {"WAITING_LOGIN"},
        "MANUAL_REQUIRED": {"WAITING_MANUAL"},
        "RETRYABLE": {"RETRYABLE"},
        "ALL": {"WAITING_LOGIN", "WAITING_MANUAL", "RETRYABLE"},
    }
    allowed = state_map[args.kind]
    selected = selected_actions(queue, args, allowed_states=allowed)
    if not selected:
        raise RunError("选择范围内没有符合 resume kind 的动作")
    login_actions = [
        action for action in selected if action["execution_state"] == "WAITING_LOGIN"
    ]
    login_resume = None
    if login_actions:
        required = {
            "--correlation-id": args.correlation_id,
            "--session-ref": args.session_ref,
            "--checkpoint": args.checkpoint,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing or not args.verification_signal:
            raise RunError(
                "恢复登录动作必须提供 "
                + "、".join(missing + (["--verification-signal"] if not args.verification_signal else []))
            )
        login_state_path = case_dir / "work" / "login" / "state.json"
        login_state = json_load(login_state_path)
        if login_state.get("protocol") != "agent-login-coordination/1.0":
            raise RunError("登录状态协议版本无效")
        if login_state.get("phase") != "RUNNING":
            raise RunError("登录协议尚未完成同会话验证，phase 必须为 RUNNING")
        if login_state.get("correlation_id") != args.correlation_id:
            raise RunError("登录 correlation_id 与已验证状态不匹配")
        if login_state.get("session", {}).get("session_ref") != args.session_ref:
            raise RunError("登录 session_ref 与已验证同一会话不匹配")
        if login_state.get("checkpoint") != args.checkpoint:
            raise RunError("登录 checkpoint 与已验证状态不匹配")
        resume_event = login_state.get("last_events", {}).get("RESUME") or login_state.get("last_event")
        resume_payload = resume_event.get("payload", {}) if isinstance(resume_event, dict) else {}
        stored_signals = [
            str(value) for value in resume_payload.get("verification_signals", []) if str(value)
        ]
        requested_signals = [str(value) for value in args.verification_signal if str(value)]
        if (
            not isinstance(resume_event, dict)
            or resume_event.get("event") != "RESUME"
            or resume_event.get("correlation_id") != args.correlation_id
            or resume_event.get("checkpoint") != args.checkpoint
            or resume_event.get("session", {}).get("session_ref") != args.session_ref
            or resume_payload.get("session_verified") is not True
            or not login_state.get("completed_login_cycle")
            or not stored_signals
            or not set(requested_signals).issubset(set(stored_signals))
        ):
            raise RunError("登录 RESUME 缺少同会话 session_verified 或匹配的 verification_signal")
        login_resume = {
            "correlation_id": args.correlation_id,
            "session_ref": args.session_ref,
            "checkpoint": args.checkpoint,
            "resume_ref": resume_payload.get("resume_ref"),
            "verification_signals": requested_signals,
        }
    resumed = []
    for action in selected:
        before = action["execution_state"]
        after = "READY" if (
            requirements_met(action.get("seed_requirements", []), case, state)
            and dependencies_met(action, queue)
            and comparison_evidence_met(action, case, state, queue)
        ) else "WAITING_DEPENDENCY"
        action["execution_state"] = after
        action["outcome"] = None
        action["park_reason"] = None
        if before == "WAITING_MANUAL":
            action["result_status"] = None
        event = make_event(
            state,
            action,
            event_type="RESUME",
            before=before,
            after=after,
            outcome=None,
            payload={
                "next_steps": [args.note] if args.note else [],
                "login_resume": login_resume if before == "WAITING_LOGIN" else None,
            },
        )
        append_jsonl_atomic(paths["log"], event)
        resumed.append(action["action_id"])
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "resume")
    output["resumed_actions"] = resumed
    emit(output)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    refresh_runtime(case, state, queue)
    save_runtime(state, queue, paths)
    output = command_summary(state, queue, "status")
    output["next_ready"] = [
        {
            "action_id": action["action_id"],
            "row_id": action["row_id"],
            "wave": action["wave"],
            "provider": action["action_spec"]["provider"],
            "platform": action["action_spec"]["platform"],
        }
        for action in sorted(
            (item for item in queue["actions"] if item["execution_state"] in {"READY", "RETRYABLE"}),
            key=lambda item: (
                WAVE_ORDER.index(item["wave"]),
                PRIORITY_ORDER.get(item.get("priority", "P3"), 9),
                item["action_id"],
            ),
        )[:10]
    ]
    emit(output)
    return 0


def cmd_quiesce(args: argparse.Namespace) -> int:
    case_dir = Path(args.case_dir).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    case, state, queue, paths = load_runtime(case_dir, run_dir)
    refresh_runtime(case, state, queue)
    counts = state["counts"]["by_execution_state"]
    active = counts.get("READY", 0) + counts.get("RETRYABLE", 0) + counts.get("RUNNING", 0)
    if active:
        raise RunError(f"仍有 {active} 个 READY/RETRYABLE/RUNNING 动作，不得 quiesce")
    if counts.get("WAITING_LOGIN", 0):
        state["case_state"] = "WAITING_LOGIN"
        state["execution_state"] = "WAITING_LOGIN"
    elif counts.get("WAITING_MANUAL", 0):
        state["case_state"] = "WAITING_MANUAL"
        state["execution_state"] = "WAITING_MANUAL"
    else:
        state["case_state"] = "QUIESCENT"
        state["execution_state"] = "QUIESCENT"
        state["quiesced_at"] = now_iso()
    save_runtime(state, queue, paths)
    emit(command_summary(state, queue, "quiesce"))
    return 0


def add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--run-dir", required=True)


def add_selectors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--action-id", action="append")
    parser.add_argument("--row-id", action="append")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="61行重案证据清单 run-first 调度器；不直接联网")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("compile", help="从case的61行row_tasks编译W0-W5动作队列")
    add_runtime_args(command)
    command.add_argument("--matrix", help="缺省使用 references/run-matrix-61.json")
    command.set_defaults(func=cmd_compile)

    command = sub.add_parser("next", help="原子派发下一个READY公开动作")
    add_runtime_args(command)
    command.set_defaults(func=cmd_next)

    command = sub.add_parser("commit", help="原子提交Agent工具调用结果")
    add_runtime_args(command)
    group = command.add_mutually_exclusive_group()
    group.add_argument("--file")
    group.add_argument("--json")
    command.set_defaults(func=cmd_commit)

    command = sub.add_parser("reconcile", help="仅用既有真实action和来源/raw引用保守回填动作状态")
    add_runtime_args(command)
    command.add_argument("--results", required=True)
    command.set_defaults(func=cmd_reconcile)

    command = sub.add_parser("status", help="汇总双状态、波次和park队列")
    add_runtime_args(command)
    command.set_defaults(func=cmd_status)

    command = sub.add_parser("resume", help="登录或人工完成后恢复park动作")
    add_runtime_args(command)
    add_selectors(command)
    command.add_argument(
        "--kind",
        choices=["LOGIN_REQUIRED", "MANUAL_REQUIRED", "RETRYABLE", "ALL"],
        default="LOGIN_REQUIRED",
    )
    command.add_argument("--note")
    command.add_argument("--correlation-id")
    command.add_argument("--session-ref")
    command.add_argument("--checkpoint")
    command.add_argument("--verification-signal", action="append")
    command.set_defaults(func=cmd_resume)

    command = sub.add_parser("park-manual", help="把指定动作或行转为人工park，不影响其他READY")
    add_runtime_args(command)
    add_selectors(command)
    command.add_argument("--reason", required=True)
    command.add_argument("--next-step")
    command.set_defaults(func=cmd_park_manual)

    command = sub.add_parser("quiesce", help="仅在READY/RUNNING耗尽后进入等待或静止态")
    add_runtime_args(command)
    command.set_defaults(func=cmd_quiesce)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (RunError, json.JSONDecodeError, OSError) as exc:
        emit({"ok": False, "command": getattr(args, "command", None), "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
