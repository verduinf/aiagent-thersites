# AI Agent Thersites — Intern Sandbox & Security Policy

## Overview
This document specifies the strict security boundaries and tool execution rules for **Thersites** ("The Intern"). All tool calls issued by Thersites are programmatically intercepted and verified by **The Warden** (`warden.py`) before touching disk or network.

---

## 📁 1. File System Permissions (Sandbox Enclosure)

* **Target Directory**: `C:\Dev\aiagent-thersites\sandbox`
* **Access Level**: **Full CRUD** (Create, Read, Update, Delete)
* **Strict Rule**: Thersites is granted full CRUD capabilities **strictly within** `C:\Dev\aiagent-thersites\sandbox`.
* **Path Enforcement**:
  * Every file path is resolved using Python's `pathlib.Path.resolve()`.
  * The target path must explicitly start with `C:\Dev\aiagent-thersites\sandbox`.
  * Any attempt to access, write, read, or delete files outside this directory (e.g. `../../etc/passwd` or system files) triggers an immediate security exception by The Warden:
    > `[ERROR: Path sandbox violation. Target path must be within /sandbox/.]`

### Approved Sandbox File Tools:
1. `write_to_file`: Create or update files in `/sandbox/`.
2. `read_file`: Read content from files in `/sandbox/`.
3. `delete_file`: Remove files from `/sandbox/`.
4. `list_sandbox`: List files and subdirectories within `/sandbox/`.
5. `write_to_scratchpad`: Hardcoded single target `scratchpad.md` in root.

---

## 🌐 2. Network Access Permissions (URL Whitelist)

* **Whitelisted Domain**: **`nu.nl`** (and subdomains `*.nu.nl`)
* **Strict Rule**: `web_fetch` requests are strictly restricted to **`nu.nl`**.
* **Domain Validation**:
  * Parsed via `urllib.parse.urlparse`.
  * If Thersites requests any domain other than `nu.nl` (e.g. `google.com`, `malicious-site.com`), The Warden intercepts the call and returns:
    > `[ERROR: Unauthorized domain. URL must be in whitelist: ['nu.nl']]`

---

## 🛡️ 3. The Warden Enforcement Contract

```
[ Thersites (Qwen3-9B) Action JSON ] ──► [ THE WARDEN (warden.py) ]
                                                   │
                                     ┌─────────────┴─────────────┐
                                     ▼                           ▼
                           (Path outside /sandbox/     (Path inside /sandbox/
                            OR domain != nu.nl)         AND domain == nu.nl)
                                     │                           │
                                     ▼                           ▼
                             🔴 [BLOCKED ERROR]         🟢 [EXECUTE PYTHON TOOL]
```
