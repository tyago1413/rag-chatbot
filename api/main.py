"""
API RAG com Litestar + LangChain
Endpoints: /chat e /scrape
VERSÃO CORRIGIDA: Processa arquivo E responde pergunta no mesmo request
"""
from litestar import Litestar, post, get, Request
from litestar.config.cors import CORSConfig
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body
from contextlib import asynccontextmanager
import logging

from app.services.rag_service import RAGService
from app.services.scraper_service import ScraperService
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rag_service = RAGService()
scraper_service = ScraperService()


@asynccontextmanager
async def lifespan(app: Litestar):
    """Inicialização e limpeza da aplicação"""
    logger.info("🚀 Inicializando API RAG...")
    
    # Scraping automático na inicialização
    try:
        logger.info(f"📄 Realizando scraping de: {settings.SCRAPE_URL}")
        await scraper_service.scrape_and_store()
        logger.info("✅ Scraping inicial concluído")
    except Exception as e:
        logger.error(f"⚠️  Erro no scraping inicial: {e}")
    
    yield
    
    logger.info("🛑 Encerrando API RAG...")


@get("/health")
async def health_check() -> dict:
    """Health check endpoint"""
    return {"status": "ok", "service": "rag-api"}


@post("/chat")
async def chat(
    request: Request,
    data: dict = Body(media_type=RequestEncodingType.MULTI_PART)
) -> dict:
    """
    Endpoint principal do chat
    COMPORTAMENTO:
    - Com arquivo + pergunta: processa arquivo E responde pergunta
    - Com arquivo sem pergunta: só processa arquivo
    - Sem arquivo: busca contexto e responde
    """
    try:
        question = data.get("question", "")
        session_id = data.get("session_id", "default")
        
        logger.info(f"📥 Requisição /chat - session: {session_id}")
        if question:
            logger.info(f"💬 Pergunta: {question[:100]}...")
        
        # Buscar arquivo em QUALQUER campo do form
        form = await request.form()
        uploaded_file = None
        file_field_name = None
        
        for key in form.keys():
            value = form[key]
            if hasattr(value, 'filename') and hasattr(value, 'read') and value.filename:
                uploaded_file = value
                file_field_name = key
                logger.info(f"📎 Arquivo detectado: {value.filename}")
                break
        
        # ===================================================================
        # CENÁRIO 1: TEM ARQUIVO
        # ===================================================================
        if uploaded_file:
            logger.info(f"✅ Processando arquivo: {uploaded_file.filename}")
            
            try:
                # Processar arquivo (com session_id para salvar documento ativo)
                doc_id = await rag_service.process_document(uploaded_file, session_id)
                logger.info(f"✅ Arquivo processado com sucesso: {doc_id}")
                
                # Se NÃO tem pergunta → só retornar confirmação
                if not question:
                    return {
                        "status": "success",
                        "message": f"Documento '{uploaded_file.filename}' processado com sucesso! Faça uma pergunta para consultar o conteúdo.",
                        "document_id": str(doc_id),
                        "filename": uploaded_file.filename
                    }
                
                # Se TEM pergunta → processar E responder no mesmo request
                # IMPORTANTE: Passa doc_id para priorizar este documento na busca
                logger.info(f"💭 Respondendo pergunta sobre o arquivo recém-processado...")
                
                response = await rag_service.answer_question(
                    question, 
                    session_id,
                    recent_document_id=str(doc_id)  # ⚠️ PRIORIZA ESTE DOCUMENTO
                )
                
                return {
                    "status": "success",
                    "message": f"Documento '{uploaded_file.filename}' processado!",
                    "document_id": str(doc_id),
                    "filename": uploaded_file.filename,
                    "answer": response["answer"],
                    "sources": response["sources"],
                    "session_id": session_id,
                    "context_size": response.get("context_size", 0)
                }
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Erro: {str(e)}",
                    "filename": uploaded_file.filename
                }
        
        # ===================================================================
        # CENÁRIO 2: SEM ARQUIVO - só pergunta
        # ===================================================================
        if not question:
            return {
                "status": "error",
                "message": "Você precisa enviar uma pergunta ou um arquivo"
            }
        
        logger.info(f"💬 Respondendo pergunta sem arquivo...")
        response = await rag_service.answer_question(question, session_id)
        
        return {
            "status": "success",
            "answer": response["answer"],
            "sources": response["sources"],
            "session_id": session_id,
            "context_size": response.get("context_size", 0)
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no chat: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }


@post("/scrape")
async def scrape(data: dict = Body(media_type=RequestEncodingType.MULTI_PART)) -> dict:
    """
    Endpoint para executar scraping manual
    
    Parâmetros opcionais:
    - url: URL para fazer scraping (default: SCRAPE_URL do .env)
    - headers: Headers customizados em JSON (opcional)
    """
    try:
        url = data.get("url", settings.SCRAPE_URL)
        
        # Parse headers se fornecidos
        custom_headers = None
        if "headers" in data:
            try:
                import json
                custom_headers = json.loads(data["headers"])
            except:
                logger.warning("Headers customizados inválidos, usando padrão")
        
        logger.info(f"🌐 Iniciando scraping de: {url}")
        doc_id = await scraper_service.scrape_and_store(url, custom_headers)
        
        return {
            "status": "success",
            "message": "Scraping concluído com sucesso",
            "document_id": str(doc_id),
            "url": url
        }
        
    except Exception as e:
        logger.error(f"❌ Erro no scraping: {e}", exc_info=True)
        return {
            "status": "error", 
            "message": str(e),
            "tip": "Se você está tendo erro 403/bloqueio, o site pode estar protegido contra scraping automatizado. LinkedIn, por exemplo, bloqueia bots."
        }


@get("/history/{session_id:str}")
async def get_history(session_id: str, limit: int = 20) -> dict:
    """
    Consultar histórico de uma sessão específica
    """
    try:
        from app.database import db
        
        query = """
            SELECT session_id, turn, role, content, 
                   to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at
            FROM chat_history
            WHERE session_id = %s
            ORDER BY turn ASC
            LIMIT %s
        """
        
        messages = db.execute_query(query, (session_id, limit), fetch=True)
        
        return {
            "status": "success",
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao buscar histórico: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@get("/sessions")
async def list_sessions(limit: int = 50) -> dict:
    """
    Listar todas as sessões com contagem de mensagens
    """
    try:
        from app.database import db
        
        query = """
            SELECT 
                session_id,
                COUNT(*) as message_count,
                to_char(MIN(created_at), 'YYYY-MM-DD HH24:MI:SS') as first_message,
                to_char(MAX(created_at), 'YYYY-MM-DD HH24:MI:SS') as last_message
            FROM chat_history
            GROUP BY session_id
            ORDER BY MAX(created_at) DESC
            LIMIT %s
        """
        
        sessions = db.execute_query(query, (limit,), fetch=True)
        
        return {
            "status": "success",
            "session_count": len(sessions),
            "sessions": sessions
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar sessões: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@get("/documents")
async def list_documents(limit: int = 50) -> dict:
    """
    Listar todos os documentos armazenados
    """
    try:
        from app.database import db
        
        query = """
            SELECT 
                d.id,
                d.source,
                d.title,
                d.metadata,
                to_char(d.created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                COUNT(c.id) as chunk_count
            FROM documents d
            LEFT JOIN chunks c ON d.id = c.document_id
            GROUP BY d.id, d.source, d.title, d.metadata, d.created_at
            ORDER BY d.created_at DESC
            LIMIT %s
        """
        
        documents = db.execute_query(query, (limit,), fetch=True)
        
        return {
            "status": "success",
            "document_count": len(documents),
            "documents": documents
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao listar documentos: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


app = Litestar(
    route_handlers=[
        health_check,
        chat,
        scrape,
        get_history,
        list_sessions,
        list_documents
    ],
    lifespan=[lifespan],
    cors_config=CORSConfig(allow_origins=["*"]),
    debug=True
)