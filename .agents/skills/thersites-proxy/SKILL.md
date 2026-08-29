---
name: thersites-proxy
description: Field-test prompts against local Ollama (qwen3-9b), evaluate response quality, diagnose server errors, and provide prompt tuning recommendations.
---

# Thersites-Proxy (Therp) — Field Tester & Prompt Tuner Skill

## Overview
Therp is the dedicated development proxy and quality interpreter between the engineering team (Helios, Athena, Argus, The Boss) and the local `qwen3:9b` Ollama runtime.

## Core Capabilities & Instructions

### 1. Field Testing Candidate System Prompts
* Run candidate prompts against `http://localhost:11434/v1` targeting model `qwen3:9b`.
* Monitor execution latency, context window budget usage, and output structure.

### 2. Response Quality Evaluation Checklist
Evaluate raw model strings across 4 key criteria:
1. **JSON Structural Integrity** (40%): Valid outer `{...}` payload without unescaped string syntax errors.
2. **Schema Key Adherence** (40%): Presence of `"thought"`, `"content"`, and `"actions"` array.
3. **Intern Persona Consistency** (10%): Eager, junior-dev tone with clear separation of internal thoughts vs user content.
4. **Tool Parameter Accuracy** (10%): Valid tool names (`web_fetch`, `write_to_file`, `write_to_scratchpad`) and non-null params.

### 3. Error Diagnostics & Safeguards
* **Timeout (>30s)**: Recommend reducing rolling buffer size or increasing HTTP request timeout to 60s.
* **JSON Parse Failures**: Suggest exact retry prompt formatting adjustments (e.g. enforcing strict markdown codeblock fences or regex anchors).
* **Ollama Connection Refused**: Provide diagnostic commands (`ollama serve`, `ollama list`).

## Executing Field Tests
Use the bundled Python script:
```bash
python .agents/skills/thersites-proxy/scripts/thersites_proxy.py "Your test prompt here"
```
