import pytest
from fastapi.testclient import TestClient

from app import store
from app import llm
from app.main import EVALUATION, FIXTURES, app
from app.pdf_text import read_pdf
from app.rules import candidates


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "review.sqlite3")
    with TestClient(app) as api:
        yield api


def test_demo_review_matches_manual_labels_for_eight_program_checks(client):
    documents = client.post("/api/demo/load").json()
    assert documents["tender"]["page_count"] == 70
    assert "inline" in client.get(f"/api/documents/{documents['flawed']['id']}/file").headers["content-disposition"]
    correct_total = 0

    for case in EVALUATION["cases"]:
        bid = documents[case["id"]]
        response = client.post("/api/reviews", json={
            "tender_id": documents["tender"]["id"], "bid_id": bid["id"], "source_mode": "demo"
        })
        assert response.status_code == 200, response.text
        review = response.json()
        assert client.post(f"/api/reviews/{review['id']}/run").status_code == 400
        confirmed = client.put(f"/api/reviews/{review['id']}/checks", json=review["checks"])
        assert confirmed.status_code == 200, confirmed.text
        run = client.post(f"/api/reviews/{review['id']}/run")
        assert run.status_code == 200, run.text
        findings = {item["rule_id"]: item for item in run.json()["findings"]}
        expected = {item["rule_id"]: item for item in case["expected"]}
        for rule in EVALUATION["rules"]:
            if rule["category"] == "semantic":
                assert findings[rule["id"]]["status"] == "需人工复核"
            else:
                assert findings[rule["id"]]["status"] == expected[rule["id"]]["status"]
            if findings[rule["id"]]["bid_page"]:
                page = client.get(f"/api/documents/{bid['id']}/pages/{findings[rule['id']]['bid_page']}").json()
                assert findings[rule["id"]]["bid_quote"] in page["text"]

        report = client.get(f"/api/reviews/{review['id']}/report.json")
        assert report.status_code == 200
        assert len(report.json()["findings"]) == 10
        assert "打印或保存为 PDF" in client.get(f"/api/reviews/{review['id']}/report.html").text
        evaluation = client.get(f"/api/reviews/{review['id']}/evaluation").json()
        assert evaluation["total"] == 10
        assert evaluation["correct"] >= 8
        correct_total += evaluation["correct"]
    assert correct_total == 17


def test_retrieval_finds_both_semantic_evidence_pages():
    rules = {item["id"]: item for item in EVALUATION["rules"]}
    for case in EVALUATION["cases"]:
        pages = read_pdf(FIXTURES / case["pdf"])
        labels = {item["rule_id"]: item for item in case["expected"]}
        for rule_id in ("R09", "R10"):
            hits = candidates(rules[rule_id], pages)
            assert any(hit["page"] == labels[rule_id]["bid_page"] for hit in hits)


def test_upload_rejects_non_pdf(client):
    response = client.post("/api/documents", data={"kind": "bid"}, files={"file": ("bad.pdf", b"plain text", "application/pdf")})
    assert response.status_code == 400
    assert "有效的 PDF" in response.json()["detail"]


def test_model_proposal_discards_unverifiable_source_quote(monkeypatch):
    pages = read_pdf(FIXTURES / EVALUATION["source"]["pdf"])
    valid = dict(EVALUATION["rules"][9])
    invalid = dict(valid, id="R99", source_quotes=["这段招标原文并不存在"])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "completion", lambda *_: {"checks": [valid, invalid]})
    assert [item["id"] for item in llm.propose_checks(pages)] == ["R10"]


def test_model_proposal_deduplicates_same_numeric_requirement(monkeypatch):
    pages = read_pdf(FIXTURES / EVALUATION["source"]["pdf"])
    valid = dict(EVALUATION["rules"][4])
    duplicate = dict(valid, id="another-validity-check", name="投标有效期至少九十日", threshold="90")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "completion", lambda *_: {"checks": [valid, duplicate]})
    assert [item["id"] for item in llm.propose_checks(pages)] == [valid["id"]]


def test_semantic_verdict_requires_real_bid_quote(monkeypatch):
    pages = read_pdf(FIXTURES / EVALUATION["cases"][0]["pdf"])
    check = EVALUATION["rules"][8]
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "completion", lambda *_: {
        "status": "满足", "bid_page": 5, "bid_quote": "完全不存在的投标承诺", "reason": "已满足"
    })
    finding = llm.judge_semantic(check, pages)
    assert finding["status"] == "需人工复核"
    assert finding["bid_quote"] is None


def test_semantic_verdict_retries_unverifiable_quote(monkeypatch):
    pages = read_pdf(FIXTURES / EVALUATION["cases"][1]["pdf"])
    check = EVALUATION["rules"][8]
    exact_quote = "监测安排为每周一至周五收集数据，并在工作日编制《综合信息》。"
    responses = iter([
        {"status": "明确冲突", "bid_page": 5, "bid_quote": "工作日监测和编制综合信息", "reason": "原文不是逐字引用"},
        {"status": "明确冲突", "bid_page": 5, "bid_quote": exact_quote, "reason": "与每日含节假日的要求冲突"},
    ])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "completion", lambda *_: next(responses))
    finding = llm.judge_semantic(check, pages)
    assert finding["status"] == "明确冲突"
    assert finding["bid_page"] == 5
    assert finding["bid_quote"] == exact_quote


def test_model_extraction_rejects_silent_document_truncation(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    with pytest.raises(ValueError, match="超过首版模型检查范围"):
        llm.propose_checks(["招" * 60000])
