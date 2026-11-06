"""Small SQLite persistence layer for documents and review sessions."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "review.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize() -> None:
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('tender','bid')),
            sha256 TEXT NOT NULL,
            path TEXT NOT NULL,
            pages_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            tender_id TEXT NOT NULL REFERENCES documents(id),
            bid_id TEXT NOT NULL REFERENCES documents(id),
            source_mode TEXT NOT NULL,
            checks_json TEXT NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 0,
            findings_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)


def add_document(name: str, kind: str, sha256: str, path: Path, pages: list[str]) -> dict:
    document = {
        "id": uuid4().hex,
        "name": name,
        "kind": kind,
        "sha256": sha256,
        "path": str(path),
        "pages": pages,
        "created_at": now(),
    }
    with connection() as db:
        db.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?)",
            (document["id"], name, kind, sha256, str(path), json.dumps(pages, ensure_ascii=False), document["created_at"]),
        )
    return document


def list_documents() -> list[dict]:
    with connection() as db:
        rows = db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(row) | {"page_count": len(json.loads(row["pages_json"]))} for row in rows]


def get_document(document_id: str) -> dict | None:
    with connection() as db:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if row is None:
        return None
    document = dict(row)
    document["pages"] = json.loads(document.pop("pages_json"))
    return document


def add_review(tender_id: str, bid_id: str, source_mode: str, checks: list[dict]) -> dict:
    review_id = uuid4().hex
    timestamp = now()
    with connection() as db:
        db.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?)",
            (review_id, tender_id, bid_id, source_mode, json.dumps(checks, ensure_ascii=False), 0, None, timestamp, timestamp),
        )
    return get_review(review_id)


def get_review(review_id: str) -> dict | None:
    with connection() as db:
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    if row is None:
        return None
    review = dict(row)
    review["checks"] = json.loads(review.pop("checks_json"))
    review["findings"] = json.loads(review.pop("findings_json")) if review["findings_json"] else None
    review["confirmed"] = bool(review["confirmed"])
    return review


def save_checks(review_id: str, checks: list[dict]) -> dict:
    with connection() as db:
        db.execute(
            "UPDATE reviews SET checks_json=?, confirmed=1, findings_json=NULL, updated_at=? WHERE id=?",
            (json.dumps(checks, ensure_ascii=False), now(), review_id),
        )
    return get_review(review_id)


def save_findings(review_id: str, findings: list[dict]) -> dict:
    with connection() as db:
        db.execute(
            "UPDATE reviews SET findings_json=?, updated_at=? WHERE id=?",
            (json.dumps(findings, ensure_ascii=False), now(), review_id),
        )
    return get_review(review_id)
