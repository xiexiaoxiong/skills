#!/usr/bin/env python3
"""Scan a DOCX for object-stringification and placeholder-like formal errors."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

BAD_PATTERNS = [
    re.compile(r"\[object Object\]"),
    re.compile(r"\[object Promise\]"),
    re.compile(r"\[object Array\]"),
    re.compile(r"\bundefined\b"),
    re.compile(r"\bNaN\b"),
    re.compile(r"\bnull\b"),
]


def iter_docx_paragraphs(path: Path):
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            if not (
                name.startswith("word/")
                or name.startswith("docProps/")
                or name == "[Content_Types].xml"
            ):
                continue
            data = zf.read(name)
            try:
                root = ET.fromstring(data)
            except ET.ParseError:
                continue
            paragraphs = root.findall(".//w:p", W_NS)
            if paragraphs:
                for idx, para in enumerate(paragraphs, 1):
                    text = "".join(t.text or "" for t in para.findall(".//w:t", W_NS))
                    if text.strip():
                        yield name, idx, text
            else:
                text_nodes = root.findall(".//w:t", W_NS)
                text = "".join(t.text or "" for t in text_nodes)
                if text.strip():
                    yield name, 1, text


def scan(path: Path):
    findings = []
    for part, paragraph, text in iter_docx_paragraphs(path):
        for pattern in BAD_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "part": part,
                        "paragraph": paragraph,
                        "token": match.group(0),
                        "text": text[:300],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a DOCX contains common generated-report formal errors."
    )
    parser.add_argument("docx", type=Path)
    parser.add_argument("--json", action="store_true", help="print machine-readable findings")
    args = parser.parse_args()

    if not args.docx.exists():
        print(f"not found: {args.docx}", file=sys.stderr)
        return 2
    if args.docx.suffix.lower() != ".docx":
        print(f"not a .docx file: {args.docx}", file=sys.stderr)
        return 2

    findings = scan(args.docx)
    if args.json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    elif findings:
        print(f"formal error scan failed: {len(findings)} hit(s)")
        for item in findings[:80]:
            print(
                f"{item['part']} paragraph {item['paragraph']}: "
                f"{item['token']} :: {item['text']}"
            )
        if len(findings) > 80:
            print(f"... {len(findings) - 80} more")
    else:
        print("formal error scan passed: 0 hits")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
