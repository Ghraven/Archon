import os
import sys
import asyncio
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import AsyncOpenAI
from supabase import create_client, Client

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

from tiktoken import get_encoding
from transformers.tokenization_utils_base import PreTrainedTokenizerBase

load_dotenv()

# Initialize OpenAI and Supabase clients
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)


@dataclass
class ProcessedChunk:
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]

def validate_chunk(chunk: ProcessedChunk):
    """Validate chunk structure before processing"""
    if not isinstance(chunk.content, str):
        raise TypeError(f"Chunk content must be string, got {type(chunk.content)}")
    if len(chunk.embedding) not in (1536, 0):  # Allow zero-vector errors
        raise ValueError(f"Invalid embedding size: {len(chunk.embedding)}")
    if not chunk.url.startswith(('http://', 'https://')):
        raise ValueError(f"Invalid URL format: {chunk.url}")

# ----------------------------------------
# Tokenizer Wrapper for OpenAI
# ----------------------------------------

class TokenizerWrapperOpenAI(PreTrainedTokenizerBase):
    """Minimal wrapper for OpenAI's tokenizer."""
    def __init__(self, model_name: str = "cl100k_base", max_length: int = 8191, **kwargs):
        super().__init__(model_max_length=max_length, **kwargs)
        self.tokenizer = get_encoding(model_name)
        self._vocab_size = self.tokenizer.max_token_value

    def tokenize(self, text: str, **kwargs) -> List[str]:
        return [str(t) for t in self.tokenizer.encode(text)]

    def _tokenize(self, text: str) -> List[str]:
        return self.tokenize(text)

    def _convert_token_to_id(self, token: str) -> int:
        return int(token)

    def _convert_id_to_token(self, index: int) -> str:
        return str(index)

    def get_vocab(self) -> Dict[str, int]:
        return dict(enumerate(range(self.vocab_size)))

    @property
    def vocab_size(self) -> int:
        return self._vocab_size

    def save_vocabulary(self, *args) -> Tuple[str]:
        return ()

    def encode(self, text: str, add_special_tokens: bool = False) -> List[int]:
        return self.tokenizer.encode(text)

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        return cls()

# ----------------------------------------
# Chunking
# ----------------------------------------

def chunker(url: str) -> List[ProcessedChunk]:
    """Chunk the document from the given URL using docling."""
    converter = DocumentConverter()
    result = converter.convert(url)

    tokenizer = TokenizerWrapperOpenAI()
    MAX_TOKENS = 8191

    chunker_instance = HybridChunker(
        tokenizer=tokenizer,
        max_tokens=MAX_TOKENS,
        merge_peers=True,
    )

    chunk_iter = chunker_instance.chunk(dl_doc=result.document)
    chunks = list(chunk_iter)

    processed_chunks = []
    for i, chunk in enumerate(chunks):
        content = chunk.render(format="markdown") if hasattr(chunk, 'render') else str(chunk)
        processed_chunk = ProcessedChunk(
            url=url,
            chunk_number=i,
            title="",
            summary="",
            content=content,
            metadata={},
            embedding=[]
        )
        processed_chunks.append(processed_chunk)

    return processed_chunks

# ----------------------------------------
# Title and Summary Extraction
# ----------------------------------------

async def get_title_and_summary(chunk_text: str, url: str, max_retries: int = 5) -> Dict[str, str]:
    """Extract title and summary using GPT-4."""
    system_prompt = """You are an AI that extracts titles and summaries from documentation chunks.
    Return a JSON object with 'title' and 'summary' keys.
    For the title: If this seems like the start of a document, extract its title. If it's a middle chunk, derive a descriptive title.
    For the summary: Create a concise summary of the main points in this chunk.
    Keep both title and summary concise but informative."""

    # Truncate content to avoid token limit issues
    MAX_CONTENT_TOKENS = 4000  # Leave room for system prompt and other tokens
    tokenizer = TokenizerWrapperOpenAI()
    tokens = tokenizer.encode(chunk_text)
    if len(tokens) > MAX_CONTENT_TOKENS:
        chunk_text = tokenizer.tokenizer.decode(tokens[:MAX_CONTENT_TOKENS])

    for attempt in range(max_retries):
        try:
            response = await openai_client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"URL: {url}\n\nContent:\n{chunk_text}"}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            if attempt < max_retries - 1:
                # Increased backoff for any error
                await asyncio.sleep(min(32, 2 ** attempt))  # Cap at 32 seconds
                if "rate_limit" in str(e):
                    # Extra delay for rate limits
                    await asyncio.sleep(2)
                continue
            print(f"Error getting title and summary for URL {url}: {e}")
            return {"title": "Error processing title", "summary": "Error processing summary"}

# ----------------------------------------
# Embedding
# ----------------------------------------

async def get_embedding(text: str, max_retries: int = 5) -> List[float]:
    """Obtain embedding vector from OpenAI."""
    # Truncate text to fit within token limit
    MAX_TOKENS = 8000  # Leave some margin below 8192
    tokenizer = TokenizerWrapperOpenAI()
    tokens = tokenizer.encode(text)
    if len(tokens) > MAX_TOKENS:
        text = tokenizer.tokenizer.decode(tokens[:MAX_TOKENS])

    for attempt in range(max_retries):
        try:
            response = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            if attempt < max_retries - 1:
                # Increased backoff for any error
                await asyncio.sleep(min(32, 2 ** attempt))  # Cap at 32 seconds
                if "rate_limit" in str(e):
                    # Extra delay for rate limits
                    await asyncio.sleep(2)
                continue
            print(f"Error getting embedding: {e}")
            return [0] * 1536

# ----------------------------------------
# Insert Chunk into Database
# ----------------------------------------

async def insert_chunk(chunk: ProcessedChunk):
    """Insert a processed chunk into Supabase."""
    try:
        data = {
            "url": chunk.url,
            "chunk_number": chunk.chunk_number,
            "title": chunk.title,
            "summary": chunk.summary,
            "content": chunk.content,
            "metadata": chunk.metadata,
            "embedding": chunk.embedding
        }
        result = supabase.table("site_pages").insert(data).execute()
        print(f"Inserted chunk {chunk.chunk_number} for {chunk.url}")
        return result
    except Exception as e:
        print(f"Error inserting chunk for URL {chunk.url}: {e}")
        return None

# ----------------------------------------
# Process a Single URL (with Metadata)
# ----------------------------------------

async def process_and_insert_chunk(chunk: ProcessedChunk, url: str):
    """Process a single chunk and insert into database."""
    validate_chunk(chunk)  # Pre-validation
    chunk_text = chunk.content
    # Extract title and summary
    ts = await get_title_and_summary(chunk_text, url)
    chunk.title = ts.get("title", "")
    chunk.summary = ts.get("summary", "")
    # Get embedding
    chunk.embedding = await get_embedding(chunk_text)
    # Generate metadata
    chunk.metadata = {
        "source": "pydantic_ai_docs",
        "chunk_size": len(chunk_text),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "url_path": urlparse(url).path
    }
    await insert_chunk(chunk)

async def process_url(url: str, semaphore: asyncio.Semaphore):
    """Process a single URL: chunk, enrich, attach metadata, and store in DB."""
    print(f"Processing URL: {url}")
    chunks = chunker(url)
    
    # Process chunks with concurrency control
    async with semaphore:
        async with asyncio.TaskGroup() as tg:
            for chunk in chunks:
                tg.create_task(process_and_insert_chunk(chunk, url))
    print(f"Finished processing URL: {url}")

# ----------------------------------------
# Sitemap Parsing
# ----------------------------------------

def get_sitemap_urls(base_url: str, sitemap_filename: str = "sitemap.xml") -> List[str]:
    """Fetch and parse a sitemap XML file to extract URLs."""
    try:
        sitemap_url = urljoin(base_url, sitemap_filename)
        response = requests.get(sitemap_url, timeout=10)
        if response.status_code == 404:
            return [base_url.rstrip("/")]
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespaces = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        if namespaces:
            urls = [elem.text for elem in root.findall(".//ns:loc", namespaces)]
        else:
            urls = [elem.text for elem in root.findall(".//loc")]
        return urls
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch sitemap: {str(e)}")
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse sitemap XML: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error processing sitemap: {str(e)}")

# ----------------------------------------
# Main Orchestration Function
# ----------------------------------------

async def main():
    sitemap_arg = sys.argv[1] if len(sys.argv) > 1 else "https://ai.pydantic.dev/"
    print(f"Processing sitemap: {sitemap_arg}")
    urls = get_sitemap_urls(sitemap_arg)
    print(f"Found {len(urls)} URLs in the sitemap")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(3)  # Limit concurrent URL processing
    
    tasks = [process_url(url, semaphore) for url in urls]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
