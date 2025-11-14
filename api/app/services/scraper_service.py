"""
Serviço de Scraping Web
"""
from bs4 import BeautifulSoup
import httpx
import uuid
import logging
import json
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings


from app.config import settings
from app.database import db

logger = logging.getLogger(__name__)

# Headers para evitar bloqueios de anti-bot
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36 RAGBot/1.0"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


class ScraperService:
    """Serviço de scraping de páginas web"""
    
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'}
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len
        )
    
    async def scrape_and_store(self, url: str = None, custom_headers: dict = None) -> uuid.UUID:
        """
        Realiza scraping e armazena no banco
        
        Args:
            url: URL para fazer scraping (usa SCRAPE_URL se não fornecida)
            custom_headers: Headers customizados (usa DEFAULT_HEADERS se não fornecidos)
        """
        try:
            scrape_url = url or settings.SCRAPE_URL
            headers = custom_headers or DEFAULT_HEADERS
            
            logger.info(f"🌐 Iniciando scraping de: {scrape_url}")
            
            # Fazer requisição com headers
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers=headers
            ) as client:
                response = await client.get(scrape_url)
                response.raise_for_status()
            
            logger.info(f"✅ Resposta recebida: {response.status_code} ({len(response.content)} bytes)")
            
            # Detectar encoding correto
            response.encoding = response.encoding or 'utf-8'
            
            # Parsear HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extrair título
            title = soup.find('h1')
            if not title:
                title = soup.find('title')
            title_text = title.get_text(strip=True) if title else "Página sem título"
            
            logger.info(f"📝 Título: {title_text}")
            
            # Remover elementos indesejados
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']):
                element.decompose()
            
            # Extrair texto principal com estratégias diferentes por site
            text = self._extract_main_content(soup, scrape_url)
            
            # Limpar texto
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            text = '\n'.join(lines)
            
            if not text or len(text) < 100:
                raise ValueError(f"Texto extraído muito curto ({len(text)} chars). Possível bloqueio ou página vazia.")
            
            logger.info(f"📄 Texto extraído: {len(text)} caracteres")
            
            # Criar documento no banco
            doc_id = uuid.uuid4()
            query = """
                INSERT INTO documents (id, source, title, metadata)
                VALUES (%s, %s, %s, %s)
            """
            metadata = json.dumps({
                "url": scrape_url,
                "scraped_at": "now",
                "text_length": len(text),
                "status_code": response.status_code,
                "content_type": response.headers.get('content-type', 'unknown')
            })
            db.execute_query(
                query,
                (str(doc_id), f"scrape:{scrape_url}", title_text, metadata)
            )
            
            # Dividir em chunks
            chunks = self.text_splitter.split_text(text)
            logger.info(f"📄 Conteúdo dividido em {len(chunks)} chunks")
            
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
            
            logger.info(f"✅ Scraping concluído: {title_text}")
            return doc_id
            
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Erro HTTP {e.response.status_code}: {e}")
            if e.response.status_code == 403:
                logger.error("⚠️  Acesso negado (403). Possível bloqueio anti-bot.")
                logger.error("   Dica: Alguns sites como LinkedIn bloqueiam scraping automatizado.")
            raise
        except Exception as e:
            logger.error(f"❌ Erro no scraping: {e}")
            raise
    
    def _extract_main_content(self, soup: BeautifulSoup, url: str) -> str:
        """
        Extrai conteúdo principal baseado no tipo de site
        
        Estratégias diferentes para:
        - Wikipedia
        - LinkedIn
        - Sites genéricos
        """
        text_parts = []
        
        # Wikipedia
        if 'wikipedia.org' in url:
            main_content = soup.find('div', {'id': 'mw-content-text'})
            if main_content:
                # Remover boxes laterais e referências
                for unwanted in main_content.find_all(['table', 'div'], class_=['infobox', 'navbox', 'reflist']):
                    unwanted.decompose()
                return main_content.get_text(separator='\n', strip=True)
        
        # LinkedIn (conteúdo principal geralmente em article ou main)
        elif 'linkedin.com' in url:
            # LinkedIn tem estrutura específica
            article = soup.find('article') or soup.find('main')
            if article:
                return article.get_text(separator='\n', strip=True)
            
            # Fallback: tentar divs com classes comuns do LinkedIn
            for class_name in ['core-rail', 'main-content', 'content-main', 'article-content']:
                content = soup.find('div', class_=class_name)
                if content:
                    return content.get_text(separator='\n', strip=True)
        
        # Medium, blogs
        elif any(domain in url for domain in ['medium.com', 'blog', 'article']):
            article = soup.find('article')
            if article:
                return article.get_text(separator='\n', strip=True)
        
        # Estratégia genérica: tentar tags semânticas primeiro
        for tag in ['article', 'main', 'section']:
            content = soup.find(tag)
            if content:
                text = content.get_text(separator='\n', strip=True)
                if len(text) > 200:  # Conteúdo significativo
                    return text
        
        # Fallback: pegar parágrafos
        paragraphs = soup.find_all('p')
        if paragraphs:
            text_parts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50]
            if text_parts:
                return '\n\n'.join(text_parts)
        
        # Último recurso: todo o texto
        return soup.get_text(separator='\n', strip=True)