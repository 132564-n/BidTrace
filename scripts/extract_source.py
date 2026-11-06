from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "source" / "2025-信息化城市管理运行-招标文件.pdf"
OUTPUT = ROOT / "fixtures" / "source" / "2025-信息化城市管理运行-逐页文字.txt"


with pdfplumber.open(SOURCE) as pdf:
    pages = [
        f"===== PDF 第 {index} 页 =====\n{page.extract_text() or ''}"
        for index, page in enumerate(pdf.pages, start=1)
    ]

OUTPUT.write_text("\n\n".join(pages) + "\n", encoding="utf-8")
print(f"已提取 {len(pages)} 页到 {OUTPUT}")
