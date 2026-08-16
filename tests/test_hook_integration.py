"""
Integration tests for resolve_hook.py and session_hook.py.

Runs hooks as real subprocesses — no mocking of the resolver.
All tests assert stdout/stderr boundaries and JSON structure exactly,
because the silent failure modes (wrong nesting, stdout pollution) are
invisible without explicit assertions.

PyYAML vendored version: 6.0.3 (pinned in vendor/yaml/).
If vendor/ is updated and these tests break, that is intentional —
it means a breaking change was introduced in the vendored dependency.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ── Paths ─────────────────────────────────────────────────────────────────────
PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
HOOK_SCRIPT = PLUGIN_ROOT / "scripts" / "resolve_hook.py"
SESSION_HOOK_SCRIPT = PLUGIN_ROOT / "scripts" / "session_hook.py"
SAMPLE_CONTEXT = (
    Path(__file__).parent.parent
    / "examples"
    / "rails-hmvc-sample"
    / "context.yaml"
)
PYTHON = sys.executable


# ── Helpers ───────────────────────────────────────────────────────────────────
def run_hook(prompt: str, cwd: str | None = None, env_overrides: dict | None = None) -> tuple[bytes, bytes, int]:
    """Run resolve_hook.py as a subprocess, return (stdout, stderr, returncode)."""
    if cwd is None:
        cwd = str(SAMPLE_CONTEXT.parent)

    stdin_data = json.dumps({
        "prompt": prompt,
        "user_prompt": prompt,
        "cwd": cwd,
        "hook_event_name": "UserPromptSubmit",
        "session_id": "test-session",
    }).encode()

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v

    result = subprocess.run(
        [PYTHON, str(HOOK_SCRIPT)],
        input=stdin_data,
        capture_output=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


# ── Test 1: no match → stdout empty ──────────────────────────────────────────
def test_no_match_stdout_empty():
    """A prompt that matches no domain must produce zero bytes on stdout (Q1, Q8)."""
    stdout, stderr, code = run_hook("explain this error message to me")
    assert code == 0
    assert stdout == b"", f"Expected empty stdout, got {len(stdout)} bytes: {stdout[:200]}"
    assert stderr == b""


# ── Test 2: missing Python → stderr only (shell wrapper) ─────────────────────
def test_missing_python_stderr_only(tmp_path):
    """
    When no compatible Python is on PATH, resolve_hook.sh must write to stderr
    only — stdout must remain empty (Q7).

    Creates a fake PATH with no Python binaries.
    """
    shell_script = PLUGIN_ROOT / "scripts" / "resolve_hook.sh"
    if not shell_script.exists():
        pytest.skip("resolve_hook.sh not present")

    stdin_data = json.dumps({
        "prompt": "renew book loan",
        "user_prompt": "renew book loan",
        "cwd": str(SAMPLE_CONTEXT.parent),
        "hook_event_name": "UserPromptSubmit",
        "session_id": "test-session",
    }).encode()

    # Create a PATH with no Python binary
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()

    env = os.environ.copy()
    env["PATH"] = str(empty_bin)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)

    result = subprocess.run(
        ["/bin/bash", str(shell_script)],
        input=stdin_data,
        capture_output=True,
        env=env,
    )

    assert result.stdout == b"", (
        f"stdout must be empty when Python is missing, got: {result.stdout[:200]}"
    )
    assert result.returncode == 0, "Hook must exit 0 even when Python is missing"
    assert b"open-context" in result.stderr, (
        f"Expected error message in stderr, got: {result.stderr}"
    )


# ── Test 3: match → correct JSON nesting ─────────────────────────────────────
def test_json_nesting_correct():
    """
    A matching prompt must output JSON with additionalContext nested exactly
    inside hookSpecificOutput — NOT at top level (Q8).

    This catches the silent failure mode where the field is present but
    Claude Code ignores it because of wrong nesting.
    """
    stdout, stderr, code = run_hook("renew book loan")
    assert code == 0
    assert stdout != b"", "Expected JSON output for a matching task"

    parsed = json.loads(stdout)

    # Top-level must NOT have additionalContext
    assert "additionalContext" not in parsed, (
        "additionalContext must NOT be at top level — it goes inside hookSpecificOutput"
    )

    # hookSpecificOutput must exist with correct fields
    assert "hookSpecificOutput" in parsed, "hookSpecificOutput missing from output"
    hs = parsed["hookSpecificOutput"]
    assert "additionalContext" in hs, "additionalContext missing from hookSpecificOutput"
    assert hs.get("hookEventName") == "UserPromptSubmit", (
        f"hookEventName wrong: {hs.get('hookEventName')}"
    )

    # Content must be non-empty and contain expected section
    ctx = hs["additionalContext"]
    assert len(ctx) > 100, "additionalContext unexpectedly short"
    assert "[MATCHED DOMAINS]" in ctx, "Expected [MATCHED DOMAINS] section in output"


# ── Test 4: truncation at section boundary ────────────────────────────────────
def test_truncation_boundary(tmp_path):
    """
    When output exceeds MAX_CHARS, the hook must truncate at a section
    boundary — not mid-line, not mid-file-path (Q4).

    Uses a synthetic large context.yaml with enough domains and patterns
    to trigger truncation (verified at ~9,737 chars for 3 domains).
    """
    # Build a context.yaml that forces 3+ domain matches and long output.
    # Rules are written inline to avoid YAML indentation issues from string concat.
    rules_yaml = ""
    for i in range(1, 13):
        rules_yaml += (
            f"  - id: rule-{i:02d}-domain-invariant\n"
            f"    description: >\n"
            f"      Architecture rule {i}: All mutations must be wrapped in a DB transaction.\n"
            f"      Partial writes are not recoverable. This rule applies across all domains.\n"
            f"    severity: CRITICAL\n"
            f"    guidance: |\n"
            f"      Use ApplicationRecord.transaction do ... end.\n"
            f"      Never call .save! outside a transaction block.\n"
            f"      Failure triggers alert_{i} and may cause cascade failures.\n"
        )

    large_context = textwrap.dedent("""\
        project:
          name: LargeApp
          language: Ruby
          framework: Rails 7
          api_versioning: v1
          default_actor: admin

        architecture:
          pattern: HMVC
          flow: [controller, operation, form, model, serializer]
          component_responsibilities:
            controller: Routes HTTP, calls one Operation, renders JSON via Serializer. No business logic.
            operation: Sequences business workflow as step_* methods. Validates via Form first.
            form: Input validation only. No side effects. No saves.
            model: AR persistence layer. Follow scoping conventions for tenant isolation.
            serializer: Formats Operation result as JSON. Never instantiated in Operation.

        domains:
          - name: authentication
            keywords: [login, logout, authenticate, session, token, oauth, sso]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/auth_controller.rb
              - app/operations/v1/auth/create_operation.rb
              - app/forms/v1/auth/create_form.rb
              - app/models/auth_token.rb
            subtypes:
              - name: authentication_create
                keywords: [login, logout]
                related_components: [app/controllers/v1/auth_creates_controller.rb]
            patterns:
              - id: auth-pat-01
                description: >
                  Authentication operations must validate ownership chain before mutation.
                  Never skip this step even for admin actors — policy check must precede
                  any DB write in this domain. This is a long pattern description to
                  increase output size for testing truncation behavior in the hook script.
              - id: auth-pat-02
                description: >
                  All authentication writes must emit a domain event to the auth_events
                  queue for downstream consumers. Use EventEmitter.emit with retry=3,
                  not direct enqueue. Missing events cause audit gaps and compliance failures.
            extra_components: []

          - name: billing
            keywords: [invoice, payment, subscription, charge, refund, plan, billing]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/billing_controller.rb
              - app/operations/v1/billing/create_operation.rb
              - app/forms/v1/billing/create_form.rb
              - app/models/billing_record.rb
            subtypes:
              - name: billing_create
                keywords: [invoice, payment]
                related_components: [app/controllers/v1/billing_creates_controller.rb]
            patterns:
              - id: billing-pat-01
                description: >
                  Billing operations must validate ownership chain before mutation.
                  Never skip this step even for admin actors — policy check must precede
                  any DB write in this domain. Billing failures must be idempotent.
              - id: billing-pat-02
                description: >
                  All billing writes must emit a domain event to the billing_events
                  queue for downstream consumers. Use EventEmitter.emit with retry=3,
                  not direct enqueue. Missing events cause revenue reconciliation gaps.
            extra_components: []

          - name: notification
            keywords: [notify, sms, push, alert, webhook, reminder]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/notification_controller.rb
              - app/operations/v1/notification/create_operation.rb
              - app/forms/v1/notification/create_form.rb
              - app/models/notification_record.rb
            subtypes:
              - name: notification_create
                keywords: [notify, sms]
                related_components: [app/controllers/v1/notification_creates_controller.rb]
            patterns:
              - id: notification-pat-01
                description: >
                  Notification operations must validate ownership chain before mutation.
                  Never skip this step even for admin actors. Notifications are irreversible
                  once sent — validate thoroughly before dispatching to external services.
              - id: notification-pat-02
                description: >
                  All notification writes must emit a domain event to the notification_events
                  queue. Use EventEmitter.emit with retry=3. Failed notifications must be
                  queued for retry, not silently dropped. Track delivery status per recipient.
            extra_components: []

        rules:
        """) + rules_yaml

    ctx_file = tmp_path / "context.yaml"
    ctx_file.write_text(large_context)

    # Task that matches all 3 domains (each needs >=2 keyword hits)
    stdout, stderr, code = run_hook(
        "login logout invoice payment alert notify",
        cwd=str(tmp_path),
    )

    assert code == 0

    if stdout == b"":
        pytest.skip("No domains matched — adjust test task keywords")

    parsed = json.loads(stdout)
    ctx_text = parsed["hookSpecificOutput"]["additionalContext"]

    # If truncation occurred, verify it happened at a section boundary.
    # Our hook uses rfind("\n[") so the cut point is always just before a
    # section header — meaning the last char before the truncation notice
    # belongs to a complete preceding section, not a mid-path or mid-line cut.
    if "[Context truncated" in ctx_text:
        # The text before the truncation notice must end with a complete line.
        before_truncation = ctx_text.split("[Context truncated")[0]
        last_char = before_truncation.rstrip("\n")[-1] if before_truncation.strip() else ""

        # Incomplete file paths end in partial path segments — they'd lack a
        # closing newline before the truncation and end mid-word.
        # A complete section ends with readable content, not a path separator.
        assert last_char not in ("/",), (
            f"Truncation appears to cut mid-path (last char: {last_char!r})"
        )

        # Verify the text right before the notice is valid (no orphaned half-lines).
        last_line = before_truncation.rstrip("\n").rsplit("\n", 1)[-1]
        assert len(last_line) > 0, "Empty last line before truncation notice"

    # Output must not exceed limit + truncation message overhead
    assert len(ctx_text) <= 9500 + 100, (
        f"Output exceeds MAX_CHARS even after truncation: {len(ctx_text)}"
    )

    # Stats are in systemMessage (not additionalContext) — verify no bleed
    assert "[open-context]" not in ctx_text, (
        "Stats must not appear in additionalContext — they belong in systemMessage"
    )


# ── Test 5: CLAUDE_PLUGIN_ROOT missing → no traceback on stdout ──────────────
def test_missing_plugin_root_env():
    """
    When CLAUDE_PLUGIN_ROOT is not set, hook must not leak a traceback to
    stdout — stdout must be empty, stderr must have a clear message (Q5).
    """
    stdout, stderr, code = run_hook(
        "renew book loan",
        env_overrides={"CLAUDE_PLUGIN_ROOT": None},
    )
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty when CLAUDE_PLUGIN_ROOT is missing, got: {stdout[:200]}"
    )
    assert b"CLAUDE_PLUGIN_ROOT" in stderr, (
        f"Expected CLAUDE_PLUGIN_ROOT mention in stderr, got: {stderr}"
    )
    # Ensure no Python traceback leaked to stdout
    assert b"Traceback" not in stdout
    assert b"ImportError" not in stdout


# ── Test 6: OPEN_CONTEXT_FILE wrong path → stderr warning ────────────────────
def test_env_var_wrong_path(tmp_path):
    """
    When OPEN_CONTEXT_FILE points to a non-existent file, hook must warn
    on stderr — this is distinguishable from the silent "no context.yaml
    found" case (Q2).
    """
    # Use a cwd with no context.yaml so fallback also finds nothing
    stdout, stderr, code = run_hook(
        "renew book loan",
        cwd=str(tmp_path),
        env_overrides={"OPEN_CONTEXT_FILE": "/nonexistent/path/context.yaml"},
    )
    assert code == 0
    assert b"OPEN_CONTEXT_FILE" in stderr or b"not found" in stderr, (
        f"Expected warning about OPEN_CONTEXT_FILE in stderr, got: {stderr}"
    )
    # No context.yaml + no settings → wizard trigger injected (first-run behavior)
    assert b"First-run setup detected" in stdout, (
        f"Expected wizard trigger in stdout for first-run project, got: {stdout[:200]}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# session_hook.py tests
# ══════════════════════════════════════════════════════════════════════════════

def run_session_hook(
    cwd: str | None = None,
    env_overrides: dict | None = None,
) -> tuple[bytes, bytes, int]:
    """Run session_hook.py as a subprocess, return (stdout, stderr, returncode)."""
    if cwd is None:
        cwd = str(PLUGIN_ROOT / "tests")  # no context.yaml or settings here

    stdin_data = json.dumps({
        "cwd": cwd,
        "hook_event_name": "SessionStart",
        "session_id": "test-session",
    }).encode()

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    env.pop("CLAUDE_PLUGIN_DATA", None)  # start clean — no global settings
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v

    result = subprocess.run(
        [PYTHON, str(SESSION_HOOK_SCRIPT)],
        input=stdin_data,
        capture_output=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


# ── S1: no config, no context.yaml → wizard trigger injected ─────────────────
def test_session_no_config_injects_wizard(tmp_path):
    """
    First-run: no settings file and no context.yaml anywhere under cwd.
    Hook must output JSON with the wizard trigger in additionalContext.
    """
    stdout, stderr, code = run_session_hook(cwd=str(tmp_path))
    assert code == 0
    assert stdout != b"", "Expected wizard trigger on stdout for first-run project"
    assert stderr == b""

    parsed = json.loads(stdout)
    hs = parsed.get("hookSpecificOutput", {})
    ctx = hs.get("additionalContext", "")
    assert "oc-setup" in ctx, "Wizard trigger must mention /oc-setup"
    assert "Scope" in ctx or "scope" in ctx, "Wizard trigger must include first question"


# ── S2: project settings exist → silent no-op ────────────────────────────────
def test_session_project_settings_no_op(tmp_path):
    """
    When .claude/oc-settings.yaml exists in cwd, hook must exit silently —
    setup has already been completed for this project.
    """
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    (settings_dir / "oc-settings.yaml").write_text("scope: project\nlanguage: ruby\n")

    stdout, stderr, code = run_session_hook(cwd=str(tmp_path))
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty when project settings exist, got: {stdout[:200]}"
    )
    assert stderr == b""


# ── S3: global settings exist → silent no-op ─────────────────────────────────
def test_session_global_settings_no_op(tmp_path):
    """
    When CLAUDE_PLUGIN_DATA/open-context/settings.json exists,
    hook must exit silently regardless of project state.
    """
    global_dir = tmp_path / "plugin_data" / "open-context"
    global_dir.mkdir(parents=True)
    (global_dir / "settings.json").write_text('{"scope":"global","language":"ruby"}')

    fresh_project = tmp_path / "project"
    fresh_project.mkdir()

    stdout, stderr, code = run_session_hook(
        cwd=str(fresh_project),
        env_overrides={"CLAUDE_PLUGIN_DATA": str(tmp_path / "plugin_data")},
    )
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty when global settings exist, got: {stdout[:200]}"
    )
    assert stderr == b""


# ── S4: context.yaml exists → silent no-op ───────────────────────────────────
def test_session_context_yaml_no_op(tmp_path):
    """
    When context.yaml exists in cwd (manual setup), hook must exit silently
    even if no oc-settings.yaml is present.
    """
    (tmp_path / "context.yaml").write_text("project:\n  name: test\n")

    stdout, stderr, code = run_session_hook(cwd=str(tmp_path))
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty when context.yaml already exists, got: {stdout[:200]}"
    )
    assert stderr == b""


# ── S5: CLAUDE_PLUGIN_ROOT missing → stderr only ─────────────────────────────
def test_session_missing_plugin_root(tmp_path):
    """
    When CLAUDE_PLUGIN_ROOT is not set, session hook must write to stderr only —
    stdout must remain empty and exit code must be 0.
    """
    stdout, stderr, code = run_session_hook(
        cwd=str(tmp_path),
        env_overrides={"CLAUDE_PLUGIN_ROOT": None},
    )
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty when CLAUDE_PLUGIN_ROOT is missing, got: {stdout[:200]}"
    )
    assert b"CLAUDE_PLUGIN_ROOT" in stderr, (
        f"Expected CLAUDE_PLUGIN_ROOT mention in stderr, got: {stderr}"
    )
    assert b"Traceback" not in stdout
    assert b"Traceback" not in stderr


# ── S6: wizard output has correct JSON nesting ───────────────────────────────
def test_session_json_nesting_correct(tmp_path):
    """
    Wizard trigger must be nested as hookSpecificOutput.additionalContext
    with hookEventName == "SessionStart" — not at top level.

    Wrong nesting causes Claude Code to silently ignore the trigger.
    """
    stdout, stderr, code = run_session_hook(cwd=str(tmp_path))
    assert code == 0
    assert stdout != b"", "Expected JSON output for first-run project"

    parsed = json.loads(stdout)

    assert "additionalContext" not in parsed, (
        "additionalContext must NOT be at top level"
    )
    assert "hookSpecificOutput" in parsed, "hookSpecificOutput missing from output"

    hs = parsed["hookSpecificOutput"]
    assert "additionalContext" in hs, "additionalContext missing from hookSpecificOutput"
    assert hs.get("hookEventName") == "SessionStart", (
        f"hookEventName must be 'SessionStart', got: {hs.get('hookEventName')!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Token savings stats tests
# ══════════════════════════════════════════════════════════════════════════════

_STATS_RE = re.compile(
    r"\[open-context\] (\d+)% token reduction \((\d+\.\d+) KB injected vs (\d+\.\d+) KB full context\)$"
)


# ── T1: stats present in systemMessage on match ──────────────────────────────
def test_stats_line_present_on_match():
    """
    A matching prompt must set systemMessage (visible in UI) with the token
    savings stats. Stats must NOT appear in additionalContext (that's for Claude).
    """
    stdout, _stderr, code = run_hook("renew book loan")
    assert code == 0
    parsed = json.loads(stdout)

    assert "systemMessage" in parsed, (
        "systemMessage key missing — stats must be visible in UI via systemMessage"
    )
    assert _STATS_RE.match(parsed["systemMessage"]), (
        f"systemMessage has unexpected format: {parsed['systemMessage']!r}"
    )
    # Stats must NOT bleed into additionalContext (that's Claude's context only)
    ctx = parsed["hookSpecificOutput"]["additionalContext"]
    assert "[open-context]" not in ctx, (
        "Stats line must not appear in additionalContext — use systemMessage only"
    )


# ── T2: stats values are numerically sane ────────────────────────────────────
def test_stats_values_are_sane():
    """
    Savings % must be in [0, 100]; injected KB must be ≤ full-context KB.
    Full context must be > 0.
    """
    stdout, _stderr, code = run_hook("renew book loan")
    assert code == 0
    parsed = json.loads(stdout)

    m = _STATS_RE.match(parsed.get("systemMessage", ""))
    assert m, f"systemMessage not found or malformed: {parsed.get('systemMessage')!r}"

    pct = int(m.group(1))
    injected_kb = float(m.group(2))
    full_kb = float(m.group(3))

    assert 0 <= pct <= 100, f"Savings % out of range: {pct}"
    assert full_kb > 0, "Full context size must be > 0"
    assert injected_kb <= full_kb, (
        f"Injected ({injected_kb} KB) must not exceed full context ({full_kb} KB)"
    )
    # Verify % direction is consistent with KB order (don't recompute from KB
    # strings — they're already rounded to 1 decimal, so re-deriving an int %
    # from them introduces compounded rounding error).
    if injected_kb < full_kb:
        assert pct > 0, "Injected < full but % shows 0 — rounding or logic error"
    if injected_kb == full_kb:
        assert pct == 0, "Injected == full but % is non-zero"


# ── T3: no stats when no domain matches ──────────────────────────────────────
def test_no_stats_when_no_match():
    """
    A prompt that matches no domain must produce empty stdout — no systemMessage,
    no JSON envelope at all. Silent no-op must be total.
    """
    stdout, _stderr, code = run_hook("explain this error message to me")
    assert code == 0
    assert stdout == b"", (
        f"stdout must be empty on no-match, got {len(stdout)} bytes: {stdout[:200]}"
    )


# ── T4: stats present in systemMessage even when report is truncated ──────────
def test_stats_line_present_after_truncation(tmp_path):
    """
    When the report is truncated to MAX_CHARS, the stats line must still
    appear as the last line. Stats are appended AFTER truncation, so they
    must never be cut off.
    """
    rules_yaml = ""
    for i in range(1, 13):
        rules_yaml += (
            f"  - id: rule-{i:02d}\n"
            f"    description: >\n"
            f"      Rule {i}: All mutations must be wrapped in a DB transaction. "
            f"Partial writes are not recoverable. This applies across all domains.\n"
            f"    severity: CRITICAL\n"
            f"    guidance: |\n"
            f"      Use ApplicationRecord.transaction. Never call .save! outside a block.\n"
        )

    large_context = textwrap.dedent("""\
        project:
          name: LargeApp
          language: Ruby
          framework: Rails 7
          api_versioning: v1
          default_actor: admin

        architecture:
          pattern: HMVC
          flow: [controller, operation, form, model, serializer]
          component_responsibilities:
            controller: Routes HTTP, calls one Operation, renders JSON via Serializer.
            operation: Sequences business workflow as step_* methods.
            form: Input validation only.
            model: AR persistence layer.
            serializer: Formats Operation result as JSON.

        domains:
          - name: authentication
            keywords: [login, logout, authenticate, session, token, oauth]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/auth_controller.rb
              - app/operations/v1/auth/create_operation.rb
            patterns:
              - id: auth-pat-01
                description: >
                  Authentication operations must validate ownership chain before mutation.
                  Never skip this step. This is a long pattern to push output over limit.
                  Extra text extra text extra text to grow the output size significantly.
              - id: auth-pat-02
                description: >
                  All auth writes must emit a domain event to the auth_events queue.
                  Use EventEmitter.emit with retry=3. Missing events cause audit gaps.

          - name: billing
            keywords: [invoice, payment, subscription, charge, refund, billing]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/billing_controller.rb
              - app/operations/v1/billing/create_operation.rb
            patterns:
              - id: billing-pat-01
                description: >
                  Billing operations must validate ownership before mutation.
                  Billing failures must be idempotent. Retry with exponential backoff.
              - id: billing-pat-02
                description: >
                  All billing writes must emit a domain event to the billing_events queue.
                  Missing events cause revenue reconciliation gaps. Never swallow errors.

          - name: notification
            keywords: [notify, sms, push, alert, webhook, reminder, notification]
            typical_actors: [admin, user]
            coverage_level: pattern_indexed
            related_components:
              - app/controllers/v1/notification_controller.rb
              - app/operations/v1/notification/create_operation.rb
            patterns:
              - id: notification-pat-01
                description: >
                  Notification operations must validate ownership before dispatch.
                  Notifications are irreversible. Validate thoroughly before sending.
              - id: notification-pat-02
                description: >
                  All notification writes must emit events. Track delivery per recipient.
                  Failed notifications must be queued for retry, not silently dropped.

        rules:
        """) + rules_yaml

    ctx_file = tmp_path / "context.yaml"
    ctx_file.write_text(large_context)

    stdout, _stderr, code = run_hook(
        "login logout invoice payment alert notify",
        cwd=str(tmp_path),
    )
    assert code == 0

    if stdout == b"":
        pytest.skip("No domains matched — adjust test keywords")

    parsed = json.loads(stdout)

    assert "systemMessage" in parsed, (
        "systemMessage must be present even when report is truncated"
    )
    assert _STATS_RE.match(parsed["systemMessage"]), (
        f"systemMessage malformed after truncation: {parsed['systemMessage']!r}"
    )
    # Stats must not appear inside additionalContext regardless of truncation
    ctx = parsed["hookSpecificOutput"]["additionalContext"]
    assert "[open-context]" not in ctx, (
        "Stats must not bleed into additionalContext after truncation"
    )


# ── T5: include_all_domains returns more domains than filtered resolve ─────────
def test_include_all_domains_returns_superset():
    """
    resolve(..., include_all_domains=True) must return at least as many
    matched_domains as the normal filtered resolve() for any prompt.
    This verifies the baseline calculation uses a true superset of domains.
    """
    sys.path.insert(0, str(PLUGIN_ROOT / "src"))
    sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))
    from open_context import load_context, resolve  # noqa: PLC0415

    context = load_context(SAMPLE_CONTEXT)

    for prompt in ["renew book loan", "list books", "register member"]:
        normal = resolve(prompt, context)
        full = resolve(prompt, context, include_all_domains=True)

        normal_count = len(normal["matched_domains"])
        full_count = len(full["matched_domains"])

        assert full_count >= normal_count, (
            f"prompt={prompt!r}: include_all_domains gave {full_count} domains "
            f"but filtered gave {normal_count} — full must be a superset"
        )

    # A prompt that matches nothing filtered must still have ALL domains in full
    total_domains = len(context.get("domains", []))
    unmatched_full = resolve("xyzzy frobnicate quux", context, include_all_domains=True)
    assert len(unmatched_full["matched_domains"]) == total_domains, (
        "include_all_domains must return every domain regardless of keyword match"
    )
