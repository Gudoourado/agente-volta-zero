from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    Groq,
    GroqError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from agent.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Voce e o Volta Zero, assistente virtual da Sunter, uma plataforma SaaS.

Seu trabalho e decidir com prudencia entre responder usando a FAQ ou escalar para um humano.

Regras de operacao:
- Se a mensagem for uma saudacao simples, responda cordialmente sem usar ferramenta.
- Para qualquer duvida operacional do cliente, use `buscar_faq` primeiro.
- REGRA DE OURO: NUNCA crie um ticket sem antes procurar no FAQ. Se o utilizador perguntar sobre senha, responda com o conteudo do FAQ e NAO crie ticket.
- Se a duvida for sobre Senha, Pagamento ou Cancelamento, USE a ferramenta `buscar_faq` obrigatoriamente antes de pensar em criar um ticket.
- Se `buscar_faq` indicar `recomenda_resposta_direta=true` e a FAQ cobrir a pergunta inteira, responda em portugues claro, objetivo e humano.
- Se houver match de palavra-chave e a FAQ trouxer uma resposta util sobre Senha, Pagamento ou Cancelamento, prefira responder com a FAQ.
- Se `buscar_faq` indicar baixa confianca, se a FAQ cobrir apenas parte do problema, se houver pedido financeiro sensivel, multiplas intencoes, ou frustracao, use `criar_ticket`.
- Apos criar um ticket, informe que o caso foi encaminhado e evite pedir novos dados desnecessarios.

Regras de seguranca:
- NUNCA invente politica, prazo, valor ou compensacao.
- NUNCA responda como se soubesse algo fora da FAQ.
- Na duvida, escale.

Tom:
- Profissional, empatico e conciso.
- Sempre em portugues.
"""

DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TEMPERATURE = 0.2
MAX_TOOL_ROUNDS = 4
MAX_HISTORY_MESSAGES = 6


@dataclass
class AgentResponse:
    """Resposta estruturada para a camada de interface."""
    content: str
    status: str
    tool_log: list[dict[str, Any]]
    ticket: dict[str, Any] | None = None
    error_type: str | None = None


class SupportAgent:
    """Agente de atendimento com tool calling nativo via Groq."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Configura o cliente Groq com chave e modelo resolvidos."""
        resolved_key = (api_key or os.getenv("GROQ_API_KEY", "")).strip()
        if not resolved_key:
            raise ValueError("GROQ_API_KEY nao configurada.")

        self.model = (model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        self.client = Groq(api_key=resolved_key)

    def chat(self, messages: list[dict[str, Any]]) -> AgentResponse:
        """Executa o fluxo da conversa e devolve um resultado estruturado para a UI."""
        working_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        working_messages.extend(self._sanitize_messages(messages))

        tool_log: list[dict[str, Any]] = []
        latest_ticket: dict[str, Any] | None = None

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=working_messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=DEFAULT_TEMPERATURE,
                )
            except Exception as exc:
                return self._handle_api_exception(exc, tool_log)

            message = response.choices[0].message
            tool_calls = list(message.tool_calls or [])

            if not tool_calls:
                final_content = (message.content or "").strip()
                if not final_content:
                    final_content = self._fallback_message(latest_ticket)

                return AgentResponse(
                    content=final_content,
                    status="escalated" if latest_ticket else "answered",
                    tool_log=tool_log,
                    ticket=latest_ticket,
                )

            assistant_tool_message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in tool_calls
                ],
            }
            if message.content is not None:
                assistant_tool_message["content"] = message.content

            working_messages.append(assistant_tool_message)

            for tool_call in tool_calls:
                print(f"Ferramenta escolhida pela IA: {tool_call.function.name}")
                result_payload, log_entry = self._execute_tool_call(tool_call)
                tool_log.append(log_entry)

                if (
                    log_entry["ferramenta"] == "criar_ticket"
                    and log_entry["sucesso"]
                    and result_payload.get("status") == "criado"
                ):
                    latest_ticket = result_payload

                working_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result_payload, ensure_ascii=False),
                    }
                )

        return AgentResponse(
            content=self._fallback_message(latest_ticket),
            status="escalated" if latest_ticket else "error",
            tool_log=tool_log,
            ticket=latest_ticket,
            error_type=None if latest_ticket else "tool_loop",
        )

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Mantem apenas historico textual compativel, sem resquicios de tool calling."""
        clean_messages: list[dict[str, str]] = []

        for message in messages:
            role = message.get("role")

            if role == "tool":
                continue

            if role == "assistant" and message.get("tool_calls"):
                continue

            raw_content = message.get("content")
            if not isinstance(raw_content, str):
                continue

            content = raw_content.strip()
            if not content:
                continue

            if role == "user":
                clean_messages.append({"role": "user", "content": content})
                continue

            if role == "assistant":
                clean_messages.append({"role": "assistant", "content": content})

        return clean_messages[-MAX_HISTORY_MESSAGES:]

    def _execute_tool_call(self, tool_call: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """Executa uma tool call devolvendo payload e log estruturado."""
        function_name = tool_call.function.name or "desconhecida"
        raw_arguments = tool_call.function.arguments or "{}"

        try:
            parsed_arguments = json.loads(raw_arguments)
            if not isinstance(parsed_arguments, dict):
                raise TypeError("Argumentos da ferramenta devem ser um objeto JSON.")
        except Exception as exc:
            parsed_arguments = {}
            result_payload = {"erro": f"Argumentos invalidos para {function_name}: {exc}"}
            return result_payload, {
                "ferramenta": function_name,
                "argumentos": parsed_arguments,
                "resultado": result_payload,
                "sucesso": False,
            }

        function = TOOL_FUNCTIONS.get(function_name)
        if function is None:
            result_payload = {"erro": f"Ferramenta '{function_name}' nao encontrada."}
            return result_payload, {
                "ferramenta": function_name,
                "argumentos": parsed_arguments,
                "resultado": result_payload,
                "sucesso": False,
            }

        try:
            raw_result = function(**parsed_arguments)
            if not isinstance(raw_result, dict):
                raise TypeError("Ferramentas devem retornar um objeto dict.")
            result_payload = raw_result
            success = "erro" not in result_payload
        except Exception as exc:
            logger.exception("Erro ao executar a ferramenta %s", function_name)
            result_payload = {"erro": f"Erro ao executar {function_name}: {exc}"}
            success = False

        return result_payload, {
            "ferramenta": function_name,
            "argumentos": parsed_arguments,
            "resultado": result_payload,
            "sucesso": success,
        }

    def _handle_api_exception(
        self,
        exc: Exception,
        tool_log: list[dict[str, Any]],
    ) -> AgentResponse:
        """Traduz erros do SDK Groq para mensagens amigaveis da aplicacao."""
        logger.exception("Erro na API Groq")

        if isinstance(exc, AuthenticationError):
            return AgentResponse(
                content=(
                    "Nao consegui autenticar na Groq com a chave atual. "
                    "Atualize a GROQ_API_KEY para continuar."
                ),
                status="error",
                tool_log=tool_log,
                error_type="auth",
            )

        if isinstance(exc, RateLimitError):
            return AgentResponse(
                content=(
                    "O limite de requisicoes da Groq foi atingido. "
                    "Aguarde alguns instantes e tente novamente."
                ),
                status="error",
                tool_log=tool_log,
                error_type="rate_limit",
            )

        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return AgentResponse(
                content=(
                    "Nao foi possivel falar com a Groq agora. "
                    "Verifique a conexao e tente novamente em instantes."
                ),
                status="error",
                tool_log=tool_log,
                error_type="connection",
            )

        if isinstance(exc, PermissionDeniedError):
            return AgentResponse(
                content="A chave atual nao tem permissao para usar este recurso na Groq.",
                status="error",
                tool_log=tool_log,
                error_type="permission",
            )

        if isinstance(exc, BadRequestError):
            return AgentResponse(
                content=(
                    "A requisicao para a Groq foi rejeitada. "
                    "Revise o modelo configurado ou os parametros enviados."
                ),
                status="error",
                tool_log=tool_log,
                error_type="bad_request",
            )

        if isinstance(exc, InternalServerError):
            return AgentResponse(
                content="A Groq reportou uma falha interna temporaria. Tente novamente em breve.",
                status="error",
                tool_log=tool_log,
                error_type="server",
            )

        if isinstance(exc, APIStatusError):
            return AgentResponse(
                content=(
                    f"A Groq devolveu um erro HTTP {exc.status_code}. "
                    "Tente novamente ou revise a configuracao atual."
                ),
                status="error",
                tool_log=tool_log,
                error_type="api_status",
            )

        if isinstance(exc, GroqError):
            return AgentResponse(
                content="Ocorreu uma falha inesperada ao usar a Groq. Tente novamente em instantes.",
                status="error",
                tool_log=tool_log,
                error_type="groq_error",
            )

        return AgentResponse(
            content="Ocorreu um erro inesperado ao processar a mensagem. Tente novamente.",
            status="error",
            tool_log=tool_log,
            error_type="unknown",
        )

    @staticmethod
    def _fallback_message(ticket: dict[str, Any] | None) -> str:
        """Devolve a mensagem final segura quando o fluxo nao fecha limpo."""
        if ticket:
            return (
                "Encaminhei o caso para atendimento humano e deixei um ticket estruturado para agilizar o retorno."
            )
        return (
            "Nao consegui concluir a solicitacao com seguranca agora. "
            "Tente novamente ou encaminhe o caso para um atendente humano."
        )
