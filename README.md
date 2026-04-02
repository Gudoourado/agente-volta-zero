# 🤖 Agente de Primeiro Atendimento — Volta Zero

Agente inteligente de suporte construído com **Python**, **Streamlit** e **Groq API (Llama 3.3)** para automatizar o primeiro atendimento ao cliente com foco em segurança, clareza e escalonamento responsável.

O sistema recebe a mensagem do utilizador, consulta uma **FAQ local em JSON** e decide autonomamente entre:

- responder diretamente com base na base de conhecimento;
- ou escalar o caso para atendimento humano, gerando um **ticket estruturado**.

---

## ✨ Propósito

Este projeto foi desenhado para simular uma **volta zero de atendimento** em um cenário realista de suporte:

- perguntas frequentes devem ser respondidas com rapidez e consistência;
- casos ambíguos, sensíveis ou mal cobertos pela FAQ devem ser encaminhados com contexto;
- a interface deve ser simples, profissional e focada na conversa.

Mais do que um chat, a proposta aqui é demonstrar uma implementação que equilibra:

- **UX limpa e corporativa**
- **tool calling nativo**
- **controle seguro de estado**
- **engenharia pragmática para produção**

---

## 🏗️ Arquitetura e Funcionalidades

### 1. Tool Calling Nativo

O agente usa **tool calling nativo da Groq** para decidir o próximo passo da conversa.

Ferramentas disponíveis:

- `buscar_faq(query)`: consulta a FAQ local e devolve os resultados mais aderentes com score de confiança
- `criar_ticket(categoria, tom, resumo, proximo_passo)`: cria um ticket estruturado para atendimento humano

Fluxo de decisão:

```text
Mensagem do cliente
        ↓
LLM chama buscar_faq(query)
        ↓
FAQ cobre bem a dúvida?
   ├─ Sim → responde diretamente ao cliente
   └─ Não → cria ticket estruturado e informa o escalonamento
```

O ponto forte aqui é que o agente não depende de frameworks pesados. A lógica fica clara, auditável e fácil de explicar em entrevista.

### 2. State Management Seguro

Um dos pontos mais críticos deste projeto foi a gestão do histórico quando há tool calling.

Para evitar o clássico **HTTP 400 da Groq** em conversas multi-turno, o histórico é sanitizado antes de cada nova chamada ao modelo:

- remove mensagens com `role == "tool"`
- remove mensagens de `assistant` com `tool_calls`
- remove mensagens de `assistant` sem conteúdo textual final
- preserva apenas:
  - o `system prompt`
  - mensagens do `user`
  - respostas finais textuais do `assistant`

Além disso, o contexto é truncado para manter apenas as últimas mensagens relevantes do diálogo. Isso torna o fluxo mais robusto e reduz o risco de o modelo "alucinar" sintaxe de ferramenta em turnos seguintes.

### 3. Clean UI & Graceful Degradation

A interface foi construída com foco em simplicidade e usabilidade:

- uso de `st.chat_message` e `st.chat_input`
- layout minimalista e centrado na janela de conversa
- tickets exibidos de forma elegante em `st.expander`
- tratamento de erros sem quebrar a aplicação

Mesmo quando a API falha, o utilizador continua a ver uma resposta amigável em vez de um crash visual ou stack trace exposto na interface.

### 4. Confiabilidade

O projeto está coberto por **20 testes automatizados com `pytest`**, incluindo:

- inicialização do agente
- chamadas diretas sem ferramentas
- fluxo de tool calling com FAQ
- escalonamento com ticket
- tratamento de ferramenta desconhecida
- regressão do histórico sanitizado para evitar erro 400 da Groq
- testes da base de conhecimento
- testes das ferramentas

---

## 🧠 Como o Agente Decide

O comportamento do agente segue uma regra simples e explícita:

1. A mensagem do cliente entra pela interface.
2. O agente consulta a FAQ via `buscar_faq`.
3. A FAQ devolve resultados com score de similaridade e sinalização de resposta direta.
4. Se a cobertura for suficiente, o agente responde.
5. Se a confiança for baixa ou a situação exigir contexto humano, o agente cria um ticket.

O sistema prioriza **não responder errado**. Quando há dúvida real, o caso é escalado.

---

## 📁 Estrutura do Projeto

```text
.
├── app.py
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── kb.py
│   └── tools.py
├── data/
│   └── faq.json
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   ├── test_kb.py
│   └── test_tools.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

### Responsabilidades por módulo

- `app.py`: interface Streamlit e gestão da sessão
- `agent/agent.py`: integração com Groq, prompt, tool calling e sanitização do histórico
- `agent/tools.py`: implementação das tools e schemas enviados ao modelo
- `agent/kb.py`: carregamento, normalização e busca na FAQ local
- `data/faq.json`: base inicial de conhecimento
- `tests/`: suíte automatizada de validação

---

## 🚀 Como Rodar o Projeto

### Pré-requisitos

- Python **3.10+**
- Conta na Groq com uma API Key válida

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd projeto
```

### 2. Criar e ativar o ambiente virtual

#### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar o `.env`

Crie um ficheiro `.env` com base no `.env.example` e adicione a sua chave da Groq:

```env
GROQ_API_KEY=sua_chave_aqui
GROQ_MODEL=llama-3.3-70b-versatile
FAQ_DIRECT_RESPONSE_THRESHOLD=0.58
```

Notas:

- `GROQ_API_KEY` é obrigatória para executar o agente
- `GROQ_MODEL` é opcional; por padrão o projeto usa `llama-3.3-70b-versatile`
- `FAQ_DIRECT_RESPONSE_THRESHOLD` permite ajustar a agressividade da resposta automática

### 5. Executar a aplicação

```bash
streamlit run app.py
```

Depois disso, a aplicação abrirá pronta para uso em ambiente local.

---

## ✅ Como Rodar os Testes

Execute:

```bash
pytest
```

Se quiser uma saída mais curta:

```bash
pytest -q
```

O projeto foi validado com **20 testes automatizados**.

---

## 🛠️ Stack Técnica

- **Python**
- **Streamlit**
- **Groq API**
- **Llama 3.3**
- **rapidfuzz**
- **python-dotenv**
- **pytest**

---

## 🎯 Diferenciais Técnicos

- Arquitetura simples, modular e fácil de manter
- Tool calling nativo, sem dependência de orquestradores pesados
- Busca local em FAQ com heurística clara e explicável
- Sanitização rigorosa do histórico para robustez em multi-turno
- Interface limpa, orientada ao caso de uso real
- Tratamento de erro amigável na camada de produto
- Cobertura automatizada com testes de regressão

---

## 📌 Observações

- O ficheiro `.env` não deve ser versionado
- A FAQ local pode ser expandida facilmente sem alterar a arquitetura principal
- O projeto já está preparado para evoluir para uma versão com base semântica ou integração com LLMs adicionais no futuro

---

## 👤 Autor

- Nome: _preencher_
- LinkedIn: _preencher_
- GitHub: _preencher_

