"""Tests pour src.core.audit — détecteurs d'anti-patterns Sprint LLL.

Chaque détecteur a son propre groupe de tests :
- happy path (zéro finding sur du code propre)
- détection (warning / error sur exemple positif)
- whitelist (`# audit: ignore <RULE>` skip le finding)
"""

from __future__ import annotations

from pathlib import Path

from src.core.audit import (
    AuditConfig,
    Finding,
    collect_paths,
    detect_hardcoded_prompts,
    detect_long_files,
    detect_opus_without_justification,
    detect_orphan_todos,
    detect_tests_without_assertions,
    run_audit,
    summarize_findings,
)

# ============================================================================
# Helpers
# ============================================================================


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ============================================================================
# FILE_TOO_LONG
# ============================================================================


def test_file_too_long_detects_above_threshold(tmp_path: Path) -> None:
    long = tmp_path / "long.py"
    long.write_text("\n".join(f"x = {i}" for i in range(600)), encoding="utf-8")
    findings = detect_long_files([long], max_lines=500)
    assert len(findings) == 1
    assert findings[0].rule == "FILE_TOO_LONG"
    assert findings[0].severity == "warning"


def test_file_too_long_skips_below_threshold(tmp_path: Path) -> None:
    short = tmp_path / "short.py"
    short.write_text("x = 1\n" * 300, encoding="utf-8")
    findings = detect_long_files([short], max_lines=500)
    assert findings == []


def test_file_too_long_respects_whitelist(tmp_path: Path) -> None:
    """Un commentaire `# audit: ignore FILE_TOO_LONG` n'importe où dans
    le fichier le marque comme exception consciente."""
    long = tmp_path / "long_intentional.py"
    body = "# audit: ignore FILE_TOO_LONG -- gros switch métier, split prévu Sprint XYZ\n"
    body += "\n".join(f"x = {i}" for i in range(600))
    long.write_text(body, encoding="utf-8")
    findings = detect_long_files([long], max_lines=500)
    assert findings == []


def test_file_too_long_skips_non_python(tmp_path: Path) -> None:
    long_md = tmp_path / "doc.md"
    long_md.write_text("\n".join("ligne" for _ in range(600)), encoding="utf-8")
    findings = detect_long_files([long_md], max_lines=500)
    assert findings == []


# ============================================================================
# TEST_NO_ASSERT
# ============================================================================


def test_test_no_assert_detects_empty_test(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "test_thing.py",
        "def test_does_nothing():\n    x = 1\n    y = 2\n",
    )
    findings = detect_tests_without_assertions([f])
    assert len(findings) == 1
    assert findings[0].rule == "TEST_NO_ASSERT"
    assert "test_does_nothing" in findings[0].snippet


def test_test_no_assert_accepts_assert(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "test_thing.py",
        "def test_ok():\n    assert 1 == 1\n",
    )
    assert detect_tests_without_assertions([f]) == []


def test_test_no_assert_accepts_pytest_raises(tmp_path: Path) -> None:
    """Un test qui utilise `with pytest.raises(...)` est valide même sans assert."""
    f = _write(
        tmp_path / "test_thing.py",
        (
            "import pytest\n"
            "def test_raises():\n"
            "    with pytest.raises(ValueError):\n"
            "        int('not a number')\n"
        ),
    )
    assert detect_tests_without_assertions([f]) == []


def test_test_no_assert_accepts_mock_assert_called(tmp_path: Path) -> None:
    """`mock.assert_called_once()` compte comme assertion."""
    f = _write(
        tmp_path / "test_thing.py",
        ("def test_mock():\n    m = create_mock()\n    do_thing(m)\n    m.assert_called_once()\n"),
    )
    assert detect_tests_without_assertions([f]) == []


def test_test_no_assert_respects_whitelist(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "test_thing.py",
        "def test_intentional():  # audit: ignore TEST_NO_ASSERT\n    pass\n",
    )
    assert detect_tests_without_assertions([f]) == []


def test_test_no_assert_skips_non_test_files(tmp_path: Path) -> None:
    """Une fonction `def test_x()` dans un fichier qui n'est pas un test
    (ex: src/fixtures.py) ne doit pas être taggée."""
    f = _write(
        tmp_path / "fixtures.py",
        "def test_helper():\n    return 42\n",
    )
    assert detect_tests_without_assertions([f]) == []


# ============================================================================
# ORPHAN_TODO
# ============================================================================


def test_orphan_todo_detects_bare_todo(tmp_path: Path) -> None:
    # audit: ignore ORPHAN_TODO -- fixture intentionnelle (TODO de test)
    todo_content = "# TODO refactor this later\nx = 1\n"
    f = _write(tmp_path / "module.py", todo_content)
    findings = detect_orphan_todos([f])
    assert len(findings) == 1
    assert findings[0].rule == "ORPHAN_TODO"


def test_orphan_todo_accepts_issue_reference(tmp_path: Path) -> None:
    f = _write(tmp_path / "module.py", "# TODO #42 refactor this later\nx = 1\n")
    assert detect_orphan_todos([f]) == []


def test_orphan_todo_accepts_sprint_reference(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "module.py",
        "# TODO Sprint XYZ : extract helper class\nx = 1\n",
    )
    assert detect_orphan_todos([f]) == []


def test_orphan_todo_accepts_adr_reference(tmp_path: Path) -> None:
    f = _write(tmp_path / "module.py", "# FIXME ADR-022 : bumper le seuil\nx = 1\n")
    assert detect_orphan_todos([f]) == []


def test_orphan_todo_accepts_owner_and_date(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "module.py",
        "# TODO @MikaelArth 2026-06-01 : décider de la stratégie\nx = 1\n",
    )
    assert detect_orphan_todos([f]) == []


def test_orphan_todo_respects_whitelist(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "module.py",
        "# TODO temporaire (debug)  # audit: ignore ORPHAN_TODO\nx = 1\n",
    )
    assert detect_orphan_todos([f]) == []


def test_orphan_todo_scans_markdown_too(tmp_path: Path) -> None:
    f = _write(tmp_path / "doc.md", "# TODO write more docs\n")  # audit: ignore ORPHAN_TODO
    assert len(detect_orphan_todos([f])) == 1


def test_orphan_todo_skips_unsupported_extension(tmp_path: Path) -> None:
    f = _write(tmp_path / "data.json", '{"todo": "TODO"}\n')
    assert detect_orphan_todos([f]) == []


# ============================================================================
# OPUS_WITHOUT_JUSTIFICATION
# ============================================================================


def test_opus_without_justification_detects_unjustified(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "agent.py",
        (
            "class MyAgent:\n"
            "    def __init__(self, s):\n"
            "        super().__init__(model=s.model_strategic)\n"  # audit: ignore OPUS_WITHOUT_JUSTIFICATION
        ),
    )
    findings = detect_opus_without_justification([f])
    assert len(findings) == 1
    assert findings[0].rule == "OPUS_WITHOUT_JUSTIFICATION"


def test_opus_without_justification_accepts_opus_comment(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "agent.py",
        (
            "class MyAgent:\n"
            "    def __init__(self, s):\n"
            "        super().__init__(\n"
            "            model=s.model_strategic,  # Opus : besoin de discernement\n"
            "        )\n"
        ),
    )
    assert detect_opus_without_justification([f]) == []


def test_opus_without_justification_accepts_sprint_eee_reference(tmp_path: Path) -> None:
    """Sprint EEE = la référence canon pour les choix de tier."""
    f = _write(
        tmp_path / "agent.py",
        (
            "# Sprint EEE — gardé en Opus pour le raisonnement architectural critique\n"
            "class MyAgent:\n"
            "    def __init__(self, s):\n"
            "        super().__init__(model=s.model_strategic)\n"
        ),
    )
    assert detect_opus_without_justification([f]) == []


def test_opus_without_justification_accepts_above_comment(tmp_path: Path) -> None:
    """Une justification dans la docstring de classe ou commentaire au-dessus
    devrait suffire (à ±3 lignes)."""
    f = _write(
        tmp_path / "agent.py",
        (
            "class MyAgent:\n"
            "    # Opus requis : jugement critique sur l'architecture\n"
            "    def __init__(self, s):\n"
            "        super().__init__(model=s.model_strategic)\n"
        ),
    )
    assert detect_opus_without_justification([f]) == []


def test_opus_without_justification_respects_whitelist(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "agent.py",
        (
            "class MyAgent:\n"
            "    def __init__(self, s):\n"
            "        super().__init__(model=s.model_strategic)  # audit: ignore OPUS_WITHOUT_JUSTIFICATION\n"
        ),
    )
    assert detect_opus_without_justification([f]) == []


# ============================================================================
# HARDCODED_PROMPT
# ============================================================================


def test_hardcoded_prompt_detects_long_string_with_indicators(tmp_path: Path) -> None:
    """Le prompt hardcodé doit avoir > 300 chars ET un marqueur 'Tu es' / 'You are'."""
    long_prompt_text = (
        "Tu es un expert en analyse de données. "
        "Tu produis des rapports structurés selon le format suivant : "
    ) + ("X" * 250)
    f = _write(
        tmp_path / "agent.py",
        f'PROMPT = """{long_prompt_text}"""\n',
    )
    findings = detect_hardcoded_prompts([f])
    assert len(findings) == 1
    assert findings[0].rule == "HARDCODED_PROMPT"


def test_hardcoded_prompt_skips_short_strings(tmp_path: Path) -> None:
    f = _write(
        tmp_path / "agent.py",
        'SHORT = """Tu es un agent."""\n',
    )
    assert detect_hardcoded_prompts([f]) == []


def test_hardcoded_prompt_skips_strings_without_indicators(tmp_path: Path) -> None:
    """Une longue string qui ne ressemble pas à un prompt n'est pas flaggée."""
    long_text = "X" * 500
    f = _write(
        tmp_path / "module.py",
        f'BIG_DATA = """{long_text}"""\n',
    )
    assert detect_hardcoded_prompts([f]) == []


def test_hardcoded_prompt_skips_test_files(tmp_path: Path) -> None:
    """Les tests peuvent contenir des canon hardcodés (Sprint OOO smoke tests)."""
    long_prompt = "Tu es un expert en analyse. " + ("Y" * 300)
    f = _write(
        tmp_path / "test_smoke.py",
        f'CANON = """{long_prompt}"""\n',
    )
    assert detect_hardcoded_prompts([f]) == []


def test_hardcoded_prompt_respects_whitelist(tmp_path: Path) -> None:
    long_prompt = "Tu es un expert. " + ("Z" * 300)
    f = _write(
        tmp_path / "agent.py",
        f'# audit: ignore HARDCODED_PROMPT\nPROMPT = """{long_prompt}"""\n',
    )
    assert detect_hardcoded_prompts([f]) == []


# ============================================================================
# Runner & config
# ============================================================================


def test_collect_paths_respects_include_dirs(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "a.py", "x = 1")
    _write(tmp_path / "scripts" / "b.py", "y = 2")
    _write(tmp_path / "node_modules" / "c.py", "z = 3")  # devrait être skip si exclu

    config = AuditConfig(include_dirs=["src", "scripts"], exclude_patterns=["__pycache__"])
    paths = collect_paths(tmp_path, config)
    paths_str = [str(p) for p in paths]
    assert any("src" in p and "a.py" in p for p in paths_str)
    assert any("scripts" in p and "b.py" in p for p in paths_str)
    assert not any("node_modules" in p for p in paths_str)


def test_collect_paths_excludes_pycache(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "real.py", "x = 1")
    _write(tmp_path / "src" / "__pycache__" / "real.cpython-312.pyc", "compiled")

    config = AuditConfig(include_dirs=["src"])
    paths = collect_paths(tmp_path, config)
    assert not any("__pycache__" in str(p) for p in paths)


def test_run_audit_aggregates_all_rules(tmp_path: Path) -> None:
    """Smoke : run_audit doit composer tous les détecteurs activés."""
    _write(
        tmp_path / "src" / "agent.py",
        "# TODO refactor\nx = " + ("1, " * 300),  # audit: ignore ORPHAN_TODO
    )
    _write(
        tmp_path / "tests" / "test_a.py",
        "def test_empty():\n    pass\n",  # TEST_NO_ASSERT
    )

    findings = run_audit(tmp_path)
    rules = {f.rule for f in findings}
    assert "ORPHAN_TODO" in rules
    assert "TEST_NO_ASSERT" in rules


def test_run_audit_disable_rule(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "agent.py",
        "# TODO refactor\nx = 1\n",  # audit: ignore ORPHAN_TODO
    )
    config = AuditConfig(rules_enabled={"ORPHAN_TODO": False})
    findings = run_audit(tmp_path, config)
    assert all(f.rule != "ORPHAN_TODO" for f in findings)


def test_summarize_findings_counts_correctly() -> None:
    findings = [
        Finding(rule="A", severity="warning", path=Path("x"), line=1, snippet="", message=""),
        Finding(rule="A", severity="warning", path=Path("y"), line=2, snippet="", message=""),
        Finding(rule="B", severity="info", path=Path("z"), line=3, snippet="", message=""),
    ]
    counts = summarize_findings(findings)
    assert counts == {"A": 2, "B": 1}


def test_summarize_findings_empty() -> None:
    assert summarize_findings([]) == {}
