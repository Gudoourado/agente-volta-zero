from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

from agent.agent import AgentResponse, SupportAgent


st.set_page_config(
    page_title="Sunter — Volta Zero",
    page_icon="💬",
    layout="centered",
)

MAX_AGENT_HISTORY_MESSAGES = 6


def init_state() -> None:
    """Inicializa o estado minimo da interface."""
    st.session_state.setdefault("messages", [])


def get_secret(name: str, default: str = "") -> str:
    """Le uma chave do st.secrets com fallback silencioso."""
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def resolve_api_key() -> str:
    """Resolve a chave da Groq via Streamlit Cloud ou ambiente local."""
    return get_secret("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY", "").strip()


def resolve_model() -> str:
    """Resolve o modelo padrao via secrets ou variavel de ambiente."""
    return get_secret("GROQ_MODEL") or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()


@st.cache_resource(show_spinner=False)
def get_agent(api_key: str, model: str) -> SupportAgent:
    """Instancia o agente apenas uma vez por combinacao chave-modelo."""
    return SupportAgent(api_key=api_key, model=model)


def best_match(tool_log: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extrai o melhor match de FAQ a partir do log de ferramentas."""
    for item in tool_log:
        if item.get("ferramenta") != "buscar_faq":
            continue

        result = item.get("resultado", {})
        if isinstance(result.get("melhor_resultado"), dict):
            return result["melhor_resultado"]

        results = result.get("resultados")
        if isinstance(results, list) and results:
            return results[0]

    return None


def render_ticket(ticket: dict[str, Any]) -> None:
    """Exibe os detalhes do ticket em um expander discreto."""
    with st.expander(f"Ver ticket {ticket['ticket_id']}", expanded=False):
        first_col, second_col = st.columns(2)

        with first_col:
            st.write("**Categoria**")
            st.write(ticket["categoria"])

        with second_col:
            st.write("**Tom**")
            st.write(ticket["tom"])

        st.write("**Resumo**")
        st.write(ticket["resumo"])

        st.write("**Proximo passo sugerido**")
        st.write(ticket["proximo_passo_sugerido"])


def render_message(message: dict[str, Any]) -> None:
    """Renderiza uma mensagem do chat e seus metadados secundarios."""
    role = message["role"]
    avatar = "👤" if role == "user" else "🛟"

    with st.chat_message(role, avatar=avatar):
        st.markdown(message["content"])

        if role != "assistant":
            return

        status = message.get("status")
        ticket = message.get("ticket")
        match = best_match(message.get("tool_log", []))

        if status == "answered" and match:
            st.caption(
                f"Resposta automatica com base na FAQ: {match['pergunta']} ({match['confianca']:.0%} de aderencia)."
            )
        elif status == "escalated":
            st.caption("Caso encaminhado para atendimento humano.")
        elif status == "error":
            st.caption("Nao foi possivel concluir automaticamente.")

        if ticket:
            render_ticket(ticket)


def append_assistant_message(result: AgentResponse) -> None:
    """Persiste a resposta do agente no historico da sessao."""
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": result.content,
            "status": result.status,
            "tool_log": result.tool_log,
            "ticket": result.ticket,
            "error_type": result.error_type,
        }
    )


def build_agent_messages() -> list[dict[str, str]]:
    """Monta um historico curto e compativel para envio ao agente."""
    clean_messages: list[dict[str, str]] = []

    for message in st.session_state.get("messages", []):
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue

        cleaned_content = content.strip()
        if cleaned_content:
            clean_messages.append({"role": role, "content": cleaned_content})

    return clean_messages[-MAX_AGENT_HISTORY_MESSAGES:]


def main() -> None:
    """Executa a interface principal de chat."""
    init_state()

    st.title("Sunter — Volta Zero")
    st.caption(
        "Agente de primeiro atendimento para responder perguntas simples e escalar casos que exigem contexto humano."
    )

    api_key = resolve_api_key()
    model = resolve_model()
    agent_available = bool(api_key)

    if not st.session_state["messages"]:
        if agent_available:
            st.info("A conversa esta pronta. Envie a primeira mensagem do cliente.")
        else:
            st.info("O agente esta temporariamente indisponivel.")

    for message in st.session_state["messages"]:
        render_message(message)

    prompt = st.chat_input(
        "Descreva a duvida do cliente...",
        disabled=not agent_available,
    )

    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Analisando a mensagem do cliente..."):
        result = get_agent(api_key, model).chat(build_agent_messages())

    append_assistant_message(result)
    st.rerun()


if __name__ == "__main__":
    main()
