"""Run the real model against the public/synthetic demo after local key setup."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from app.llm import MODEL, available, judge_semantic, propose_checks  # noqa: E402
from app.pdf_text import read_pdf  # noqa: E402


if not available():
    raise SystemExit("请先在项目根目录 .env 中配置 DEEPSEEK_API_KEY")

fixtures = ROOT / "fixtures"
data = json.loads((fixtures / "evaluation.json").read_text(encoding="utf-8"))
source_pages = read_pdf(fixtures / data["source"]["pdf"])
proposed = propose_checks(source_pages)
semantic_rules = [rule for rule in data["rules"] if rule["category"] == "semantic"]
judgments = []

for case in data["cases"]:
    pages = read_pdf(fixtures / case["pdf"])
    expected = {item["rule_id"]: item["status"] for item in case["expected"]}
    for rule in semantic_rules:
        finding = judge_semantic(rule, pages)
        judgments.append({
            "case": case["id"], "rule_id": rule["id"],
            "expected": expected[rule["id"]], "actual": finding["status"],
            "bid_page": finding["bid_page"], "bid_quote": finding["bid_quote"],
            "reason": finding["reason"],
        })

result = {
    "model": MODEL,
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "extracted_check_count": len(proposed),
    "extracted_checks": proposed,
    "semantic_judgments": judgments,
    "semantic_correct": sum(item["expected"] == item["actual"] for item in judgments),
    "semantic_total": len(judgments),
    "scope_note": "仅为公开招标文件和两份模拟投标文件上的开发验证",
}

output = ROOT / "tmp" / "deepseek-smoke.json"
output.parent.mkdir(exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"模型提取 {len(proposed)} 条有效检查项；技术响应 {result['semantic_correct']}/{len(judgments)} 与人工标注一致。")
print(f"详细结果：{output}")
