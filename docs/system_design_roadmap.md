# AI Agent Thersites — System Design & Roadmap

## Overview & Philosophy
Thersites is an autonomous, locally-hosted AI agent powered by `qwen3-9b` running via Ollama on the Aether laptop. Thersites is designed as a contextually-challenged, error-prone, but eager-to-please "Intern" wrapped in a robust Python orchestration harness.

---

## Phase 1: Core Engine, SQLite Persistence & Primary Execution Flow

* **SQLite Schema & Decoupled Logging**:
  * `messages`: Main episodic memory table for user-facing conversation history.
  * `scratch_messages`: Isolated table for intermediate subagent tool outputs, failed JSON attempts, and raw HTML/data snippets.
* **Inference Client**:
  * Local connection using `requests`, `httpx`, or the `openai` Python SDK with custom `base_url` (`http://localhost:11434/v1`) and dummy API key, configured with persistent session flags.
* **Primary Execution Flow via Nested Loops**:
  * **The Inner Loop (Autonomous/Agentic)**: Initiated after user prompt. Local model outputs structured JSON action array (`content` and `actions`). Orchestrator executes tool(s), logs results as scratch message, and feeds back to model. Includes Iterative Multi-Source Discovery.
  * **Turn-1 Consistent Telemetry Guardrail**: Injects live telemetry header from Turn 1 (e.g. `[TELEMETRY: Turn X of Y | Rolling Buffer: A/B chars]`) for 100% prompt pattern consistency and pacing.
  * **The Outer Loop (User-Facing)**: Triggers only after inner loop hits terminal state (`actions: []` or max turn limit). Pushes final content to `messages` table, renders output to client, and yields control back to user.
* **Sequential Unloading and State Persistence**: Safe model handoffs and session state persistence.

---

## Phase 2: Rolling Buffer, Context Pipeline & Budget Telemetry

* **Rolling Buffer Query**: Pulls recent message rows from SQLite up to a strict **20,000-character** rolling limit.
* **Dynamic Budget Telemetry**: Inject live telemetry tags into inner loop prompt every turn (e.g. `[TELEMETRY: Rolling buffer at 16,400 / 20,000 chars. Turn 3 of 5.]`) to give Thersites spatial awareness from Turn 1.
* **Manual Pinning Mechanics**: Clicking historic messages transforms them into permanent session context anchors.
* **Scroll-back Fetcher**: 5,000-character historical refresh flagged as `[HISTORIC REFRESHED CONTEXT]`.
* **Payload Priority & Assembly Order**:
  1. System Prompt Contract (Persona & hardcoded whitelist)
  2. Active Toolkit (Single or Batch Action Schema)
  3. Pinned Context & Historic Refreshed Context
  4. Rolling Conversation-to-Date (`messages`)
  5. Transient Scratch Messages (`scratch_messages`)
  6. Recent User Prompt + Dynamic Budget Telemetry Tag

---

## Phase 3: Intermediary Parser, Tool Interception Hook & Guardrails

* **Response Interception Filter & Multi-Action Array Support**: Scans raw model strings for JSON action arrays. Natively supports batch action calls (`actions: [...]`).
* **The Bouncer Guardrail Architecture**:
  * Programmatic Python harness acts as an unyielding bouncer.
  * Python intercepts tool calls and enforces absolute rules before hitting network or disk (whitelists, path sandbox, parameter validation).
* **Automatic Subagent Post-Fetch Pipeline**:
  * Any `web_fetch` execution automatically triggers a transient secondary subagent context to run `summarize_tool` on raw HTML, returning only clean summaries to Thersites.
* **Console Logging Architecture**:
  * **Main Agent (Thersites)**: Light Green (`\033[92m`).
  * **Subagents (Summarizers)**: Light Yellow (`\033[93m`) with indented tree rendering (`│   ├── [SUBAGENT]`).
  * **Bouncer / Guardrail**: Light Red / Amber (`\033[91m`).
  * **Stoplights**: 🟢 `[DONE]`, 🟡 `[RUNNING/THINKING]`, 🔴 `[BLOCKED/ERROR]`.
* **Robust Error Recovery via Self-Correction Loops**: Catch `json.JSONDecodeError` to trigger an automated retry prompt (max 2 attempts).

---

## Phase 4: FastAPI Backend & Thin HTML Client

* **Architecture**: FastAPI backend + thin HTML/JS frontend (upgraded over CustomTkinter).
* **Benefits**: Eliminates desktop GUI threading freezes, natively handles async background tasks, and streams tool outputs and subagent summaries in real-time via WebSockets or Server-Sent Events (SSE).

---

## Initial Toolbelt & Security Policies

1. **`web_fetch`**:
   * Programmatic URL Whitelist Validation via `urllib.parse` / domain check.
   * Auto-pipelined to `summarize_tool` subagent.
   * Invalid URLs return hard error: `[ERROR: Invalid or unauthorized URL. Stick to the whitelist.]`.
2. **`summarize_tool`**:
   * Dedicated subagent pipeline for processing messy HTML into concise summaries.
3. **`write_to_file`**:
   * Sandbox Directory Enclosure via `pathlib.Path.resolve()`.
   * Enforces target path stays strictly inside `/projects/sandbox/`.
4. **`write_to_scratchpad`**:
   * Exact Scratchfile Enforcement: Hardcoded target path `scratchpad.md`. Passing any other path returns hard error.
5. **`sqlite_query_executor`**:
   * Read-only SQL query execution against local project databases.
