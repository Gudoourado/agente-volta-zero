from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.kb import FAQKnowledgeBase


def _write_faq(entries: list[dict], path: Path) -> Path:
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return path


SAMPLE_FAQ = [
    {
        "category": "senha",
        "question": "Como redefinir minha senha?",
        "answer": "Acesse a pagina de login e clique em Esqueci minha senha.",
    },
    {
        "category": "pagamento",
        "question": "Quais formas de pagamento sao aceitas?",
        "answer": "Cartao, boleto e Pix.",
    },
]


class TestFAQLoad:
    def test_loads_valid_faq(self, tmp_path):
        faq_path = _write_faq(SAMPLE_FAQ, tmp_path / "faq.json")
        kb = FAQKnowledgeBase(faq_path)
        assert len(kb.entries) == 2

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FAQKnowledgeBase(tmp_path / "missing.json")

    def test_raises_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON invalido"):
            FAQKnowledgeBase(bad)

    def test_raises_on_missing_fields(self, tmp_path):
        incomplete = [{"category": "x"}]
        faq_path = _write_faq(incomplete, tmp_path / "faq.json")
        with pytest.raises(ValueError, match="campos obrigatorios"):
            FAQKnowledgeBase(faq_path)


class TestFAQSearch:
    def test_exact_match_returns_high_score(self, tmp_path):
        faq_path = _write_faq(SAMPLE_FAQ, tmp_path / "faq.json")
        kb = FAQKnowledgeBase(faq_path)
        results = kb.search("Como redefinir minha senha?")
        assert len(results) > 0
        assert results[0]["confianca"] > 0.9
        assert results[0]["categoria"] == "senha"

    def test_normalizes_accents_and_case(self, tmp_path):
        faq_path = _write_faq(SAMPLE_FAQ, tmp_path / "faq.json")
        kb = FAQKnowledgeBase(faq_path)
        results = kb.search("COMO redefinir minha SENHA")
        assert results[0]["categoria"] == "senha"
        assert results[0]["confianca"] > 0.8

    def test_no_entries_returns_empty(self, tmp_path):
        faq_path = _write_faq([], tmp_path / "faq.json")
        kb = FAQKnowledgeBase(faq_path)
        assert kb.search("qualquer coisa") == []

    def test_top_k_limits_results(self, tmp_path):
        faq_path = _write_faq(SAMPLE_FAQ, tmp_path / "faq.json")
        kb = FAQKnowledgeBase(faq_path)
        results = kb.search("senha", top_k=1)
        assert len(results) == 1
