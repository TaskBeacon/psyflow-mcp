# psyflow_mcp

A minimal complete project (MCP) for psyflow.

---

## Overview

`psyflow_mcp` is a lightweight **FastMCP** server that lets a language-model clone, transform, download and localize PsyFlow task templates using a single entry-point tool.

This README provides instructions for setting up and using `psyflow_mcp` in different environments.

---

## 1 · Quick Start (Recommended)

The easiest way to use `psyflow_mcp` is with `uvx`. This tool automatically downloads the package from PyPI, installs it and its dependencies into a temporary virtual environment, and runs it in a single step. No manual cloning or setup is required.

### 1.1 · Prerequisites

Ensure you have `uvx` installed. If not, you can install it with `pip`:

```bash
pip install uvx
```

### 1.2 · LLM Tool Configuration (JSON)

To integrate `psyflow_mcp` with your LLM tool (like Gemini CLI or Cursor), use the following JSON configuration. This tells the tool how to run the server using `uvx`.

```json
{
  "name": "psyflow_mcp",
  "type": "stdio",
  "description": "Local FastMCP server for PsyFlow task operations. Uses uvx for automatic setup.",
  "isActive": true,
  "command": "uvx",
  "args": [
    "psyflow_mcp"
  ]
}
```

With this setup, the LLM can now use the `psyflow_mcp` tools.

---

## 2 · Manual Setup (For Developers)

This method is for developers who want to modify the source code of `psyflow_mcp`.

### 2.1 · Local Setup (StdIO)

This is the standard mode for local development and testing, where the server communicates over `STDIN/STDOUT`.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/TaskBeacon/psyflow_mcp.git
    cd psyflow_mcp
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    uv venv
    uv pip install "mcp[cli]>=1.12.2" psyflow gitpython httpx ruamel.yaml
    ```

3.  **Launch the std-IO server:**
    ```bash
    uv run python main.py
    ```

The process stays in the foreground and communicates with the LLM via the Model-Context-Protocol (MCP).

### 2.2 · Server Setup (SSE)

For a persistent, stateful server, you can use Server-Sent Events (SSE). This is ideal for production or when multiple clients need to interact with the same server instance.

1.  **Modify `main.py`:**
    Change the last line from `mcp.run(transport="stdio")` to:
    ```python
    mcp.run(transport="sse", port=8000)
    ```

2.  **Run the server:**
    ```bash
    uv run python main.py
    ```
    The server will now be accessible at `http://localhost:8000/mcp`.

---

## 3 · Conceptual Workflow

1.  **User** describes the task they want (e.g. “Make a Stroop out of Flanker”).
2.  **LLM** calls the `build_task` tool:
    *   If the model already knows the best starting template it passes `source_task`.
    *   Otherwise it omits `source_task`, receives a menu created by `choose_template_prompt`, picks a repo, then calls `build_task` again with that repo.
3.  The server clones the chosen template, returns a Stage 0→5 instruction prompt (`transform_prompt`) plus the local template path.
4.  The LLM edits files locally, optionally invokes `localize` to translate and adapt `config.yaml`, then zips / commits the new task.

---

## 4 · Exposed Tools

| Tool | Arguments | Purpose / Return |
| :--- | :--- | :--- |
| `build_task` | `target_task:str`, `source_task?:str` | **Main entry-point.** • With `source_task` → clones repo and returns: `prompt` (Stage 0→5) **+** `template_path` (local clone). • Without `source_task` → returns `prompt_messages` from `choose_template_prompt` so the LLM can pick the best starting template, then call `build_task` again. |
| `list_tasks` | *none* | Returns an array of objects: `{ repo, readme_snippet, branches }`, where `branches` lists up to 20 branch names for that repo. |
| `download_task` | `repo:str` | Clones any template repo from the registry and returns its local path. |
| `localize` | `task_path:str`, `target_language:str`, `voice?:str` | Reads `config.yaml`, wraps it in `localize_prompt`, and returns `prompt_messages`. If a `voice` is not provided, it first calls `list_voices` to find suitable options. Also deletes old `_voice.mp3` files. |
| `list_voices` | `filter_lang?:str` | Returns a human-readable string of available text-to-speech voices from `psyflow`, optionally filtered by language (e.g., "ja", "en"). |

---

## 5 · Exposed Prompts

| Prompt | Parameters | Description |
| :--- | :--- | :--- |
| `transform_prompt` | `source_task`, `target_task` | Single **User** message containing the full Stage 0→5 instructions to convert `source_task` into `target_task`. |
| `choose_template_prompt` | `desc`, `candidates:list[{repo,readme_snippet}]` | Three **User** messages: task description, template list, and selection criteria. The LLM must reply with **one repo name** or the literal word `NONE`. |
| `localize_prompt` | `yaml_text`, `target_language`, `voice_options?` | Two-message sequence: strict translation instruction + raw YAML. The LLM must return the fully-translated YAML body, adding the `voice: <short_name>` if suitable options were provided. |

---

## 6 · Advanced Setup

### 6.1 · Using a Custom PyPI Repository

If you need to install dependencies from a private or alternative package index, you can configure `uv` using an environment variable or a command-line flag.

**Using an environment variable:**
```bash
export UV_INDEX_URL="https://your-pypi-repository.com/"
uv pip install ...
```

**Using a command-line flag:**
```bash
uv pip install --index-url "https://your-pypi-repository.com/" ...
```

### 6.2 · Template Folder Layout

The Stage 0→5 transformation prompt assumes the following repository structure.

```
<repo>/
├─ config/
│  └─ config.yaml
├─ main.py
├─ src/
│  └─ run_trial.py
└─ README.md
```

---

Adjust `NON_TASK_REPOS`, network timeouts, or `git` clone depth in `main.py` to match your infrastructure.
