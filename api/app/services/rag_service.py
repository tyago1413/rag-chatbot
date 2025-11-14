"""
Serviço RAG - Processamento de documentos e respostas
VERSÃO CORRIGIDA: Prioriza documento recém-processado
"""
from litestar.datastructures import UploadFile
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.memory import ConversationBufferMemory
import uuid
import logging
from typing import Dict, List, Optional
import json
import httpx

from app.config import settings
from app.database import db
from app.utils.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)


class RAGService:
    """Serviço principal de RAG"""
    
    def __init__(self):
        # Embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'}
        )
        
        # Text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len
        )
        
        # Memória por sessão
        self.memories: Dict[str, ConversationBufferMemory] = {}
        
        # ✨ NOVO: Memória de documento ativo por sessão
        self.session_documents: Dict[str, str] = {}
        
        # Document processor
        self.doc_processor = DocumentProcessor()
    
    def _get_memory(self, session_id: str) -> ConversationBufferMemory:
        """Obtém ou cria memória para sessão, carregando histórico do banco se necessário"""
        if session_id not in self.memories:
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=False
            )
            
            # Carregar histórico do banco (últimas 10 mensagens)
            history = self._load_history_from_db(session_id, limit=10)
            
            if history:
                # Recarregar mensagens na memória
                for msg in history:
                    if msg['role'] == 'user':
                        memory.chat_memory.add_user_message(msg['content'])
                    elif msg['role'] == 'assistant':
                        memory.chat_memory.add_ai_message(msg['content'])
                
                logger.info(f"🔄 Histórico carregado do banco: {session_id} ({len(history)} mensagens)")
            
            self.memories[session_id] = memory
        
        return self.memories[session_id]
    
    def _save_message_to_db(self, session_id: str, role: str, content: str):
        """Salva mensagem no banco de dados"""
        try:
            # Buscar o próximo turn number
            query_max = """
                SELECT COALESCE(MAX(turn), 0) as max_turn 
                FROM chat_history 
                WHERE session_id = %s
            """
            result = db.execute_query(query_max, (session_id,), fetch=True)
            next_turn = result[0]['max_turn'] + 1 if result else 1
            
            # Inserir mensagem
            query_insert = """
                INSERT INTO chat_history (session_id, turn, role, content)
                VALUES (%s, %s, %s, %s)
            """
            db.execute_query(query_insert, (session_id, next_turn, role, content))
            
            logger.info(f"💾 Mensagem salva no banco: {session_id} - turn {next_turn}")
        except Exception as e:
            logger.error(f"Erro ao salvar mensagem no banco: {e}")
    
    def _load_history_from_db(self, session_id: str, limit: int = 10) -> list:
        """Carrega histórico do banco de dados"""
        try:
            query = """
                SELECT role, content, turn
                FROM chat_history
                WHERE session_id = %s
                ORDER BY turn DESC
                LIMIT %s
            """
            messages = db.execute_query(query, (session_id, limit), fetch=True)
            
            # Retornar em ordem cronológica (mais antiga primeiro)
            return list(reversed(messages)) if messages else []
        except Exception as e:
            logger.error(f"Erro ao carregar histórico do banco: {e}")
            return []
    
    def _set_session_document(self, session_id: str, document_id: str):
        """
        Salva o documento ativo para uma sessão
        """
        self.session_documents[session_id] = document_id
        logger.info(f"📌 Documento ativo definido para sessão {session_id}: {document_id}")
    
    def _get_session_document(self, session_id: str) -> Optional[str]:
        """
        Recupera o documento ativo de uma sessão
        """
        doc_id = self.session_documents.get(session_id)
        if doc_id:
            logger.info(f"🔄 Recuperado documento ativo da sessão {session_id}: {doc_id}")
        return doc_id
    
    def _clear_session_document(self, session_id: str):
        """
        Limpa o documento ativo de uma sessão
        """
        if session_id in self.session_documents:
            del self.session_documents[session_id]
            logger.info(f"🗑️ Documento ativo limpo da sessão {session_id}")
    
    def _get_document_info(self, document_id: str) -> Optional[dict]:
        """
        Busca informações sobre um documento
        """
        try:
            query = """
                SELECT title, source, created_at
                FROM documents
                WHERE id = %s
            """
            result = db.execute_query(query, (document_id,), fetch=True)
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar info do documento: {e}")
            return None
    
    async def process_document(self, file: UploadFile, session_id: str = None) -> uuid.UUID:
        """
        Processa documento enviado pelo usuário
        
        Args:
            file: Arquivo enviado
            session_id: ID da sessão (para salvar documento ativo)
        """
        try:
            # Ler conteúdo do arquivo
            content = await file.read()
            
            # Extrair texto do documento
            text = self.doc_processor.extract_text(content, file.filename)
            
            if not text:
                raise ValueError("Não foi possível extrair texto do documento")
            
            # Criar documento no banco
            doc_id = uuid.uuid4()
            query = """
                INSERT INTO documents (id, source, title, metadata)
                VALUES (%s, %s, %s, %s)
            """
            metadata = json.dumps({
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content)
            })
            db.execute_query(query, (str(doc_id), f"upload:{file.filename}", file.filename, metadata))
            
            # Dividir em chunks
            chunks = self.text_splitter.split_text(text)
            logger.info(f"📄 Documento dividido em {len(chunks)} chunks")
            
            # Gerar embeddings e armazenar
            for idx, chunk in enumerate(chunks):
                embedding = self.embeddings.embed_query(chunk)
                
                query = """
                    INSERT INTO chunks (document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s)
                """
                db.execute_query(
                    query,
                    (str(doc_id), idx, chunk, str(embedding))
                )
            
            # ✨ SALVAR documento como ativo na sessão
            if session_id:
                self._set_session_document(session_id, str(doc_id))
            
            logger.info(f"✅ Documento {file.filename} processado com sucesso")
            return doc_id
            
        except Exception as e:
            logger.error(f"Erro ao processar documento: {e}")
            raise
    
    def _search_similar_chunks(
        self, 
        query: str, 
        top_k: int = None,
        prioritize_document_id: Optional[str] = None
    ) -> List[dict]:
        """
        Busca chunks similares - VERSÃO AGRESSIVA
        
        Se há documento ativo, USA SEMPRE (ignora threshold)
        """
        if top_k is None:
            top_k = settings.TOP_K
        
        # Gerar embedding da query
        query_embedding = self.embeddings.embed_query(query)
        
        # Se deve priorizar um documento específico
        if prioritize_document_id:
            logger.info(f"🔒 Priorizando documento (modo FORÇADO): {prioritize_document_id}")
            
            # Buscar APENAS no documento específico
            sql_specific = """
                SELECT 
                    c.content,
                    d.title,
                    d.source,
                    d.id as document_id,
                    1 - (c.embedding <=> %s::vector) as similarity
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.id = %s
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
            """
            
            results_specific = db.execute_query(
                sql_specific,
                (str(query_embedding), prioritize_document_id, str(query_embedding), top_k),
                fetch=True
            )
            
            # USA SEMPRE, independente da similaridade
            if results_specific and len(results_specific) > 0:
                best_similarity = max([r['similarity'] for r in results_specific])
                logger.info(f"✅ FORÇANDO uso de {len(results_specific)} chunks do documento ativo (melhor: {best_similarity:.2f})")
                
                # Se similaridade é muito baixa, avisar nos sources
                if best_similarity < 0.2:
                    logger.warning(f"⚠️ Similaridade baixa ({best_similarity:.2f}) - resposta pode não ser precisa")
                
                return results_specific
            else:
                logger.warning(f"⚠️ Nenhum chunk encontrado no documento {prioritize_document_id}")
        
        # Busca normal (em todos os documentos) - só quando NÃO há doc ativo
        logger.info(f"🔍 Buscando em todos os documentos disponíveis")
        sql = """
            SELECT 
                c.content,
                d.title,
                d.source,
                d.id as document_id,
                1 - (c.embedding <=> %s::vector) as similarity
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """
        
        results = db.execute_query(
            sql,
            (str(query_embedding), str(query_embedding), top_k),
            fetch=True
        )
        
        return results
    
    async def answer_question(
        self, 
        question: str, 
        session_id: str = "default",
        recent_document_id: Optional[str] = None
    ) -> dict:
        """
        Responde pergunta usando RAG com SYSTEM PROMPT SEPARADO
        
        Args:
            question: Pergunta do usuário
            session_id: ID da sessão
            recent_document_id: ID do documento recém-processado (para priorizar)
                               Se None, tenta usar documento ativo da sessão
        """
        try:
            # 🔍 DETECTAR COMANDOS ESPECIAIS
            question_lower = question.lower().strip()
            
            # Comando: Esquecer documento
            if any(cmd in question_lower for cmd in ["esqueça o documento", "esquecer documento", "limpar contexto", "novo contexto"]):
                self._clear_session_document(session_id)
                return {
                    "answer": "Ok! Contexto de documento limpo. Agora buscarei em todos os documentos disponíveis.",
                    "sources": [],
                    "context_size": 0
                }
            
            # Comando: Qual documento ativo
            if any(cmd in question_lower for cmd in ["qual documento", "que documento", "documento ativo", "documento atual"]):
                active_doc_id = self._get_session_document(session_id)
                if active_doc_id:
                    doc_info = self._get_document_info(active_doc_id)
                    if doc_info:
                        return {
                            "answer": f"Estou priorizando o documento: **{doc_info['title']}** (enviado em {doc_info['created_at']})",
                            "sources": [{"title": doc_info['title'], "source": doc_info['source'], "similarity": 1.0}],
                            "context_size": 0
                        }
                return {
                    "answer": "No momento, não há documento ativo. Estou buscando em todos os documentos disponíveis.",
                    "sources": [],
                    "context_size": 0
                }
            
            # ✨ SE NÃO TEM recent_document_id, TENTA RECUPERAR DA SESSÃO
            prioritize_doc_id = recent_document_id
            
            if not prioritize_doc_id:
                prioritize_doc_id = self._get_session_document(session_id)
                if prioritize_doc_id:
                    logger.info(f"💡 Usando documento ativo da sessão: {prioritize_doc_id}")
            
            # Buscar contexto relevante (priorizando documento se houver)
            similar_chunks = self._search_similar_chunks(
                question,
                prioritize_document_id=prioritize_doc_id
            )
            
            # Filtrar apenas chunks com similaridade > 0.3 (30%)
            SIMILARITY_THRESHOLD = 0.3
            
            context_parts = []
            sources = []
            
            if not similar_chunks:
                context = "Nenhum documento foi fornecido ainda."
            else:
                # Filtrar por threshold e montar contexto
                total_chars = 0
                
                for chunk in similar_chunks:
                    similarity = float(chunk['similarity'])
                    
                    # Ignorar chunks com similaridade muito baixa
                    if similarity < SIMILARITY_THRESHOLD:
                        continue
                    
                    chunk_text = chunk['content']
                    if total_chars + len(chunk_text) > settings.MAX_CONTEXT_CHARS:
                        break
                    
                    context_parts.append(chunk_text)
                    total_chars += len(chunk_text)
                    
                    source_info = {
                        "title": chunk['title'],
                        "source": chunk['source'],
                        "similarity": similarity
                    }
                    if source_info not in sources:
                        sources.append(source_info)
                
                if context_parts:
                    context = "\n\n".join(context_parts)
                else:
                    context = "Não encontrei informações relevantes nos documentos disponíveis."
            
            # Obter memória da conversa
            memory = self._get_memory(session_id)
            
            # Carregar histórico da memória
            chat_history = memory.load_memory_variables({})
            history_text = chat_history.get("chat_history", "")
            
            logger.info(f"🔍 Memória atual: {history_text[:200] if history_text else 'vazia'}...")
            
            # Preparar input do usuário
            has_relevant_context = context_parts and context not in [
                "Nenhum documento foi fornecido ainda.", 
                "Não encontrei informações relevantes nos documentos disponíveis."
            ]
            
            if has_relevant_context:
                user_input = f"""Contexto dos documentos:
{context}

Pergunta: {question}"""
            else:
                user_input = question
            
            # SYSTEM PROMPT SEPARADO
            system_prompt = """Você é um assistente útil e amigável especializado em responder perguntas baseadas em documentos.

Instruções importantes:
- SEMPRE use o histórico da conversa para manter contexto entre mensagens
- Se o usuário mencionou informações pessoais (como nome), LEMBRE-SE delas nas próximas respostas
- Quando houver contexto relevante dos documentos, use-o para fundamentar suas respostas
- Para saudações simples, seja breve e natural
- Seja direto, objetivo e preciso
- Se não souber algo ou não houver informação nos documentos, admita honestamente
- Responda sempre em português brasileiro"""
            
            # Montar mensagens no formato correto da API /api/chat do Ollama
            messages = []
            
            # 1. System message
            messages.append({
                "role": "system",
                "content": system_prompt
            })
            
            # 2. Histórico da conversa
            if history_text:
                history_lines = history_text.split('\n')
                for line in history_lines:
                    line = line.strip()
                    if line.startswith('Human: '):
                        messages.append({
                            "role": "user",
                            "content": line.replace('Human: ', '', 1)
                        })
                    elif line.startswith('AI: '):
                        messages.append({
                            "role": "assistant",
                            "content": line.replace('AI: ', '', 1)
                        })
            
            # 3. Mensagem atual
            messages.append({
                "role": "user",
                "content": user_input
            })
            
            logger.info(f"📤 Enviando {len(messages)} mensagens para Ollama (1 system + {len(messages)-2} histórico + 1 atual)")
            
            # Chamar Ollama diretamente com system prompt separado
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:  # ⚠️ Aumentado para 120s
                    response = await client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": settings.OLLAMA_MODEL,
                            "messages": messages,
                            "stream": False,
                            "options": {
                                "temperature": 0.7,
                                "num_predict": 256  # ⚠️ Reduzido para responder mais rápido
                            }
                        }
                    )
                    response.raise_for_status()
                    result = response.json()
                    answer = result["message"]["content"].strip()
            except httpx.ReadTimeout:
                logger.error("⏱️ Timeout ao chamar Ollama - modelo demorou muito para responder")
                answer = "Desculpe, o modelo demorou muito para responder. Tente uma pergunta mais simples ou aguarde um momento."
            except httpx.ConnectError:
                logger.error("❌ Erro de conexão com Ollama - verifique se o serviço está rodando")
                answer = "Erro ao conectar com o modelo de IA. Verifique se o serviço Ollama está rodando."
            except Exception as e:
                logger.error(f"❌ Erro ao chamar Ollama: {e}")
                answer = f"Erro ao gerar resposta: {str(e)}"
            
            # Atualizar memória manualmente
            memory.chat_memory.add_user_message(question)
            memory.chat_memory.add_ai_message(answer)
            
            # Salvar pergunta e resposta no banco
            self._save_message_to_db(session_id, "user", question)
            self._save_message_to_db(session_id, "assistant", answer)
            
            logger.info(f"✅ Resposta gerada para: {question[:50]}... (fontes: {len(sources)})")
            
            return {
                "answer": answer,
                "sources": sources,
                "context_size": len(context) if context_parts else 0
            }
            
        except Exception as e:
            logger.error(f"Erro ao responder pergunta: {e}", exc_info=True)
            raise