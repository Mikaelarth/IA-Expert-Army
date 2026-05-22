"""prompt_ab — A/B testing des prompts système (v0.9.0 A2, ADR-029).

MVP suggest-only : pas d'auto-promote. L'humain valide via la page GUI
A/B Testing après avoir vu les stats agrégées sur ≥10 missions.

Cycle d'utilisation typique :
1. Écrire une variante : `prompts/orchestrator/code_reviewer_v2.md` à côté
   du `code_reviewer.md` canonique.
2. Activer l'A/B pour cet agent : `AB_TESTING_AGENTS=code_reviewer` dans `.env`.
3. Laisser tourner ≥10 missions Engineering.
4. Ouvrir la page GUI A/B Testing → comparer les stats.
5. Cliquer "Promouvoir comme canonique" sur la variante gagnante (renomme
   le fichier, archive l'ancien).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.logging import get_logger

_log = get_logger("prompt_ab")


@dataclass
class PromptVariant:
    """Une variante (canonique ou alternative) d'un prompt agent."""

    role: str  # ex. "code_reviewer"
    label: str  # ex. "" (canonique) ou "v2", "concise"
    path: Path  # chemin .md
    is_canonical: bool  # True si c'est le prompt principal (pas une variante)


@dataclass
class VariantStats:
    """Stats agrégées d'une variante sur ses missions trackées."""

    role: str
    label: str
    n_missions: int = 0
    n_approved: int = 0
    n_needs_changes: int = 0
    n_rejected: int = 0
    avg_quality_score: float | None = None
    avg_cost_usd: float = 0.0
    avg_duration_seconds: float = 0.0

    @property
    def approval_rate(self) -> float:
        return self.n_approved / self.n_missions if self.n_missions else 0.0


@dataclass
class VariantComparison:
    """Résultat de comparaison entre 2+ variantes d'un même rôle."""

    role: str
    stats: list[VariantStats]  # triées par approval_rate × avg_quality_score desc
    recommended_label: str | None  # label suggéré comme canonique (ou None si insuffisant)
    is_significant: bool  # True si Δ approval_rate ≥ 10pp ET n ≥ 10 sur les 2 variantes
    rationale: str = ""


# ============================================================================
# Service
# ============================================================================


class PromptAB:
    """Découverte de variantes + sélection déterministe + tracking + stats.

    Stateless côté instance. Le store fichier vit dans `data/ab_tests/`.
    """

    def __init__(self, prompts_root: Path, ab_store_root: Path) -> None:
        self.prompts_root = Path(prompts_root)
        self.ab_store_root = Path(ab_store_root)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_variants(self, prompt_path: Path) -> list[PromptVariant]:
        """Trouve toutes les variantes d'un prompt canonique.

        Convention : variantes = `<role>_<label>.md` dans le même dossier
        que le prompt canonique `<role>.md`. Le canonique est inclus dans
        la liste retournée avec `is_canonical=True` et `label=""`.

        Si le prompt canonique n'existe pas, retourne [].
        """
        prompt_path = Path(prompt_path)
        if not prompt_path.exists():
            return []
        role = prompt_path.stem  # "code_reviewer"
        folder = prompt_path.parent

        variants: list[PromptVariant] = [
            PromptVariant(role=role, label="", path=prompt_path, is_canonical=True)
        ]
        for candidate in sorted(folder.glob(f"{role}_*.md")):
            # On exclut les archives (préfixe `<role>_archived_`)
            label = candidate.stem[len(role) + 1 :]  # "v2" depuis "code_reviewer_v2"
            if label.startswith("archived_"):
                continue
            variants.append(
                PromptVariant(role=role, label=label, path=candidate, is_canonical=False)
            )
        return variants

    # ------------------------------------------------------------------
    # Sélection
    # ------------------------------------------------------------------

    def pick_variant(
        self,
        prompt_path: Path,
        mission_id: str,
        enabled_agents: Iterable[str] | None = None,
    ) -> PromptVariant:
        """Choisit une variante pour cette mission.

        - Si l'agent (`prompt_path.stem`) n'est PAS dans `enabled_agents`,
          retourne toujours le canonique (A/B désactivé).
        - Sinon, sélection déterministe via `hash(mission_id) % n_variants`.
          Reproductible : un resume avec le même mission_id pick la même variante.

        Si une seule variante existe (canonique seul), elle est retournée
        directement, peu importe l'activation A/B.
        """
        variants = self.discover_variants(prompt_path)
        if not variants:
            raise FileNotFoundError(f"Prompt absent : {prompt_path}")

        if len(variants) == 1:
            return variants[0]  # canonique seul, pas de choix à faire

        role = variants[0].role
        if enabled_agents is not None and role not in enabled_agents:
            # A/B désactivé pour cet agent — on retourne le canonique
            canonical = next((v for v in variants if v.is_canonical), variants[0])
            return canonical

        # Sélection déterministe par hash
        digest = hashlib.sha256(str(mission_id).encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % len(variants)
        return variants[index]

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def track_outcome(
        self,
        role: str,
        label: str,
        mission_id: str,
        final_verdict: str,
        quality_score: float | None,
        cost_usd: float,
        duration_seconds: float,
    ) -> Path | None:
        """Persiste le résultat d'une mission pour la variante choisie.

        Best-effort : échec d'écriture loggue et retourne None sans lever.
        """
        try:
            store_dir = self.ab_store_root / role / (label or "_canonical")
            store_dir.mkdir(parents=True, exist_ok=True)
            path = store_dir / f"{mission_id}.json"
            payload = {
                "mission_id": str(mission_id),
                "role": role,
                "label": label,
                "tracked_at": datetime.now(UTC).isoformat(),
                "final_verdict": final_verdict,
                "quality_score": quality_score,
                "cost_usd": cost_usd,
                "duration_seconds": duration_seconds,
            }
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            return path
        except OSError as exc:
            _log.warning(
                "prompt_ab.track.failed",
                role=role,
                label=label,
                mission_id=mission_id,
                error=str(exc),
            )
            return None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def compute_stats(self, role: str) -> list[VariantStats]:
        """Agrège les stats par variante pour un rôle donné.

        Retourne une liste (potentiellement vide si aucun tracking) avec
        une entrée par sous-dossier de `data/ab_tests/<role>/`. Tolérant
        aux fichiers corrompus (skippés sans crash).
        """
        role_dir = self.ab_store_root / role
        if not role_dir.exists():
            return []

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for variant_dir in role_dir.iterdir():
            if not variant_dir.is_dir():
                continue
            label = variant_dir.name if variant_dir.name != "_canonical" else ""
            for json_path in variant_dir.glob("*.json"):
                try:
                    grouped[label].append(json.loads(json_path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue

        stats: list[VariantStats] = []
        for label, runs in grouped.items():
            n = len(runs)
            if n == 0:
                continue
            s = VariantStats(role=role, label=label, n_missions=n)
            sum_cost = sum_duration = 0.0
            sum_score = 0.0
            n_scored = 0
            for r in runs:
                verdict = str(r.get("final_verdict", "")).upper()
                if verdict == "APPROVED":
                    s.n_approved += 1
                elif verdict == "NEEDS_CHANGES":
                    s.n_needs_changes += 1
                elif verdict == "REJECTED":
                    s.n_rejected += 1
                score = r.get("quality_score")
                if isinstance(score, (int, float)):
                    sum_score += float(score)
                    n_scored += 1
                cost = r.get("cost_usd", 0.0)
                dur = r.get("duration_seconds", 0.0)
                if isinstance(cost, (int, float)):
                    sum_cost += float(cost)
                if isinstance(dur, (int, float)):
                    sum_duration += float(dur)
            s.avg_quality_score = round(sum_score / n_scored, 3) if n_scored else None
            s.avg_cost_usd = round(sum_cost / n, 6)
            s.avg_duration_seconds = round(sum_duration / n, 2)
            stats.append(s)

        return stats

    def compare(self, role: str) -> VariantComparison:
        """Compare toutes les variantes d'un rôle et suggère un winner.

        Sort triée par `approval_rate × avg_quality_score`. Le recommanded
        est `None` si :
        - Moins de 2 variantes ont des données.
        - Δ approval_rate < 10pp entre top et 2nd (pas significatif au seuil MVP).
        - Top variant a < 10 missions trackées.
        """
        stats = self.compute_stats(role)
        if not stats:
            return VariantComparison(
                role=role, stats=[], recommended_label=None, is_significant=False
            )

        def _composite(s: VariantStats) -> float:
            score = s.avg_quality_score or 0.0
            return s.approval_rate * score

        stats.sort(key=_composite, reverse=True)
        if len(stats) < 2:
            return VariantComparison(
                role=role,
                stats=stats,
                recommended_label=None,
                is_significant=False,
                rationale="Une seule variante avec données — rien à comparer.",
            )

        top, second = stats[0], stats[1]
        delta_pp = (top.approval_rate - second.approval_rate) * 100
        is_significant = top.n_missions >= 10 and abs(delta_pp) >= 10.0

        if is_significant:
            recommended = top.label or "(canonique)"
            rationale = (
                f"{recommended} domine avec {top.approval_rate:.0%} approval "
                f"sur {top.n_missions} missions (vs {second.approval_rate:.0%} "
                f"pour la 2nde · Δ={delta_pp:+.1f} pp)."
            )
        else:
            recommended = None
            if top.n_missions < 10:
                rationale = (
                    f"Pas assez de missions ({top.n_missions} < 10) pour conclure. "
                    "Laisse tourner plus longtemps."
                )
            else:
                rationale = (
                    f"Différence trop faible ({delta_pp:+.1f} pp, seuil 10 pp). "
                    "Variantes équivalentes statistiquement."
                )

        return VariantComparison(
            role=role,
            stats=stats,
            recommended_label=recommended,
            is_significant=is_significant,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # Promotion (manuelle — appelée depuis la GUI)
    # ------------------------------------------------------------------

    def promote_variant(self, prompt_path: Path, variant_label: str) -> Path:
        """Promeut une variante comme nouveau canonique.

        1. Archive le canonique courant en `<role>_archived_<YYYYMMDD_HHMM>.md`.
        2. Renomme la variante en `<role>.md`.
        3. Retourne le path du nouveau canonique.

        Lève si la variante n'existe pas ou si une opération de fichier échoue.
        """
        prompt_path = Path(prompt_path)
        variants = self.discover_variants(prompt_path)
        target = next(
            (v for v in variants if v.label == variant_label and not v.is_canonical),
            None,
        )
        if target is None:
            raise ValueError(f"Variante '{variant_label}' introuvable pour {prompt_path}")

        canonical = next((v for v in variants if v.is_canonical), None)
        if canonical is None:
            raise FileNotFoundError(f"Pas de canonique pour {prompt_path}")

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        role = canonical.role
        archive_path = canonical.path.parent / f"{role}_archived_{timestamp}.md"
        canonical.path.rename(archive_path)
        target.path.rename(canonical.path)
        return canonical.path
