"""Shared utilities for open-context hook scripts."""
import json
import os
import sys
import tempfile
from pathlib import Path


def check_plugin_root(hook_label: str) -> str:
    """Return CLAUDE_PLUGIN_ROOT or exit 0 with a stderr message."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        print(
            f"[open-context] CLAUDE_PLUGIN_ROOT not set — {hook_label} skipped",
            file=sys.stderr,
        )
        sys.exit(0)
    return plugin_root


def read_stdin_json() -> dict:
    """Read and parse JSON from stdin, exit 0 on parse error."""
    try:
        return json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(
            f"[open-context] Failed to parse hook JSON from stdin: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)


def setup_plugin_path(plugin_root: str) -> None:
    """Insert src/ and vendor/ from the plugin root into sys.path."""
    root = Path(plugin_root)
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "vendor"))


WIZARD_TRIGGER = (
    "[open-context] First-run setup detected — no configuration found for this project.\n\n"
    "Start the open-context setup wizard now. Do not wait for the user to invoke a command — "
    "begin the `/oc-setup` skill immediately by asking the first setup question:\n\n"
    "**Question 1 — Scope**\n"
    "Where should open-context save its settings?\n"
    "1. `project` — saved to `.open-context/oc-settings.yaml` in this repo "
    "(local to your machine — gitignored, not shared with the team)\n"
    "2. `global` — saved to your machine only (applies to all your projects)\n\n"
    "After the user answers, continue with Questions 2–5 per the `/oc-setup` skill, "
    "then generate context.yaml, test files, and run validation automatically."
)


def context_yaml_candidates(cwd: "Path") -> "list[Path]":
    """
    Return candidate context.yaml paths for cwd: the wizard-generated
    location first, then hand-authored locations (project root, git root) —
    everything open-context generates lives under .open-context/, but a
    project can still hand-write context.yaml anywhere else per the README.
    """
    cwd = Path(cwd).resolve()
    candidates = [cwd / ".open-context" / "context.yaml", cwd / "context.yaml"]
    d = cwd
    while d != d.parent:
        if (d / ".git").exists():
            candidates.append(d / "context.yaml")
            break
        d = d.parent
    return candidates


def repo_root_for_context(context_path: "Path") -> "Path":
    """
    The repo root that related_components paths are relative to, derived
    from which candidate in context_yaml_candidates() matched:
      cwd/.open-context/context.yaml -> cwd (go up one extra level)
      cwd/context.yaml               -> cwd
      git_root/context.yaml          -> git_root
    """
    context_path = Path(context_path).resolve()
    parent = context_path.parent
    if parent.name == ".open-context":
        return parent.parent
    return parent


def _session_state_dir() -> "Path":
    """
    Directory for per-session domain-drift state, one JSON file per
    session_id. Prefers CLAUDE_PLUGIN_DATA (survives across processes for
    the same plugin install); falls back to the system temp dir when unset
    so the drift hook still degrades gracefully instead of erroring.
    """
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or tempfile.gettempdir()
    d = Path(base) / "open-context" / "session-state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def session_state_path(session_id: str) -> "Path":
    return _session_state_dir() / f"{session_id or 'unknown'}.json"


def _atomic_write_json(path: "Path", data: dict) -> None:
    """Write-temp-then-rename so a killed/interrupted write can never leave
    a half-written, unparseable state file behind."""
    tmp = path.with_suffix(f"{path.suffix}.tmp{os.getpid()}")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def read_session_domains(session_id: str) -> "set[str]":
    """Domains already surfaced (via prompt match or drift hook) this turn."""
    path = session_state_path(session_id)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("domains", []))
    except (json.JSONDecodeError, OSError):
        return set()


def reset_session_domains(session_id: str, domains: "list[str]") -> None:
    """Overwrite the per-turn domain set. Called once per UserPromptSubmit
    so drift tracking starts fresh for each new task."""
    if not session_id:
        return
    _atomic_write_json(session_state_path(session_id), {"domains": sorted(set(domains))})


def add_session_domains(session_id: str, domains: "list[str]") -> None:
    """Merge newly-surfaced domains into the per-turn set. Called from the
    drift hook after injecting. This is read-modify-write, not locked —
    under a genuine race (two Edit/Write calls firing concurrently in the
    same domain) the worst case is one redundant re-injection later, not
    state corruption (writes themselves are always atomic)."""
    if not session_id:
        return
    current = read_session_domains(session_id)
    current.update(domains)
    _atomic_write_json(session_state_path(session_id), {"domains": sorted(current)})


def drift_detection_enabled(cwd: "Path") -> bool:
    """
    Read the domain_drift_detection flag from oc-settings.yaml (project
    scope, checked first) or settings.json (global scope). Defaults to
    True (enabled) when the key is absent or no settings file exists yet —
    this is an MVP being dogfooded by a single user, so the feature should
    be on by default; the flag exists so it can be switched off to compare
    behavior/latency without touching code.
    """
    cwd = Path(cwd).resolve()

    project_settings = cwd / ".open-context" / "oc-settings.yaml"
    if project_settings.exists():
        try:
            import yaml  # pylint: disable=import-outside-toplevel
            # sys.path is only set up by the caller (setup_plugin_path)
            # before this function is called, so this can't be a top-level import
            data = yaml.safe_load(project_settings.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict) and "domain_drift_detection" in data:
                return bool(data["domain_drift_detection"])
        except Exception:  # pylint: disable=broad-except
            pass

    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if plugin_data:
        global_settings = Path(plugin_data) / "open-context" / "settings.json"
        if global_settings.exists():
            try:
                data = json.loads(global_settings.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "domain_drift_detection" in data:
                    return bool(data["domain_drift_detection"])
            except (json.JSONDecodeError, OSError):
                pass

    return True


def is_first_run(cwd: "Path") -> bool:
    """Return True if no open-context config exists for this project."""
    cwd = Path(cwd).resolve()

    if (cwd / ".open-context" / "oc-settings.yaml").exists():
        return False

    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if plugin_data and (Path(plugin_data) / "open-context" / "settings.json").exists():
        return False

    return not any(c.exists() for c in context_yaml_candidates(cwd))
