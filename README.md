# 🤖 RAG Chatbot - Sistema de Chat com IA Local

Sistema completo de chatbot com RAG (Retrieval-Augmented Generation) utilizando LLM local (Ollama + Llama3), embeddings vetoriais (PGVector) e interface N8N.

---

## 📋 Índice

- [Características](#-características)
- [Arquitetura](#-arquitetura)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Uso](#-uso)
- [API](#-api)
- [Tecnologias](#-tecnologias)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Troubleshooting](#-troubleshooting)
- [Contribuindo](#-contribuindo)
- [Licença](#-licença)

---

## ✨ Características

### 🎯 Funcionalidades Principais

- **Chat Inteligente**: Interface de chat via N8N com memória de contexto
- **Upload de Documentos**: Suporte a 9 formatos diferentes
- **RAG (Retrieval-Augmented Generation)**: Respostas baseadas em documentos
- **LLM Local**: Ollama + Llama3 rodando 100% local
- **Scraping Automático**: Coleta automática de conteúdo web
- **Busca Vetorial**: PGVector para similaridade semântica
- **Histórico Persistente**: Conversas armazenadas no PostgreSQL
- **OCR Integrado**: Extração de texto de imagens

### 📄 Formatos Suportados

| Categoria | Formatos |
|-----------|----------|
| Documentos | PDF, DOCX, DOC, TXT |
| Planilhas | XLSX, XLS, CSV |
| Apresentações | PPTX, PPT |
| Imagens (OCR) | JPG, PNG, GIF, BMP, WEBP, TIFF |

### 🚀 Tecnologias de IA

- **LLM**: Ollama (Llama 3) - Execução local, zero custo
- **Embeddings**: HuggingFace all-MiniLM-L6-v2 (384 dimensões)
- **Vector DB**: PostgreSQL + PGVector (IVFFlat index)
- **OCR**: Tesseract (Português + Inglês)
- **Framework**: LangChain para orquestração

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                     USUÁRIO                              │
│                  (Interface N8N)                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ Chat + Upload
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  N8N WORKFLOW                            │
│  • Chat Trigger                                          │
│  • Conditional Logic (file detection)                    │
│  • HTTP Request to API                                   │
│  • Response Display                                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ REST API
                     ▼
┌─────────────────────────────────────────────────────────┐
│             LITESTAR API (Python)                        │
│  Endpoints:                                              │
│  • POST /chat      → Process & Answer                    │
│  • POST /scrape    → Web Scraping                        │
│  • GET  /history   → Chat History                        │
│  • GET  /sessions  → List Sessions                       │
│  • GET  /documents → List Documents                      │
└──────┬──────────────────────┬──────────────────────────┘
       │                      │
       │ Embeddings           │ LLM
       ▼                      ▼
┌──────────────┐      ┌─────────────────┐
│ HuggingFace  │      │     OLLAMA      │
│  Embeddings  │      │   (Llama 3)     │
└──────┬───────┘      └─────────────────┘
       │
       │ Store Vectors
       ▼
┌─────────────────────────────────────────────────────────┐
│          POSTGRESQL + PGVECTOR                           │
│  Tables:                                                 │
│  • documents   → Metadata                                │
│  • chunks      → Text + Embeddings (vector 384)          │
│  • chat_history → Conversation History                   │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Pré-requisitos

### Software Necessário

- **Docker** (20.10+) e **Docker Compose** (2.0+)
- **Git** (para clonar o repositório)
- **8GB RAM** mínimo (recomendado: 16GB)
- **10GB** espaço em disco livre

### Portas Utilizadas

| Serviço | Porta | Descrição |
|---------|-------|-----------|
| N8N | 5678 | Interface web |
| API | 8000 | Backend REST |
| PostgreSQL | 5433 | Banco de dados |
| Ollama | 11434 | LLM Server |

---

## 🚀 Instalação

### 1. Clone o Repositório

```bash
git clone https://github.com/tyago1413/rag-chatbot.git
cd rag-chatbot
```

### 2. Configure as Variáveis de Ambiente

```bash
# Editar se necessário (opcional)
nano .env
```

**Principais variáveis:**
```bash
# URL para scraping automático
SCRAPE_URL=https://pt.wikipedia.org/wiki/Intelig%C3%AAncia_artificial

# Modelo de embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Configurações RAG
TOP_K=5
MAX_CONTEXT_CHARS=2000
CHUNK_SIZE=500
```

### 3. Inicialize o Sistema

```bash
# Build das imagens e iniciar todos os serviços
docker-compose up -d --build

# Ver logs em tempo real
docker-compose logs -f
```

**⏱️ Primeira inicialização:** O download do modelo Llama3 (~4GB) pode levar 10-30 minutos dependendo da sua internet.

### 4. Aguarde a Inicialização

```bash
# Verificar status dos containers
docker-compose ps

# Todos devem estar "healthy"
# NAME          STATUS
# n8n           Up (healthy)
# rag-api       Up (healthy)
# postgres      Up (healthy)
# ollama        Up (healthy)
```

### 5. Importe o Workflow N8N

1. Acesse http://localhost:5678
2. Vá em **Workflows** → **Import from File**
3. Selecione `RAG_Chatbot.json`
4. Ative o workflow (botão "Active")

---

## 💻 Uso

### Via N8N (Interface Gráfica)

#### Chat Simples
1. Abra o workflow no N8N
2. Clique em "Test Workflow"
3. Digite sua pergunta
4. Aguarde a resposta

#### Upload de Documento
1. Clique no ícone 📎 (clipe)
2. Selecione um arquivo
3. Digite uma pergunta sobre o arquivo (opcional)
4. Envie!

**Exemplo:**
```
Arquivo: relatorio_vendas.pdf
Pergunta: "Qual foi o total de vendas no Q3?"
```

### Via API (REST)

#### Pergunta Simples

```bash
curl -X POST http://localhost:8000/chat \
  -F "question=O que é inteligência artificial?" \
  -F "session_id=user123"
```

#### Upload + Pergunta

```bash
curl -X POST http://localhost:8000/chat \
  -F "question=Resuma este documento" \
  -F "session_id=user123" \
  -F "file=@documento.pdf"
```

#### Scraping Manual

```bash
curl -X POST http://localhost:8000/scrape \
  -F "url=https://example.com/artigo"
```

---

## 📡 API

### Endpoints Principais

#### POST /chat
Envia mensagem e/ou arquivo para processamento.

**Parâmetros:**
- `question` (string): Pergunta do usuário
- `session_id` (string, opcional): ID da sessão
- `file` (binary, opcional): Arquivo para processar

**Resposta:**
```json
{
  "status": "success",
  "answer": "Resposta gerada pela IA...",
  "sources": [
    {
      "title": "documento.pdf",
      "source": "upload:documento.pdf",
      "similarity": 0.89
    }
  ],
  "session_id": "user123",
  "context_size": 1500
}
```

#### POST /scrape
Realiza scraping de uma URL.

**Parâmetros:**
- `url` (string, opcional): URL para scraping

**Resposta:**
```json
{
  "status": "success",
  "message": "Scraping concluído com sucesso",
  "document_id": "uuid...",
  "url": "https://example.com"
}
```

#### GET /history/{session_id}
Consulta histórico de uma sessão.

**Resposta:**
```json
{
  "status": "success",
  "session_id": "user123",
  "message_count": 10,
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "content": "Olá!",
      "created_at": "2024-01-15 10:30:00"
    }
  ]
}
```

#### GET /sessions
Lista todas as sessões.

#### GET /documents
Lista todos os documentos processados.

#### GET /health
Health check da API.

---

## 🔧 Tecnologias

### Backend
- **Framework**: Litestar 2.12.1
- **LLM Orchestration**: LangChain 0.3.7
- **Embeddings**: Sentence Transformers 3.3.1
- **Database**: psycopg2-binary 2.9.10
- **Vector Extension**: pgvector 0.3.6
- **Document Processing**: PyPDF2, pdfplumber, python-docx, python-pptx
- **OCR**: pytesseract 0.3.10
- **Scraping**: BeautifulSoup4, httpx

### Infraestrutura
- **Container**: Docker + Docker Compose
- **Web Server**: Uvicorn (ASGI)
- **Database**: PostgreSQL 16 + PGVector
- **LLM**: Ollama (Llama 3)
- **Workflow**: N8N

### IA/ML
- **LLM**: Meta Llama 3 (via Ollama)
- **Embeddings**: all-MiniLM-L6-v2 (384 dims)
- **Vector Search**: IVFFlat (cosine similarity)
- **OCR Engine**: Tesseract 4.x

---

## 📁 Estrutura do Projeto

```
rag-chatbot/
├── docker-compose.yml          # Orquestração dos serviços
├── .env                        # Variáveis de ambiente
├── RAG_Chatbot.json            # Workflow N8N
│
├── api/                        # Backend Python
│   ├── Dockerfile              # Container da API
│   ├── requirements.txt        # Dependências Python
│   ├── main.py                 # Endpoints da API
│   ├── config.py               # Configurações
│   ├── database.py             # Conexão PostgreSQL
│   │
│   └── app/
│       ├── services/
│       │   ├── rag_service.py         # Lógica RAG
│       │   └── scraper_service.py     # Web scraping
│       │
│       └── utils/
│           └── document_processor.py   # Processamento de docs
│
└── db/
    └── init/
        └── 010_schema_rag.sql  # Schema inicial do banco
```

---

## 🐛 Troubleshooting

### Problema: Containers não sobem

**Solução:**
```bash
# Limpar containers antigos
docker-compose down -v

# Rebuild
docker-compose build --no-cache

# Subir novamente
docker-compose up -d
```

### Problema: API retorna erro 500

**Verificar logs:**
```bash
docker-compose logs api

# Possíveis causas:
# - Modelo Ollama não baixado ainda
# - PostgreSQL não iniciou
# - Falta de memória
```

**Solução:**
```bash
# Aguardar modelo baixar
docker-compose logs -f ollama-init

# Verificar healthcheck
curl http://localhost:8000/health
```

### Problema: OCR não funciona

**Causa:** Tesseract não instalado no container

**Solução:**
```dockerfile
# No Dockerfile, verificar se tem:
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    libtesseract-dev
```

### Problema: Respostas muito lentas

**Causas comuns:**
1. **Primeira execução** - Modelo precisa carregar (normal)
2. **Pouca RAM** - Ollama precisa ~4GB
3. **CPU lenta** - LLM local é computacionalmente intensivo

**Soluções:**
- Aguardar "warm-up" (primeira resposta é sempre lenta)
- Aumentar RAM alocada ao Docker
- Usar GPU (configurar no docker-compose)
- Reduzir `num_predict` em config.py

### Problema: N8N não conecta na API

**Verificar rede:**
```bash
# Dentro do N8N
docker-compose exec n8n ping api

# Se não pingar, verificar network
docker network inspect imparprojeto_backend
```

---

## 📊 Monitoramento

### Ver Logs

```bash
# Todos os serviços
docker-compose logs -f

# Serviço específico
docker-compose logs -f api
docker-compose logs -f ollama
docker-compose logs -f postgres
```

### Verificar Saúde dos Serviços

```bash
# Health check API
curl http://localhost:8000/health

# Status containers
docker-compose ps

# Uso de recursos
docker stats
```

### Consultar Banco de Dados

```bash
# Conectar no PostgreSQL
docker-compose exec postgres psql -U impar -d impar

# Queries úteis
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM chunks;
SELECT COUNT(*) FROM chat_history;

# Ver documentos
SELECT id, title, source, created_at FROM documents ORDER BY created_at DESC LIMIT 5;

# Ver sessões
SELECT session_id, COUNT(*) as msg_count 
FROM chat_history 
GROUP BY session_id;
```

---

## 🎯 Boas Práticas

### Para Melhores Respostas

1. **Seja específico nas perguntas**
   - ❌ "Vendas?"
   - ✅ "Qual foi o total de vendas no Q3 de 2023?"

2. **Use o contexto da conversa**
   - O sistema mantém memória entre mensagens
   - Você pode fazer perguntas de acompanhamento

3. **Para documentos grandes**
   - Divida em seções menores se possível
   - Faça perguntas específicas sobre partes do documento

4. **Para OCR**
   - Use imagens nítidas e com boa resolução
   - Textos retos (não inclinados) funcionam melhor

### Performance

1. **Primeira mensagem sempre é mais lenta** (~30s)
   - Modelo precisa carregar na memória
   - Subsequentes são mais rápidas (~5-10s)

2. **Documentos grandes** (>10MB)
   - Aumentar timeout no N8N
   - Considerar dividir o arquivo

3. **Muitos documentos no banco**
   - Limpar documentos antigos periodicamente
   - Usar filtros por sessão

---

## 🔐 Segurança

### Produção

Para ambiente de produção, implemente:

1. **Autenticação**
   - API Keys na API
   - Login no N8N
   - JWT tokens

2. **HTTPS**
   - Certificados SSL
   - Reverse proxy (nginx)

3. **Rate Limiting**
   - Limite de requisições por IP
   - Throttling

4. **Sanitização**
   - Validação de inputs
   - Escape de SQL
   - Limpeza de uploads

5. **Secrets**
   - Use Docker secrets
   - Não commite .env
   - Rotate credenciais

---

## 🤝 Contribuindo

Contribuições são bem-vindas! Para contribuir:

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

---

## 👥 Autores

- **Tiago Mendonça** - *Trabalho Inicial* - [GitHub](https://github.com/tyago1413)

---

## 🙏 Agradecimentos

- [Anthropic](https://anthropic.com) - LangChain
- [Meta](https://ai.meta.com) - Llama 3
- [Ollama](https://ollama.ai) - LLM local
- [N8N](https://n8n.io) - Workflow automation
- [PostgreSQL](https://postgresql.org) - Database
- [HuggingFace](https://huggingface.co) - Embeddings

---

## 📞 Suporte

Para dúvidas ou problemas:

- 📧 Email: tyago_art@hotmail.com
- 💬 Issues: [GitHub Issues](https://github.com/tyago1413/rag-chatbot/issues)

---

<p align="center">
  Feito com ❤️ usando Python, Docker, Claude.ia, e muito café ☕
</p>