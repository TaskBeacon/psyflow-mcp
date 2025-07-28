# psyflow-mcp

A minimal complete project (MCP) for psyflow.

## Installation

To install this project using `uv`:

```bash
uv pip install psyflow-mcp
```

## Usage with uvx

`uvx` allows you to run commands within the project's `uv` environment without explicitly activating it. First, ensure you have `uvx` installed:

```bash
pip install uvx
```

Then, you can run the `psyflow-mcp` command (assuming `main.py` has a `main` function that is exposed as a script):

```bash
uvx psyflow-mcp
```

### Example `uvx` Configuration (uvx.json)

You can configure `uvx` to automatically use this project's environment. Create a `uvx.json` file in your project root or a parent directory with the following content:

```json
{
  "project_name": "psyflow-mcp",
  "entry_point": "main:main",
  "commands": {
    "run": "psyflow-mcp"
  }
}
```

With this `uvx.json` in place, you can simply run:

```bash
uvx run
```

This will execute the `main` function from `main.py` within the `psyflow-mcp` environment.


A lightweight **FastMCP** server that lets a language-model clone, transform, download and localize PsyFlow task templates using a single entry-point tool.

---

## 1 · Setup & Run

This project uses `uv` for fast and reliable dependency management.

### 1.1 · Local Setup (StdIO)

This is the standard mode for local development and testing, where the server communicates over `STDIN/STDOUT`.

```bash
# 1. Clone the repository
git clone https://github.com/TaskBeacon/psyflow-mcp.git
cd psyflow-mcp

# 2. Create a virtual environment and install dependencies
uv venv
uv pip install "mcp[cli]>=1.12.2" psyflow gitpython httpx ruamel.yaml

# 3. Launch the std-IO server
uv run python main.py
```

The process stays in the foreground and communicates with the LLM via the Model-Context-Protocol (MCP).

### 1.2 · Server Setup (SSE)

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

## 2 · MCP/LLM Setup

To connect this server to a Large Language Model (LLM) via a command-line interface (CLI) like Gemini CLI or a tool-integrated environment like Cursor, you'll need to provide a JSON configuration. Below are templates for both `StdIO` and `SSE` modes.

### 2.1 · StdIO Mode (Local Tool)

This configuration tells the CLI how to launch and communicate with the MCP server directly. Create a `psyflow-mcp.json` file with the following content, making sure to replace `/path/to/your/project/psyflow-mcp` with the actual absolute path to the cloned repository on your machine.

```json
{
  "tool": {
    "name": "psyflow_mcp_stdio",
    "description": "A lightweight server to clone, transform, and download PsyFlow task templates.",
    "command": ["uv", "run", "python", "main.py"],
    "working_directory": "/path/to/your/project/psyflow-mcp"
  }
}
```

```json
 "psyflow-mcp": {
      "name": "PsyFlow-MCP",
      "type": "stdio",          // communicate over STDIN / STDOUT
      "description": "Local FastMCP server for PsyFlow task operations",
      "isActive": true,         // set false to disable without deleting
      "registryUrl": "",        // leave blank – weʼre running locally
      "command": "python",      // executable to launch
      "args": [
            "E:\\xhmhc\\TaskBeacon\\psyflow-mcp\\main.py"
               ]
    }


 "psyflow-mcp-pypi": {
      "name": "PsyFlow-MCP",
      "type": "stdio",          // communicate over STDIN / STDOUT
      "description": "FastMCP server for PsyFlow task operations",
      "isActive": true,         // set false to disable without deleting
      "registryUrl": "",        // leave blank – weʼre running locally
      "command": "uvx",      // executable to launch
      "args": [
            "psyflow-mcp"
               ]
    }
```

### 2.2 · SSE Mode (Remote Tool)

When the server is running persistently (as described in section 1.2), you can connect to it as a remote tool using its HTTP endpoint.

```json
{
  "tool": {
    "name": "psyflow_mcp_sse",
    "description": "A lightweight server to clone, transform, and download PsyFlow task templates.",
    "endpoint": "http://localhost:8000/mcp"
  }
}
```

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
export UV_INDEX_URL="https://pypi.org/manage/project/psyflow-mcp/"
uv pip install ...
```

**Using a command-line flag:**
```bash
uv pip install --index-url "https://pypi.org/manage/project/psyflow-mcp/" ...
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
