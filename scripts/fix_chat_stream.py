"""
Fix form submit page reload bug and add rich server console telemetry.
"""
from pathlib import Path

DEST_DIR = Path(r"C:\Dev\ai-chatbot")

def fix_index_html():
    path = DEST_DIR / "static" / "index.html"
    content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Chatbot — Fast Local LLM</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>&#128172;</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <link rel="stylesheet" href="/static/style.css?v=3">
</head>
<body>
    <div class="app-container">
        <!-- Left Sidebar: Sessions -->
        <aside class="sidebar">
            <div class="sidebar-header">
                <div class="brand">
                    <span class="brand-icon">&#128172;</span>
                    <span class="brand-title">AI Chatbot</span>
                </div>
                <button id="newChatBtn" class="btn btn-new-chat" title="New Conversation (Ctrl+N)">
                    <span>+ New Chat</span>
                </button>
            </div>

            <div class="sessions-scroll" id="sessionsList">
                <!-- Dynamically loaded chat sessions -->
            </div>

            <div class="sidebar-footer">
                <div class="model-pill">
                    <span class="pulse-dot"></span>
                    <span id="sidebarModelName">qwen3.5:9b</span>
                </div>
                <div class="port-tag">Port 8080</div>
            </div>
        </aside>

        <!-- Main Chat Surface -->
        <main class="chat-viewport">
            <header class="topbar">
                <div class="topbar-left">
                    <div class="model-selector-box" title="Select Local Model">
                        <span class="control-label">&#9881;&#65039; Model:</span>
                        <select id="modelSelect" class="styled-select"></select>
                    </div>
                </div>

                <div class="topbar-right">
                    <div class="perf-tag" id="perfTag">&#9889; -- tok/s</div>
                </div>
            </header>

            <section class="messages-container" id="messagesContainer">
                <div class="empty-state" id="emptyState">
                    <div class="empty-icon">&#129302;</div>
                    <h2>How can I help you today?</h2>
                    <p>Direct local responses. Fast, private, and zero cloud dependencies.</p>
                    <div class="suggestion-chips">
                        <button class="chip" onclick="usePrompt('Explain how quantum entanglement works simply.')">&#128161; Quantum physics simply</button>
                        <button class="chip" onclick="usePrompt('Write a Python function to compute moving averages.')">&#128013; Python moving average</button>
                        <button class="chip" onclick="usePrompt('Draft a concise professional project status email.')">&#9993;&#65039; Status update email</button>
                    </div>
                </div>
            </section>

            <footer class="input-container">
                <form id="chatForm" class="input-dock" onsubmit="event.preventDefault(); handleSend(); return false;">
                    <textarea 
                        id="promptInput" 
                        placeholder="Type a message... (Press Enter to send, Shift+Enter for newline)"
                        rows="1"
                    ></textarea>
                    <div class="dock-actions">
                        <button type="button" id="sendBtn" class="btn btn-send" onclick="handleSend()" title="Send message">
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </form>
            </footer>
        </main>
    </div>

    <script src="/static/app.js?v=3"></script>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")
    print("[OK] index.html updated")

def fix_app_js():
    path = DEST_DIR / "static" / "app.js"
    content = """// AI Chatbot — Direct Streaming Controller (Zero Reasoning Overhead)
let activeSessionId = null;
let isStreaming = false;

// DOM references
const sessionsList = document.getElementById("sessionsList");
const newChatBtn = document.getElementById("newChatBtn");
const modelSelect = document.getElementById("modelSelect");
const sidebarModelName = document.getElementById("sidebarModelName");
const perfTag = document.getElementById("perfTag");
const messagesContainer = document.getElementById("messagesContainer");
const emptyState = document.getElementById("emptyState");
const chatForm = document.getElementById("chatForm");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");

// Markdown configuration
marked.setOptions({
    highlight: function(code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            return hljs.highlight(code, { language: lang }).value;
        }
        return hljs.highlightAuto(code).value;
    },
    breaks: true
});

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    loadModels();
    loadSessions();
    setupEventListeners();
});

function setupEventListeners() {
    if (newChatBtn) {
        newChatBtn.addEventListener("click", () => createNewChat());
    }
    
    if (promptInput) {
        promptInput.addEventListener("input", () => {
            promptInput.style.height = "auto";
            promptInput.style.height = Math.min(promptInput.scrollHeight, 200) + "px";
        });

        promptInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
            }
        });
    }

    window.addEventListener("keydown", (e) => {
        if (e.ctrlKey && e.key.toLowerCase() === "n") {
            e.preventDefault();
            createNewChat();
        }
    });

    if (chatForm) {
        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            handleSend();
            return false;
        });
    }
}

function handleSend() {
    if (!promptInput || isStreaming) return;
    const prompt = promptInput.value.trim();
    if (!prompt) return;
    sendMessage(prompt);
}
window.handleSend = handleSend;

function usePrompt(text) {
    if (!promptInput) return;
    promptInput.value = text;
    promptInput.focus();
    handleSend();
}
window.usePrompt = usePrompt;

async function loadModels() {
    try {
        const res = await fetch("/api/models");
        const data = await res.json();
        if (!modelSelect) return;
        modelSelect.innerHTML = "";
        data.models.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            if (m === data.default) opt.selected = true;
            modelSelect.appendChild(opt);
        });
        if (sidebarModelName) sidebarModelName.textContent = modelSelect.value;
        modelSelect.addEventListener("change", () => {
            if (sidebarModelName) sidebarModelName.textContent = modelSelect.value;
        });
    } catch (e) {
        console.error("Failed to load models:", e);
    }
}

async function loadSessions() {
    try {
        const res = await fetch("/api/sessions");
        const data = await res.json();
        activeSessionId = data.active_session_id;
        renderSessions(data.sessions);
        if (activeSessionId) {
            loadMessages(activeSessionId);
        }
    } catch (e) {
        console.error("Failed to load sessions:", e);
    }
}

function renderSessions(sessions) {
    if (!sessionsList) return;
    sessionsList.innerHTML = "";
    sessions.forEach(sess => {
        const item = document.createElement("div");
        item.className = `session-item ${sess.id === activeSessionId ? "active" : ""}`;
        item.dataset.id = sess.id;

        const title = document.createElement("span");
        title.className = "session-title-text";
        title.textContent = sess.title || "New Chat";
        title.addEventListener("click", () => switchSession(sess.id));

        const delBtn = document.createElement("button");
        delBtn.className = "session-delete-btn";
        delBtn.innerHTML = "&#10005;";
        delBtn.title = "Delete conversation";
        delBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteSession(sess.id);
        });

        item.appendChild(title);
        item.appendChild(delBtn);
        sessionsList.appendChild(item);
    });
}

async function switchSession(sessionId) {
    if (isStreaming || sessionId === activeSessionId) return;
    try {
        await fetch(`/api/sessions/${sessionId}/activate`, { method: "POST" });
        activeSessionId = sessionId;
        document.querySelectorAll(".session-item").forEach(el => {
            el.classList.toggle("active", el.dataset.id === sessionId);
        });
        loadMessages(sessionId);
    } catch (e) {
        console.error("Failed to activate session:", e);
    }
}

async function createNewChat() {
    if (isStreaming) return;
    try {
        const res = await fetch("/api/sessions", { method: "POST" });
        const newSess = await res.json();
        await loadSessions();
        await switchSession(newSess.id);
        if (promptInput) promptInput.focus();
    } catch (e) {
        console.error("Failed to create session:", e);
    }
}

async function deleteSession(sessionId) {
    if (!confirm("Delete this conversation?")) return;
    try {
        await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
        await loadSessions();
    } catch (e) {
        console.error("Failed to delete session:", e);
    }
}

async function loadMessages(sessionId) {
    try {
        const res = await fetch(`/api/messages?session_id=${sessionId}`);
        const messages = await res.json();
        if (!messagesContainer) return;
        messagesContainer.innerHTML = "";

        if (messages.length === 0) {
            if (emptyState) {
                messagesContainer.appendChild(emptyState);
                emptyState.style.display = "flex";
            }
            return;
        }

        if (emptyState) emptyState.style.display = "none";
        messages.forEach(m => {
            if (m.role === "user") {
                appendUserMessage(m.content);
            } else if (m.role === "assistant") {
                appendAssistantMessage(m.content, m.tok_per_sec);
            }
        });
        scrollToBottom();
    } catch (e) {
        console.error("Failed to load messages:", e);
    }
}

function appendUserMessage(content) {
    if (emptyState) emptyState.style.display = "none";
    const row = document.createElement("div");
    row.className = "message-row user";
    
    const bubble = document.createElement("div");
    bubble.className = "user-bubble";
    bubble.textContent = content;

    row.appendChild(bubble);
    messagesContainer.appendChild(row);
    scrollToBottom();
}

function appendAssistantMessage(content, tokPerSec = 0) {
    if (emptyState) emptyState.style.display = "none";
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const payload = document.createElement("div");
    payload.className = "assistant-payload";

    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.innerHTML = "&#128172;";

    const body = document.createElement("div");
    body.className = "assistant-body";

    const prose = document.createElement("div");
    prose.className = "prose";
    prose.innerHTML = renderMarkdown(content);
    addCodeCopyButtons(prose);
    body.appendChild(prose);

    payload.appendChild(avatar);
    payload.appendChild(body);
    row.appendChild(payload);
    messagesContainer.appendChild(row);
    scrollToBottom();
}

function renderMarkdown(raw) {
    try {
        return marked.parse(raw);
    } catch (e) {
        return raw;
    }
}

function addCodeCopyButtons(container) {
    container.querySelectorAll("pre").forEach(pre => {
        if (pre.parentElement.classList.contains("code-block-wrapper")) return;
        
        const wrapper = document.createElement("div");
        wrapper.className = "code-block-wrapper";

        const header = document.createElement("div");
        header.className = "code-header";
        
        const codeEl = pre.querySelector("code");
        const langClass = codeEl ? Array.from(codeEl.classList).find(c => c.startsWith("language-")) : "";
        const langName = langClass ? langClass.replace("language-", "") : "code";
        header.innerHTML = `<span>${langName}</span>`;

        const copyBtn = document.createElement("button");
        copyBtn.className = "copy-btn";
        copyBtn.textContent = "Copy";
        copyBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(pre.innerText).then(() => {
                copyBtn.textContent = "Copied!";
                setTimeout(() => copyBtn.textContent = "Copy", 1500);
            });
        });

        header.appendChild(copyBtn);
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(header);
        wrapper.appendChild(pre);
    });
}

function scrollToBottom() {
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

async function sendMessage(prompt) {
    isStreaming = true;
    if (sendBtn) sendBtn.disabled = true;
    if (promptInput) {
        promptInput.value = "";
        promptInput.style.height = "auto";
    }

    appendUserMessage(prompt);

    // Setup streaming Assistant UI
    const row = document.createElement("div");
    row.className = "message-row assistant";
    const payload = document.createElement("div");
    payload.className = "assistant-payload";
    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.innerHTML = "&#128172;";
    const body = document.createElement("div");
    body.className = "assistant-body";

    const prose = document.createElement("div");
    prose.className = "prose";
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";

    body.appendChild(prose);
    body.appendChild(cursor);
    payload.appendChild(avatar);
    payload.appendChild(body);
    row.appendChild(payload);
    messagesContainer.appendChild(row);
    scrollToBottom();

    let rawAssistantContent = "";
    const model = modelSelect ? modelSelect.value : "";

    const streamUrl = `/api/chat/stream?prompt=${encodeURIComponent(prompt)}&session_id=${encodeURIComponent(activeSessionId || "")}&model=${encodeURIComponent(model)}`;
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);

            if (data.type === "session_title") {
                loadSessions();
            } else if (data.type === "token") {
                rawAssistantContent += data.chunk;
                prose.innerHTML = renderMarkdown(rawAssistantContent);
                scrollToBottom();
            } else if (data.type === "done") {
                if (data.tok_per_sec && perfTag) {
                    perfTag.textContent = `⚡ ${data.tok_per_sec} tok/s`;
                }
                if (cursor.parentNode) cursor.remove();
                addCodeCopyButtons(prose);
                eventSource.close();
                isStreaming = false;
                if (sendBtn) sendBtn.disabled = false;
                if (promptInput) promptInput.focus();
            } else if (data.type === "error") {
                prose.innerHTML += `<p style="color:#f87171;">⚠️ ${data.message}</p>`;
                if (cursor.parentNode) cursor.remove();
                eventSource.close();
                isStreaming = false;
                if (sendBtn) sendBtn.disabled = false;
            }
        } catch (err) {
            console.error("SSE parse error:", err);
        }
    };

    eventSource.onerror = (err) => {
        console.error("EventSource error:", err);
        if (cursor.parentNode) cursor.remove();
        eventSource.close();
        isStreaming = false;
        if (sendBtn) sendBtn.disabled = false;
    };
}
"""
    path.write_text(content, encoding="utf-8")
    print("[OK] app.js updated")

def fix_engine_and_server():
    engine_path = DEST_DIR / "core" / "engine.py"
    engine_code = '''"""
Streaming Conversation Engine for AI Chatbot (Direct response, zero reasoning).
"""
import time
from typing import Generator, Dict, Any, Optional
from config import MODEL_NAME, SYSTEM_PROMPT, ROLLING_BUFFER_CHAR_LIMIT
from core.database import (
    add_message, get_rolling_messages, get_all_messages, update_session_title
)
from models.ollama_client import stream_ollama_chat

def run_chat_stream(
    session_id: str,
    user_prompt: str,
    model_name: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Executes pure streaming chat conversation with zero reasoning overhead.
    """
    effective_model = model_name or MODEL_NAME
    
    print("\\n" + "=" * 60)
    print(f"⚡ [AI Chatbot] Session: {session_id} | Model: {effective_model}")
    print(f"💬 Prompt: {user_prompt.strip()}")
    print("=" * 60)
    
    # 1. Store user prompt
    add_message(session_id, "user", user_prompt)
    
    # Auto-generate friendly title if this is the very first exchange
    existing_messages = get_all_messages(session_id)
    if len(existing_messages) <= 2:
        clean_title = user_prompt.strip().split("\\n")[0][:36]
        if len(user_prompt.strip()) > 36:
            clean_title += "..."
        update_session_title(session_id, clean_title)
        yield {"type": "session_title", "title": clean_title}

    # 2. Build conversation context
    rolling = get_rolling_messages(session_id, char_limit=ROLLING_BUFFER_CHAR_LIMIT)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + rolling
    
    yield {"type": "start", "model": effective_model}

    assistant_content = []
    tok_per_sec = 0.0

    # 3. Stream direct tokens from Ollama
    for chunk in stream_ollama_chat(messages, model=effective_model):
        c_type = chunk.get("type")
        if c_type == "token":
            t = chunk.get("chunk", "")
            assistant_content.append(t)
            yield chunk
        elif c_type == "done":
            tok_per_sec = chunk.get("tok_per_sec", 0.0)
            yield chunk
        elif c_type == "error":
            print(f"❌ [AI Chatbot] Error: {chunk.get('message')}")
            yield chunk
            return

    # 4. Persist completed assistant response
    full_text = "".join(assistant_content)
    add_message(session_id, "assistant", full_text, tok_per_sec=tok_per_sec)
    print(f"✅ [AI Chatbot] Response complete: {len(full_text)} chars | {tok_per_sec} tok/s\\n")
'''
    engine_path.write_text(engine_code, encoding="utf-8")
    print("[OK] engine.py updated with telemetry")

    server_path = DEST_DIR / "server.py"
    server_content = server_path.read_text(encoding="utf-8")
    if 'print(f"[SSE] Incoming chat query:' not in server_content:
        server_content = server_content.replace(
            'set_active_session(session_id)\n\n    async def event_generator():',
            'set_active_session(session_id)\n    print(f"⚡ [HTTP] Streaming chat request for session \'{session_id}\' (model: {model or MODEL_NAME})...")\n\n    async def event_generator():'
        )
        server_path.write_text(server_content, encoding="utf-8")
        print("[OK] server.py updated with HTTP telemetry")

def main():
    print("Applying chat stream fix and telemetry to C:\\Dev\\ai-chatbot...")
    fix_index_html()
    fix_app_js()
    fix_engine_and_server()
    print("[SUCCESS] Fix applied successfully!")

if __name__ == "__main__":
    main()
