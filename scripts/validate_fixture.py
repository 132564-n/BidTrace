"""Check that every gold-label quote exists on its stated PDF page."""

import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
DATA = json.loads((FIXTURES / "evaluation.json").read_text(encoding="utf-8"))


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def page_text(pdf, number: int) -> str:
    assert 1 <= number <= len(pdf.pages), f"无效页码：{number}"
    return compact(pdf.pages[number - 1].extract_text() or "")


source_path = FIXTURES / DATA["source"]["pdf"]
with pdfplumber.open(source_path) as source:
    assert len(source.pages) == DATA["source"]["pdf_pages"]
    for rule in DATA["rules"]:
        actual = page_text(source, rule["source_page"])
        for quote in rule["source_quotes"]:
            assert compact(quote) in actual, f"{rule['id']} 招标原文缺失：{quote}"

rule_ids = {rule["id"] for rule in DATA["rules"]}
assert len(rule_ids) == 10
for case in DATA["cases"]:
    with pdfplumber.open(FIXTURES / case["pdf"]) as bid:
        labels = case["expected"]
        assert {item["rule_id"] for item in labels} == rule_ids
        for label in labels:
            assert label["status"] in DATA["statuses"]
            if label["status"] == "未找到证据":
                assert label["bid_page"] is None and label["bid_quote"] is None
                continue
            actual = page_text(bid, label["bid_page"])
            assert compact(label["bid_quote"]) in actual, (
                f"{case['id']} / {label['rule_id']} 投标原文缺失：{label['bid_quote']}"
            )
        print(case["id"], len(bid.pages), dict(Counter(x["status"] for x in labels)))

print("全部原文引用和页码已核对。")
