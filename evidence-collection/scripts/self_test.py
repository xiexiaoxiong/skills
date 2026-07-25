#!/usr/bin/env python3
"""Forward tests for evidence-collection.

Creates three non-accusatory cases:
1. A complete fictional evidence package.
2. A real public URL with insufficient infringement nexus.
3. A blocked private-network URL that must be rejected.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parent / "evidence_case.py"
CHECKLIST_SCRIPT = Path(__file__).resolve().parent / "checklist_case.py"


def run(
    args: list[str],
    expected: set[int] | None = None,
    script: Path = SCRIPT,
) -> dict[str, Any]:
    expected = expected or {0}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw_stdout": proc.stdout, "raw_stderr": proc.stderr}
    return {
        "command": args[0],
        "returncode": proc.returncode,
        "expected": sorted(expected),
        "passed": proc.returncode in expected,
        "payload": payload,
    }


def write_fixture(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def add_fixture(
    case_dir: Path,
    file: Path,
    title: str,
    source: str,
    group_id: int,
    proof: str,
    fact_status: str,
    litigation_status: str,
    task_id: str,
    limitations: str = "模拟材料，仅用于技术回归测试，不代表真实侵权事实。",
) -> dict[str, Any]:
    return run(
        [
            "add",
            "--case-dir",
            str(case_dir),
            "--file",
            str(file),
            "--title",
            title,
            "--source",
            source,
            "--source-type",
            "模拟测试材料",
            "--group-id",
            str(group_id),
            "--proof-point",
            proof,
            "--fact-status",
            fact_status,
            "--litigation-status",
            litigation_status,
            "--task-id",
            task_id,
            "--limitations",
            limitations,
        ]
    )


def docx_ok(path: Path) -> bool:
    if not path.is_file() or not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as zf:
        return "word/document.xml" in zf.namelist() and "word/numbering.xml" in zf.namelist()


def close_complete_fixture_tasks(case_dir: Path) -> None:
    path = case_dir / "search_tasks.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    completed = {"B03", "2-3-3", "B07", "2-2-5", "1-1-2"}
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    for task in document["tasks"]:
        if task["id"] in completed:
            task["status"] = "DONE"
            task["notes"] = "模拟证据已登记并链接到本任务。"
        else:
            task["status"] = "NOT_APPLICABLE"
            task["notes"] = "本技术回归案例仅验证五组目录、附件和状态闭环；该方向经模拟设定不适用，不代表真实案件可省略。"
        task["updated_at"] = timestamp
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    root = Path(args.output).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        print(json.dumps({"ok": False, "error": f"测试目录非空：{root}"}, ensure_ascii=False))
        return 1
    root.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    # Case A: fictional but complete enough to exercise all five Word groups.
    case_a = root / "案例A_虚构完整证据包"
    steps.append(
        run(
            [
                "init",
                "--rights-holder",
                "甲方创新设计有限公司（虚构）",
                "--url",
                "https://example.com/mock-product",
                "--output",
                str(case_a),
                "--defendants",
                "乙方网络销售有限公司（虚构）",
                "--defendant-seed",
                "乙方X-1模拟商品（虚构）",
                "--cause",
                "侵害商标权及不正当竞争纠纷（模拟）",
            ]
        )
    )
    fixtures = case_a / "work" / "fixtures"
    generated_tasks = json.loads((case_a / "search_tasks.json").read_text(encoding="utf-8"))["tasks"]
    task_by_id = {task["id"]: task for task in generated_tasks}
    ordinary_queries = task_by_id["1-2-4"]["queries"]
    reputation_queries = task_by_id["2-3-3"]["queries"]
    defendant_query_direction_ok = bool(ordinary_queries) and all(
        "乙方X-1模拟商品（虚构）" in query and "甲方创新设计有限公司（虚构）" not in query
        for query in ordinary_queries
    )
    reputation_query_direction_ok = bool(reputation_queries) and all(
        "甲方创新设计有限公司（虚构）" in query
        for query in reputation_queries
    )
    files = [
        write_fixture(fixtures / "rights.txt", "模拟权利证书\n权利人：甲方创新设计有限公司\n权利号：MOCK-001\n状态：有效（模拟）\n"),
        write_fixture(fixtures / "reputation.html", "<html><title>模拟媒体报道</title><body>甲方品牌自2020年持续使用并获得行业关注。此为模拟数据。</body></html>"),
        write_fixture(fixtures / "suspect.html", "<html><title>模拟疑似商品页</title><body>店铺：乙方旗舰店；型号：X-1；价格：199元；显示销量：8000；仅为技术测试。</body></html>"),
        write_fixture(fixtures / "comments.txt", "模拟评论1：看起来像甲方品牌。\n模拟评论2：是否与甲方有合作？\n"),
        write_fixture(fixtures / "registry.txt", "模拟工商信息\n乙方网络销售有限公司；股东：丙某；收款主体：乙方网络销售有限公司。\n"),
    ]
    steps.append(add_fixture(case_a, files[0], "甲方模拟权利证书及状态说明", "模拟登记机关", 1, "证明模拟权利人、权利客体和有效状态。", "VERIFIED", "FIXED", "B03"))
    steps.append(add_fixture(case_a, files[1], "甲方品牌持续使用及媒体报道", "模拟媒体", 2, "证明模拟品牌持续使用和知名度线索。", "LEAD", "PUBLIC_CAPTURE", "2-3-3"))
    steps.append(add_fixture(case_a, files[2], "乙方模拟疑似商品页面", "模拟平台", 3, "证明模拟页面的店铺、商品型号、价格和显示销量。", "VERIFIED", "FIXED", "B07"))
    steps.append(add_fixture(case_a, files[3], "模拟消费者评论完整记录", "模拟评论平台", 4, "证明存在消费者混淆线索；仍需核验账号真实性与自然形成。", "LEAD", "NEEDS_NOTARIZATION", "2-2-5"))
    steps.append(add_fixture(case_a, files[4], "乙方模拟工商及收款主体信息", "模拟企业公示系统", 5, "证明模拟经营主体与收款主体的连接。", "STRONG_INFERENCE", "PUBLIC_CAPTURE", "1-1-2"))
    close_complete_fixture_tasks(case_a)
    steps.append(run(["report", "--case-dir", str(case_a)]))
    validation_a = run(["validate", "--case-dir", str(case_a), "--report", str(case_a / "案件证据报告.docx")])
    steps.append(validation_a)
    cases.append(
        {
            "name": "案例A_虚构完整证据包",
            "purpose": "覆盖五组证据、跨表连续编号、附件哈希和缺口清单。",
            "report": str(case_a / "案件证据报告.docx"),
            "docx_ok": docx_ok(case_a / "案件证据报告.docx"),
            "validation_ok": validation_a["payload"].get("ok") is True,
            "evidence_count": validation_a["payload"].get("evidence_count"),
            "high_priority_pending": validation_a["payload"].get("high_priority_pending"),
            "plaintiff_only_ordinary_query_rejected": defendant_query_direction_ok,
            "plaintiff_reputation_query_allowed": reputation_query_direction_ok,
        }
    )

    # Case B: real public URL, intentionally insufficient to avoid false accusation.
    case_b = root / "案例B_公开网页但关联不足"
    steps.append(
        run(
            [
                "init",
                "--rights-holder",
                "Internet Assigned Numbers Authority (IANA)",
                "--url",
                "https://example.com/",
                "--output",
                str(case_b),
                "--cause",
                "技术测试：不得据此认定侵权",
                "--defendant-seed",
                "Example Domain被诉测试对象",
            ]
        )
    )
    if args.online:
        online_step = run(
            [
                "capture",
                "--case-dir",
                str(case_b),
                "--url",
                "https://example.com/",
                "--title",
                "Example Domain公开页面",
                "--source",
                "IANA保留示例域名页面",
                "--group-id",
                "3",
                "--proof-point",
                "仅证明该公开页面在访问时可见；不证明存在侵权。",
                "--fact-status",
                "LEAD",
                "--litigation-status",
                "PUBLIC_CAPTURE",
                "--task-id",
                "B07",
                "--limitations",
                "该页面属于保留示例域名，和侵权无直接关联；本材料专门测试系统不得把可访问页面误写为侵权事实。",
            ],
            expected={0},
        )
    else:
        offline = write_fixture(
            case_b / "work" / "fixtures" / "example.html",
            "<html><title>Example Domain离线测试副本</title><body>仅用于测试关联不足分支。</body></html>",
        )
        online_step = add_fixture(
            case_b,
            offline,
            "Example Domain离线测试副本",
            "IANA示例页面（离线模拟）",
            3,
            "仅证明系统能登记公开页面；不证明侵权。",
            "LEAD",
            "PUBLIC_CAPTURE",
            "B07",
            "离线模拟；不能证明真实访问或侵权。",
        )
    steps.append(online_step)
    steps.append(run(["report", "--case-dir", str(case_b)]))
    validation_b = run(["validate", "--case-dir", str(case_b)])
    steps.append(validation_b)
    warning_codes_b = {w.get("code") for w in validation_b["payload"].get("warnings", [])}
    cases.append(
        {
            "name": "案例B_公开网页但关联不足",
            "purpose": "验证公开可访问不等于侵权，权属缺失必须保留警告。",
            "online_requested": args.online,
            "online_capture_ok": online_step["passed"],
            "report": str(case_b / "案件证据报告.docx"),
            "docx_ok": docx_ok(case_b / "案件证据报告.docx"),
            "validation_ok": validation_b["payload"].get("ok") is True,
            "required_warning_present": "MISSING_RIGHTS_BASIS" in warning_codes_b,
        }
    )

    # Case C: SSRF/private address must be blocked and converted to a manual task.
    case_c = root / "案例C_访问受阻与人工闸门"
    steps.append(
        run(
            [
                "init",
                "--rights-holder",
                "测试权利人（虚构）",
                "--url",
                "http://127.0.0.1/private",
                "--output",
                str(case_c),
            ]
        )
    )
    blocked = run(
        [
            "capture",
            "--case-dir",
            str(case_c),
            "--url",
            "http://127.0.0.1/private",
            "--title",
            "不得访问的本机地址",
            "--group-id",
            "3",
            "--proof-point",
            "安全测试",
        ],
        expected={2},
    )
    steps.append(blocked)
    steps.append(
        run(
            [
                "task",
                "--case-dir",
                str(case_c),
                "--task-id",
                "B07",
                "--status",
                "BLOCKED",
                "--notes",
                "安全策略拒绝私网地址；实际案件应由用户提供公开链接或在有权访问的可见浏览器中处理。",
            ]
        )
    )
    steps.append(run(["report", "--case-dir", str(case_c)]))
    validation_c = run(["validate", "--case-dir", str(case_c)])
    steps.append(validation_c)
    checklist_contract_test = run(["self-test"], script=CHECKLIST_SCRIPT)
    steps.append(checklist_contract_test)
    cases.append(
        {
            "name": "案例C_访问受阻与人工闸门",
            "purpose": "验证SSRF防护、失败日志和人工任务，不生成占位证据。",
            "private_url_blocked": blocked["passed"] and blocked["returncode"] == 2,
            "report": str(case_c / "案件证据报告.docx"),
            "docx_ok": docx_ok(case_c / "案件证据报告.docx"),
            "validation_ok": validation_c["payload"].get("ok") is True,
            "evidence_count": validation_c["payload"].get("evidence_count"),
        }
    )

    technical_pass = all(step["passed"] for step in steps)
    semantic_pass = (
        cases[0]["docx_ok"]
        and cases[0]["validation_ok"]
        and cases[0]["evidence_count"] == 5
        and cases[0]["high_priority_pending"] == 0
        and cases[0]["plaintiff_only_ordinary_query_rejected"]
        and cases[0]["plaintiff_reputation_query_allowed"]
        and cases[1]["docx_ok"]
        and cases[1]["validation_ok"]
        and cases[1]["required_warning_present"]
        and cases[2]["docx_ok"]
        and cases[2]["private_url_blocked"]
        and cases[2]["evidence_count"] == 0
        and checklist_contract_test["passed"]
    )
    result = {
        "ok": technical_pass and semantic_pass,
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "online_requested": args.online,
        "technical_pass": technical_pass,
        "semantic_pass": semantic_pass,
        "cases": cases,
        "steps": steps,
        "issues_exercised": [
            "公开网页可访问但与侵权无关联时不得误判",
            "权属证据缺失必须给出明确警告",
            "私网/SSRF地址必须拒绝并记录失败",
            "零证据案件不得生成占位证据",
            "五组证据跨表连续编号必须与附件数一致",
            "普通任务必须使用被告商品种子，不能只查询权利人",
            "2-3知名度任务允许使用权利人查询",
            "附件存在性、元数据和SHA-256必须校验",
        ],
    }
    (root / "模拟测试结果.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
