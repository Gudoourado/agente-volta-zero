from __future__ import annotations

from agent.tools import buscar_faq, criar_ticket, get_direct_response_threshold


class TestBuscarFAQ:
    def test_returns_results_for_known_question(self):
        result = buscar_faq("Como redefinir minha senha?")
        assert result["encontrada"] is True
        assert result["melhor_resultado"]["confianca"] > 0.8
        assert len(result["resultados"]) > 0

    def test_returns_not_found_for_unrelated_query(self):
        result = buscar_faq("zzzzz qqqqq wwwww")
        assert result["encontrada"] is False
        assert result["recomenda_resposta_direta"] is False

    def test_returns_threshold_metadata(self):
        result = buscar_faq("pagamento")
        assert result["threshold_resposta_direta"] == get_direct_response_threshold()


class TestCriarTicket:
    def test_creates_ticket_with_all_fields(self):
        ticket = criar_ticket(
            categoria="cobranca",
            tom="frustrado",
            resumo="Cliente relata cobranca duplicada.",
            proximo_passo="Verificar historico de pagamentos.",
        )
        assert ticket["status"] == "criado"
        assert ticket["categoria"] == "cobranca"
        assert ticket["tom"] == "frustrado"
        assert ticket["resumo"] == "Cliente relata cobranca duplicada."
        assert ticket["proximo_passo_sugerido"] == "Verificar historico de pagamentos."
        assert ticket["ticket_id"].startswith("TK-")

    def test_ticket_sanitizes_empty_fields(self):
        ticket = criar_ticket(
            categoria="",
            tom="",
            resumo="Fui cobrado duas vezes e quero ajuda.",
            proximo_passo="",
        )
        assert ticket["categoria"] == "cobranca"
        assert ticket["tom"] in {"frustrado", "urgente", "neutro"}
        assert ticket["proximo_passo_sugerido"]
