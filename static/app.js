/**
 * AI Agent Thersites — Clean Dark-Mode Web Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
    const sessionSelect = document.getElementById("sessionSelect");
    const btnNewSession = document.getElementById("btnNewSession");
    const messagesContainer = document.getElementById("messagesContainer");
    const pinnedList = document.getElementById("pinnedList");
    const pinnedCount = document.getElementById("pinnedCount");
    const msgCountBadge = document.getElementById("msgCountBadge");
    const modelTag = document.getElementById("modelTag");
    const telemetryStatsText = document.getElementById("telemetryStatsText");
    const telemetryProgressBar = document.getElementById("telemetryProgressBar");
    const promptInput = document.getElementById("promptInput");
    const btnSend = document.getElementById("btnSend");
    
    const liveScratchAccordion = document.getElementById("liveScratchAccordion");
    const liveScratchTitle = document.getElementById("liveScratchTitle");
    const liveScratchContent = document.getElementById("liveScratchContent");

    let currentSessionId = null;

    async function init() {
        await loadSessions();
        await loadMessages();
    }

    async function loadSessions() {
        try {
            const res = await fetch("/api/sessions");
            const data = await res.json();
            currentSessionId = data.active_session_id;

            sessionSelect.innerHTML = "";
            data.sessions.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s.id;
                opt.textContent = `${s.title} (${s.message_count} msgs)`;
                if (s.id === currentSessionId) opt.selected = true;
                sessionSelect.appendChild(opt);
            });
        } catch (err) {
            console.error("Error loading sessions:", err);
        }
    }

    async function loadMessages() {
        try {
            const res = await fetch("/api/messages");
            const data = await res.json();
            
            modelTag.textContent = data.model_name || "qwen3.5:9b";
            renderMessages(data.messages, data.active_rolling_ids || [], data.pinned_ids || []);
            renderPinned(data.pinned_messages, data.telemetry.pinned_chars, data.telemetry.pinned_limit);
            updateTelemetryBar(data.telemetry.rolling_chars, data.telemetry.rolling_limit, data.telemetry.pinned_chars, data.telemetry.pinned_limit);
        } catch (err) {
            console.error("Error loading messages:", err);
        }
    }

    function renderMessages(messages, activeRollingIds, pinnedIds) {
        messagesContainer.innerHTML = "";
        msgCountBadge.textContent = `${messages.length} messages`;

        if (messages.length === 0) {
            // Completely clean timeline — no static filler text
            return;
        }

        messages.forEach(msg => {
            const card = document.createElement("div");
            const isUser = msg.role === "user";
            card.className = `message-card ${isUser ? 'user-message' : 'assistant-message'}`;

            const avatar = isUser ? "👤" : "📜";
            const roleName = isUser ? "The Boss" : "Thersites (Intern)";

            const isPinned = pinnedIds.includes(msg.id) || msg.is_pinned === 1;
            const isInRolling = activeRollingIds.includes(msg.id);

            let statusBadgeHtml = "";
            if (isPinned) {
                statusBadgeHtml = `<span class="context-status-badge pinned">📌 Pinned Anchor</span>`;
            } else if (isInRolling) {
                statusBadgeHtml = `<span class="context-status-badge in-rolling">🟢 In 20k Window</span>`;
            } else {
                statusBadgeHtml = `<span class="context-status-badge historic">📜 Historic History</span>`;
            }

            card.innerHTML = `
                <div class="avatar">${avatar}</div>
                <div class="message-bubble">
                    <div class="message-meta">
                        <div>
                            <span class="role-name">${roleName}</span>
                            ${statusBadgeHtml}
                        </div>
                        <div class="meta-details">
                            <span class="seq-badge">Msg #${msg.sequence_id}</span>
                            <span class="timestamp">${msg.created_at}</span>
                            <button class="pin-btn ${isPinned ? 'pinned' : ''}" data-id="${msg.id}" title="Toggle Pinned Context">
                                ${isPinned ? '📌 Pinned' : '📌'}
                            </button>
                        </div>
                    </div>
                    <div class="message-text">${escapeHtml(msg.content)}</div>
                </div>
            `;

            const pinBtn = card.querySelector(".pin-btn");
            pinBtn.addEventListener("click", () => togglePin(msg.id));

            messagesContainer.appendChild(card);
        });

        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function renderPinned(pinnedMsgs, pinnedChars, pinnedLimit) {
        pinnedCount.textContent = `${pinnedChars.toLocaleString()} / ${pinnedLimit.toLocaleString()} chars`;
        pinnedList.innerHTML = "";

        if (pinnedMsgs.length === 0) {
            pinnedList.innerHTML = `
                <div class="empty-pinned-state">
                    <p>No pinned context anchors.</p>
                </div>
            `;
            return;
        }

        pinnedMsgs.forEach(msg => {
            const card = document.createElement("div");
            card.className = "pinned-card";
            card.innerHTML = `
                <div class="pinned-card-header">
                    <span>Msg #${msg.sequence_id} • ${msg.created_at.split(' ')[1]}</span>
                    <button class="unpin-btn" data-id="${msg.id}" title="Unpin">✖</button>
                </div>
                <div class="pinned-card-content">${escapeHtml(msg.content)}</div>
            `;

            card.querySelector(".unpin-btn").addEventListener("click", () => togglePin(msg.id));
            pinnedList.appendChild(card);
        });
    }

    function updateTelemetryBar(rollingChars, rollingLimit, pinnedChars, pinnedLimit) {
        telemetryStatsText.textContent = `Rolling: ${rollingChars.toLocaleString()} / 20k | Pinned: ${pinnedChars.toLocaleString()} / 5k`;
        const percentage = Math.min(100, Math.round((rollingChars / rollingLimit) * 100));
        telemetryProgressBar.style.width = `${Math.max(5, percentage)}%`;
    }

    async function togglePin(messageId) {
        try {
            await fetch(`/api/pin/${messageId}`, { method: "POST" });
            await loadMessages();
        } catch (err) {
            console.error("Error toggling pin:", err);
        }
    }

    sessionSelect.addEventListener("change", async (e) => {
        const newSessionId = e.target.value;
        try {
            await fetch("/api/sessions/active", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: newSessionId })
            });
            await loadMessages();
        } catch (err) {
            console.error("Error switching session:", err);
        }
    });

    btnNewSession.addEventListener("click", async () => {
        const title = prompt("Enter Title for New Session:", `Session ${new Date().toLocaleTimeString()}`);
        if (!title) return;

        try {
            await fetch("/api/sessions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title })
            });
            await init();
        } catch (err) {
            console.error("Error creating session:", err);
        }
    });

    async function sendTask() {
        const promptText = promptInput.value.trim();
        if (!promptText) return;

        promptInput.value = "";
        btnSend.disabled = true;

        liveScratchAccordion.classList.remove("hidden");
        liveScratchTitle.textContent = "Intern is thinking... (Turn 1/5)";
        liveScratchContent.textContent = "Connecting to Ollama model...";

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: promptText })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        const eventData = JSON.parse(line.slice(6));
                        handleSSEEvent(eventData);
                    }
                }
            }
        } catch (err) {
            console.error("SSE Chat Error:", err);
            liveScratchContent.textContent += `\nError: ${err.message}`;
        } finally {
            liveScratchAccordion.classList.add("hidden");
            btnSend.disabled = false;
            await loadMessages();
        }
    }

    function handleSSEEvent(event) {
        if (event.type === "telemetry") {
            liveScratchTitle.textContent = `Intern is thinking... (Turn ${event.turn}/${event.max_turns})`;
            updateTelemetryBar(event.char_count, event.max_chars, 0, 5000);
        } else if (event.type === "scratch_step") {
            let logText = `[Turn ${event.turn}] `;
            if (event.thought) logText += `Thought: ${event.thought}\n`;
            if (event.actions && event.actions.length > 0) {
                logText += `Action Requested: ${JSON.stringify(event.actions)}\n`;
            }
            if (event.details) logText += `Details: ${event.details}\n`;
            liveScratchContent.textContent += logText + "\n";
        } else if (event.type === "final_response") {
            liveScratchTitle.textContent = "Intern completed task! 🟢 [DONE]";
        }
    }

    btnSend.addEventListener("click", sendTask);
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendTask();
        }
    });

    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    init();
});
