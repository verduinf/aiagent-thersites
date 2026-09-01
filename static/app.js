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

    function escapeHtml(str) {
        if (!str) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatMarkdownAndMermaid(text) {
        if (!text) return "";

        // 1. Preserve Mermaid blocks
        const mermaidBlocks = [];
        let processed = text.replace(/```mermaid\s*([\s\S]*?)```/gi, (match, code) => {
            const placeholder = `__MERMAID_PLACEHOLDER_${mermaidBlocks.length}__`;
            mermaidBlocks.push(code.trim());
            return placeholder;
        });

        // 2. Preserve SVG vector graphics (both ```svg <svg>...</svg> ``` and inline <svg>...</svg>)
        const svgBlocks = [];
        processed = processed.replace(/```(?:svg|xml)?\s*(<svg[\s\S]*?<\/svg>)\s*```/gi, (match, svgCode) => {
            const placeholder = `__SVG_PLACEHOLDER_${svgBlocks.length}__`;
            svgBlocks.push(svgCode.trim());
            return placeholder;
        });
        processed = processed.replace(/(<svg[\s\S]*?<\/svg>)/gi, (match, svgCode) => {
            const placeholder = `__SVG_PLACEHOLDER_${svgBlocks.length}__`;
            svgBlocks.push(svgCode.trim());
            return placeholder;
        });

        // 3. Preserve other code blocks
        const codeBlocks = [];
        processed = processed.replace(/```([a-zA-Z0-9_-]*)\s*([\s\S]*?)```/g, (match, lang, code) => {
            const placeholder = `__CODE_PLACEHOLDER_${codeBlocks.length}__`;
            codeBlocks.push({ lang: lang || 'plaintext', code: escapeHtml(code.trim()) });
            return placeholder;
        });

        // 4. Escape HTML for standard text
        processed = escapeHtml(processed);

        // 5. Markdown images: ![alt](url)
        processed = processed.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, url) => {
            return `<div class="chat-image-card" style="margin: 8px 0;"><img src="${url}" alt="${alt}" class="rendered-chat-img" style="max-width: 100%; max-height: 420px; border-radius: 8px; border: 1px solid var(--border-color); display: block;"><span class="chat-img-caption" style="display: block; font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">${alt || 'Generated Image'}</span></div>`;
        });

        // 6. Markdown links: [text](url)
        processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, url) => {
            return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-link" style="color: #60a5fa; text-decoration: underline;">${label}</a>`;
        });

        // 7. Bold & inline code
        processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        processed = processed.replace(/`([^`]+)`/g, '<code class="inline-code" style="background: rgba(255,255,255,0.08); padding: 2px 5px; border-radius: 4px; font-family: var(--font-mono); font-size: 0.85em;">$1</code>');

        // 8. Convert linebreaks
        processed = processed.replace(/\n/g, '<br>');

        // 9. Restore code blocks
        codeBlocks.forEach((cb, idx) => {
            const blockHtml = `<pre class="code-block" style="background: #0f172a; padding: 10px 14px; border-radius: 6px; overflow-x: auto; border: 1px solid rgba(255,255,255,0.1); margin: 8px 0;"><code class="language-${cb.lang}" style="font-family: var(--font-mono); font-size: 0.82rem; color: #38bdf8;">${cb.code}</code></pre>`;
            processed = processed.replace(`__CODE_PLACEHOLDER_${idx}__`, blockHtml);
        });

        // 10. Restore Mermaid blocks
        mermaidBlocks.forEach((code, idx) => {
            const uniqueId = `mermaid-graph-${Date.now()}-${idx}`;
            const mermaidHtml = `<div class="mermaid-card" style="background: #0f172a; padding: 14px; border-radius: 8px; margin: 10px 0; border: 1px solid rgba(96, 165, 250, 0.3); overflow-x: auto;"><div class="mermaid" id="${uniqueId}">${code}</div></div>`;
            processed = processed.replace(`__MERMAID_PLACEHOLDER_${idx}__`, mermaidHtml);
        });

        // 11. Restore interactive SVG vector cards
        svgBlocks.forEach((svgCode, idx) => {
            const svgHtml = `<div class="interactive-svg-card" style="background: #0f172a; padding: 14px; border-radius: 8px; margin: 10px 0; border: 1px solid rgba(56, 189, 248, 0.3); overflow-x: auto; display: flex; justify-content: center; align-items: center;">${svgCode}</div>`;
            processed = processed.replace(`__SVG_PLACEHOLDER_${idx}__`, svgHtml);
        });

        return processed;
    }

    function triggerMermaid() {
        if (window.mermaid) {
            try {
                setTimeout(() => {
                    mermaid.run({
                        nodes: document.querySelectorAll(".mermaid:not([data-processed='true'])")
                    });
                }, 50);
            } catch (e) {
                console.warn("Mermaid render error:", e);
            }
        }
    }

    const voiceSelect = document.getElementById("voiceSelect");

    function populateVoiceList() {
        if (!voiceSelect || !('speechSynthesis' in window)) return;
        const voices = window.speechSynthesis.getVoices();
        if (!voices || voices.length === 0) return;

        const currentSaved = localStorage.getItem("thersites_tts_voice");
        voiceSelect.innerHTML = "";

        // Sort voices: English and Dutch first
        const sorted = [...voices].sort((a, b) => {
            const aPri = a.lang.startsWith("en") ? 1 : (a.lang.startsWith("nl") ? 2 : 3);
            const bPri = b.lang.startsWith("en") ? 1 : (b.lang.startsWith("nl") ? 2 : 3);
            if (aPri !== bPri) return aPri - bPri;
            return a.name.localeCompare(b.name);
        });

        sorted.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v.name;
            opt.textContent = `${v.name} (${v.lang})`;
            if (currentSaved && currentSaved === v.name) {
                opt.selected = true;
            } else if (!currentSaved && !voiceSelect.value && v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Google") || v.name.includes("Online"))) {
                opt.selected = true;
            }
            voiceSelect.appendChild(opt);
        });
    }

    if ('speechSynthesis' in window) {
        populateVoiceList();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
            window.speechSynthesis.onvoiceschanged = populateVoiceList;
        }
        if (voiceSelect) {
            voiceSelect.addEventListener("change", () => {
                localStorage.setItem("thersites_tts_voice", voiceSelect.value);
            });
        }
    }

    let currentlySpeakingMsgId = null;

    function cleanTextForSpeech(rawText) {
        if (!rawText) return "";
        return rawText
            .replace(/```mermaid[\s\S]*?```/gi, " [flowchart diagram omitted] ")
            .replace(/```[\s\S]*?```/g, " [code snippet omitted] ")
            .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
            .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
            .replace(/`([^`]+)`/g, "$1")
            .replace(/[*_#~>]/g, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function handleSpeakMessage(msgId, rawText, btnElement) {
        if (!('speechSynthesis' in window)) {
            alert("Speech synthesis is not supported in this browser.");
            return;
        }

        // Toggle off if currently speaking this message
        if (window.speechSynthesis.speaking && currentlySpeakingMsgId === msgId) {
            window.speechSynthesis.cancel();
            currentlySpeakingMsgId = null;
            if (btnElement) btnElement.innerHTML = "&#128266;";
            return;
        }

        // Cancel any existing speech
        window.speechSynthesis.cancel();
        document.querySelectorAll(".speak-btn").forEach(b => b.innerHTML = "&#128266;");

        const clean = cleanTextForSpeech(rawText);
        if (!clean) return;

        const utterance = new SpeechSynthesisUtterance(clean);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        const voices = window.speechSynthesis.getVoices();
        if (voices && voices.length > 0) {
            const chosenName = (voiceSelect && voiceSelect.value) || localStorage.getItem("thersites_tts_voice");
            let chosenVoice = voices.find(v => v.name === chosenName);
            if (!chosenVoice) {
                chosenVoice = voices.find(v => v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Google") || v.name.includes("Online"))) || voices.find(v => v.lang.startsWith("en"));
            }
            if (chosenVoice) utterance.voice = chosenVoice;
        }

        currentlySpeakingMsgId = msgId;
        if (btnElement) btnElement.innerHTML = "&#9209;&#65039;"; // Stop icon

        utterance.onend = () => {
            currentlySpeakingMsgId = null;
            if (btnElement) btnElement.innerHTML = "&#128266;";
        };

        utterance.onerror = () => {
            currentlySpeakingMsgId = null;
            if (btnElement) btnElement.innerHTML = "&#128266;";
        };

        window.speechSynthesis.speak(utterance);
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
                <div class="message-body" style="font-size: 0.8rem; line-height: 1.35; color: #e6edf3;">${formatMarkdownAndMermaid(m.content)}</div>
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

            const speakBtnHtml = `<button class="speak-btn" data-msg-id="${m.id}" title="Read aloud">&#128266;</button>`;

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
                        ${speakBtnHtml}
                        <button class="pin-btn ${pinClass}" data-msg-id="${m.id}" title="Toggle Pin">&#128205;</button>
                        <button class="delete-btn" data-msg-id="${m.id}" title="Delete Message">&#128465;</button>
                    </div>
                </div>
                <div class="message-body">${formatMarkdownAndMermaid(m.content)}</div>
            `;

            timelineContainer.appendChild(card);
        });

        rollingBadge.textContent = `Rolling: ${rollingCharCount.toLocaleString()} / 20k`;
        pinnedBadge.textContent = `Pinned: ${pinnedCharCount.toLocaleString()} / 5k`;

        renderPinnedSidebar(pinnedMessages);
        triggerMermaid();

        timelineContainer.querySelectorAll(".speak-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const msgId = btn.getAttribute("data-msg-id");
                const msg = messages.find(item => String(item.id) === String(msgId));
                if (msg) {
                    handleSpeakMessage(msgId, msg.content, btn);
                }
            });
        });

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
