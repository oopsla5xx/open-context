"""
Unit tests for discovery.py (Phase 4a stack detection).

Direct-import unit tests, not subprocess integration tests like
test_hook_integration.py — discovery.py is a plain deterministic module
with no hook/CLI-boundary concerns to exercise as a subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PLUGIN_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))

from open_context.discovery import (  # noqa: E402
    detect,
    detect_go,
    detect_java,
    detect_node,
    detect_python,
    detect_ruby,
    detect_rust,
)


def test_no_manifest_returns_none(tmp_path):
    assert detect_ruby(tmp_path) is None
    assert detect_node(tmp_path) is None
    assert detect_python(tmp_path) is None
    assert detect_go(tmp_path) is None
    assert detect_rust(tmp_path) is None
    assert detect_java(tmp_path) is None
    result = detect(tmp_path)
    assert result["ecosystems"] == []


def test_ruby_rails_happy_path(tmp_path):
    (tmp_path / "Gemfile").write_text(
        "ruby '3.2.1'\n"
        "gem 'rails', '7.0.4.2'\n"
        "gem 'pg', '1.4.5'\n"
        "gem 'rspec-rails'\n"
    )
    (tmp_path / "Gemfile.lock").write_text("")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.yml").write_text("default:\n  adapter: postgresql\n")
    (tmp_path / "spec").mkdir()
    (tmp_path / ".rspec").write_text("--require spec_helper\n")

    result = detect_ruby(tmp_path)
    fields = result["fields"]
    assert fields["language"]["value"] == "Ruby"
    assert fields["language_version"]["value"] == "3.2.1"
    assert fields["framework"]["value"] == "Rails"
    assert fields["framework_version"]["value"] == "7.0.4.2"
    assert fields["package_manager"]["value"] == "Bundler"
    assert fields["database"]["value"] == "PostgreSQL"
    assert fields["orm"]["value"] == "ActiveRecord"
    assert fields["test_framework"]["value"] == "RSpec"
    # structured-file fields must be high confidence, not blended with prose-derived ones
    assert fields["language_version"]["confidence"] >= 0.9


def test_ruby_secondary_mongoid_database_detected(tmp_path):
    """Regression guard: a Rails app can wire in Mongoid alongside ActiveRecord
    (e.g. qlear-v2-bot in production) — this must not be silently dropped just
    because config/database.yml only describes the primary relational DB."""
    (tmp_path / "Gemfile").write_text(
        "ruby '3.2.1'\ngem 'rails', '7.0.4.2'\ngem 'mongoid', '7.5.2'\n"
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.yml").write_text("default:\n  adapter: postgresql\n")
    (tmp_path / "config" / "mongoid.yml").write_text("development:\n  clients:\n    default: {}\n")

    fields = detect_ruby(tmp_path)["fields"]
    assert fields["database"]["value"] == "PostgreSQL"
    assert fields["orm"]["value"] == "ActiveRecord"
    assert fields["database_secondary"]["value"] == "MongoDB"
    assert fields["orm_secondary"]["value"] == "Mongoid"


def test_ruby_database_version_from_prose_is_lower_confidence(tmp_path):
    (tmp_path / "Gemfile").write_text("ruby '3.2.1'\ngem 'rails', '7.0.4.2'\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "database.yml").write_text("default:\n  adapter: postgresql\n")
    (tmp_path / "CLAUDE.md").write_text("## Stack\nRuby 3.2.1 · Rails 7.0 · PostgreSQL 13.4\n")

    fields = detect_ruby(tmp_path)["fields"]
    assert fields["database_version"]["value"] == "13.4"
    assert fields["database_version"]["confidence"] < fields["database"]["confidence"]
    assert "prose" in fields["database_version"]["source"]


def test_node_nextjs_happy_path(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"next": "^16.2.2", "typescript": "^5.9.2"}, '
        '"devDependencies": {"jest": "^29.0.0"}}'
    )
    (tmp_path / "package-lock.json").write_text("{}")

    fields = detect_node(tmp_path)["fields"]
    assert fields["framework"]["value"] == "Next.js"
    assert fields["framework_version"]["value"] == "16.2.2"
    assert fields["package_manager"]["value"] == "npm"
    assert fields["test_framework"]["value"] == "Jest"
    assert fields["language"]["value"] == "TypeScript"


def test_node_no_lockfile_lowers_package_manager_confidence(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"}}')

    fields = detect_node(tmp_path)["fields"]
    assert fields["package_manager"]["value"] == "npm"
    assert fields["package_manager"]["confidence"] <= 0.5


def test_node_invalid_json_reports_error_not_crash(tmp_path):
    (tmp_path / "package.json").write_text("{not valid json")

    result = detect_node(tmp_path)
    assert result["error"]


def test_python_fastapi_happy_path(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n'
        'dependencies = ["fastapi", "sqlalchemy", "pytest"]\n'
    )

    fields = detect_python(tmp_path)["fields"]
    assert fields["language_version"]["value"] == ">=3.11"
    assert fields["framework"]["value"] == "FastAPI"
    assert fields["orm"]["value"] == "SQLAlchemy"
    assert fields["test_framework"]["value"] == "pytest"
    assert "_source_conflict_note" not in fields


def test_python_conflicting_sources_flagged(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\ndependencies = ["fastapi"]\n'
    )
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\nsqlalchemy==2.0.0\n")

    fields = detect_python(tmp_path)["fields"]
    assert "_source_conflict_note" in fields
    # union of both sources still used for presence detection
    assert fields["orm"]["value"] == "SQLAlchemy"


def test_multi_ecosystem_reported_independently_no_merge(tmp_path):
    (tmp_path / "Gemfile").write_text("ruby '3.2.1'\ngem 'rails', '7.0.4.2'\n")
    (tmp_path / "package.json").write_text('{"dependencies": {}}')

    result = detect(tmp_path)
    ecosystems = {e["ecosystem"] for e in result["ecosystems"]}
    assert ecosystems == {"ruby", "node"}


def test_detect_is_non_recursive(tmp_path):
    """A manifest one level down must NOT be picked up by a scan of the parent —
    this is the load-bearing assumption behind the monorepo per-subdirectory
    workflow (--repo <subdir> run once per ecosystem)."""
    nested = tmp_path / "backend"
    nested.mkdir()
    (nested / "requirements.txt").write_text("fastapi\n")

    assert detect(tmp_path)["ecosystems"] == []
    assert detect(nested)["ecosystems"][0]["ecosystem"] == "python"


def test_go_gin_happy_path(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module github.com/example/api\n\n"
        "go 1.21\n\n"
        "require (\n"
        "\tgithub.com/gin-gonic/gin v1.9.1\n"
        ")\n"
    )
    (tmp_path / "go.sum").write_text("")

    fields = detect_go(tmp_path)["fields"]
    assert fields["language"]["value"] == "Go"
    assert fields["language_version"]["value"] == "1.21"
    assert fields["framework"]["value"] == "Gin"
    assert fields["framework_version"]["value"] == "1.9.1"
    assert fields["package_manager"]["value"] == "Go Modules"
    assert fields["package_manager"]["confidence"] == 0.95


def test_go_no_framework_still_detects_language(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/tool\n\ngo 1.20\n")

    fields = detect_go(tmp_path)["fields"]
    assert fields["language"]["value"] == "Go"
    assert "framework" not in fields
    assert fields["package_manager"]["confidence"] == 0.7


def test_rust_axum_happy_path(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "api"\nversion = "0.1.0"\nrust-version = "1.75"\n\n'
        '[dependencies]\naxum = "0.7"\ntokio = { version = "1", features = ["full"] }\n'
    )
    (tmp_path / "Cargo.lock").write_text("")

    fields = detect_rust(tmp_path)["fields"]
    assert fields["language"]["value"] == "Rust"
    assert fields["language_version"]["value"] == "1.75"
    assert fields["framework"]["value"] == "Axum"
    assert fields["framework_version"]["value"] == "0.7"
    assert fields["package_manager"]["value"] == "Cargo"
    assert fields["package_manager"]["confidence"] == 0.95


def test_java_maven_spring_boot_happy_path(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n"
        "  <properties><java.version>17</java.version></properties>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>org.springframework.boot</groupId>\n"
        "      <artifactId>spring-boot-starter-web</artifactId>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n"
    )

    fields = detect_java(tmp_path)["fields"]
    assert fields["language"]["value"] == "Java"
    assert fields["language_version"]["value"] == "17"
    assert fields["framework"]["value"] == "Spring Boot"
    assert fields["package_manager"]["value"] == "Maven"


def test_java_gradle_kotlin_ktor_happy_path(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        'plugins {\n    kotlin("jvm") version "1.9.0"\n}\n\n'
        'dependencies {\n    implementation("io.ktor:ktor-server-core:2.3.0")\n}\n'
    )

    fields = detect_java(tmp_path)["fields"]
    assert fields["language"]["value"] == "Kotlin"
    assert fields["framework"]["value"] == "Ktor"
    assert fields["package_manager"]["value"] == "Gradle"


def test_java_maven_preferred_over_gradle_when_both_present(tmp_path):
    (tmp_path / "pom.xml").write_text("<project></project>\n")
    (tmp_path / "build.gradle").write_text("dependencies {}\n")

    result = detect_java(tmp_path)
    assert result["fields"]["package_manager"]["value"] == "Maven"
