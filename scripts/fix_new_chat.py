"""
Fix createNewChat() to properly clear the chat interface and reset to empty state.
"""
from pathlib import Path

DEST = Path(r"C:\Dev\ai-chatbot")

def patch_app_js():
    app_js_path = DEST / "static" / "app.js"
    code = app_js_path.read_text(encoding="utf-8")

    # Add resetChatView function and update createNewChat, switchSession, deleteSession, loadMessages
    replacement_block = '''function resetChatView() {
    if (!messagesContainer) return;
    messagesContainer.innerHTML = "";
    if (emptyState) {
        messagesContainer.appendChild(emptyState);
        emptyState.style.display = "flex";
    }
    if (perfTag) {
        perfTag.textContent = "⚡ -- tok/s";
    }
    if (promptInput) {
        promptInput.value = "";
        promptInput.style.height = "auto";
        promptInput.focus();
    }
}

async function switchSession(sessionId, force = false) {
    if (isStreaming || (!force && sessionId === activeSessionId)) return;
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
        activeSessionId = newSess.id;
        await loadSessions(false);
        resetChatView();
    } catch (e) {
        console.error("Failed to create session:", e);
    }
}

async function deleteSession(sessionId) {
    if (!confirm("Delete this conversation?")) return;
    try {
        await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
        const res = await fetch("/api/sessions");
        const data = await res.json();
        renderSessions(data.sessions);
        if (data.sessions.length > 0) {
            await switchSession(data.active_session_id, true);
        } else {
            await createNewChat();
        }
    } catch (e) {
        console.error("Failed to delete session:", e);
    }
}

async function loadMessages(sessionId) {
    try {
        const res = await fetch(`/api/messages?session_id=${sessionId}`);
        const messages = await res.json();
        if (!messagesContainer) return;

        if (messages.length === 0) {
            resetChatView();
            return;
        }

        messagesContainer.innerHTML = "";
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
}'''

    # Find the target section from async function switchSession to the end of loadMessages
    start_str = "async function switchSession(sessionId) {"
    end_str = "scrollToBottom();\n    } catch (e) {\n        console.error(\"Failed to load messages:\", e);\n    }\n}"

    if start_str in code and end_str in code:
        idx_start = code.find(start_str)
        idx_end = code.find(end_str) + len(end_str)
        code = code[:idx_start] + replacement_block + code[idx_end:]
        app_js_path.write_text(code, encoding="utf-8")
        print("[OK] app.js patched with clean resetChatView and createNewChat logic")
    else:
        print("[WARN] Could not find exact block to replace in app.js")

def patch_index_html():
    index_path = DEST / "static" / "index.html"
    content = index_path.read_text(encoding="utf-8")
    content = content.replace("app.js?v=4", "app.js?v=5").replace("style.css?v=4", "style.css?v=5")
    index_path.write_text(content, encoding="utf-8")
    print("[OK] index.html bumped to v=5")

if __name__ == "__main__":
    patch_app_js()
    patch_index_html()
