"""Local API for a traceable bid-document review workflow."""

import hashlib
import html
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from . import store
from .llm import available, judge_semantic, propose_checks, validate_check
from .pdf_text import MAX_BYTES, read_pdf
from .rules import numeric, presence


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
EVALUATION = json.loads((FIXTURES / "evaluation.json").read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.initialize()
    yield


app = FastAPI(title="标尺 · 投标文件自查", version="0.1.0", lifespan=lifespan)


class ReviewCreate(BaseModel):
    tender_id: str
    bid_id: str
    source_mode: str = "demo"


def public_document(document: dict) -> dict:
    return {
        "id": document["id"], "name": document["name"], "kind": document["kind"],
        "sha256": document["sha256"],
        "page_count": len(document["pages"]) if "pages" in document else document["page_count"],
        "created_at": document["created_at"],
    }


def require_document(document_id: str) -> dict:
    document = store.get_document(document_id)
    if document is None:
        raise HTTPException(404, "找不到文件")
    return document


def require_review(review_id: str) -> dict:
    review = store.get_review(review_id)
    if review is None:
        raise HTTPException(404, "找不到审核记录")
    return review


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@app.get("/api/health")
def health():
    return {"ok": True, "model_available": available(), "model_name": "DeepSeek" if available() else None}


@app.get("/api/documents")
def documents():
    return [public_document(item) for item in store.list_documents()]


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), kind: str = Form(...)):
    if kind not in {"tender", "bid"}:
        raise HTTPException(400, "文件类型须为招标文件或投标文件")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "请上传 PDF 文件")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(400, "PDF 超过 25 MB，请先拆分文件")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "文件不是有效的 PDF")
    path = store.UPLOAD_DIR / f"{hashlib.sha256(content).hexdigest()}.pdf"
    path.write_bytes(content)
    try:
        pages = read_pdf(path)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    document = store.add_document(file.filename or "未命名.pdf", kind, sha256(path), path, pages)
    return public_document(document)


@app.post("/api/demo/load")
def load_demo():
    source = FIXTURES / EVALUATION["source"]["pdf"]
    paths = [source, *(FIXTURES / case["pdf"] for case in EVALUATION["cases"])]
    kinds = ["tender", "bid", "bid"]
    result = []
    for path, kind in zip(paths, kinds):
        digest = sha256(path)
        existing = next((item for item in store.list_documents() if item["sha256"] == digest and item["kind"] == kind), None)
        if existing:
            result.append(public_document(existing))
        else:
            result.append(public_document(store.add_document(path.name, kind, digest, path, read_pdf(path))))
    return {"tender": result[0], "compliant": result[1], "flawed": result[2]}


@app.get("/api/documents/{document_id}")
def document_detail(document_id: str):
    return public_document(require_document(document_id))


@app.get("/api/documents/{document_id}/pages/{page_number}")
def document_page(document_id: str, page_number: int):
    document = require_document(document_id)
    if not 1 <= page_number <= len(document["pages"]):
        raise HTTPException(404, "页码超出范围")
    return {"page": page_number, "text": document["pages"][page_number - 1]}


@app.get("/api/documents/{document_id}/file")
def document_file(document_id: str):
    document = require_document(document_id)
    return FileResponse(document["path"], media_type="application/pdf", filename=document["name"],
                        content_disposition_type="inline")


@app.post("/api/reviews")
def create_review(payload: ReviewCreate):
    tender = require_document(payload.tender_id)
    bid = require_document(payload.bid_id)
    if tender["kind"] != "tender" or bid["kind"] != "bid":
        raise HTTPException(400, "请选择一份招标文件和一份投标文件")
    if payload.source_mode == "demo":
        if tender["sha256"] != sha256(FIXTURES / EVALUATION["source"]["pdf"]):
            raise HTTPException(400, "演示检查项只适用于内置招标文件")
        checks = [dict(rule, enabled=True) for rule in EVALUATION["rules"]]
    elif payload.source_mode == "model":
        try:
            checks = [dict(rule, enabled=True) for rule in propose_checks(tender["pages"])]
        except ValueError as exc:
            raise HTTPException(502, str(exc)) from exc
    else:
        raise HTTPException(400, "检查项来源无效")
    return store.add_review(tender["id"], bid["id"], payload.source_mode, checks)


@app.get("/api/reviews/{review_id}")
def review_detail(review_id: str):
    return require_review(review_id)


@app.put("/api/reviews/{review_id}/checks")
def confirm_checks(review_id: str, checks: list[dict] = Body(...)):
    review = require_review(review_id)
    tender = require_document(review["tender_id"])
    if not 1 <= len(checks) <= 20:
        raise HTTPException(400, "请保留 1 至 20 条检查项")
    ids = [item.get("id") for item in checks]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, "检查项编号重复")
    try:
        for check in checks:
            validate_check(check, tender["pages"])
            check["enabled"] = bool(check.get("enabled", True))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return store.save_checks(review_id, checks)


@app.post("/api/reviews/{review_id}/run")
def run_review(review_id: str):
    review = require_review(review_id)
    if not review["confirmed"]:
        raise HTTPException(400, "请先确认检查项")
    bid = require_document(review["bid_id"])
    findings = []
    for check in review["checks"]:
        if not check.get("enabled", True):
            continue
        if check["category"] == "document_presence":
            finding = presence(check, bid["pages"])
        elif check["category"] == "numeric":
            finding = numeric(check, bid["pages"])
        else:
            try:
                finding = judge_semantic(check, bid["pages"])
            except ValueError as exc:
                from .rules import base_finding, candidates
                finding = base_finding(check, "需人工复核", f"模型调用失败：{exc}", hits=candidates(check, bid["pages"]))
        findings.append(finding)
    return store.save_findings(review_id, findings)


@app.get("/api/reviews/{review_id}/evaluation")
def evaluate_review(review_id: str):
    review = require_review(review_id)
    if review["findings"] is None:
        raise HTTPException(400, "请先运行审核")
    bid = require_document(review["bid_id"])
    case = next((case for case in EVALUATION["cases"] if sha256(FIXTURES / case["pdf"]) == bid["sha256"]), None)
    if case is None or review["source_mode"] != "demo":
        raise HTTPException(400, "这份审核没有人工标注的演示答案")
    expected = {item["rule_id"]: item["status"] for item in case["expected"]}
    rows = [
        {"rule_id": item["rule_id"], "expected": expected[item["rule_id"]], "actual": item["status"],
         "correct": expected[item["rule_id"]] == item["status"]}
        for item in review["findings"] if item["rule_id"] in expected
    ]
    return {"case": case["id"], "total": len(rows), "correct": sum(row["correct"] for row in rows), "rows": rows,
            "note": "仅用于两份模拟样本，不代表真实标书准确率"}


@app.get("/api/reviews/{review_id}/report.json")
def report_json(review_id: str):
    review = require_review(review_id)
    if review["findings"] is None:
        raise HTTPException(400, "请先运行审核")
    return {
        "review_id": review_id,
        "tender": public_document(require_document(review["tender_id"])),
        "bid": public_document(require_document(review["bid_id"])),
        "findings": review["findings"],
        "generated_at": review["updated_at"],
    }


@app.get("/api/reviews/{review_id}/report.html", response_class=HTMLResponse)
def report_html(review_id: str):
    report = report_json(review_id)
    lines = []
    for finding in report["findings"]:
        source = "；".join(finding["source_quotes"])
        bid = finding.get("bid_quote") or "未找到可引用的投标原文"
        bid_page = f"PDF 第 {finding['bid_page']} 页" if finding.get("bid_page") else "待人工定位"
        bid_label = "投标候选原文" if finding["status"] == "需人工复核" else "投标文件"
        lines.append(
            "<article><div class='top'><h2>" + html.escape(finding["name"]) + "</h2><strong>" + html.escape(finding["status"]) + "</strong></div>"
            + "<p>" + html.escape(finding["reason"]) + "</p>"
            + "<div class='evidence'><section><small>招标文件 · PDF 第 " + str(finding["source_page"]) + " 页</small><blockquote>" + html.escape(source) + "</blockquote></section>"
            + "<section><small>" + bid_label + " · " + html.escape(bid_page) + "</small><blockquote>" + html.escape(bid) + "</blockquote></section></div></article>"
        )
    title = html.escape(report["bid"]["name"])
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>标尺审核报告</title>
    <style>body{font-family:'Microsoft YaHei',sans-serif;color:#213347;max-width:980px;margin:40px auto;padding:0 24px;background:#f7f9fb}
    header{border-bottom:2px solid #1d5c76;padding-bottom:20px;margin-bottom:28px}h1{font-size:28px;margin:0 0 10px}h2{font-size:17px;margin:0}
    article{background:white;border:1px solid #dce4e9;margin:14px 0;padding:20px;break-inside:avoid}.top{display:flex;justify-content:space-between;gap:20px}
    strong{color:#1d5c76}.evidence{display:grid;grid-template-columns:1fr 1fr;gap:16px}section{background:#f3f7f9;padding:14px}
    small{color:#577085}blockquote{margin:10px 0 0;line-height:1.7}p{line-height:1.6;color:#42576a}
    @media print{body{background:white;margin:10mm auto}article{border-color:#cbd4db}button{display:none}}
    </style><header><h1>投标文件自查报告</h1><div>""" + title + """</div><p>逐项结果供提交前复核；未找到证据不等于确认缺失。</p>
    <button onclick="window.print()">打印或保存为 PDF</button></header>""" + "".join(lines) + "</html>"
