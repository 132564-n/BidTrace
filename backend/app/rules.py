"""Evidence-bounded presence and numeric checks."""

import re

from .pdf_text import normalized
from .retrieval import search
from .pdf_text import split_pages


def query_for(check: dict) -> str:
    parts = [check.get("name", ""), check.get("target", ""), *check.get("source_quotes", [])]
    return " ".join(part for part in parts if part)


def candidates(check: dict, bid_pages: list[str], limit: int = 5) -> list[dict]:
    return search(query_for(check), split_pages(bid_pages), limit=limit)


def base_finding(check: dict, status: str, reason: str, page: int | None = None, quote: str | None = None,
                 hits: list[dict] | None = None) -> dict:
    return {
        "rule_id": check["id"],
        "name": check["name"],
        "category": check["category"],
        "status": status,
        "reason": reason,
        "source_page": check["source_page"],
        "source_quotes": check["source_quotes"],
        "bid_page": page,
        "bid_quote": quote,
        "candidates": hits or [],
    }


def presence(check: dict, bid_pages: list[str]) -> dict:
    target = normalized(check.get("target") or check["name"].replace("可找到", ""))
    hits = candidates(check, bid_pages)
    for page_number, page in enumerate(bid_pages, 1):
        for line in page.splitlines():
            if target in normalized(line):
                return base_finding(check, "满足", "找到了对应章节文字；签章和内容质量仍需人工检查。",
                                    page_number, line.strip(), hits)
    return base_finding(check, "未找到证据", "未在可提取文字中找到对应章节，建议人工翻阅原件。", hits=hits)


def numeric_value(field_key: str, line: str):
    clean = re.sub(r"\s+", "", line)
    if field_key == "quote_total":
        match = re.search(r"(?:投标总报价|总报价|报价).{0,18}?(\d+(?:\.\d+)?)(万元|元)", clean)
        return (float(match[1]) / 10000 if match[2] == "元" else float(match[1])) if match else None
    if field_key == "validity_days":
        match = re.search(r"投标有效期.{0,50}?(\d+)(?:日历天|天|日)", clean)
        return int(match[1]) if match else None
    if field_key == "duration_months":
        match = re.search(r"(?:项目实施期限|实施期限|服务期限).{0,30}?(\d+)(年|个月|月)", clean)
        return int(match[1]) * (12 if match[2] == "年" else 1) if match else None
    if field_key == "service_hours":
        match = re.search(r"每周(\d+)天.{0,12}?每[天日](\d+)小时", clean)
        if match:
            return (int(match[1]), int(match[2]))
        match = re.search(r"(\d+)[*×xX](\d+)小时.{0,8}?(?:现场)?值守", clean)
        return (int(match[1]), int(match[2])) if match else None
    if field_key == "manager_count":
        if re.search(r"不设.{0,8}?项目负责人", clean):
            return 0
        match = re.search(r"项目负责人(\d+)名", clean)
        return int(match[1]) if match else None
    return None


def meets(check: dict, value) -> bool:
    if check["field_key"] == "service_hours":
        expected = re.search(r"(\d+)天[×*xX](\d+)小时", str(check["threshold"]))
        if not expected:
            raise ValueError("值守门槛格式无效")
        return value[0] >= int(expected[1]) and value[1] >= int(expected[2])
    threshold = float(check["threshold"])
    operator = check["operator"]
    return {"<=": value <= threshold, ">=": value >= threshold, "=": value == threshold}[operator]


def numeric(check: dict, bid_pages: list[str]) -> dict:
    hits = candidates(check, bid_pages)
    found: list[tuple[object, int, str]] = []
    # Scan all pages for exact field patterns. Retrieval hits remain visible for recall analysis.
    for page_number, page in enumerate(bid_pages, 1):
        for line in page.splitlines():
            value = numeric_value(check["field_key"], line)
            if value is not None:
                found.append((value, page_number, line.strip()))
    if not found:
        return base_finding(check, "未找到证据", "未找到可比较的明确数值，建议人工核对。", hits=hits)
    values = {str(item[0]) for item in found}
    if len(values) > 1:
        return base_finding(check, "需人工复核", "文件中出现不一致的数值承诺。", found[0][1], found[0][2], hits)
    value, page, quote = found[0]
    if meets(check, value):
        return base_finding(check, "满足", "已按确认的单位和门槛完成程序比较。", page, quote, hits)
    return base_finding(check, "明确冲突", "投标文件中的明确数值与招标门槛冲突。", page, quote, hits)
