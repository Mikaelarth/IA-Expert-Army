"""Audit codebase — détecteurs d'anti-patterns spécifiques à IA-Expert-Army.

Sprint LLL — garde-fou défensif contre la dérive architecturale.

Cible 5 anti-patterns réels observés sur des projets jeunes qui croissent vite,
ou qui peuvent être introduits par un agent IA qui code sans connaître la
politique du repo :

1. **FILE_TOO_LONG** — fichier source > 500 lignes (signal qu'on doit split)
2. **TEST_NO_ASSERT** — fonctions test_* sans aucune assertion (test bidon)
3. **ORPHAN_TODO** — marqueurs de dette sans référence Sprint/ADR/issue
4. **OPUS_WITHOUT_JUSTIFICATION** — agent qui utilise model_strategic sans
   commentaire `# Opus :` à proximité (politique ADR-016)
5. **HARDCODED_PROMPT** — string > 300 chars qui ressemble à un system prompt
   et qui n'est pas chargée depuis prompts/

Chaque détecteur :
- Renvoie une liste de Finding (path, line, snippet, message)
- Est testable indépendamment via unit tests
- Peut être whitelisté via commentaire `# audit: ignore <RULE>` à la ligne

Le script CLI `scripts/audit_codebase.py` invoque les détecteurs et formatte
le rapport. À brancher en pre-commit ou step CI séparé.
"""  # audit: ignore ORPHAN_TODO

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["info", "warning", "error"]


@dataclass
class Finding:
    """Un anti-pattern détecté."""

    rule: str
    severity: Severity
    path: Path
    line: int  # 1-based ; 0 = whole file
    snippet: str
    message: str


# ============================================================================
# Whitelisting via commentaire inline `# audit: ignore <RULE>`
# ============================================================================

_IGNORE_RE = re.compile(r"#\s*audit:\s*ignore\s+(\w+)", re.IGNORECASE)


def _is_ignored(line: str, rule: str) -> bool:
    """True si la ligne contient `# audit: ignore <rule>` (insensible à la casse)."""
    match = _IGNORE_RE.search(line)
    if match is None:
        return False
    return match.group(1).upper() == rule.upper()


# ============================================================================
# Rule FILE_TOO_LONG — fichier > 500 lignes
# ============================================================================

DEFAULT_MAX_LINES = 500


def detect_long_files(paths: list[Path], max_lines: int = DEFAULT_MAX_LINES) -> list[Finding]:
    """Signale les fichiers > max_lines.

    Whitelist : un commentaire `# audit: ignore FILE_TOO_LONG` n'importe où dans
    le fichier suffit à le marquer comme exception consciente.
    """
    findings: list[Finding] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        if len(lines) <= max_lines:
            continue
        # Whitelist scan
        if any(_is_ignored(line, "FILE_TOO_LONG") for line in lines):
            continue
        findings.append(
            Finding(
                rule="FILE_TOO_LONG",
                severity="warning",
                path=path,
                line=0,
                snippet=f"{len(lines)} lignes",
                message=(
                    f"Fichier > {max_lines} lignes ({len(lines)}). Envisage un split "
                    f"par responsabilité ou ajoute `# audit: ignore FILE_TOO_LONG` "
                    f"avec justification."
                ),
            )
        )
    return findings


# ============================================================================
# Rule TEST_NO_ASSERT — fonction test sans assertion
# ============================================================================
# Implémentation via ast.parse() : robuste, correcte, et capture toutes les
# subtilités (decorators, async, nested functions, with-statements).


def _function_contains_assertion(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Vrai si l'AST de la fonction contient au moins un signe d'assertion :
    - `assert ...`
    - `with pytest.raises(...):`
    - `mock.assert_called*()` / `mock.assert_*()`
    - `pytest.fail(...)` / `pytest.fixture` (decorator d'un autre test)
    """
    for sub in ast.walk(func_node):
        # `assert ...`
        if isinstance(sub, ast.Assert):
            return True
        # `with pytest.raises(...)` ou `with pytest.warns(...)`
        if isinstance(sub, ast.With):
            for item in sub.items:
                ce = item.context_expr
                if isinstance(ce, ast.Call):
                    func_attr = _get_attr_chain(ce.func)
                    if func_attr in {"pytest.raises", "pytest.warns", "pytest.deprecated_call"}:
                        return True
        # `obj.assert_called_once()`, `mock.assert_called_with(...)`, etc.
        if isinstance(sub, ast.Call):
            func_attr = _get_attr_chain(sub.func)
            if func_attr and (
                func_attr.startswith("pytest.fail")
                or func_attr.startswith("pytest.skip")
                or ".assert_" in func_attr
            ):
                return True
    return False


def _get_attr_chain(node: ast.AST) -> str:
    """Reconstruit `a.b.c` depuis un Attribute node ; renvoie '' si pas une chaîne d'attrs."""
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    elif current is not None:
        return ""
    return ".".join(reversed(parts))


def detect_tests_without_assertions(paths: list[Path]) -> list[Finding]:
    """Signale les `def test_*():` qui ne contiennent aucun assert / pytest helper.

    Implémentation AST :
      - Parse le fichier en arbre syntaxique
      - Pour chaque FunctionDef / AsyncFunctionDef nommée test_*
      - Walk dans son corps, cherche : assert, with pytest.raises,
        mock.assert_*, pytest.fail/skip
      - Si rien trouvé → finding

    Whitelist : `# audit: ignore TEST_NO_ASSERT` sur la ligne du def.
    """
    findings: list[Finding] = []
    for path in paths:
        if path.suffix != ".py" or "test" not in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        lines = text.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            line_no = node.lineno  # 1-based
            # Vérifie le tag d'ignore sur la ligne du def
            if line_no - 1 < len(lines) and _is_ignored(lines[line_no - 1], "TEST_NO_ASSERT"):
                continue
            if _function_contains_assertion(node):
                continue
            findings.append(
                Finding(
                    rule="TEST_NO_ASSERT",
                    severity="warning",
                    path=path,
                    line=line_no,
                    snippet=f"def {node.name}",
                    message=(
                        f"Fonction de test `{node.name}` sans assert / "
                        f"pytest.raises / mock.assert_*. Ajoute une assertion ou "
                        f"supprime le test (un test sans assertion ne valide RIEN)."
                    ),
                )
            )
    return findings


# ============================================================================
# Rule ORPHAN_TODO — TODO/FIXME sans référence
# ============================================================================

_TODO_RE = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\b\s*[:.]?\s*(.*)", re.IGNORECASE)
# Référence acceptable : #123 (issue), Sprint XXX, ADR-NNN, @username, owner:
_REFERENCE_RE = re.compile(
    r"(?:"
    r"#\d+"  # GitHub issue
    r"|sprint\s+[A-Z]{2,4}"  # Sprint XYZ
    r"|adr-\d+"  # ADR-NNN
    r"|@\w+"  # @user
    r"|owner\s*[:=]"  # owner: foo
    r"|\d{4}-\d{2}-\d{2}"  # date YYYY-MM-DD (deadline)
    r")",
    re.IGNORECASE,
)


def detect_orphan_todos(paths: list[Path]) -> list[Finding]:
    """Signale les TODO/FIXME sans référence (ticket, sprint, ADR, owner, date).

    Un TODO orphelin = dette non tracée = oubli garanti. La règle force à
    transformer chaque TODO en dette explicite (ex: `# TODO Sprint XXX:` ou
    `# TODO @MikaelArth 2026-06-01:`)."""
    findings: list[Finding] = []
    for path in paths:
        if path.suffix not in {".py", ".md", ".sh", ".yml", ".yaml", ".toml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        all_lines = text.splitlines()
        for line_no, line in enumerate(all_lines, start=1):
            # Sprint QQQ : whitelist tolérante ±2 lignes (les formatters ruff
            # peuvent déplacer un commentaire `# audit: ignore` d'une ligne).
            if _is_ignored(line, "ORPHAN_TODO"):
                continue
            window_start = max(0, line_no - 3)  # -3 pour ±2 lignes (0-based)
            window_end = min(len(all_lines), line_no + 2)
            if any(
                _is_ignored(all_lines[i], "ORPHAN_TODO") for i in range(window_start, window_end)
            ):
                continue
            todo_match = _TODO_RE.search(line)
            if not todo_match:
                continue
            kind = todo_match.group(1).upper()
            content = todo_match.group(2).strip()
            if _REFERENCE_RE.search(content):
                continue  # a une référence : OK
            findings.append(
                Finding(
                    rule="ORPHAN_TODO",
                    severity="info",
                    path=path,
                    line=line_no,
                    snippet=line.strip()[:100],
                    message=(
                        f"{kind} sans référence (issue #N, Sprint XXX, ADR-NNN, "
                        f"@user, date YYYY-MM-DD). Ajoute une référence ou utilise "
                        f"`# audit: ignore ORPHAN_TODO` si volontaire."
                    ),
                )
            )
    return findings


# ============================================================================
# Rule OPUS_WITHOUT_JUSTIFICATION — model_strategic sans commentaire à proximité
# ============================================================================

_OPUS_USAGE_RE = re.compile(r"model\s*=\s*[a-zA-Z_]\w*\.model_strategic")
# Justification = commentaire `# Opus :` ou `# Sprint EEE :` à ±3 lignes
_JUSTIFICATION_RE = re.compile(r"#.*(opus|jugement|critique|sprint\s+EEE)", re.IGNORECASE)


def detect_opus_without_justification(paths: list[Path]) -> list[Finding]:
    """Signale les agents qui utilisent model_strategic (Opus) sans commentaire
    de justification à ±3 lignes.

    Politique ADR-016 : tier mixing = chaque agent Opus doit être conscient.
    Force le développeur (humain ou IA) à justifier explicitement le coût ~5x."""
    findings: list[Finding] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            if _is_ignored(line, "OPUS_WITHOUT_JUSTIFICATION"):
                continue
            if not _OPUS_USAGE_RE.search(line):
                continue
            # Vérifie ±3 lignes pour une justification
            window_start = max(0, line_no - 4)  # -4 car on indexe sur 0 dans lines
            window_end = min(len(lines), line_no + 3)
            window = "\n".join(lines[window_start:window_end])
            if _JUSTIFICATION_RE.search(window):
                continue
            findings.append(
                Finding(
                    rule="OPUS_WITHOUT_JUSTIFICATION",
                    severity="warning",
                    path=path,
                    line=line_no,
                    snippet=line.strip()[:120],
                    message=(
                        "Agent utilise `model_strategic` (Opus, ~5× plus cher) sans "
                        "commentaire de justification à ±3 lignes (cherchait "
                        "'Opus' / 'jugement' / 'critique' / 'Sprint EEE'). "
                        "Politique ADR-016 : chaque Opus doit être documenté."
                    ),
                )
            )
    return findings


# ============================================================================
# Rule HARDCODED_PROMPT — string longue ressemblant à un prompt système
# ============================================================================

# Heuristique : string multi-ligne > 300 chars, hors module test, qui contient
# un marqueur typique de prompt système.
_PROMPT_INDICATORS = (
    "tu es ",
    "you are ",
    "ton rôle",
    "your role",
    "## rôle",
    "## role",
    "system prompt",
    "tu produis",
    "you must produce",
)


def detect_hardcoded_prompts(paths: list[Path]) -> list[Finding]:
    """Signale les strings python > 300 chars qui ressemblent à un system prompt.

    Politique : tous les prompts d'agent doivent vivre dans `prompts/**/*.md`
    (versionnés, lisibles diff). Un prompt hardcodé en string Python =
    impossible à diff cleanly + risque de drift entre versions.

    Implémentation AST : on examine UNIQUEMENT les `Assign` avec une str
    literal en value. Évite les faux positifs sur :
    - docstrings de modules (Module.body[0] = Expr(Constant(str)))
    - docstrings de fonctions/classes (FunctionDef/ClassDef.body[0] idem)
    - paramètres `description="..."` dans les decorators typer (Call args)
    """
    findings: list[Finding] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        # Skip les tests : un canon hardcodé y est légitime (Sprint OOO)
        if "test" in path.name or "/tests/" in str(path).replace("\\", "/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        lines = text.splitlines()

        for node in ast.walk(tree):
            # Cible : `VAR = "..."` au top-level ou dans une classe
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            content = value.value
            if len(content) < 300:
                continue
            content_lower = content.lower()
            if not any(indicator in content_lower for indicator in _PROMPT_INDICATORS):
                continue
            line_no = node.lineno
            # Whitelist : tag sur la ligne ou la ligne au-dessus
            if line_no - 1 < len(lines) and _is_ignored(lines[line_no - 1], "HARDCODED_PROMPT"):
                continue
            if line_no >= 2 and _is_ignored(lines[line_no - 2], "HARDCODED_PROMPT"):
                continue
            findings.append(
                Finding(
                    rule="HARDCODED_PROMPT",
                    severity="warning",
                    path=path,
                    line=line_no,
                    snippet=content[:80].replace("\n", " ") + "…",
                    message=(
                        "String multi-ligne > 300 chars assignée à une variable "
                        "et contenant des marqueurs de system prompt ('Tu es', "
                        "'You are', etc.). Les prompts d'agent doivent vivre "
                        "dans `prompts/**/*.md` (versionnés, diffables). "
                        "Si volontaire, ajoute `# audit: ignore HARDCODED_PROMPT`."
                    ),
                )
            )
    return findings


# ============================================================================
# Runner principal
# ============================================================================


@dataclass
class AuditConfig:
    """Configuration de l'audit. Permet d'activer/désactiver des règles."""

    rules_enabled: dict[str, bool] = field(
        default_factory=lambda: {
            "FILE_TOO_LONG": True,
            "TEST_NO_ASSERT": True,
            "ORPHAN_TODO": True,
            # Désactivée par défaut depuis la bascule Ollama (ADR-025) : il
            # n'y a plus de tier payant à protéger contre l'escalade silencieuse
            # vers Opus. Réactiver explicitement si tu remets un backend cloud
            # avec tarification par token.
            "OPUS_WITHOUT_JUSTIFICATION": False,
            "HARDCODED_PROMPT": True,
        }
    )
    max_file_lines: int = DEFAULT_MAX_LINES
    # Paths à scanner (par défaut : src/, scripts/, tests/, prompts/)
    include_dirs: list[str] = field(default_factory=lambda: ["src", "scripts", "tests"])
    # Paths à exclure systématiquement
    exclude_patterns: list[str] = field(
        default_factory=lambda: [
            "__pycache__",
            ".pytest_cache",
            ".venv",
            ".mypy_cache",
            ".ruff_cache",
            "build",
            "dist",
        ]
    )


def collect_paths(root: Path, config: AuditConfig) -> list[Path]:
    """Recense tous les fichiers à scanner depuis la racine."""
    paths: list[Path] = []
    for include_dir in config.include_dirs:
        full_dir = root / include_dir
        if not full_dir.exists():
            continue
        for path in full_dir.rglob("*"):
            if not path.is_file():
                continue
            # Skip les patterns exclus
            path_str = str(path).replace("\\", "/")
            if any(excluded in path_str for excluded in config.exclude_patterns):
                continue
            paths.append(path)
    return paths


def run_audit(root: Path, config: AuditConfig | None = None) -> list[Finding]:
    """Lance tous les détecteurs activés sur la racine donnée."""
    cfg = config or AuditConfig()
    paths = collect_paths(root, cfg)
    findings: list[Finding] = []

    if cfg.rules_enabled.get("FILE_TOO_LONG"):
        findings.extend(detect_long_files(paths, max_lines=cfg.max_file_lines))
    if cfg.rules_enabled.get("TEST_NO_ASSERT"):
        findings.extend(detect_tests_without_assertions(paths))
    if cfg.rules_enabled.get("ORPHAN_TODO"):
        findings.extend(detect_orphan_todos(paths))
    if cfg.rules_enabled.get("OPUS_WITHOUT_JUSTIFICATION"):
        findings.extend(detect_opus_without_justification(paths))
    if cfg.rules_enabled.get("HARDCODED_PROMPT"):
        findings.extend(detect_hardcoded_prompts(paths))

    # Tri stable : path puis line
    findings.sort(key=lambda f: (str(f.path), f.line, f.rule))
    return findings


def summarize_findings(findings: list[Finding]) -> dict[str, int]:
    """Compte par règle. Utile pour les exit codes / résumés CI."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.rule] = counts.get(f.rule, 0) + 1
    return counts
