"""approvals — Human-In-The-Loop pour actions sensibles (Sprint CCC).

Mécanisme central : un producteur (workflow, run_mission, autonomous_run)
détecte qu'une action mérite validation humaine, appelle `request_approval()`.
Cela écrit un fichier YAML dans `data/approvals/pending/<uuid>.yml`. Un
humain le revue via `scripts/approvals.py` (CLI) et décide. La décision
est archivée dans `data/approvals/decided/<uuid>.yml`.

Politique optionnelle dans `data/approvals/policy.yml` :
    auto_approve:
      - event_type: file_overwrite
        paths_regex: "^skills/.*"
        rationale: "Skills sont auto-générées, overwrite OK"

Si la requête matche une règle d'auto-approve, la décision est posée
immédiatement (status=APPROVED, decided_by=policy) et le caller n'est
pas bloqué.

Sémantique du blocking :
- blocking=False (défaut) : on enregistre la demande mais le caller continue.
  Permet de "demander pendant qu'on travaille".
- blocking=True : si non auto-approuvé, lève ApprovalRequired. Le caller
  décide (abort, sauvegarder l'état + relancer plus tard, etc.).

NOTE : ce module fournit le MÉCANISME. Le wiring dans les call sites
(overwrite avec --force, budget > seuil, killswitch release) viendra
dans des sprints suivants une fois la primitive stabilisée.
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

# ===== Constantes =====

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_EXPIRED = "EXPIRED"


class ApprovalRequired(RuntimeError):
    """Levée quand blocking=True et la requête n'est pas auto-approuvée."""


class ApprovalRequest(BaseModel):
    """Une demande d'approbation persistée."""

    approval_id: str
    event_type: str
    context: dict[str, Any] = Field(default_factory=dict)
    requested_at: str
    requested_by: str = "system"
    status: str = STATUS_PENDING
    blocking: bool = False
    # Champs renseignés si décidé
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None


# ===== Storage =====


class ApprovalStore:
    """Gestionnaire fichier des approvals (un YAML par demande)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.pending_dir = self.root / "pending"
        self.decided_dir = self.root / "decided"
        for d in (self.pending_dir, self.decided_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _pending_path(self, approval_id: str) -> Path:
        return self.pending_dir / f"{approval_id}.yml"

    def _decided_path(self, approval_id: str) -> Path:
        return self.decided_dir / f"{approval_id}.yml"

    def write(self, request: ApprovalRequest) -> Path:
        """Écrit la requête dans le bon dossier selon son status."""
        target_dir = self.pending_dir if request.status == STATUS_PENDING else self.decided_dir
        path = target_dir / f"{request.approval_id}.yml"
        data = request.model_dump(mode="json")
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path

    def read(self, approval_id: str) -> ApprovalRequest | None:
        """Cherche d'abord en pending, puis en decided. None si introuvable."""
        for path in (self._pending_path(approval_id), self._decided_path(approval_id)):
            if path.exists():
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    return ApprovalRequest(**data)
                except (yaml.YAMLError, OSError, TypeError):
                    return None
        return None

    def list_pending(self) -> list[ApprovalRequest]:
        """Liste les requêtes en attente, triées par requested_at croissant (FIFO).

        Le tri par UUID lexicographique serait aléatoire ; on lit le YAML et on
        trie par champ sémantique. Coût O(N) mais N reste petit en pratique
        (<100 pending à la fois — sinon il y a un problème de capacité humaine).
        """
        out: list[ApprovalRequest] = []
        for path in self.pending_dir.glob("*.yml"):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                out.append(ApprovalRequest(**data))
            except (yaml.YAMLError, OSError, TypeError):
                continue
        out.sort(key=lambda r: r.requested_at)
        return out

    def list_decided(self, limit: int = 50) -> list[ApprovalRequest]:
        """Liste les requêtes décidées, plus récentes en premier (mtime desc)."""
        files = sorted(
            self.decided_dir.glob("*.yml"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
        out: list[ApprovalRequest] = []
        for path in files:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                out.append(ApprovalRequest(**data))
            except (yaml.YAMLError, OSError, TypeError):
                continue
        return out

    def remove_pending(self, approval_id: str) -> None:
        """Supprime le fichier pending/. No-op si absent."""
        pending = self._pending_path(approval_id)
        if pending.exists():
            with contextlib.suppress(OSError):
                pending.unlink()


# ===== Policy (auto-approve) =====


class PolicyRule(BaseModel):
    event_type: str
    paths_regex: str | None = None  # regex sur context['path'] si présent
    max_usd: float | None = None  # plafond sur context['cost_usd']
    rationale: str = ""


class Policy(BaseModel):
    auto_approve: list[PolicyRule] = Field(default_factory=list)


def load_policy(root: Path) -> Policy:
    """Charge `<root>/policy.yml`. Retourne Policy vide si absent ou invalide."""
    path = Path(root) / "policy.yml"
    if not path.exists():
        return Policy()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Policy(**data)
    except (yaml.YAMLError, OSError, TypeError):
        return Policy()


def policy_matches(rule: PolicyRule, event_type: str, context: dict[str, Any]) -> bool:
    """Vrai si la règle matche la requête (event_type + filtres optionnels)."""
    if rule.event_type != event_type:
        return False
    if rule.paths_regex is not None:
        path = str(context.get("path", ""))
        if not re.search(rule.paths_regex, path):
            return False
    if rule.max_usd is not None:
        cost = context.get("cost_usd")
        if not isinstance(cost, (int, float)) or float(cost) > rule.max_usd:
            return False
    return True


def find_matching_rule(
    policy: Policy, event_type: str, context: dict[str, Any]
) -> PolicyRule | None:
    for rule in policy.auto_approve:
        if policy_matches(rule, event_type, context):
            return rule
    return None


# ===== API publique =====


def request_approval(
    store: ApprovalStore,
    event_type: str,
    context: dict[str, Any],
    requested_by: str = "system",
    blocking: bool = False,
    policy: Policy | None = None,
) -> ApprovalRequest:
    """Enregistre une demande d'approbation.

    Si une règle de policy matche → auto-APPROVED immédiatement.
    Sinon :
      - blocking=False : la demande est posée en pending, le caller continue.
      - blocking=True  : ApprovalRequired levée.

    Retourne le ApprovalRequest tel que persisté (status reflète la décision
    finale dans le cas auto-approve, sinon PENDING).
    """
    policy = policy or load_policy(store.root)
    approval_id = str(uuid4())
    now = datetime.now(UTC).isoformat()

    rule = find_matching_rule(policy, event_type, context)
    if rule is not None:
        # Auto-approve via policy
        request = ApprovalRequest(
            approval_id=approval_id,
            event_type=event_type,
            context=context,
            requested_at=now,
            requested_by=requested_by,
            status=STATUS_APPROVED,
            blocking=blocking,
            decided_at=now,
            decided_by=f"policy:{rule.event_type}",
            reason=rule.rationale or "auto-approved by policy",
        )
        store.write(request)
        return request

    # Pas de match policy → pending
    request = ApprovalRequest(
        approval_id=approval_id,
        event_type=event_type,
        context=context,
        requested_at=now,
        requested_by=requested_by,
        status=STATUS_PENDING,
        blocking=blocking,
    )
    store.write(request)

    if blocking:
        raise ApprovalRequired(
            f"Action '{event_type}' nécessite approbation humaine (id={approval_id}). "
            f"Voir `just approvals` puis `just approve {approval_id}` ou "
            f'`just reject {approval_id} --reason "..."`.'
        )
    return request


def decide(
    store: ApprovalStore,
    approval_id: str,
    approved: bool,
    decided_by: str,
    reason: str = "",
) -> ApprovalRequest | None:
    """Pose une décision sur une demande pending.

    Retourne le ApprovalRequest mis à jour, ou None si l'id n'existe pas ou
    si la demande est déjà décidée.
    """
    request = store.read(approval_id)
    if request is None or request.status != STATUS_PENDING:
        return None
    request.status = STATUS_APPROVED if approved else STATUS_REJECTED
    request.decided_at = datetime.now(UTC).isoformat()
    request.decided_by = decided_by
    request.reason = reason
    # `store.write` écrit dans decided/ car status != PENDING, puis on
    # nettoie le pending/. Pas de race entre les deux sur OS modernes
    # (un read concurrent verrait la version finale dans decided/).
    store.write(request)
    store.remove_pending(approval_id)
    return request


def wait_for_decision(
    store: ApprovalStore,
    approval_id: str,
    timeout_seconds: float = 300.0,
    poll_interval_seconds: float = 1.0,
) -> ApprovalRequest:
    """Bloque jusqu'à ce qu'une décision soit posée OU timeout.

    En cas de timeout, marque la demande comme EXPIRED et lève TimeoutError.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        request = store.read(approval_id)
        if request is None:
            raise ValueError(f"Approval id introuvable : {approval_id}")
        if request.status != STATUS_PENDING:
            return request
        if time.monotonic() >= deadline:
            # Timeout : on marque EXPIRED et on lève
            request.status = STATUS_EXPIRED
            request.decided_at = datetime.now(UTC).isoformat()
            request.decided_by = "timeout"
            request.reason = f"Timeout après {timeout_seconds}s sans décision"
            store.write(request)
            store.remove_pending(approval_id)
            raise TimeoutError(
                f"Approval {approval_id} expirée après {timeout_seconds}s sans décision humaine"
            )
        time.sleep(poll_interval_seconds)
