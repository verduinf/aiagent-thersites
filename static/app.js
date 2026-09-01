document.addEventListener("DOMContentLoaded", () => {
    const sessionSelect = document.getElementById("sessionSelect");
    const newSessionBtn = document.getElementById("newSessionBtn");
    const perfTag = document.getElementById("perfTag");
    const rollingBadge = document.getElementById("rollingBadge");
    const pinnedBadge = document.getElementById("pinnedBadge");
    const pinnedContainer = document.getElementById("pinnedContainer");
    const timelineContainer = document.getElementById("timelineContainer");
    const scratchpadAccordion = document.getElementById("scratchpadAccordion");
    const accordionHeader = document.getElementById("accordionHeader");
    const accordionBody = document.getElementById("accordionBody");
    const chatForm = document.getElementById("chatForm");
    const promptInput = document.getElementById("promptInput");
    const sendBtn = document.getElementById("sendBtn");
    const attachBtn = document.getElementById("attachBtn");
    const imageInput = document.getElementById("imageInput");
    const imagePreviewTray = document.getElementById("imagePreviewTray");
    const thinkToggle = document.getElementById("thinkToggle");
    const modelSelect = document.getElementById("modelSelect");
    const modelStatusText = document.getElementById("modelStatusText");

    let currentSessionId = null;
    let attachedImage = null;

    async function loadModels() {
        try {
            const res = await fetch("/api/models");
            const data = await res.json();
            const models = data.models || ["qwen3.5:9b"];
            const defaultModel = data.default || "qwen3.5:9b";

            if (modelSelect) {
                modelSelect.innerHTML = "";
                models.forEach(m => {
                    const opt = document.createElement("option");
                    opt.value = m;
                    opt.textContent = m;
                    if (m === defaultModel) {
                        opt.selected = true;
                    }
                    modelSelect.appendChild(opt);
                });

                if (modelStatusText) {
                    modelStatusText.textContent = modelSelect.value;
                }

                modelSelect.addEventListener("change", () => {
                    if (modelStatusText) {
                        modelStatusText.textContent = modelSelect.value;
                    }
                });
            }
        } catch (e) {
            console.error("Failed to load models list", e);
        }
    }

    async function initApp() {
        await loadModels();
        await loadSessions();
        if (currentSessionId) {
            await loadMessages(currentSessionId);
        } else if (sessionSelect.options.length > 0) {
            currentSessionId = sessionSelect.value;
            await loadMessages(currentSessionId);
        } else {
            await createNewSession();
        }
    }

    async function loadSessions(targetSessionId = null) {
        try {
            const res = await fetch("/api/sessions");
            const data = await res.json();
            const sessions = Array.isArray(data) ? data : (data.sessions || []);
            const selectId = targetSessionId || currentSessionId || data.active_session_id;

            sessionSelect.innerHTML = "";
            sessions.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s.id;
                const titleText = s.title && s.title !== s.id ? s.title : s.id;
                opt.textContent = `${titleText} (${s.created_at || 'New'})`;
                sessionSelect.appendChild(opt);
            });

            if (selectId && sessionSelect.querySelector(`option[value="${selectId}"]`)) {
                currentSessionId = selectId;
                sessionSelect.value = currentSessionId;
            } else if (sessionSelect.options.length > 0) {
                currentSessionId = sessionSelect.value;
            }
        } catch (err) {
            console.error("Error loading sessions:", err);
        }
    }

    async function createNewSession() {
        try {
            const res = await fetch("/api/sessions", { method: "POST" });
            const newSess = await res.json();
            currentSessionId = newSess.id;
            await loadSessions(currentSessionId);
            await loadMessages(currentSessionId);
        } catch (err) {
            console.error("Error creating session:", err);
        }
    }

    async function loadMessages(sessionId) {
        if (!sessionId) return;
        try {
            const res = await fetch(`/api/messages?session_id=${sessionId}`);
            const messages = await res.json();
            renderTimeline(messages);
        } catch (err) {
            console.error("Error loading messages:", err);
        }
    }

    function renderPinnedSidebar(pinnedMessages) {
        if (!pinnedContainer) return;
        pinnedContainer.innerHTML = "";
        if (!pinnedMessages || pinnedMessages.length === 0) {
            pinnedContainer.innerHTML = `<div class="empty-pinned">No pinned context anchors.</div>`;
            return;
        }

        pinnedMessages.forEach(m => {
            const card = document.createElement("div");
            card.className = "message-card role-user pinned-sidebar-card";
            card.style.padding = "0.6rem 0.75rem";
            card.style.marginBottom = "0.6rem";
            card.style.fontSize = "0.8rem";
            card.style.position = "relative";

            card.innerHTML = `
                <div class="message-header" style="margin-bottom: 0.35rem; display: flex; justify-content: space-between; align-items: center;">
                    <div class="message-author" style="font-size: 0.75rem; font-weight: 600; color: #fde047;">
                        <span>&#128205; Anchor (Msg #${m.sequence_id})</span>
                    </div>
                    <button class="unpin-sidebar-btn" data-msg-id="${m.id}" title="Unpin this anchor from context" style="cursor: pointer; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; border-radius: 4px; padding: 2px 7px; font-size: 0.72rem; font-weight: 600; transition: all 0.2s; display: flex; align-items: center; gap: 4px;">
                        <span>&#10005;</span> Unpin
                    </button>
                </div>
                <div class="message-body" style="font-size: 0.8rem; line-height: 1.35; color: #e6edf3;">${escapeHtml(m.content)}</div>
            `;
            pinnedContainer.appendChild(card);
        });

        pinnedContainer.querySelectorAll(".unpin-sidebar-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const msgId = btn.getAttribute("data-msg-id");
                if (msgId) {
                    await togglePin(msgId);
                }
            });
        });
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
            renderPinnedSidebar([]);
            return;
        }

        let rollingCharCount = 0;
        let pinnedCharCount = 0;
        const pinnedMessages = [];

        messages.forEach(m => {
            const card = document.createElement("div");
            card.className = `message-card ${m.role === 'user' ? 'role-user' : 'role-assistant'}`;

            const isUser = m.role === 'user';
            const author = isUser ? "The Boss" : "Thersites (Intern)";
            const avatarIcon = isUser ? "&#128104;" : '<img src="/static/images/thersites.png" class="msg-avatar-thumb" alt="Thersites">';

            const isPinned = m.is_pinned === 1;
            const pinClass = isPinned ? "pinned" : "";

            let statusTagHtml = "";
            if (isPinned) {
                statusTagHtml = `<span class="context-badge pinned" title="Pinned Anchor in System Contract">&#128205; Pinned Anchor</span>`;
                pinnedCharCount += m.content.length;
                pinnedMessages.push(m);
            } else {
                statusTagHtml = `<span class="context-badge in-rolling" title="Active 20k Rolling Buffer">&#128994; In 20k Window</span>`;
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
                        <button class="pin-btn ${pinClass}" data-msg-id="${m.id}" title="Toggle Pin">&#128205;</button>
                        <button class="delete-btn" data-msg-id="${m.id}" title="Delete Message">&#128465;</button>
                    </div>
                </div>
                <div class="message-body">${escapeHtml(m.content)}</div>
            `;

            timelineContainer.appendChild(card);
        });

        rollingBadge.textContent = `Rolling: ${rollingCharCount.toLocaleString()} / 20k`;
        pinnedBadge.textContent = `Pinned: ${pinnedCharCount.toLocaleString()} / 5k`;

        renderPinnedSidebar(pinnedMessages);

        timelineContainer.querySelectorAll(".pin-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const msgId = btn.getAttribute("data-msg-id");
                if (msgId) {
                    await togglePin(msgId);
                }
            });
        });

        timelineContainer.querySelectorAll(".delete-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const msgId = btn.getAttribute("data-msg-id");
                if (msgId && confirm("Delete this message to free up context budget?")) {
                    await deleteMessage(msgId);
                }
            });
        });

        setTimeout(() => {
            timelineContainer.scrollTop = timelineContainer.scrollHeight;
        }, 50);
    }


    async function deleteMessage(msgId) {
        try {
            await fetch(`/api/messages/${msgId}`, { method: "DELETE" });
            await loadMessages(currentSessionId);
        } catch (err) {
            console.error("Error deleting message:", err);
        }
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


    if (attachBtn && imageInput) {
        attachBtn.addEventListener("click", () => imageInput.click());

        imageInput.addEventListener("change", async () => {
            if (!imageInput.files || imageInput.files.length === 0) return;
            const file = imageInput.files[0];
            const formData = new FormData();
            formData.append("file", file);

            try {
                attachBtn.disabled = true;
                attachBtn.textContent = "Uploading...";
                const res = await fetch("/api/upload", { method: "POST", body: formData });
                const data = await res.json();
                if (data.status === "success") {
                    attachedImage = data;
                    renderImagePreview();
                } else {
                    alert("Upload failed: " + (data.detail || "Unknown error"));
                }
            } catch (err) {
                console.error("Error uploading image:", err);
                alert("Failed to upload image.");
            } finally {
                attachBtn.disabled = false;
                attachBtn.innerHTML = "&#128065;&#65039; Attach";
                imageInput.value = "";
            }
        });
    }

    function renderImagePreview() {
        if (!imagePreviewTray) return;
        if (!attachedImage) {
            imagePreviewTray.style.display = "none";
            imagePreviewTray.innerHTML = "";
            return;
        }
        imagePreviewTray.style.display = "flex";
        imagePreviewTray.innerHTML = `
            <div class="image-preview-card">
                <img src="${attachedImage.url}" class="image-preview-thumb" alt="Preview">
                <span class="image-preview-name">${escapeHtml(attachedImage.filename)}</span>
                <button type="button" class="image-remove-btn" title="Remove attachment">&times;</button>
            </div>
        `;
        imagePreviewTray.querySelector(".image-remove-btn").addEventListener("click", () => {
            attachedImage = null;
            renderImagePreview();
        });
    }

    function appendOptimisticUserMessage(promptText, attachedImg = null) {
        const emptyPlaceholder = timelineContainer.querySelector("div[style*='text-align: center']");
        if (emptyPlaceholder) {
            timelineContainer.innerHTML = "";
        }

        const card = document.createElement("div");
        card.className = "message-card role-user optimistic-user-card";

        let imgHtml = "";
        if (attachedImg) {
            imgHtml = `<div class="msg-image-attachment" style="margin-bottom: 8px;"><img src="${attachedImg.url}" alt="Attachment" style="max-width: 220px; max-height: 180px; border-radius: 8px; border: 1px solid var(--accent-cyan); display: block;"></div>`;
        }

        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        card.innerHTML = `
            <div class="message-header">
                <div class="message-author">
                    <span class="message-avatar">&#128104;</span>
                    <span>The Boss</span>
                    <span class="context-badge in-rolling" title="Active 20k Rolling Buffer">&#128994; In 20k Window</span>
                </div>
                <div class="message-actions">
                    <span class="seq-badge">Pending</span>
                    <span class="message-time">${timeStr}</span>
                </div>
            </div>
            <div class="message-body">${imgHtml}${escapeHtml(promptText)}</div>
        `;

        timelineContainer.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        let prompt = promptInput.value.trim();
        if (!prompt) {
            prompt = "Please check for tasks in your pinned instructions and execute them.";
        }

        const currentAttachedImage = attachedImage;
        appendOptimisticUserMessage(prompt, currentAttachedImage);

        promptInput.value = "";
        sendBtn.disabled = true;

        scratchpadAccordion.classList.add("visible");
        scratchpadAccordion.classList.remove("collapsed");
        accordionHeader.innerHTML = `<span class="accordion-title">&#128993; Intern is thinking... (Turn 1/8)</span><span class="accordion-icon">&#9650;</span>`;
        accordionBody.innerHTML = `<div class="accordion-step"><span class="step-icon">&#128993;</span> Connecting to Ollama model...</div>`;

        let lastTurn = 1;

        try {
            const selectedThinkRadio = document.querySelector("input[name='thinkMode']:checked");
            const selectedThink = selectedThinkRadio ? selectedThinkRadio.value : "off";
            const selectedModel = modelSelect ? modelSelect.value : "qwen3.5:9b";
            let streamUrl = `/api/chat/stream?session_id=${currentSessionId}&prompt=${encodeURIComponent(prompt)}&think=${encodeURIComponent(selectedThink)}&model=${encodeURIComponent(selectedModel)}`;
            if (attachedImage) {
                streamUrl += `&image_path=${encodeURIComponent(attachedImage.filepath)}`;
            }
            attachedImage = null;
            renderImagePreview();

            const eventSource = new EventSource(streamUrl);

            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === "telemetry") {
                    lastTurn = data.turn;
                    const isCollapsed = scratchpadAccordion.classList.contains("collapsed");
                    const icon = isCollapsed ? "&#9660;" : "&#9650;";
                    accordionHeader.innerHTML = `<span class="accordion-title">&#128993; Intern is thinking... (Turn ${data.turn}/${data.max_turns})</span><span class="accordion-icon">${icon}</span>`;
                } else if (data.type === "performance") {
                    if (perfTag) {
                        perfTag.textContent = `⚡ ${data.tok_per_sec} tok/s (${data.latency_sec}s)`;
                    }
                } else if (data.type === "scratch_step") {
                    const stepDiv = document.createElement("div");
                    stepDiv.className = "accordion-step";

                    if (data.status === "error") {
                        stepDiv.innerHTML = `<span class="step-icon">&#128308;</span> [Turn ${data.turn}] Details: ${escapeHtml(data.details)}`;
                    } else {
                        let actionText = "";
                        if (data.actions && data.actions.length > 0) {
                            actionText = `<br><b>Action Requested:</b> <code>${escapeHtml(JSON.stringify(data.actions))}</code>`;
                        }
                        stepDiv.innerHTML = `<span class="step-icon">&#128994;</span> [Turn ${data.turn}] <b>Thought:</b> ${escapeHtml(data.thought)}${actionText}`;
                    }
                    accordionBody.appendChild(stepDiv);
                    accordionBody.scrollTop = accordionBody.scrollHeight;
                } else if (data.type === "final_response") {
                    eventSource.close();
                    sendBtn.disabled = false;
                    const isCollapsed = scratchpadAccordion.classList.contains("collapsed");
                    const icon = isCollapsed ? "&#9660;" : "&#9650;";
                    accordionHeader.innerHTML = `<span class="accordion-title">&#128994; Intern task complete! (${lastTurn} turn${lastTurn > 1 ? 's' : ''})</span><span class="accordion-icon">${icon}</span>`;
                    loadMessages(currentSessionId);
                }
            };

            eventSource.onerror = (err) => {
                console.error("SSE Error:", err);
                eventSource.close();
                sendBtn.disabled = false;
                const isCollapsed = scratchpadAccordion.classList.contains("collapsed");
                const icon = isCollapsed ? "&#9660;" : "&#9650;";
                accordionHeader.innerHTML = `<span class="accordion-title">&#128308; Task completed with error</span><span class="accordion-icon">${icon}</span>`;
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
        const isCollapsed = scratchpadAccordion.classList.toggle("collapsed");
        const iconSpan = accordionHeader.querySelector(".accordion-icon");
        if (iconSpan) {
            iconSpan.innerHTML = isCollapsed ? "&#9660;" : "&#9650;";
        }
        setTimeout(() => {
            timelineContainer.scrollTop = timelineContainer.scrollHeight;
        }, 50);
    });

    initApp();
});
