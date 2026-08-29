document.addEventListener("DOMContentLoaded", () => {
    const sessionSelect = document.getElementById("sessionSelect");
    const newSessionBtn = document.getElementById("newSessionBtn");
    const timelineContainer = document.getElementById("timelineContainer");
    const chatForm = document.getElementById("chatForm");
    const promptInput = document.getElementById("promptInput");
    const sendBtn = document.getElementById("sendBtn");
    const accordionHeader = document.getElementById("accordionHeader");
    const accordionBody = document.getElementById("accordionBody");
    const perfTag = document.getElementById("perfTag");
    const rollingBadge = document.getElementById("rollingBadge");
    const pinnedBadge = document.getElementById("pinnedBadge");

    let currentSessionId = null;

    async function initApp() {
        await loadSessions();
        if (currentSessionId) {
            await loadMessages(currentSessionId);
        }
    }

    async function loadSessions() {
        try {
            const res = await fetch("/api/sessions");
            const rawData = await res.json();
            const sessions = Array.isArray(rawData) ? rawData : (rawData.sessions || []);
            
            sessionSelect.innerHTML = "";
            
            if (sessions.length === 0) {
                const newRes = await fetch("/api/sessions", { method: "POST" });
                const newSess = await newRes.json();
                currentSessionId = newSess.id;
                sessions.push(newSess);
            }
            
            sessions.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s.id;
                const displayTitle = s.title && s.title !== s.id ? s.title : "Intern Session";
                const countText = s.msg_count !== undefined ? `${s.msg_count} msgs` : "0 msgs";
                opt.textContent = `${displayTitle} (${countText})`;
                if (s.is_active && !currentSessionId) {
                    currentSessionId = s.id;
                }
                sessionSelect.appendChild(opt);
            });

            if (!currentSessionId && sessions.length > 0) {
                currentSessionId = sessions[0].id;
            }
            sessionSelect.value = currentSessionId;
        } catch (err) {
            console.error("Error loading sessions:", err);
        }
    }

    async function createNewSession() {
        try {
            const res = await fetch("/api/sessions", { method: "POST" });
            const newSess = await res.json();
            currentSessionId = newSess.id;
            await loadSessions();
            await loadMessages(currentSessionId);
        } catch (err) {
            console.error("Error creating session:", err);
        }
    }

    async function loadMessages(sessionId) {
        try {
            const res = await fetch(`/api/messages?session_id=${sessionId}`);
            const messages = await res.json();
            renderTimeline(messages);
        } catch (err) {
            console.error("Error loading messages:", err);
        }
    }

    function renderTimeline(messages) {
        timelineContainer.innerHTML = "";
        if (!messages || messages.length === 0) {
            timelineContainer.innerHTML = `
                <div style="text-align: center; color: var(--text-muted); padding: 40px;">
                    <p>No messages yet. Send a prompt to Thersites to begin!</p>
                </div>
            `;
            updateContextBadges([]);
            return;
        }

        let rollingCharCount = 0;
        let pinnedCharCount = 0;

        messages.forEach(m => {
            const card = document.createElement("div");
            card.className = `message-card ${m.role === 'user' ? 'role-user' : 'role-assistant'}`;
            
            const isUser = m.role === 'user';
            const author = isUser ? "The Boss" : "Thersites (Intern)";
            const avatarIcon = isUser ? "👤" : "📜";
            
            const isPinned = m.is_pinned === 1;
            const pinClass = isPinned ? "pinned" : "";
            
            let statusTagHtml = "";
            if (isPinned) {
                statusTagHtml = `<span class="context-badge pinned" title="Pinned Anchor in System Contract">📌 Pinned Anchor</span>`;
                pinnedCharCount += m.content.length;
            } else {
                statusTagHtml = `<span class="context-badge in-rolling" title="Active 20k Rolling Buffer">🟢 In 20k Window</span>`;
                rollingCharCount += m.content.length;
            }

            card.innerHTML = `
                <div class="message-header">
                    <div class="message-author">
                        <span class="message-avatar">${avatarIcon}</span>
                        <span>${author}</span>
                        ${statusTagHtml}
                    </div>
                    <div class="message-actions">
                        <span class="seq-badge">Msg #${m.sequence_id}</span>
                        <span class="message-time">${m.created_at || ''}</span>
                        <button class="pin-btn ${pinClass}" data-msg-id="${m.id}" title="Toggle Pin">📌</button>
                    </div>
                </div>
                <div class="message-body">${escapeHtml(m.content)}</div>
            `;

            timelineContainer.appendChild(card);
        });

        rollingBadge.textContent = `Rolling: ${rollingCharCount.toLocaleString()} / 20k`;
        pinnedBadge.textContent = `Pinned: ${pinnedCharCount.toLocaleString()} / 5k`;

        document.querySelectorAll(".pin-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const msgId = e.target.getAttribute("data-msg-id");
                await togglePin(msgId);
            });
        });

        setTimeout(() => {
            timelineContainer.scrollTop = timelineContainer.scrollHeight;
        }, 50);
    }

    async function togglePin(msgId) {
        try {
            await fetch(`/api/messages/${msgId}/pin`, { method: "POST" });
            await loadMessages(currentSessionId);
        } catch (err) {
            console.error("Error toggling pin:", err);
        }
    }

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function updateContextBadges(messages) {
        rollingBadge.textContent = "Rolling: 0 / 20k";
        pinnedBadge.textContent = "Pinned: 0 / 5k";
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const prompt = promptInput.value.trim();
        if (!prompt) return;

        promptInput.value = "";
        sendBtn.disabled = true;
        
        accordionBody.innerHTML = `<div class="accordion-step"><span class="step-icon">🟡</span> Connecting to Ollama model...</div>`;
        accordionBody.parentElement.classList.add("active");

        try {
            const eventSource = new EventSource(`/api/chat/stream?session_id=${currentSessionId}&prompt=${encodeURIComponent(prompt)}`);

            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === "telemetry") {
                    // Handled live
                } else if (data.type === "performance") {
                    if (perfTag) {
                        perfTag.textContent = `⚡ ${data.tok_per_sec} tok/s (${data.latency_sec}s)`;
                    }
                } else if (data.type === "scratch_step") {
                    const stepDiv = document.createElement("div");
                    stepDiv.className = "accordion-step";
                    
                    if (data.status === "error") {
                        stepDiv.innerHTML = `<span class="step-icon">🔴</span> [Turn ${data.turn}] Details: ${escapeHtml(data.details)}`;
                    } else {
                        let actionText = "";
                        if (data.actions && data.actions.length > 0) {
                            actionText = `<br><b>Action Requested:</b> <code>${escapeHtml(JSON.stringify(data.actions))}</code>`;
                        }
                        stepDiv.innerHTML = `<span class="step-icon">🟢</span> [Turn ${data.turn}] <b>Thought:</b> ${escapeHtml(data.thought)}${actionText}`;
                    }
                    accordionBody.appendChild(stepDiv);
                } else if (data.type === "final_response") {
                    eventSource.close();
                    sendBtn.disabled = false;
                    loadMessages(currentSessionId);
                }
            };

            eventSource.onerror = (err) => {
                console.error("SSE Error:", err);
                eventSource.close();
                sendBtn.disabled = false;
            };

        } catch (err) {
            console.error("Chat Submit Error:", err);
            sendBtn.disabled = false;
        }
    });

    sessionSelect.addEventListener("change", (e) => {
        currentSessionId = e.target.value;
        loadMessages(currentSessionId);
    });

    newSessionBtn.addEventListener("click", () => {
        createNewSession();
    });

    accordionHeader.addEventListener("click", () => {
        accordionHeader.parentElement.classList.toggle("active");
    });

    initApp();
});
