from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.kb import FAQKnowledgeBase, normalize_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


DEFAULT_FAQ_PATH = Path(__file__).resolve().parent.parent / "data" / "faq.json"
DEFAULT_DIRECT_RESPONSE_THRESHOLD = 0.58
MIN_RELEVANT_MATCH = 0.25
KEYWORD_MATCH_DIRECT_THRESHOLD = 0.42
PRIORITY_FAQ_CATEGORIES = {"senha", "pagamento", "cancelamento"}

CATEGORY_HINTS = {
    "senha": ["senha", "login", "acesso", "credencial"],
    "pagamento": ["pagamento", "cartao", "pix", "boleto", "metodo"],
    "cobranca": ["cobranca", "cobrado", "estorno", "reembolso", "duplicada", "fatura"],
    "cancelamento": ["cancelar", "cancelamento", "encerrar", "assinatura"],
    "planos": ["plano", "upgrade", "downgrade", "starter", "pro", "enterprise"],
    "conta": ["conta", "perfil", "email", "e-mail", "usuario"],
    "tecnico": ["erro", "bug", "falha", "nao funciona", "suporte", "problema"],
}

NEGATIVE_TONE_HINTS = [
    "revoltado",
    "frustrado",
    "urgente",
    "absurdo",
    "nao funciona",
    "problema",
    "erro",
    "cobrado duas vezes",
]

URGENT_TONE_HINTS = ["agora", "urgente", "imediato", "hoje"]
POLITE_TONE_HINTS = ["por favor", "gostaria", "poderia", "obrigado", "obrigada"]

NEXT_STEP_BY_CATEGORY = {
    "senha": "Validar identidade do cliente e confirmar se o fluxo de redefinicao foi concluido com sucesso.",
    "pagamento": "Conferir metodo de pagamento atual e revisar falhas de aprovacao recentes.",
    "cobranca": "Analisar o historico financeiro da conta e verificar necessidade de estorno ou ajuste.",
    "cancelamento": "Confirmar o status da assinatura e alinhar efeitos do cancelamento no acesso e na cobranca.",
    "planos": "Revisar plano atual, restricoes e regras de migracao antes de orientar o cliente.",
    "conta": "Validar dados da conta e orientar o ajuste de credenciais ou informacoes cadastrais.",
    "tecnico": "Coletar contexto do erro, passos para reproduzir e evidencias para investigacao.",
}

_kb: FAQKnowledgeBase | None = None


def _get_faq_path() -> Path:
    """Resolve o caminho da FAQ a partir do ambiente ou do default local."""
    configured_path = os.getenv("FAQ_PATH", str(DEFAULT_FAQ_PATH))
    return Path(configured_path)


def _get_kb() -> FAQKnowledgeBase:
    """Carrega a base FAQ uma unica vez por processo."""
    global _kb
    if _kb is None:
        _kb = FAQKnowledgeBase(_get_faq_path())
    return _kb


def get_kb_entry_count() -> int:
    """Retorna a quantidade de entradas atualmente carregadas na FAQ."""
    return len(_get_kb())


def get_direct_response_threshold() -> float:
    """Le o threshold de resposta direta com fallback seguro."""
    configured = os.getenv("FAQ_DIRECT_RESPONSE_THRESHOLD")
    if configured:
        try:
            return float(configured)
        except ValueError:
            return DEFAULT_DIRECT_RESPONSE_THRESHOLD
    return DEFAULT_DIRECT_RESPONSE_THRESHOLD


def _clean_text(value: Any, fallback: str = "") -> str:
    """Normaliza valores de entrada para texto simples."""
    if value is None:
        return fallback
    cleaned = " ".join(str(value).split())
    return cleaned or fallback


def _infer_category(text: str, fallback: str = "tecnico") -> str:
    """Infere uma categoria basica a partir de palavras-chave."""
    normalized = normalize_text(text)
    for category, hints in CATEGORY_HINTS.items():
        if any(hint in normalized for hint in hints):
            return category
    return fallback


def _has_category_keyword_match(text: str, category: str) -> bool:
    """Verifica se a mensagem contem palavras-chave da categoria informada."""
    normalized = normalize_text(text)
    return any(hint in normalized for hint in CATEGORY_HINTS.get(category, []))


def _rank_results(query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioriza resultados da FAQ com match de palavra-chave na categoria."""
    return sorted(
        results,
        key=lambda item: (
            _has_category_keyword_match(query, item["categoria"]),
            item["confianca"],
        ),
        reverse=True,
    )


def _infer_tone(text: str) -> str:
    """Infere o tom do cliente por heuristica simples."""
    normalized = normalize_text(text)

    if any(hint in normalized for hint in NEGATIVE_TONE_HINTS):
        return "frustrado"

    if any(hint in normalized for hint in URGENT_TONE_HINTS):
        return "urgente"

    if any(hint in normalized for hint in POLITE_TONE_HINTS):
        return "educado"

    return "neutro"


def _default_next_step(category: str) -> str:
    """Devolve o proximo passo padrao para a categoria informada."""
    return NEXT_STEP_BY_CATEGORY.get(
        category,
        "Revisar o caso manualmente e orientar o cliente com o proximo passo correto.",
    )


def buscar_faq(query: str) -> dict[str, Any]:
    """Busca na FAQ e devolve um payload estruturado para o agente."""
    cleaned_query = _clean_text(query)
    if not cleaned_query:
        return {
            "encontrada": False,
            "mensagem": "Consulta vazia. E necessario informar a duvida do cliente.",
            "recomenda_resposta_direta": False,
            "threshold_resposta_direta": get_direct_response_threshold(),
            "resultados": [],
        }

    results = _get_kb().search(cleaned_query, top_k=3)
    if not results:
        return {
            "encontrada": False,
            "mensagem": "Nenhuma resposta relevante encontrada na FAQ.",
            "recomenda_resposta_direta": False,
            "threshold_resposta_direta": get_direct_response_threshold(),
            "resultados": [],
        }

    ranked_results = _rank_results(cleaned_query, results)
    best_result = ranked_results[0]
    threshold = get_direct_response_threshold()
    keyword_match = _has_category_keyword_match(cleaned_query, best_result["categoria"])
    priority_keyword_match = (
        keyword_match
        and best_result["categoria"] in PRIORITY_FAQ_CATEGORIES
        and best_result["confianca"] >= MIN_RELEVANT_MATCH
    )
    has_relevant_match = keyword_match or best_result["confianca"] >= MIN_RELEVANT_MATCH
    recommends_direct_response = (
        best_result["confianca"] >= threshold
        or (keyword_match and best_result["confianca"] >= KEYWORD_MATCH_DIRECT_THRESHOLD)
        or priority_keyword_match
    )

    return {
        "encontrada": has_relevant_match,
        "mensagem": (
            "FAQ relevante encontrada."
            if has_relevant_match
            else "Nenhuma resposta suficientemente aderente encontrada na FAQ."
        ),
        "recomenda_resposta_direta": recommends_direct_response,
        "threshold_resposta_direta": threshold,
        "keyword_match": keyword_match,
        "melhor_resultado": best_result if has_relevant_match else None,
        "resultados": ranked_results if has_relevant_match else [],
    }


def criar_ticket(
    categoria: str,
    tom: str,
    resumo: str,
    proximo_passo: str,
) -> dict[str, Any]:
    """Cria um ticket defensivo a partir dos campos recebidos da LLM."""
    cleaned_summary = _clean_text(resumo, fallback="Cliente pediu atendimento humano.")
    resolved_category = _clean_text(categoria) or _infer_category(cleaned_summary)
    resolved_tone = _clean_text(tom) or _infer_tone(cleaned_summary)
    resolved_step = _clean_text(proximo_passo) or _default_next_step(resolved_category)
    ticket_id = f"TK-{secrets.randbelow(90000) + 10000}"

    return {
        "ticket_id": ticket_id,
        "status": "criado",
        "categoria": resolved_category,
        "tom": resolved_tone,
        "resumo": cleaned_summary,
        "proximo_passo_sugerido": resolved_step,
        "mensagem": (
            f"Ticket {ticket_id} criado com sucesso. "
            "Um atendente humano vai analisar o caso em seguida."
        ),
    }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_faq",
            "description": (
                "OBRIGATORIO: Voce DEVE usar esta ferramenta PRIMEIRO para QUALQUER pergunta do utilizador, "
                "especialmente sobre senhas, acessos, pagamentos ou cancelamentos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pergunta ou problema do cliente, em texto claro.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_ticket",
            "description": (
                "ULTIMO RECURSO: PROIBIDO usar esta ferramenta a menos que voce JA TENHA usado a "
                "'buscar_faq' e nao tenha encontrado a resposta. Nao use para problemas de senha "
                "ou cancelamento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {
                        "type": "string",
                        "description": "Categoria principal do caso, como senha, pagamento, cobranca, cancelamento ou tecnico.",
                    },
                    "tom": {
                        "type": "string",
                        "description": "Tom do cliente, como neutro, educado, frustrado ou urgente.",
                    },
                    "resumo": {
                        "type": "string",
                        "description": "Resumo objetivo do problema em uma frase curta.",
                    },
                    "proximo_passo": {
                        "type": "string",
                        "description": "Sugestao objetiva para o atendente humano continuar o caso.",
                    },
                },
                "required": ["categoria", "tom", "resumo", "proximo_passo"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "buscar_faq": buscar_faq,
    "criar_ticket": criar_ticket,
}
