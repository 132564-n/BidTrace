"""Small, inspectable Chinese text retrieval baseline."""

import math
import re
from collections import Counter

from .pdf_text import Chunk, normalized


def terms(value: str) -> list[str]:
    result: list[str] = []
    for part in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+|\d+(?:\.\d+)?", normalized(value)):
        if "\u4e00" <= part[0] <= "\u9fff":
            result.extend(part[index:index + 2] for index in range(max(len(part) - 1, 1)))
        else:
            result.append(part)
    return result


def search(query: str, chunks: list[Chunk], limit: int = 5) -> list[dict]:
    if not chunks:
        return []
    tokenized = [Counter(terms(chunk.text)) for chunk in chunks]
    query_terms = set(terms(query))
    document_frequency = Counter(term for doc in tokenized for term in doc)
    mean_length = sum(sum(doc.values()) for doc in tokenized) / len(tokenized)
    ranked: list[tuple[float, Chunk]] = []
    for chunk, doc in zip(chunks, tokenized):
        length = sum(doc.values())
        score = 0.0
        for term in query_terms:
            frequency = doc[term]
            if not frequency:
                continue
            inverse = math.log(1 + (len(chunks) - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / max(mean_length, 1)))
        if score:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        {"page": chunk.page, "text": chunk.text, "score": round(score, 3)}
        for score, chunk in ranked[:limit]
    ]
