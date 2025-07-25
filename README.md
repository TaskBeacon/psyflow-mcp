# PsyFlow‑MCP · Usage Guide

A lightweight **FastMCP** server that lets a language‑model clone, transform, download and local‑translate PsyFlow task templates using a single entry‑point tool.

---

## 1 · Install & Run

```bash
# 1. Clone your project repository
git clone https://github.com/TaskBeacon/psyflow-mcp.git
cd psyflow_mcp

# 2. Install runtime deps
pip install "mcp-sdk[fastmcp]" gitpython httpx ruamel.yaml

# 3. Launch the std‑IO server
python main.py
```

The process stays in the foreground and communicates with the LLM over **STDIN/STDOUT** via the Model‑Context‑Protocol (MCP).

---

## 2 · Conceptual Workflow

1. **User** describes the task they want (e.g. “Make a Stroop out of Flanker”).
2. **LLM** calls the `` tool:\
   • If the model already knows the best starting template it passes `source_task`.\
   • Otherwise it omits `source_task`, receives a menu created by ``, picks a repo, then calls `` again with that repo.
3. The server clones the chosen template, returns a Stage 0→5 instruction prompt (``) plus the local template path.
4. The LLM edits files locally, optionally invokes `` to localise *config.yaml*, then zips / commits the new task.

---

## 3 · Exposed Tools

| Tool               | Arguments                              | Purpose / Return                                                                                                                                                                                                                                                             |
| ------------------ | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `build_task`       | `target_task:str`, `source_task?:str`  | **Main entry‑point.**  • With `source_task` → clones repo and returns:  `prompt` (Stage 0→5) **+** `template_path` (local clone).  • Without `source_task` → returns `prompt_messages` from `` so the LLM can pick the best starting template, then call `build_task` again. |
| `list_tasks`       | *none*                                 | Returns an array of objects: `{ repo, readme_snippet, branches }`, where `branches` lists up to 20 branch names for that repo.                                                                                                                                               |
| `download_task`    | `repo:str`                             | Clones any template repo from the registry and returns its local path.                                                                                                                                                                                                       |
| `translate_config` | `task_path:str`, `target_language:str` | Reads `config.yaml`, wraps it in ``, and returns `prompt_messages` so the LLM can translate YAML fields in‑place.                                                                                                                                                            |

> **Why a single entry‑point?**  `build_task` already covers both “discover a template” **and** “explicitly transform template X into Y”. Separate `transform_task` became redundant, so it has been removed.

---

## 4 · Exposed Prompts

| Prompt                    | Parameters                                       | Description                                                                                                                                                      |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `transform_prompt`        | `source_task`, `target_task`                     | Single **User** message containing the full Stage 0→5 instructions to convert `source_task` into `target_task`.                                                  |
| `choose_template_prompt`  | `desc`, `candidates:list[{repo,readme_snippet}]` | Three **User** messages: task description, template list, and selection criteria. The LLM must reply with **one repo name** or the literal word `NONE`.          |
| `translate_config_prompt` | `yaml_text`, `target_language`                   | Two‑message sequence: strict translation instruction + raw YAML. The LLM must return the fully‑translated YAML body with formatting preserved and no commentary. |

---

## 5 · Typical Call‑and‑Response

### 5.1 – Template Discovery

```json
{ "tool": "build_task", 
    "arguments": { "target_task": "Stroop" } 
}
```

Server → returns `prompt_messages` .

### 5.2 – LLM Chooses Template & Requests Build

```json
{ "tool": "build_task", 
    "arguments": { "target_task": "Stroop", 
                   "source_task": "Flanker" } 
}
```

Server → returns Stage 0→5 `prompt` + `template_path` (cloned **Flanker** repo).

### 5.3 – Translating YAML (Optional)

```json
{ "tool": "translate_config", 
        "arguments": { "task_path": "/abs/path/Flanker", 
                       "target_language": "zh" } 
}
```

Server → returns `prompt_messages`; LLM translates YAML and writes it back.

---

## 6 · Template Folder Layout

```
<repo>/
├─ config/
│  └─ config.yaml
├─ main.py
├─ src/
│  └─ run_trial.py
└─ README.md
```

Stage 0→5 assumes this structure.

---


Adjust `NON_TASK_REPOS`, network timeouts, or `git` clone depth to match your infrastructure.

