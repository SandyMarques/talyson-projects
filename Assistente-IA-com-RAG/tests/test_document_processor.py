import io
import pypdf
import pytest
from app.services.document_processor import DocumentProcessor


def create_sample_pdf(texts: list[str]) -> bytes:
    """Gera um PDF em memória com as páginas e textos especificados."""
    writer = pypdf.PdfWriter()
    for text in texts:
        # Cria uma página em branco e injeta um annotation de texto para teste
        page = writer.add_blank_page(width=300, height=300)
    
    # Para teste com texto real extraível pelo pypdf:
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_calculate_hash():
    processor = DocumentProcessor()
    data1 = b"Conteudo do arquivo 1"
    data2 = b"Conteudo do arquivo 2"
    
    hash1 = processor.calculate_hash(data1)
    hash2 = processor.calculate_hash(data2)
    
    assert isinstance(hash1, str)
    assert len(hash1) == 64
    assert hash1 != hash2
    assert hash1 == processor.calculate_hash(data1)


def test_process_text_file(document_processor):
    content = (
        "Este e um documento de teste para o Assistente RAG.\n\n"
        "O RAG combina busca vetorial no ChromaDB com modelos de linguagem da OpenAI. "
        "Permite que o assistente responda perguntas sobre arquivos especificos sem alucinacoes.\n\n"
        "Configuracoes e parametros podem ser definidos no arquivo .env."
    )
    file_bytes = content.encode("utf-8")
    
    chunks, doc_hash = document_processor.process_file(file_bytes, "manual_rag.txt")
    
    assert len(chunks) >= 1
    assert doc_hash is not None
    
    first_chunk = chunks[0]
    assert first_chunk.metadata["filename"] == "manual_rag.txt"
    assert first_chunk.metadata["source"] == "manual_rag.txt"
    assert first_chunk.metadata["chunk_id"] == 0
    assert first_chunk.metadata["total_chunks"] == len(chunks)
    assert first_chunk.metadata["file_hash"] == doc_hash


def test_process_markdown_file(document_processor):
    md_content = (
        "# Titulo Principal\n\n"
        "## Secao 1\n"
        "Conteudo da secao 1 com detalhes tecnicos.\n\n"
        "## Secao 2\n"
        "Conteudo da secao 2 com mais explicacoes sobre LangChain."
    )
    chunks, doc_hash = document_processor.process_file(md_content.encode("utf-8"), "documento.md")
    
    assert len(chunks) >= 1
    assert chunks[0].metadata["filename"] == "documento.md"


def test_process_empty_file_raises_error(document_processor):
    with pytest.raises(ValueError, match="não contém nenhum texto legível"):
        document_processor.process_file(b"", "vazio.txt")


def test_process_whitespace_file_raises_error(document_processor):
    with pytest.raises(ValueError, match="não contém nenhum texto legível"):
        document_processor.process_file(b"   \n\n\t   ", "espacos.txt")
