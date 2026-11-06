"""Read text PDFs while preserving physical page numbers."""

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


MAX_PAGES = 300
MAX_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class Chunk:
    page: int
    text: str


def read_pdf(path: Path) -> list[str]:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("PDF 超过 25 MB，请先拆分文件")
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise ValueError("文件不是有效的 PDF")
    try:
        with pdfplumber.open(path) as pdf:
            if not 1 <= len(pdf.pages) <= MAX_PAGES:
                raise ValueError("PDF 页数须在 1 到 300 页之间")
            pages = [page.extract_text() or "" for page in pdf.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("无法读取 PDF，请检查文件是否损坏或已加密") from exc
    text = "".join(pages)
    readable = sum(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in text)
    if readable < 80 or "\ufffd" in text or readable / max(len(text), 1) < 0.3:
        raise ValueError("无法提取足够的文字；首版仅支持可复制文字的 PDF")
    return pages


def split_pages(pages: list[str], max_chars: int = 500) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_number, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        batch: list[str] = []
        size = 0
        for line in lines:
            if batch and size + len(line) > max_chars:
                chunks.append(Chunk(page_number, "\n".join(batch)))
                batch, size = [], 0
            batch.append(line)
            size += len(line)
        if batch:
            chunks.append(Chunk(page_number, "\n".join(batch)))
    return chunks


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()
