"""Tests pour src.core.approvals — Sprint CCC HITL.

Couvre :
- ApprovalStore : write/read/list_pending/list_decided/move_to_decided
- Policy : load_policy, policy_matches, find_matching_rule
- request_approval : pending vs auto-approve, blocking ApprovalRequired
- decide : transitions PENDING → APPROVED/REJECTED, fichier déplacé
- wait_for_decision : timeout, polling
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import yaml

from src.core.approvals import (
    STATUS_APPROVED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_REJECTED,
    ApprovalRequired,
    ApprovalStore,
    Policy,
    PolicyRule,
    decide,
    find_matching_rule,
    load_policy,
    policy_matches,
    request_approval,
    wait_for_decision,
)


@pytest.fixture
def store(tmp_path: Path) -> ApprovalStore:
    return ApprovalStore(tmp_path / "approvals")


# ===== ApprovalStore =====


def test_store_creates_dirs_on_init(tmp_path: Path) -> None:
    root = tmp_path / "approvals"
    assert not root.exists()
    ApprovalStore(root)
    assert (root / "pending").is_dir()
    assert (root / "decided").is_dir()


def test_store_write_then_read_roundtrip(store: ApprovalStore) -> None:
    req = request_approval(
        store=store,
        event_type="file_overwrite",
        context={"path": "src/foo.py", "size_bytes": 1234},
    )
    fetched = store.read(req.approval_id)
    assert fetched is not None
    assert fetched.event_type == "file_overwrite"
    assert fetched.context["path"] == "src/foo.py"


def test_store_read_missing_returns_none(store: ApprovalStore) -> None:
    assert store.read("00000000-0000-0000-0000-000000000000") is None


def test_store_list_pending_excludes_decided(store: ApprovalStore) -> None:
    req1 = request_approval(store, "evt1", {})
    req2 = request_approval(store, "evt2", {})
    decide(store, req1.approval_id, approved=True, decided_by="test")

    pending = store.list_pending()
    pending_ids = {r.approval_id for r in pending}
    assert req2.approval_id in pending_ids
    assert req1.approval_id not in pending_ids


def test_store_list_pending_fifo_order(store: ApprovalStore) -> None:
    """Tri par requested_at croissant (le plus ancien d'abord)."""
    req1 = request_approval(store, "first", {})
    time.sleep(0.01)
    req2 = request_approval(store, "second", {})
    pending = store.list_pending()
    assert pending[0].approval_id == req1.approval_id
    assert pending[1].approval_id == req2.approval_id


def test_store_list_decided_returns_recent_first(store: ApprovalStore) -> None:
    req1 = request_approval(store, "evt1", {})
    req2 = request_approval(store, "evt2", {})
    decide(store, req1.approval_id, approved=True, decided_by="test")
    time.sleep(0.02)
    decide(store, req2.approval_id, approved=False, decided_by="test", reason="nope")

    decided = store.list_decided()
    assert decided[0].approval_id == req2.approval_id  # plus récent
    assert decided[1].approval_id == req1.approval_id


# ===== Policy =====


def test_load_policy_returns_empty_when_missing(store: ApprovalStore) -> None:
    policy = load_policy(store.root)
    assert policy.auto_approve == []


def test_load_policy_reads_yaml(store: ApprovalStore) -> None:
    policy_path = store.root / "policy.yml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "auto_approve": [
                    {
                        "event_type": "file_overwrite",
                        "paths_regex": r"^skills/",
                        "rationale": "Skills auto-générées",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = load_policy(store.root)
    assert len(policy.auto_approve) == 1
    assert policy.auto_approve[0].event_type == "file_overwrite"


def test_load_policy_tolerates_corrupt_yaml(store: ApprovalStore) -> None:
    (store.root / "policy.yml").write_text("not: valid: yaml: [", encoding="utf-8")
    policy = load_policy(store.root)
    assert policy.auto_approve == []


def test_policy_matches_event_type_only() -> None:
    rule = PolicyRule(event_type="evt1")
    assert policy_matches(rule, "evt1", {}) is True
    assert policy_matches(rule, "evt2", {}) is False


def test_policy_matches_with_paths_regex() -> None:
    rule = PolicyRule(event_type="file_overwrite", paths_regex=r"^skills/")
    assert policy_matches(rule, "file_overwrite", {"path": "skills/dev/foo.md"}) is True
    assert policy_matches(rule, "file_overwrite", {"path": "src/foo.py"}) is False
    # Pas de path dans context → fail
    assert policy_matches(rule, "file_overwrite", {}) is False


def test_policy_matches_with_max_usd() -> None:
    rule = PolicyRule(event_type="budget_exceed", max_usd=5.0)
    assert policy_matches(rule, "budget_exceed", {"cost_usd": 3.0}) is True
    assert policy_matches(rule, "budget_exceed", {"cost_usd": 7.0}) is False
    assert policy_matches(rule, "budget_exceed", {"cost_usd": "invalid"}) is False


def test_find_matching_rule_returns_first_match() -> None:
    policy = Policy(
        auto_approve=[
            PolicyRule(event_type="evt1"),
            PolicyRule(event_type="evt2"),
        ]
    )
    assert find_matching_rule(policy, "evt2", {}).event_type == "evt2"  # type: ignore[union-attr]
    assert find_matching_rule(policy, "evt3", {}) is None


# ===== request_approval =====


def test_request_approval_pending_when_no_policy(store: ApprovalStore) -> None:
    req = request_approval(store, "evt", {"foo": "bar"})
    assert req.status == STATUS_PENDING
    assert req.decided_at is None
    # Le fichier est dans pending/
    assert (store.pending_dir / f"{req.approval_id}.yml").exists()


def test_request_approval_auto_approve_via_policy(store: ApprovalStore) -> None:
    policy = Policy(
        auto_approve=[PolicyRule(event_type="evt", rationale="auto OK")]
    )
    req = request_approval(store, "evt", {}, policy=policy)
    assert req.status == STATUS_APPROVED
    assert req.decided_by is not None and "policy" in req.decided_by
    assert req.reason == "auto OK"
    # Directement dans decided/
    assert (store.decided_dir / f"{req.approval_id}.yml").exists()
    assert not (store.pending_dir / f"{req.approval_id}.yml").exists()


def test_request_approval_blocking_raises_when_pending(store: ApprovalStore) -> None:
    with pytest.raises(ApprovalRequired):
        request_approval(store, "evt_critical", {}, blocking=True)


def test_request_approval_blocking_does_not_raise_when_auto_approved(
    store: ApprovalStore,
) -> None:
    policy = Policy(auto_approve=[PolicyRule(event_type="evt")])
    # Pas d'exception car la policy auto-approve
    req = request_approval(store, "evt", {}, blocking=True, policy=policy)
    assert req.status == STATUS_APPROVED


# ===== decide =====


def test_decide_approves_pending_request(store: ApprovalStore) -> None:
    req = request_approval(store, "evt", {})
    result = decide(store, req.approval_id, approved=True, decided_by="alice", reason="OK")
    assert result is not None
    assert result.status == STATUS_APPROVED
    assert result.decided_by == "alice"
    assert result.reason == "OK"
    # Le fichier a bougé pending → decided
    assert not (store.pending_dir / f"{req.approval_id}.yml").exists()
    assert (store.decided_dir / f"{req.approval_id}.yml").exists()


def test_decide_rejects_pending_request(store: ApprovalStore) -> None:
    req = request_approval(store, "evt", {})
    result = decide(store, req.approval_id, approved=False, decided_by="bob", reason="no way")
    assert result is not None
    assert result.status == STATUS_REJECTED


def test_decide_returns_none_when_not_pending(store: ApprovalStore) -> None:
    """Si déjà décidé OU si id n'existe pas → None (idempotent)."""
    req = request_approval(store, "evt", {})
    decide(store, req.approval_id, approved=True, decided_by="alice")
    # Re-décider la même requête
    assert decide(store, req.approval_id, approved=False, decided_by="bob") is None
    # ID inconnu
    assert decide(store, "ghost", approved=True, decided_by="alice") is None


# ===== wait_for_decision =====


def test_wait_for_decision_returns_immediately_when_already_decided(
    store: ApprovalStore,
) -> None:
    req = request_approval(store, "evt", {})
    decide(store, req.approval_id, approved=True, decided_by="alice")
    result = wait_for_decision(store, req.approval_id, timeout_seconds=2.0)
    assert result.status == STATUS_APPROVED


def test_wait_for_decision_blocks_until_decided(store: ApprovalStore) -> None:
    """Un thread parallèle pose la décision, le wait doit retourner."""
    req = request_approval(store, "evt", {})

    def delayed_approve() -> None:
        time.sleep(0.2)
        decide(store, req.approval_id, approved=True, decided_by="alice")

    t = threading.Thread(target=delayed_approve)
    t.start()
    result = wait_for_decision(
        store, req.approval_id, timeout_seconds=5.0, poll_interval_seconds=0.05
    )
    t.join(timeout=2)
    assert result.status == STATUS_APPROVED


def test_wait_for_decision_times_out_and_marks_expired(store: ApprovalStore) -> None:
    req = request_approval(store, "evt", {})
    with pytest.raises(TimeoutError):
        wait_for_decision(
            store, req.approval_id, timeout_seconds=0.2, poll_interval_seconds=0.05
        )
    # Après timeout, la requête est marquée EXPIRED dans decided/
    fetched = store.read(req.approval_id)
    assert fetched is not None
    assert fetched.status == STATUS_EXPIRED
    assert fetched.decided_by == "timeout"


def test_wait_for_decision_raises_on_unknown_id(store: ApprovalStore) -> None:
    with pytest.raises(ValueError, match="introuvable"):
        wait_for_decision(store, "ghost", timeout_seconds=0.1)
