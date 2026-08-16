document.addEventListener('DOMContentLoaded', () => {
    // Elementos da Interface
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadProgress = document.getElementById('upload-progress');
    const uploadStatusText = document.getElementById('upload-status-text');
    const docsList = document.getElementById('docs-list');
    const refreshDocsBtn = document.getElementById('refresh-docs-btn');
    const statTotalDocs = document.getElementById('stat-total-docs');
    const statTotalChunks = document.getElementById('stat-total-chunks');
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const queryInput = document.getElementById('query-input');
    const sendButton = document.getElementById('send-button');
    const clearChatBtn = document.getElementById('clear-chat-btn');
    const toast = document.getElementById('toast');

    // Estado da Aplicação
    let chatHistory = [];
    let isProcessing = false;

    // Inicialização
    fetchHealthStatus();
    loadDocuments();

    // =========================================================================
    // Funções de Notificação Toast
    // =========================================================================
    function showToast(message, type = 'info') {
        toast.textContent = message;
        toast.className = `toast ${type}`;
        setTimeout(() => {
            toast.className = 'toast hidden';
        }, 4000);
    }

    // =========================================================================
    // Verificação de Integridade (Health Check)
    // =========================================================================
    async function fetchHealthStatus() {
        try {
            const res = await fetch('/api/v1/health');
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'ok') {
                    statusIndicator.className = 'status-indicator online';
                    statusText.textContent = `Online • ${data.total_indexed_chunks} chunks`;
                } else {
                    statusIndicator.className = 'status-indicator';
                    statusText.textContent = 'Vector Store Degradado';
                }
            } else {
                throw new Error('Falha no health check');
            }
        } catch (e) {
            statusIndicator.className = 'status-indicator';
            statusText.textContent = 'Servidor Offline';
        }
    }

    // =========================================================================
    // Gerenciamento e Listagem de Documentos
    // =========================================================================
    async function loadDocuments() {
        try {
            const res = await fetch('/api/v1/documents');
            if (!res.ok) throw new Error('Erro ao listar documentos');
            const data = await res.json();

            statTotalDocs.textContent = data.total_documents;
            statTotalChunks.textContent = data.total_chunks;

            if (!data.documents || data.documents.length === 0) {
                docsList.innerHTML = '<div class="empty-state">Nenhum documento indexado ainda. Envie um arquivo acima.</div>';
                return;
            }

            docsList.innerHTML = '';
            data.documents.forEach(doc => {
                const item = document.createElement('div');
                item.className = 'doc-item';
                
                const pagesText = doc.pages ? ` • ${doc.pages.length} pág(s)` : '';
                item.innerHTML = `
                    <div class="doc-info">
                        <span class="doc-name" title="${doc.filename}">${doc.filename}</span>
                        <span class="doc-meta">${doc.chunks_count} chunks${pagesText}</span>
                    </div>
                    <button class="icon-button delete-doc-btn" data-filename="${encodeURIComponent(doc.filename)}" title="Excluir documento">
                        ✖
                    </button>
                `;
                docsList.appendChild(item);
            });

            // Bind dos botões de exclusão
            document.querySelectorAll('.delete-doc-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const filename = decodeURIComponent(e.currentTarget.getAttribute('data-filename'));
                    if (confirm(`Deseja realmente remover o documento '${filename}' da base de conhecimento?`)) {
                        await deleteDocument(filename);
                    }
                });
            });

        } catch (error) {
            console.error('Erro ao carregar documentos:', error);
            showToast('Falha ao carregar lista de documentos.', 'error');
        }
    }

    async function deleteDocument(filename) {
        try {
            const res = await fetch(`/api/v1/documents/${encodeURIComponent(filename)}`, {
                method: 'DELETE'
            });
            if (res.ok) {
                showToast(`Documento '${filename}' removido com sucesso.`, 'success');
                await loadDocuments();
                await fetchHealthStatus();
            } else {
                const err = await res.json();
                showToast(`Erro ao excluir: ${err.detail || 'Falha na requisição'}`, 'error');
            }
        } catch (error) {
            showToast('Erro de conexão ao excluir documento.', 'error');
        }
    }

    // =========================================================================
    // Upload de Documentos e Drag & Drop
    // =========================================================================
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', async (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            await handleFilesUpload(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            await handleFilesUpload(e.target.files);
            fileInput.value = '';
        }
    });

    refreshDocsBtn.addEventListener('click', async () => {
        await loadDocuments();
        await fetchHealthStatus();
        showToast('Lista de documentos atualizada.', 'info');
    });

    async function handleFilesUpload(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            await uploadSingleFile(file);
        }
        await loadDocuments();
        await fetchHealthStatus();
    }

    async function uploadSingleFile(file) {
        uploadProgress.classList.remove('hidden');
        uploadStatusText.textContent = `Processando '${file.name}'...`;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/v1/documents/upload', {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                showToast(data.message, 'success');
            } else {
                const err = await response.json();
                showToast(`Erro no upload de '${file.name}': ${err.detail || 'Falha no processamento'}`, 'error');
            }
        } catch (error) {
            console.error('Erro no upload:', error);
            showToast(`Erro de conexão ao enviar '${file.name}'.`, 'error');
        } finally {
            uploadProgress.classList.add('hidden');
        }
    }

    // =========================================================================
    // Chat e Mensagens
    // =========================================================================
    // Ajuste dinâmico de altura do Textarea
    queryInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = `${Math.min(this.scrollHeight, 140)}px`;
    });

    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query || isProcessing) return;

        // Limpa campo e reseta altura
        queryInput.value = '';
        queryInput.style.height = 'auto';

        // Renderiza mensagem do usuário
        appendMessage('user', query);
        chatHistory.push({ role: 'user', content: query });

        // Adiciona indicador de digitação do assistente
        const typingElem = appendTypingIndicator();
        isProcessing = true;
        sendButton.disabled = true;

        try {
            const response = await fetch('/api/v1/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: query,
                    history: chatHistory.slice(-6), // Mantém os últimos 6 turnos de contexto
                })
            });

            typingElem.remove();

            if (response.ok) {
                const data = await response.json();
                appendAssistantMessage(data);
                chatHistory.push({ role: 'assistant', content: data.answer });
            } else {
                const err = await response.json();
                appendMessage('assistant', `⚠️ Erro ao consultar assistente: ${err.detail || 'Falha interna'}`);
            }
        } catch (error) {
            typingElem.remove();
            appendMessage('assistant', '⚠️ Não foi possível conectar ao servidor para processar sua pergunta.');
        } finally {
            isProcessing = false;
            sendButton.disabled = false;
            queryInput.focus();
        }
    });

    clearChatBtn.addEventListener('click', () => {
        if (confirm('Deseja limpar todo o histórico desta conversa?')) {
            chatMessages.innerHTML = `
                <div class="message assistant-message welcome-message">
                    <div class="avatar">🤖</div>
                    <div class="message-body">
                        <div class="message-sender">Assistente RAG</div>
                        <div class="message-content">
                            <p>Conversa reiniciada. Como posso ajudar com seus documentos?</p>
                        </div>
                    </div>
                </div>
            `;
            chatHistory = [];
        }
    });

    function appendMessage(role, content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}-message`;

        const avatar = role === 'user' ? '👤' : '🤖';
        const sender = role === 'user' ? 'Você' : 'Assistente RAG';

        msgDiv.innerHTML = `
            <div class="avatar">${avatar}</div>
            <div class="message-body">
                <div class="message-sender">${sender}</div>
                <div class="message-content">${formatMarkdown(content)}</div>
            </div>
        `;

        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function appendAssistantMessage(data) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message assistant-message';

        let sourcesHtml = '';
        if (data.sources && data.sources.length > 0) {
            const sourceCards = data.sources.map((s, idx) => {
                const pageBadge = s.page ? ` (Pág. ${s.page})` : '';
                const scoreText = s.score !== null ? `Relevância: ${(1 - s.score).toFixed(2)}` : '';
                return `
                    <div class="source-card">
                        <div class="source-card-header">
                            <span>📄 ${s.source}${pageBadge}</span>
                            <small>${scoreText}</small>
                        </div>
                        <div class="source-card-content">${escapeHtml(s.content)}</div>
                    </div>
                `;
            }).join('');

            sourcesHtml = `
                <div class="sources-container">
                    <button class="sources-toggle-btn" onclick="this.nextElementSibling.classList.toggle('hidden')">
                        📎 Fontes Citadas (${data.sources.length}) ▼
                    </button>
                    <div class="sources-list hidden">
                        ${sourceCards}
                    </div>
                </div>
            `;
        }

        msgDiv.innerHTML = `
            <div class="avatar">🤖</div>
            <div class="message-body">
                <div class="message-sender">Assistente RAG</div>
                <div class="message-content">
                    ${formatMarkdown(data.answer)}
                    ${sourcesHtml}
                </div>
                <div class="message-meta">
                    <span>Modelo: ${data.model_used}</span>
                    <span>Tempo: ${data.execution_time_ms}ms</span>
                </div>
            </div>
        `;

        chatMessages.appendChild(msgDiv);
        scrollToBottom();
    }

    function appendTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message assistant-message';
        typingDiv.innerHTML = `
            <div class="avatar">🤖</div>
            <div class="message-body">
                <div class="message-sender">Assistente RAG</div>
                <div class="message-content">
                    <div class="typing-indicator">
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                        <span class="typing-dot"></span>
                    </div>
                </div>
            </div>
        `;
        chatMessages.appendChild(typingDiv);
        scrollToBottom();
        return typingDiv;
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // =========================================================================
    // Formatadores e Utilitários de Texto
    // =========================================================================
    function escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }

    function formatMarkdown(text) {
        if (!text) return '';
        let escaped = escapeHtml(text);

        // Bloco de código
        escaped = escaped.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        // Código inline
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        // Negrito
        escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Itálico
        escaped = escaped.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        // Quebras de linha
        escaped = escaped.replace(/\n\n/g, '</p><p>');
        escaped = escaped.replace(/\n/g, '<br>');

        return `<p>${escaped}</p>`;
    }
});
