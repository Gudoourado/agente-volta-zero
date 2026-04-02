from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz


def normalize_text(text: str) -> str:
    """Normaliza texto para comparacao por similaridade."""
    normalized = unicodedata.normalize("NFKD", text)
    without_accents = normalized.encode("ascii", "ignore").decode("ascii")
    without_symbols = re.sub(r"[^a-zA-Z0-9\s]", " ", without_accents.lower())
    return re.sub(r"\s+", " ", without_symbols).strip()


@dataclass(frozen=True)
class FAQEntry:
    category: str
    question: str
    answer: str


class FAQKnowledgeBase:
    """Carrega e pesquisa a FAQ com normalizacao simples e score explicito."""

    def __init__(self, faq_path: str | Path) -> None:
        self.faq_path = Path(faq_path)
        self.entries = self._load_entries()

    def __len__(self) -> int:
        """Retorna a quantidade de entradas disponiveis."""
        return len(self.entries)

    def _load_entries(self) -> list[FAQEntry]:
        """Valida e carrega o arquivo JSON da FAQ."""
        if not self.faq_path.exists():
            raise FileNotFoundError(f"Arquivo FAQ nao encontrado: {self.faq_path}")

        try:
            with self.faq_path.open("r", encoding="utf-8") as file:
                raw_entries = json.load(file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido em {self.faq_path}: {exc}") from exc

        if not isinstance(raw_entries, list):
            raise ValueError(f"FAQ deve ser uma lista, recebeu {type(raw_entries).__name__}.")

        required_keys = {"category", "question", "answer"}
        entries: list[FAQEntry] = []

        for index, entry in enumerate(raw_entries):
            if not isinstance(entry, dict):
                raise ValueError(f"Entry {index} deve ser um objeto JSON.")

            missing = required_keys - entry.keys()
            if missing:
                raise ValueError(f"Entry {index} sem campos obrigatorios: {missing}")

            entries.append(
                FAQEntry(
                    category=str(entry["category"]).strip(),
                    question=str(entry["question"]).strip(),
                    answer=str(entry["answer"]).strip(),
                )
            )

        return entries

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Retorna as top_k entradas mais relevantes com score de 0 a 1."""
        normalized_query = normalize_text(query)
        if not normalized_query or not self.entries:
            return []

        results = []
        for entry in self.entries:
            normalized_question = normalize_text(entry.question)
            score = fuzz.token_set_ratio(normalized_query, normalized_question) / 100
            results.append(
                {
                    "pergunta": entry.question,
                    "resposta": entry.answer,
                    "categoria": entry.category,
                    "confianca": round(score, 2),
                }
            )

        results.sort(key=lambda item: item["confianca"], reverse=True)
        return results[:top_k]
