#!/usr/bin/env python3
"""Fail IP-proposal DOCX reports that outrun their access or visual evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


def extract_text(zf: zipfile.ZipFile) -> str:
    root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for para in root.findall(".//w:p", W_NS):
        text = "".join(node.text or "" for node in para.findall(".//w:t", W_NS))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def external_hyperlink_count(zf: zipfile.ZipFile) -> int:
    rel_name = "word/_rels/document.xml.rels"
    if rel_name not in zf.namelist():
        return 0
    root = ET.fromstring(zf.read(rel_name))
    count = 0
    for rel in root.findall("r:Relationship", REL_NS):
        if rel.get("Type", "").endswith("/hyperlink") and rel.get("TargetMode") == "External":
            count += 1
    return count


def section_between(text: str, start: str, end: str | None) -> str | None:
    start_index = text.find(start)
    if start_index < 0:
        return None
    content_start = start_index + len(start)
    if end is None:
        return text[content_start:].strip()
    end_index = text.find(end, content_start)
    if end_index < 0:
        return None
    return text[content_start:end_index].strip()


def add_empty_span(findings: list[dict[str, str]], text: str, label: str, start: str, end: str | None, minimum: int = 12) -> None:
    content = section_between(text, start, end)
    if content is None:
        findings.append({"gate": "required_content", "message": f"missing anchor/span: {label}"})
    elif len(re.sub(r"\s+", "", content)) < minimum:
        findings.append({"gate": "required_content", "message": f"empty or insubstantial span: {label}"})


def choose_anchor(text: str, *candidates: str) -> str:
    for candidate in candidates:
        if candidate in text:
            return candidate
    return candidates[0]


def scan(path: Path, working_notes: str = "") -> tuple[list[dict[str, str]], dict[str, int | bool]]:
    findings: list[dict[str, str]] = []
    with zipfile.ZipFile(path) as zf:
        text = extract_text(zf)
        media_count = sum(1 for name in zf.namelist() if name.startswith("word/media/") and not name.endswith("/"))
        hyperlink_count = external_hyperlink_count(zf)

    packaging_case = bool(re.search(r"包装|装潢|trade\s*dress|外观", text, re.I))
    login_unresolved = bool(
        re.search(
            r"(?:需|需要|要求|重定向至|跳转至).{0,10}(?:登录|验证码|安全验证)|"
            r"(?:登录|验证码|安全验证).{0,10}(?:未完成|未执行|不可得|不可用)|"
            r"无可用浏览器|浏览器不可用|可见交互表面不可用|有头\s*Playwright.{0,8}不可用",
            text,
        )
    )
    audit_text = f"{text}\n{working_notes}"
    generic_post_login_claim = bool(
        re.search(r"用户已完成登录|登录后已核验|登录后(?:截图|录屏|采集)|已登录并(?:截图|采集)", text)
    )
    handoff_method = bool(re.search(r"登录交接方式[:：]\s*\S+", audit_text))
    visible_window = bool(re.search(r"可见窗口[:：]\s*是", audit_text))
    session_kept = bool(re.search(r"会话保持[:：]\s*是", audit_text))
    user_confirmed_login = bool(re.search(r"用户确认[:：]\s*已登录", audit_text))
    reinspection_success = bool(re.search(r"登录后复核[:：]\s*成功", audit_text))
    post_login_evidence = bool(
        re.search(r"登录后证据[:：]\s*(?!无\b|无$|待核验|未采集|—|-\s*$)\S+", audit_text)
    )
    handoff_complete = all(
        (
            handoff_method,
            visible_window,
            session_kept,
            user_confirmed_login,
            reinspection_success,
            post_login_evidence,
        )
    )
    post_login_verified = handoff_complete or (generic_post_login_claim and media_count > 0)
    preliminary_consent = bool(
        re.search(r"用户决策[:：].{0,30}继续生成初步线索版|用户已明确选择.{0,20}初步线索版", text)
    )
    decisive_visual = bool(
        re.search(
            r"包装.{0,20}高度近似|整体视觉印象.{0,12}高度|完整保留.{0,20}(?:视觉|装潢|包装)|"
            r"(?:视觉|装潢|包装).{0,20}(?:完全一致|完全相同)|换商标[、，, ]*留装潢|"
            r"(?:不正当竞争|第六条第一项).{0,18}要件齐备",
            text,
        )
    )

    if login_unresolved and not handoff_complete and not preliminary_consent:
        findings.append(
            {
                "gate": "login",
                "message": "login/visible-interactive access is unresolved, but no explicit user decision authorizes a preliminary clue-only report",
            }
        )

    if generic_post_login_claim and not handoff_complete and not preliminary_consent:
        findings.append(
            {
                "gate": "login_handoff_record",
                "message": "post-login access is claimed, but the cross-agent working-note handoff record is incomplete; pass --working-notes without putting the access log in the report",
            }
        )

    if packaging_case and media_count == 0 and decisive_visual:
        findings.append(
            {
                "gate": "visual_evidence",
                "message": "decisive packaging-similarity language appears, but the DOCX contains no embedded image/contact sheet",
            }
        )

    if preliminary_consent and decisive_visual:
        findings.append(
            {
                "gate": "preliminary_scope",
                "message": "a preliminary clue-only report must not contain a decisive visual-similarity conclusion",
            }
        )

    route_end = choose_anchor(text, "五、管辖与被告", "六、管辖与被告")
    evidence_start = choose_anchor(text, "七、证据计划", "八、证据计划")
    defenses_start = choose_anchor(text, "八、被告可能抗辩与应对", "九、被告可能抗辩与应对")
    immediate_start = choose_anchor(text, "九、立即行动清单", "十、立即行动清单")
    rights_appendix = choose_anchor(text, "附录 A", "附录A")
    sources_anchor = choose_anchor(text, "附录 E：来源与依据", "附录 F：来源与依据")

    required_spans = [
        ("executive recommendation", "推荐结论", "三条最强理由", 12),
        ("three reasons", "三条最强理由", "三个最关键证据缺口", 18),
        ("three evidence gaps", "三个最关键证据缺口", "二、关键事实", 18),
        ("route rationale", "为何反不正当竞争（包装装潢）胜出", "会改变推荐的事实", 18),
        ("route change triggers", "会改变推荐的事实", route_end, 18),
        ("evidence plan", evidence_start, defenses_start, 30),
        ("immediate action list", immediate_start, rights_appendix, 30),
        ("sources appendix", sources_anchor, None, 30),
    ]
    for label, start, end, minimum in required_spans:
        add_empty_span(findings, text, label, start, end, minimum)

    sources = section_between(text, sources_anchor, None) or ""
    if not re.search(r"https?://|证据编号|公证书|用户提供", sources):
        findings.append(
            {
                "gate": "sources",
                "message": "sources appendix contains no source URL or precisely identified evidence item",
            }
        )
    if sources and hyperlink_count == 0 and re.search(r"https?://", sources):
        findings.append(
            {
                "gate": "sources",
                "message": "source URLs exist only as plain text; add clickable external hyperlinks",
            }
        )

    metrics: dict[str, int | bool] = {
        "packaging_case": packaging_case,
        "login_unresolved": login_unresolved,
        "post_login_verified": post_login_verified,
        "handoff_complete": handoff_complete,
        "handoff_method": handoff_method,
        "visible_window": visible_window,
        "session_kept": session_kept,
        "user_confirmed_login": user_confirmed_login,
        "reinspection_success": reinspection_success,
        "post_login_evidence": post_login_evidence,
        "preliminary_consent": preliminary_consent,
        "decisive_visual": decisive_visual,
        "embedded_media": media_count,
        "external_hyperlinks": hyperlink_count,
    }
    return findings, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit IP-proposal DOCX access, evidence, and completeness gates.")
    parser.add_argument("docx", type=Path)
    parser.add_argument(
        "--working-notes",
        type=Path,
        help="Optional UTF-8 TXT/MD/JSON working-note record for login handoff fields; keeps operational access logs out of the client report.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.docx.exists() or args.docx.suffix.lower() != ".docx":
        print(f"invalid DOCX: {args.docx}", file=sys.stderr)
        return 2

    try:
        working_notes = ""
        if args.working_notes:
            if not args.working_notes.exists():
                print(f"working notes not found: {args.working_notes}", file=sys.stderr)
                return 2
            working_notes = args.working_notes.read_text(encoding="utf-8")
        findings, metrics = scan(args.docx, working_notes)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        print(f"cannot inspect DOCX: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"metrics": metrics, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        print("evidence metrics: " + ", ".join(f"{key}={value}" for key, value in metrics.items()))
        if findings:
            print(f"evidence gate scan failed: {len(findings)} issue(s)")
            for item in findings:
                print(f"- {item['gate']}: {item['message']}")
        else:
            print("evidence gate scan passed: 0 issues")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
