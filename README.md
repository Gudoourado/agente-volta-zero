# Agente de Primeiro Atendimento — Volta Zero
> Desafio técnico · Estágio Dev IA · Sunter

## Demo
🚀 **[Testar Aplicação ao Vivo Aqui](https://agente-volta-zero-kdhup6wqnhtgphtgnyptp6.streamlit.app/)**

## O problema que estou resolvendo
As equipes de suporte humano gastam a maior parte do seu tempo a responder a perguntas repetitivas de Nível 1 (recuperação de senhas, dúvidas de faturação, cancelamentos). Isso gera filas de espera e atrasa muito o atendimento de clientes com problemas críticos reais.

O **Agente Volta Zero** atua como uma barreira inteligente. O seu impacto é **filtrar e resolver autonomamente as dúvidas comuns em segundos** utilizando a Base de Conhecimento (FAQ), libertando os agentes humanos para atuarem apenas nos casos complexos. Quando o escalonamento é necessário, o sistema já entrega ao humano um ticket estruturado, com resumo, tom de voz do cliente e sugestão de próximos passos.

## Como o agente funciona

### Fluxo de decisão
```text
Mensagem do cliente
       ↓
A IA avalia a intenção e chama buscar_faq(query)
       ↓
  confiança >= 0.58? ──── sim ──→ IA formata a resposta e responde ao cliente
       │
      não
       ↓
IA chama criar_ticket(dados) → IA avisa o cliente ("Vou acionar um humano...")
```

### Ferramentas implementadas (Tool Calling)
- `buscar_faq(query)`: Busca entradas relevantes na base de conhecimento (JSON). **Obrigatória e prioritária** sempre que chega uma nova mensagem.
- `criar_ticket(dados)`: Registra um ticket estruturado (Categoria, Tom, Resumo, etc.). Como **último recurso**, apenas quando a confiança na FAQ é baixa ou o cliente exige um humano.
- *Resposta Direta*: Responde de forma natural no chat. Ao final do fluxo, traduzindo o resultado da tool para o cliente.

### Critério de confiança
A decisão de escalar ou resolver baseia-se numa **arquitetura de priorização semântica e threshold**:
1. **Limiar (Threshold):** A ferramenta `buscar_faq` exige uma confiança mínima de `0.58` (e relevância de `0.25`) para classificar um *match* como válido.
2. **Priorização de Categoria:** Implementei um reforço no código para dúvidas críticas de negócio (*senha*, *pagamento*, *cancelamento*). Se houver *match* nestas palavras, a flag `recomenda_resposta_direta` é ativada.
3. **Guardrails no Prompt:** O `SYSTEM_PROMPT` contém uma "Regra de Ouro" estrita e as descrições das ferramentas (JSON Schema) usam gatilhos como "OBRIGATÓRIO" e "PROIBIDO" para forçar o LLM a ler a FAQ antes de pensar em criar um ticket.

## Decisões técnicas

### LLM escolhida
**Provedor:** Groq  
**Modelo:** `llama-3.3-70b-versatile`  
**Por quê:** A API da Groq oferece uma latência quase nula, o que proporciona uma experiência de chat em tempo real excelente. O modelo Llama 3.3 de 70B provou ter uma precisão fantástica no seguimento de instruções de Tool Calling e na formatação de tickets.

### Stack
**Backend/Lógica:** Python 3.10+  
**Interface:** Streamlit  
**Testes:** Pytest (20 testes automatizados passando)  
**Deploy:** Streamlit Community Cloud  
**Por quê essa combinação:** O Streamlit permite construir interfaces orientadas a chat de forma rápida e limpa. A stack nativa em Python facilita a manipulação de dicionários para os históricos de conversa da Groq e o ecossistema do `pytest` garantiu a estabilidade das refatorações.

### Base de conhecimento
Utilizei um ficheiro **JSON** (`faq.json`) atuando como um banco chave-valor simples.  
**Porquê:** Para um protótipo de primeiro atendimento, o JSON é extremamente leve, rápido de iterar e não exige infraestrutura externa.  
**Cobertura:** Foquei nas três maiores dores do suporte SaaS (Acesso/Senha, Faturação/PIX, Churn/Cancelamento).

### Gestão de Estado (Proteção contra Erro 400)
Implementei uma **sanitização rigorosa do histórico de mensagens** (Sliding Window de 6 mensagens). O código limpa rastos de *tool calls* antigas antes de enviar um novo turno à Groq, prevenindo falhas de geração (HTTP 400 - `failed_generation`) e economizando tokens de contexto.

## Casos de teste

### Resolvidos pelo agente
**Caso 1 — Recuperação de Acesso**  
Entrada:  "Esqueci a minha senha e não consigo entrar no sistema."  
Ferramenta chamada: buscar_faq("senha")  
Resultado: respondeu direto (Confiança e Match validados)  
Resposta: "Para redefinir sua senha, acesse a página de login..."

**Caso 2 — Dúvida de Faturação**  
Entrada:  "Consigo pagar o plano mensal no PIX ou é só cartão?"  
Ferramenta chamada: buscar_faq("pagamento PIX")  
Resultado: respondeu direto  
Resposta: "Aceitamos Cartão de Crédito e PIX para planos mensais."

### Escalados corretamente
**Caso 3 — Escalonamento Crítico / Urgência**  
Entrada:  "O sistema caiu no meio da minha operação e estou perdendo euros! Preciso de alguém agora!"  
Motivo do escalonamento: Intenção não mapeada na FAQ + Tom Urgente  
Ticket gerado: categoria: "Suporte Técnico", tom: "Frustrado/Urgente"

**Caso 4 — Dúvida de Integração (Fora de Escopo)**  
Entrada:  "Como faço para integrar o banco de dados da Sunter com o meu Power BI?"  
Motivo do escalonamento: Ferramenta buscar_faq retornou abaixo do threshold (sem resposta).  
Ticket gerado: categoria: "Integrações/API", tom: "Neutro/Dúvida"

## O que eu faria diferente com mais tempo
1. **RAG com Vector Database:** Substituiria o `faq.json` por um banco vetorial (como ChromaDB ou Pinecone) utilizando modelos de embeddings para lidar com FAQs na escala de milhares de documentos baseados puramente em similaridade semântica profunda.
2. **Integração Real de Tickets:** Conectaria a função `criar_ticket` a uma API real de Help Desk em vez de simular na interface com `st.expander`.
3. **Memória de Longo Prazo:** Implementaria PostgreSQL + SQLAlchemy para guardar o histórico das sessões.

## Como rodar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/Gudoourado/agente-volta-zero.git
cd agente-volta-zero

# 2. Crie o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env e adicione a sua chave da API da Groq

# 5. Rode a bateria de testes (Garantia de Qualidade)
pytest -q

# 6. Rode o projeto
streamlit run app.py
```

## Variáveis de ambiente
Crie um ficheiro `.env` baseado no `.env.example`:

```env
GROQ_API_KEY=sua_chave_real_aqui_gsk...
```

⚠️ Nunca commite o arquivo `.env`. Ele já está protegido no `.gitignore`.

## Autor
**Nome:** Gustavo Aurelio  
**LinkedIn:** https://www.linkedin.com/in/gustavodoourado/  
**GitHub:** https://github.com/Gudoourado
