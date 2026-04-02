from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestSupportAgentInit:
    def test_raises_without_api_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=False):
            from agent.agent import SupportAgent

            with pytest.raises(ValueError, match="GROQ_API_KEY"):
                SupportAgent()


class TestSupportAgentChat:
    def _make_agent(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}, clear=False):
            with patch("agent.agent.Groq"):
                from agent.agent import SupportAgent

                agent = SupportAgent()
        return agent

    def _mock_response(self, content: str | None, tool_calls=None):
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    def _mock_tool_call(self, call_id: str, name: str, arguments: dict):
        tool_call = MagicMock()
        tool_call.id = call_id
        tool_call.function.name = name
        tool_call.function.arguments = json.dumps(arguments)
        return tool_call

    def test_direct_response_without_tools(self):
        agent = self._make_agent()
        agent.client.chat.completions.create.return_value = self._mock_response(
            content="Ola! Como posso ajudar?"
        )

        result = agent.chat([{"role": "user", "content": "Oi"}])
        assert result.content == "Ola! Como posso ajudar?"
        assert result.status == "answered"
        assert result.tool_log == []

    def test_sanitize_messages_removes_tool_call_history(self):
        from agent.agent import SupportAgent

        sanitized = SupportAgent._sanitize_messages(
            [
                {"role": "user", "content": "Primeira pergunta"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "call_1"}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '{"ok": true}',
                },
                {"role": "assistant", "content": "Resposta final"},
                {"role": "assistant", "content": "   "},
                {"role": "user", "content": "Segunda pergunta"},
            ]
        )

        assert sanitized == [
            {"role": "user", "content": "Primeira pergunta"},
            {"role": "assistant", "content": "Resposta final"},
            {"role": "user", "content": "Segunda pergunta"},
        ]

    def test_tool_call_then_response(self):
        agent = self._make_agent()
        tc = self._mock_tool_call("call_1", "buscar_faq", {"query": "redefinir senha"})
        first = self._mock_response(content=None, tool_calls=[tc])
        second = self._mock_response(
            content="Para redefinir sua senha, acesse a pagina de login."
        )

        agent.client.chat.completions.create.side_effect = [first, second]

        result = agent.chat([{"role": "user", "content": "Como redefinir minha senha?"}])
        assert "senha" in result.content.lower() or "login" in result.content.lower()
        assert result.status == "answered"
        assert len(result.tool_log) == 1
        assert result.tool_log[0]["ferramenta"] == "buscar_faq"

    def test_tool_history_payload_is_compatible_with_groq(self):
        agent = self._make_agent()
        tc = self._mock_tool_call("call_1", "buscar_faq", {"query": "redefinir senha"})
        agent.client.chat.completions.create.side_effect = [
            self._mock_response(content=None, tool_calls=[tc]),
            self._mock_response(content="Use o fluxo de recuperacao de senha no login."),
        ]

        agent.chat([{"role": "user", "content": "Como redefinir minha senha?"}])

        second_call_messages = agent.client.chat.completions.create.call_args_list[1].kwargs["messages"]
        assert second_call_messages[0]["role"] == "system"
        assert second_call_messages[1] == {"role": "user", "content": "Como redefinir minha senha?"}
        assert second_call_messages[2]["role"] == "assistant"
        assert "tool_calls" in second_call_messages[2]
        assert second_call_messages[3]["role"] == "tool"
        assert second_call_messages[3]["tool_call_id"] == "call_1"
        assert all(message["role"] != "system" for message in second_call_messages[1:])

    def test_escalation_with_ticket(self):
        agent = self._make_agent()
        tc_faq = self._mock_tool_call("call_1", "buscar_faq", {"query": "cobranca duplicada"})
        tc_ticket = self._mock_tool_call(
            "call_2",
            "criar_ticket",
            {
                "categoria": "cobranca",
                "tom": "frustrado",
                "resumo": "Cliente relata cobranca duplicada.",
                "proximo_passo": "Verificar historico de pagamentos.",
            },
        )

        agent.client.chat.completions.create.side_effect = [
            self._mock_response(content=None, tool_calls=[tc_faq]),
            self._mock_response(content=None, tool_calls=[tc_ticket]),
            self._mock_response(
                content="Entendo sua frustracao. Criei um ticket e um atendente vai analisar seu caso."
            ),
        ]

        result = agent.chat([{"role": "user", "content": "Fui cobrado duas vezes e estou revoltado!"}])
        assert "ticket" in result.content.lower() or "atendente" in result.content.lower()
        assert result.status == "escalated"
        assert result.ticket is not None
        assert len(result.tool_log) == 2
        assert result.tool_log[1]["ferramenta"] == "criar_ticket"

    def test_unknown_tool_handled_gracefully(self):
        agent = self._make_agent()
        tc = self._mock_tool_call("call_1", "ferramenta_inexistente", {})

        agent.client.chat.completions.create.side_effect = [
            self._mock_response(content=None, tool_calls=[tc]),
            self._mock_response(content="Desculpe, nao consegui processar."),
        ]

        result = agent.chat([{"role": "user", "content": "teste"}])
        assert len(result.tool_log) == 1
        assert "erro" in result.tool_log[0]["resultado"]
