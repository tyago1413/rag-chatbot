-- 010_schema_rag.sql
-- Criação automática do schema RAG (executado na inicialização do container Postgres)

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ======================
-- Tabela de documentos
-- ======================
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source TEXT NOT NULL,      -- Ex: 'upload:pdf', 'scrape:http://...'
  title TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ======================
-- Tabela de chunks (partes do texto)
-- Modelo padrão: all-MiniLM-L6-v2 (dimensão 384)
-- ======================
CREATE TABLE IF NOT EXISTS chunks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(384) NOT NULL
);

-- Índices de performance
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
  ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_chunks_docid
  ON chunks(document_id);

-- ======================
-- Histórico de conversa
-- ======================
CREATE TABLE IF NOT EXISTS chat_history (
  session_id TEXT NOT NULL,
  turn INT NOT NULL,
  role TEXT NOT NULL,      -- 'user' | 'assistant'
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (session_id, turn)
);

-- ======================
-- Otimização inicial
-- ======================
ANALYZE;