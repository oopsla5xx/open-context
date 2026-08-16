"""Shared utilities for open-context hook scripts."""
import json
import os
import sys
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
