"""
Unit tests for architecture_discovery.py (Phase 4b component-chain detection).

Two of these tests are direct regression guards for real bugs found while
running this module against qlear-v2-admin (ground truth, real Rails repo):

  - test_class_token_requires_actual_class_declaration: an ActiveAdmin
    resource file (`app/admin/company_domain.rb`, `ActiveAdmin.register
    CompanyDomain do ... end`) shares its exact basename with the real model
    it administers (`app/models/company_domain.rb`, `class CompanyDomain`).
    Trusting the filename alone produced a phantom operations->admin edge.

  - test_fan_out_is_not_silently_dropped: qlear-v2-admin's `operations`
    component calls both `forms` (weaker evidence) and `models` (stronger
    evidence) — a greedy single-path walk picked the stronger edge and
    silently dropped `forms` from the suggested flow entirely.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PLUGIN_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT / "vendor"))

from open_context.architecture_discovery import (  # noqa: E402
    assess_confidence,
    component_class_tokens,
    discover_architecture,
    discover_components,
    scan_call_evidence,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_discover_components_skips_non_code_dirs(tmp_path):
    app = tmp_path / "app"
    _write(app / "models" / "book.rb", "class Book < ApplicationRecord\nend\n")
    (app / "assets").mkdir(parents=True)
    (app / "assets" / "logo.png").write_text("")
    (app / "views").mkdir(parents=True)
    (app / "views" / "index.html.erb").write_text("")

    components, external = discover_components(app)
    assert set(components) == {"models"}
    assert external == set()


def test_discover_components_follows_symlink_but_flags_external(tmp_path):
    """Regression: qlear-v2-bot's own app/ has almost nothing but symlinked
    dirs into a shared/ submodule (models, jobs, mailers, ...). Excluding
    them entirely produced a near-empty, unhelpful result — they must still
    be scanned for real call-evidence, just flagged as not owned by this repo."""
    app = tmp_path / "app"
    _write(app / "controllers" / "widgets_controller.rb", "class WidgetsController\nend\n")
    shared_target = tmp_path / "shared_models"
    _write(shared_target / "book.rb", "class Book < ApplicationRecord\nend\n")
    (app / "models").symlink_to(shared_target)

    components, external = discover_components(app)
    assert set(components) == {"controllers", "models"}
    assert external == {"models"}


def test_class_token_requires_actual_class_declaration(tmp_path):
    """Regression: filename-only tokens caused a real false-positive edge on
    qlear-v2-admin (operations -> admin) via a company_domain.rb basename
    collision between an ActiveAdmin DSL file and the real model file."""
    app = tmp_path / "app"
    admin_file = _write(app / "admin" / "company_domain.rb", "ActiveAdmin.register CompanyDomain do\nend\n")
    model_file = _write(app / "models" / "company_domain.rb", "class CompanyDomain < ApplicationRecord\nend\n")

    admin_tokens = component_class_tokens([admin_file])
    model_tokens = component_class_tokens([model_file])

    assert admin_tokens == {}, "ActiveAdmin.register block must not be treated as a class declaration"
    assert model_tokens == {"CompanyDomain": model_file}


def test_call_evidence_detects_cross_component_reference(tmp_path):
    app = tmp_path / "app"
    op_file = _write(
        app / "operations" / "create_operation.rb",
        "class CreateOperation\n  def call\n    Book.create!(title: 'x')\n  end\nend\n",
    )
    model_file = _write(app / "models" / "book.rb", "class Book < ApplicationRecord\nend\n")

    components = {"operations": [op_file], "models": [model_file]}
    edges = scan_call_evidence(components)

    assert len(edges) == 1
    assert edges[0]["from"] == "operations"
    assert edges[0]["to"] == "models"
    assert edges[0]["matched_files"] == 1


def test_fan_out_is_not_silently_dropped(tmp_path):
    """Regression: a single-path greedy walk dropped a real, weaker-but-valid
    edge (operations -> forms) in favor of the strongest one (operations ->
    models) on qlear-v2-admin. Every connected component must survive into
    `suggested_flow`."""
    app = tmp_path / "app"
    _write(
        app / "admin" / "companies.rb",
        "ActiveAdmin.register Company do\nend\n",
    )
    _write(app / "controllers" / "widgets_controller.rb", "class WidgetsController\nend\n")
    op_file = _write(
        app / "operations" / "create_operation.rb",
        "class CreateOperation\n"
        "  def call\n"
        "    form = CreateForm.new(params)\n"  # strong-ish
        "    form.valid?\n"
        "    Book.create!(title: form.title)\n"  # stronger (more hits)
        "    Book.touch\n"
        "  end\n"
        "end\n",
    )
    _write(app / "forms" / "create_form.rb", "class CreateForm\nend\n")
    _write(app / "models" / "book.rb", "class Book < ApplicationRecord\nend\n")

    result = discover_architecture(tmp_path)
    assert "forms" in result["suggested_flow"], "fan-out target must not be silently dropped"
    assert "models" in result["suggested_flow"]
    assert result["cycle_detected"] == []


def test_cycle_is_reported_not_hidden(tmp_path):
    app = tmp_path / "app"
    _write(app / "a" / "thing_a.rb", "class ThingA\n  def call\n    ThingB.new.call\n  end\nend\n")
    _write(app / "b" / "thing_b.rb", "class ThingB\n  def call\n    ThingA.new.call\n  end\nend\n")

    result = discover_architecture(tmp_path)
    assert set(result["cycle_detected"]) == {"a", "b"}
    # still present in the flow, not dropped just because they're cyclic
    assert set(result["suggested_flow"]) == {"a", "b"}


def test_rails_implicit_validator_shorthand_detected(tmp_path):
    """Regression: `validates :field, key: true` never mentions the validator
    class literally — the plain `<Token>.<method>` pattern can't see it, so
    every custom Rails validator looked "unconnected" on qlear-v2-admin
    despite being used extensively by forms/."""
    app = tmp_path / "app"
    _write(
        app / "forms" / "signup_form.rb",
        "class SignupForm\n  validates :phone_number, presence: true, phone_number: true\nend\n",
    )
    _write(
        app / "validators" / "phone_number_validator.rb",
        "class PhoneNumberValidator < ActiveModel::EachValidator\nend\n",
    )

    result = discover_architecture(tmp_path)
    assert any(e["from"] == "forms" and e["to"] == "validators" for e in result["edges"])


def test_no_app_dir_reports_note_not_crash(tmp_path):
    result = discover_architecture(tmp_path)
    assert result["components"] == {}
    assert "note" in result


def test_assess_confidence_no_edges_means_dont_propose():
    assessment = assess_confidence({"edges": [], "cycle_detected": []})
    assert assessment["propose"] is False
    assert assessment["reasons"]


def test_assess_confidence_clean_graph_proposes(tmp_path):
    """Regression: a hand-verified-correct, cycle-free result (qlear-v2-admin
    shape) must clear the propose gate — this is the ground-truth case the
    red-flag design exists to get right, unlike the blended-score attempts
    that landed ~69% on this exact shape of evidence."""
    app = tmp_path / "app"
    _write(app / "admin" / "companies.rb", "class Companies\n  def index\n    CreateOperation.new.call\n  end\nend\n")
    _write(app / "operations" / "create_operation.rb", "class CreateOperation\n  def call\n    Book.create!\n  end\nend\n")
    _write(app / "models" / "book.rb", "class Book < ApplicationRecord\nend\n")

    result = discover_architecture(tmp_path)
    assessment = assess_confidence(result)
    assert assessment["propose"] is True
    assert assessment["reasons"] == []


def test_assess_confidence_majority_cycle_blocks_propose():
    """qlear-v2-bot shape: most of the connected components are stuck in a
    cycle (batches/jobs/models) — must not propose a linear flow."""
    assessment = assess_confidence({
        "edges": [
            {"from": "a", "to": "b", "confidence": 0.5},
            {"from": "b", "to": "a", "confidence": 0.5},
            {"from": "b", "to": "c", "confidence": 0.5},
        ],
        "cycle_detected": ["a", "b"],
    })
    assert assessment["propose"] is False
    assert "cycle" in assessment["reasons"][0]
