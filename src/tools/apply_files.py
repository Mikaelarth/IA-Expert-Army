"""apply_files — écriture sécurisée sur disque des fichiers produits par un agent.

Politique de sécurité (Phase 1.5, sera renforcée en Phase 3 avec sandbox Docker) :
- Le chemin doit être relatif (pas d'absolu, pas de `..`)
- Le chemin résolu doit rester INSIDE `project_root`
- Le chemin doit pointer vers un dossier whitelisté
- Pas d'overwrite par défaut (passer `force=True` pour autoriser)
- Les noms de fichiers contenant des caractères suspects (espaces, parens) sont rejetés
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class ApplyAction(StrEnum):
    WRITTEN = "written"
    SKIPPED_EXISTS = "skipped_exists"
    REJECTED_PATH = "rejected_path"
    REJECTED_NAME = "rejected_name"
    REJECTED_OUTSIDE = "rejected_outside"
    REJECTED_DIR = "rejected_directory_not_allowed"


class ApplyResult(BaseModel):
    path: str
    absolute_path: str | None
    action: ApplyAction
    reason: str = ""
    bytes_written: int = 0


# Dossiers où les agents Phase 1 sont autorisés à écrire
DEFAULT_ALLOWED_DIRS: tuple[str, ...] = (
    "src",
    "tests",
    "scripts",
    "docs",
    "prompts",
    "skills",
)

# Caractères interdits dans un chemin de fichier de production
_BAD_CHARS = re.compile(r"[(){}<>|*?\"'`]| à | ou | et |sectionn?")
_PATH_TRAVERSAL = re.compile(r"(^|/|\\)\.\.(/|\\|$)")


def apply_files(
    files: list[dict[str, str]],
    project_root: Path,
    allowed_dirs: tuple[str, ...] = DEFAULT_ALLOWED_DIRS,
    force: bool = False,
    approval_store: object | None = None,  # ApprovalStore | None — duck-typed
) -> list[ApplyResult]:
    """Écrit les fichiers sur disque selon la politique de sécurité.

    Retourne un résultat par fichier (succès ou raison du rejet).
    N'arrête JAMAIS à la première erreur — tous les fichiers sont évalués indépendamment.

    v0.7.0 — HITL audit trail (L1) :
    Si `approval_store` est fourni ET `force=True`, chaque overwrite d'un
    fichier existant déclenche un `request_approval` (event_type=
    "file_overwrite"). Par défaut non-bloquant : la trace est posée mais
    l'overwrite proceed. Configurable via `data/approvals/policy.yml`
    (auto_approve sur paths_regex pour éviter de polluer la queue).
    """
    results: list[ApplyResult] = []
    project_root = project_root.resolve()
    allowed = set(allowed_dirs)

    for entry in files:
        raw_path = entry.get("path", "").strip()
        content = entry.get("content", "")

        # Validation du nom
        if not raw_path or _BAD_CHARS.search(raw_path):
            results.append(
                ApplyResult(
                    path=raw_path,
                    absolute_path=None,
                    action=ApplyAction.REJECTED_NAME,
                    reason="Nom de fichier suspect (caractères interdits)",
                )
            )
            continue

        # Pas de path absolu, pas de path traversal
        if Path(raw_path).is_absolute() or _PATH_TRAVERSAL.search(raw_path):
            results.append(
                ApplyResult(
                    path=raw_path,
                    absolute_path=None,
                    action=ApplyAction.REJECTED_PATH,
                    reason="Path absolu ou traversal interdit",
                )
            )
            continue

        # Résolution + vérification que ça reste DANS project_root
        candidate = (project_root / raw_path).resolve()
        try:
            candidate.relative_to(project_root)
        except ValueError:
            results.append(
                ApplyResult(
                    path=raw_path,
                    absolute_path=str(candidate),
                    action=ApplyAction.REJECTED_OUTSIDE,
                    reason="Chemin résolu hors du project root",
                )
            )
            continue

        # Whitelist de dossiers : la première composante doit être autorisée
        relative = candidate.relative_to(project_root)
        first_component = relative.parts[0] if relative.parts else ""
        if first_component not in allowed:
            results.append(
                ApplyResult(
                    path=raw_path,
                    absolute_path=str(candidate),
                    action=ApplyAction.REJECTED_DIR,
                    reason=f"Dossier '{first_component}' non whitelisté (autorisés : {sorted(allowed)})",
                )
            )
            continue

        # Pas d'overwrite sauf force
        if candidate.exists() and not force:
            results.append(
                ApplyResult(
                    path=raw_path,
                    absolute_path=str(candidate),
                    action=ApplyAction.SKIPPED_EXISTS,
                    reason="Fichier déjà présent (utiliser --force pour overwrite)",
                )
            )
            continue

        # v0.7.0 L1 — HITL audit trail : si force=True et fichier existant et
        # approval_store fourni, on pose une demande d'approbation
        # (non-bloquante par défaut, traçabilité). La policy peut auto-approve
        # ou refuser (raises ApprovalRequired qu'on catche pour SKIP).
        if force and candidate.exists() and approval_store is not None:
            try:
                from src.core.approvals import ApprovalRequired, request_approval

                request_approval(
                    store=approval_store,  # type: ignore[arg-type]
                    event_type="file_overwrite",
                    context={
                        "path": raw_path,
                        "absolute_path": str(candidate),
                        "size_before": candidate.stat().st_size,
                        "size_after": len(content.encode("utf-8")),
                    },
                    requested_by="apply_files",
                    blocking=False,
                )
            except ApprovalRequired:
                results.append(
                    ApplyResult(
                        path=raw_path,
                        absolute_path=str(candidate),
                        action=ApplyAction.SKIPPED_EXISTS,
                        reason="Overwrite refusé par la policy approvals (ApprovalRequired)",
                    )
                )
                continue
            except Exception:  # noqa: S110 — best-effort audit trail, ne doit jamais bloquer l'apply
                pass

        # OK on écrit
        candidate.parent.mkdir(parents=True, exist_ok=True)
        # Normaliser le contenu : assurer une fin de ligne unique
        normalized = content if content.endswith("\n") or content == "" else content + "\n"
        candidate.write_text(normalized, encoding="utf-8")
        results.append(
            ApplyResult(
                path=raw_path,
                absolute_path=str(candidate),
                action=ApplyAction.WRITTEN,
                bytes_written=len(normalized.encode("utf-8")),
            )
        )

    return results
