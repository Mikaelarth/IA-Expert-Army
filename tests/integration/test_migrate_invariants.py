"""Tests d'invariants migrate_vps — fallback Python pur (cross-plateforme).

`test_migrate_vps.py` (existant) lance le vrai `scripts/migrate_vps.sh` pour
valider le round-trip end-to-end, mais skip automatiquement si bash est absent
(ex. Windows sans Git Bash). Conséquence : sur Windows CI, **aucun signal**
n'est produit sur les régressions du chemin migration (path separators,
encoding UTF-8, intégrité des données).

Ce fichier complète le précédent en exerçant les **invariants Python purs** :

1. Le script `migrate_vps.sh` existe et est syntaxiquement plausible (shebang,
   références à des commandes connues).
2. Un round-trip tarfile équivalent (`data/memory` → `.tar.gz` → restore
   ailleurs) préserve l'intégrité byte-for-byte sur toutes les plateformes.

Cf. ADR v0.7.0 audit zéro-dette L12.
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE_SCRIPT = REPO_ROOT / "scripts" / "migrate_vps.sh"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    """Hashe chaque fichier du tree, indexé par chemin relatif POSIX."""
    return {
        p.relative_to(root).as_posix(): _hash_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# Invariants statiques sur migrate_vps.sh
# ---------------------------------------------------------------------------


def test_migrate_vps_script_exists() -> None:
    """Le script de migration doit exister à l'emplacement attendu."""
    assert MIGRATE_SCRIPT.exists(), (
        f"scripts/migrate_vps.sh manquant — chemin attendu {MIGRATE_SCRIPT}"
    )


def test_migrate_vps_script_has_shebang() -> None:
    """Le script doit commencer par un shebang bash (#!/usr/bin/env bash ou /bin/bash)."""
    if not MIGRATE_SCRIPT.exists():
        pytest.skip("script absent — couvert par test_migrate_vps_script_exists")
    first_line = MIGRATE_SCRIPT.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!") and "bash" in first_line, (
        f"shebang manquant ou non-bash : {first_line!r}"
    )


def test_migrate_vps_script_references_expected_commands() -> None:
    """Vérifie que le script référence les commandes critiques attendues."""
    if not MIGRATE_SCRIPT.exists():
        pytest.skip("script absent")
    content = MIGRATE_SCRIPT.read_text(encoding="utf-8")
    for token in ("tar", "sha256sum", "export", "import", "verify"):
        assert token in content, f"Token attendu absent du script : {token!r}"


# ---------------------------------------------------------------------------
# Round-trip Python tarfile — équivalent fonctionnel à migrate_vps export/import
# ---------------------------------------------------------------------------


def test_tarfile_roundtrip_preserves_directory_tree(tmp_path: Path) -> None:
    """Crée une fausse arbo data/memory → tar.gz → extract ailleurs → hash diff.

    C'est le mécanisme sous-jacent de migrate_vps.sh export/import. Ce test
    vérifie l'invariant cross-plateforme (Windows compris) sans dépendre de bash.
    """
    src = tmp_path / "src_install"
    dest = tmp_path / "dest_install"
    archive = tmp_path / "snapshot.tar.gz"

    # Crée une arbo représentative
    (src / "data" / "memory" / "missions").mkdir(parents=True)
    (src / "data" / "memory" / "episodes").mkdir(parents=True)
    (src / "skills" / "code_reviewer").mkdir(parents=True)
    (src / "data" / "memory" / "missions" / "m1.md").write_text(
        "---\nverdict: APPROVED\n---\nbody\n", encoding="utf-8"
    )
    (src / "data" / "memory" / "episodes" / "e1.md").write_text(
        "---\nagent: code_reviewer\n---\noutput\n", encoding="utf-8"
    )
    (src / "skills" / "code_reviewer" / "s1.md").write_text(
        "---\ntitle: skill\n---\nbody\n", encoding="utf-8"
    )
    (src / ".env").write_text("OLLAMA_BASE_URL=http://localhost:11434/v1\n", encoding="utf-8")

    src_hashes = _hash_tree(src)
    assert len(src_hashes) == 4

    # Pack
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname=".")
    assert archive.exists() and archive.stat().st_size > 0

    # Unpack ailleurs
    dest.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        # Python 3.12+ : data filter par défaut, mais on l'explicite pour
        # garantir le comportement cross-version.
        tar.extractall(dest, filter="data")  # type: ignore[arg-type]

    dest_hashes = _hash_tree(dest)
    assert dest_hashes == src_hashes, "Le round-trip tarfile a altéré au moins un fichier"


def test_tarfile_roundtrip_preserves_unicode_paths(tmp_path: Path) -> None:
    """Garantit que les caractères accentués (mission FR, emojis dans paths)
    survivent au round-trip. C'est un cas réel : les épisodes contiennent
    des frontmatter avec descriptions FR, et certaines pages GUI ont des
    noms avec emojis (cf. 0_🛠_Setup.py).
    """
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    archive = tmp_path / "unicode.tar.gz"

    src.mkdir()
    (src / "résumé_de_mission.md").write_text("contenu avec accents é à ç", encoding="utf-8")

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname=".")
    dest.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest, filter="data")  # type: ignore[arg-type]

    restored = (dest / "résumé_de_mission.md").read_text(encoding="utf-8")
    assert "é à ç" in restored
