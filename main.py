"""
psyflow_mcp/main.py
-------------------
FastMCP std-IO server exposing:
  • build_task, transform_task, download_task, translate_config (tools)
  • transform_prompt, translate_config_prompt, choose_template_prompt (prompts)
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from git import Repo
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from ruamel.yaml import YAML

# ─────────────────────────────
# Config
# ─────────────────────────────
ORG = "TaskBeacon"
CACHE = Path("./task_cache"); CACHE.mkdir(exist_ok=True)
NON_TASK_REPOS = {"task-registry", ".github","psyflow","psyflow-mcp","community","taskbeacon.github.io"}

yaml = YAML(); yaml.indent(mapping=2, sequence=4, offset=2)

# ─────────────────────────────
# FastMCP instance
# ─────────────────────────────
mcp = FastMCP(name="psyflow-mcp")

# ═════════════════════════════
# Prompts
# ═════════════════════════════
_PROMPT_TEMPLATE = textwrap.dedent("""
Turn my existing {source_task} implementation in PsyFlow/TAPs into a {target_task} task with as few changes as possible.

Breakdown:

Stage 0: Plan
* Read literature and figure out what a typical {target_task} task looks like
* Define the flow: blocks → trials → events
* Identify stimulus types, response keys, timing parameters, and key output fields

Stage 1: config.yaml
* Adapt the existing config.yaml to run a {target_task} task
* Highlight any parameters that need careful review

Stage 2: Trial logic (src/run_trial.py)
* Adapt one existing trial template to run a single {target_task} trial
* (Optional) If needed, add helpers in src/utils.py; otherwise skip

Stage 3: Block/session logic (main.py)
* Implement block order, feedback screens, and pauses based on the template task
* Keep the public API consistent with the original task

Stage 4: README.md
* Match the structure and tone of existing tasks
* Cover: purpose, install steps, config details, run instructions, and expected outputs

Stage 5: Static validation
* Check that config.yaml keys line up with code references
* Ensure logged DataFrame columns match the template task
* Verify naming, docstrings, and imports follow PsyFlow conventions
* Confirm variables such as timing and triggers match between run_trial.py and config.yaml
* Spot any logic errors or unused variables

(No PsychoPy runtime or unit tests are required during this step)
""").strip()

@mcp.prompt(title="Task Transformation Prompt")
def transform_prompt(source_task: str, target_task: str) -> base.UserMessage:
    return base.UserMessage(_PROMPT_TEMPLATE.format(
        source_task=source_task, target_task=target_task
    ))


@mcp.prompt(title="Translate Config YAML")
def translate_config_prompt(yaml_text: str, target_language: str) -> list[base.Message]:
    intro = (
        f"Translate selected fields of this PsyFlow config into {target_language}. "
        "Translate ONLY:\n"
        "  • subinfo_mapping values\n"
        "  • stimuli entries of type 'text' or 'textbox' (the `text` field)\n\n"
        "Return the COMPLETE YAML with translated values — no commentary."
    )
    return [base.UserMessage(intro), base.UserMessage(yaml_text)]


@mcp.prompt(title="Choose Template")
def choose_template_prompt(
    desc: str,
    candidates: list[dict],
) -> list[base.Message]:
    """
    Ask the LLM to pick the SINGLE template repo that will require the
    fewest changes to become the requested task.

    Parameters
    ----------
    desc : str
        Free-form description of the task the user ultimately wants
        (e.g. “A classic color-word Stroop with 2 blocks of 48 trials”).
    candidates : list[dict]
        Each dict must have:
          { "repo": "<name>", "readme_snippet": "<first 400 chars>" }
    """
    criteria = (
        "- Prefer tasks with the same **response mapping paradigm** "
        "(e.g. 2-choice left/right, go/no-go, continuous RT).\n"
        "- Prefer tasks whose **trial/block flow** most closely matches "
        "the requested task’s flow.\n"
        "- If several are equally close, choose the repo that appears to "
        "need the **fewest code edits** (smaller conceptual jump).\n"
    )

    intro = (
        "You are given a desired task description plus candidate PsyFlow "
        "template repositories.\n\n"
        "Select the **one** template that will require the LEAST effort to "
        "transform into the desired task, using these tie-breakers:\n"
        f"{criteria}\n"
        "Respond with **only** the repo name on a single line.\n"
        "If NONE of the templates are reasonably close, respond with `NONE`."
    )

    menu = "\n".join(
        f"- **{c['repo']}**: {c['readme_snippet']}" for c in candidates
    ) or "(no templates found)"

    return [
        base.UserMessage(intro),
        base.UserMessage(f"Desired task:\n{desc}"),
        base.UserMessage("Candidate templates:\n" + menu),
    ]

# ═════════════════════════════
# HELPERS
# ═════════════════════════════
async def _github_repos() -> List[dict]:
    url = f"https://api.github.com/orgs/{ORG}/repos?per_page=100"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=30); r.raise_for_status()
    return r.json()

async def _repo_branches(repo: str) -> List[str]:
    url = f"https://api.github.com/repos/{ORG}/{repo}/branches?per_page=100"
    async with httpx.AsyncClient() as c:
        r = await c.get(url, timeout=15)
    return [b["name"] for b in r.json()][:20]  # cap at 10

async def task_repos() -> List[str]:
    return [r["name"] for r in await _github_repos() if r["name"] not in NON_TASK_REPOS]

def clone(repo: str) -> Path:
    dest = CACHE / repo
    if dest.exists(): return dest
    Repo.clone_from(f"https://github.com/{ORG}/{repo}.git", dest, depth=1)
    return dest

# ═════════════════════════════
# TOOLS
# ═════════════════════════════
@mcp.tool()
async def build_task(target_task: str, source_task: Optional[str] = None) -> Dict:
    """
    • With `source_task` → clone repo & return Stage-0→5 prompt + local path.
    • Without `source_task` → send `choose_template_prompt` so the LLM picks.
    """
    repos = await task_repos()

    # branch 1 : explicit source
    if source_task:
        repo = next((r for r in repos if source_task.lower() in r.lower()), None)
        if not repo:
            raise ValueError("Template repo not found.")
        path = await asyncio.to_thread(clone, repo)
        return {
            "prompt": transform_prompt(source_task, target_task).content,
            "template_path": str(path),
        }

    # branch 2 : no source → build menu
    snippets = []
    for repo in repos:
        url = f"https://raw.githubusercontent.com/{ORG}/{repo}/main/README.md"
        async with httpx.AsyncClient() as c:
            rd = await c.get(url, timeout=10)
        snippet = rd.text[:2000].replace("\n", " ") if rd.status_code == 200 else ""
        snippets.append({"repo": repo, "readme_snippet": snippet})

    msgs = choose_template_prompt(f"A {target_task} task.", snippets)
    return {
        "prompt_messages": [m.dict() for m in msgs],
        "note": "Reply with chosen repo, then call build_task again with source_task=<repo>.",
    }

@mcp.tool()
async def download_task(repo: str) -> Dict:
    """Clone any template repo locally and return the path."""
    repos = await task_repos()
    if repo not in repos:
        raise ValueError("Repo not found or not a task template.")
    path = await asyncio.to_thread(clone, repo)
    return {"template_path": str(path)}


@mcp.tool()
async def translate_config(task_path: str, target_language: str) -> Dict:
    """
    Load <task_path>/config.yaml and feed its YAML text to
    translate_config_prompt.  Returns prompt_messages ready for the LLM.
    """
    cfg_path = Path(task_path) / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError("config.yaml not found in given path.")
    yaml_text = cfg_path.read_text(encoding="utf-8")
    msgs = translate_config_prompt(yaml_text, target_language)
    return {"prompt_messages": [m.dict() for m in msgs]}

@mcp.tool()
async def list_tasks() -> List[Dict]:
    """
    Return metadata for every task template repo:

      • repo              – repository name
      • readme_snippet    – first 2000 characters of README.md
      • branches          – up to 10 branch names
    """
    repos = await task_repos()
    results: List[Dict] = []

    async def build_entry(repo: str) -> Dict:
        readme_url = f"https://raw.githubusercontent.com/{ORG}/{repo}/main/README.md"
        async with httpx.AsyncClient() as c:
            rd = await c.get(readme_url, timeout=10)
        snippet = rd.text[:2000].replace("\n", " ") if rd.status_code == 200 else ""
        branches = await _repo_branches(repo)
        return {"repo": repo, "readme_snippet": snippet, "branches": branches}

    # gather concurrently for speed
    entries = await asyncio.gather(*(build_entry(r) for r in repos))
    results.extend(entries)
    return results

# ═════════════════════════════
# MAIN
# ═════════════════════════════
if __name__ == "__main__":
    mcp.run_stdio()
