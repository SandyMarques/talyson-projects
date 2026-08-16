# Imagem base Python slim para menor tamanho e maior segurança
FROM python:3.11-slim

# Variáveis de ambiente Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Diretório de trabalho
WORKDIR /app

# Instalação de dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalação de dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia código fonte da aplicação
COPY app/ ./app/
COPY pyproject.toml .

# Criação de diretórios de dados com permissões adequadas
RUN mkdir -p /app/data/chroma /app/data/uploads

# Exposição da porta da API
EXPOSE 8000

# Comando de inicialização do servidor Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
