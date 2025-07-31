
'''
psyflow_mcp/main.py
-------------------
FastMCP std-IO server exposing:
  • build_task, transform_task, download_task, localize (tools)
  • transform_prompt, localize_prompt, choose_template_prompt (prompts)
'''

# from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from git import Repo
from mcp.server.fastmcp import FastMCP
# from mcp.server.fastmcp.prompts import base
from mcp.server.fastmcp.prompts.base import UserMessage, Message
from ruamel.yaml import YAML
from edge_tts import VoicesManager


# ─────────────────────────────
# Config
# ─────────────────────────────
ORG = "TaskBeacon"
CACHE = Path("./task_cache"); 
NON_TASK_REPOS = {"task-registry", ".github","psyflow","psyflow-mcp","community","taskbeacon.github.io"}

yaml = YAML(); yaml.indent(mapping=2, sequence=4, offset=2)

# ─────────────────────────────
# FastMCP instance
# ─────────────────────────────
mcp = FastMCP(name="psyflow-mcp")

# ═════════════════════════════
# Prompts
# ═════════════════════════════
_PROMPT_TEMPLATE = textwrap.dedent('''
Turn my existing {source_task} implementation in PsyFlow/TAPs into a {target_task} task with as few changes as possible.

**Key requirements:**
- The unit for all stimuli sizes must be in \'deg\' (degrees of visual angle).
- When creating the new task, a new folder should be created with the task name, and the temporary `task_cache` folder should be removed.
- All voice-over files (`_voice.mp3`) and other non-relevant files in the `assets/` directory of the source task must be removed.
- When accessing recorded variables for stats (e.g., in `main.py` for break or final stats), you must prefix the variable with the `stimunit` label from `run_trial.py`. For example, to access `hit` for a `stimunit` labeled "target", use `target_hit`.

Breakdown:

Stage 0: Plan
* Read literature and figure out what a typical {target_task} task looks like.
* Define the flow: blocks → trials → events.
* Identify stimulus types (ensuring sizes are in \'deg\'), response keys, timing parameters, and key output fields.

Stage 1: config.yaml
* Adapt the existing config.yaml to run a {target_task} task.
* Ensure all stimulus sizes are defined in \'deg\' and are of an appropriate size for a typical screen.
* Highlight any parameters that need careful review.

Stage 2: Trial logic (src/run_trial.py)
* Adapt one existing trial template to run a single {target_task} trial.
* (Optional) If needed, add helpers in src/utils.py; otherwise skip.

Stage 3: Block/session logic (main.py)
* Implement block order, feedback screens, and pauses based on the template task.
* Keep the public API consistent with the original task.
* Ensure that when accessing recorded variables to a specific stimunit, the correct `stimunit` prefix is used (e.g., `target_hit`).

Stage 4: Asset handling
* Identify and list for removal all `_voice.mp3` files from the `assets/` directory.
* Identify and list for removal any other files in `assets/` not relevant to the new {target_task}.

Stage 5: README.md
* Match the structure and tone of existing tasks.
* Cover: purpose, install steps, config details, run instructions, and expected outputs.

Stage 6: Static validation
* Check for correct chainable syntax (e.g., using `\\` for new lines).
* Check that `src/__init__.py` is properly defined.
* Cross-reference `config.yaml` with `main.py`, `run_trial.py`, and `utils.py` (if it exists) to ensure all stimuli, variables, durations, and triggers are defined and used consistently.
* Check that config.yaml keys line up with code references.
* Ensure logged DataFrame columns match the template task.
* Verify naming, docstrings, and imports follow PsyFlow conventions.
* Spot any logic errors or unused variables.

(No PsychoPy runtime or unit tests are required during this step)
''').strip()

@mcp.prompt(title="Task Transformation Prompt")
def transform_prompt(source_task: str, target_task: str) -> UserMessage:
    return UserMessage(_PROMPT_TEMPLATE.format(
        source_task=source_task, target_task=target_task
    ))


@mcp.prompt(title="Localize task")
def localize_prompt(yaml_text: str, target_language: str, voice_options: Optional[str] = None) -> list[Message]:
    intro = (
        f"Translate selected fields of this PsyFlow config into {target_language}. "
        "Translate ONLY:"
        "  • subinfo_mapping values"
        "  • stimuli entries of type 'text' or 'textbox' (the `text` field)"
    )

    intro = (
        f"For the {target_language}, please also adjust font field for stimuli entries of type 'text' or 'textbox' "
        "Ensure the text, or textbox is displayed in the correct font.")


    if voice_options:
        intro += (
            f"Then, select the most suitable voice for {target_language} from the list below. Update the `voice_name` field in the config with the selected voice's short name. "
            "The short name is the identifier at the beginning of each line (e.g., 'zh-CN-YunyangNeural')."
            "If no suitable voice is available, set `voice_name: null`."
            f"Available voices: {voice_options}; select one from it"
        )
    intro += "Lastly, update the config.yaml file with translated values and tweaks — no commentary."
    return [UserMessage(intro), UserMessage(yaml_text)]


@mcp.prompt(title="Choose Template")
def choose_template_prompt(
    desc: str,
    candidates: list[dict],
) -> list[Message]:
    '''
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
    '''
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
        UserMessage(intro),
        UserMessage(f"Desired task:\n{desc}"),
        UserMessage("Candidate templates:\n" + menu),
    ]


@mcp.prompt(title="Choose Repository for Download")
def choose_repo_prompt(
    user_query: str,
    candidates: list[dict],
) -> list[Message]:
    '''
    Ask the LLM to pick the SINGLE repository that best matches the user's query.

    Parameters
    ----------
    user_query : str
        The user's natural language query for the desired task/repository.
    candidates : list[dict]
        Each dict must have:
          { "repo": "<name>", "readme_snippet": "<first 2000 chars>" }
    '''
    intro = (
        "You are given a user's query for a task/repository and a list of "
        "candidate PsyFlow template repositories.\n\n"
        "Select the **one** repository that best matches the user's intent. "
        "Consider the repository name and the README snippet for context.\n"
        "Respond with **only** the repo name on a single line.\n"
        "If NONE of the candidates are a reasonable match, respond with `NONE`."
    )

    menu = "\n".join(
        f"- **{c['repo']}**: {c['readme_snippet']}" for c in candidates
    ) or "(no repositories found)"

    return [
        UserMessage(intro),
        UserMessage(f"User query: {user_query}"),
        UserMessage("Candidate repositories:\n" + menu),
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


async def _list_supported_voices_async(filter_lang: Optional[str] = None):
    vm = await VoicesManager.create()
    voices = vm.voices
    if filter_lang:
        voices = [v for v in voices if v["Locale"].startswith(filter_lang)]
    return voices
async def list_supported_voices(
    filter_lang: Optional[str] = None,
    human_readable: bool = False
):
    """Query available edge-tts voices.

    Parameters
    ----------
    filter_lang : str, optional
        Return only voices whose locale starts with this prefix.
    human_readable : bool, optional
        If ``True`` print a formatted table; otherwise return the raw list.

    Returns
    -------
    list of dict or None
        The raw voice dictionaries if ``human_readable`` is ``False``,
        otherwise ``None``.
    """
    voices = await _list_supported_voices_async(filter_lang)
    if not human_readable:
        return voices

    # Table header including the Personalities column
    header = (
        f"{'ShortName':25} {'Locale':10} {'Gender':8} "
        f"{'Personalities':30} {'FriendlyName'}"
    )
    separator = "-" * len(header)
    print(header)
    print(separator)

    for v in voices:
        short = v.get("ShortName", "")[:25]
        loc   = v.get("Locale", "")[:10]
        gen   = v.get("Gender", "")[:8]
        # Extract the personalities list and join with commas
        pers_list = v.get("VoiceTag", {}).get("VoicePersonalities", [])
        pers = ", ".join(pers_list)[:30]
        # Use FriendlyName as the display name
        disp  = v.get("FriendlyName", v.get("Name", ""))

        print(f"{short:25} {loc:10} {gen:8} {pers:30} {disp}")
# ═════════════════════════════
# TOOLS
# ═════════════════════════════
@mcp.tool()
async def build_task(target_task: str, source_task: Optional[str] = None) -> Dict:
    '''
    • With `source_task` → clone repo & return Stage-0→5 prompt + local path.
    • Without `source_task` → send `choose_template_prompt` so the LLM picks.
    '''
    CACHE.mkdir(exist_ok=True)
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
    '''
    Clone any template repo locally and return the path.
    If the repo name is ambiguous or a natural language query, it will
    use an LLM to select the best matching repository.
    '''
    CACHE.mkdir(exist_ok=True)
    all_repos = await task_repos()

    # Check for exact match first
    if repo in all_repos:
        path = await asyncio.to_thread(clone, repo)
        return {"template_path": str(path)}

    # If not an exact match, use LLM to select the best repo
    snippets = []
    for r_name in all_repos:
        readme_url = f"https://raw.githubusercontent.com/{ORG}/{r_name}/main/README.md"
        async with httpx.AsyncClient() as c:
            rd = await c.get(readme_url, timeout=10)
        snippet = rd.text[:2000].replace("\n", " ") if rd.status_code == 200 else ""
        snippets.append({"repo": r_name, "readme_snippet": snippet})

    msgs = choose_repo_prompt(repo, snippets)
    return {
        "prompt_messages": [m.dict() for m in msgs],
        "note": "Reply with chosen repo, then call download_task again with the selected repo name.",
    }


@mcp.tool()
async def localize(task_path: str, target_language: str, voice: Optional[str] = None) -> Dict:
    '''
    Load <task_path>/config.yaml and feed its YAML text to
    localize_prompt.  Returns prompt_messages ready for the LLM.
    '''
    CACHE.mkdir(exist_ok=True)
    # Delete old voice files
    assets_path = Path(task_path) / "assets"
    if assets_path.exists():
        for f in assets_path.glob("*_voice.mp3"):
            f.unlink()

    cfg_path = Path(task_path) / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError("config.yaml not found in given path.")
    yaml_text = cfg_path.read_text(encoding="utf-8")

    # Get voice options if not provided
    if voice:
        voice_options = voice
    else:
        voice_options = list_voices(filter_lang=target_language)

    msgs = localize_prompt(yaml_text, target_language, voice_options)
    return {"prompt_messages": [m.dict() for m in msgs]}

@mcp.tool()
def list_voices(filter_lang: Optional[str] = None) -> str:
    '''
    List supported voices from psyflow, optionally filtering by language.
    '''
    return list_supported_voices(filter_lang=filter_lang, human_readable=True)

@mcp.tool()
async def list_tasks() -> List[Dict]:
    '''
    Return metadata for every task template repo:

      • repo              – repository name
      • readme_snippet    – first 2000 characters of README.md
      • branches          – up to 10 branch names
    '''
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

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    mcp.run(transport="stdio")


