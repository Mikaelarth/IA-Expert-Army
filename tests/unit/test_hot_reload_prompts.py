"""Tests v0.8.0 F4 — hot-reload des prompts système.

Valide :
- Par défaut (Settings.hot_reload_prompts=False), le prompt est caché.
- Avec hot_reload_prompts=True, modifier le fichier prompt change
  ce que retourne `agent.system_prompt`.
- Si le fichier est temporairement inaccessible pendant l'édition, on
  retombe sur le cache (fallback gracieux, pas de crash mission).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config import Settings


def _write_prompt(path: Path, body: str) -> None:
    """Écrit un prompt au format MemoryRecord attendu (frontmatter + body)."""
    content = f"---\nname: fake_agent\nrole: test\n---\n{body}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_agent(tmp_path: Path, settings: Settings):
    """Construit un BaseAgent minimal avec un prompt sur disque éditable."""
    from src.orchestrator.base_agent import BaseAgent

    prompt_path = tmp_path / "fake.md"
    _write_prompt(prompt_path, "Initial prompt body v1")

    # Stub client OpenAI pour ne pas faire d'appel réseau
    class _StubClient:
        chat = None

    return BaseAgent(
        name="fake_agent",
        prompt_path=prompt_path,
        model="qwen2.5:14b",
        memory=None,  # type: ignore[arg-type] — non utilisé pour ce test
        settings=settings,
        client=_StubClient(),
    ), prompt_path


def test_default_caches_system_prompt_at_init(tmp_path: Path) -> None:
    """Sans hot_reload, le prompt est lu UNE fois au __init__ puis caché."""
    settings = Settings(_env_file=None, hot_reload_prompts=False)  # type: ignore[call-arg]
    agent, prompt_path = _build_agent(tmp_path, settings)

    initial = agent.system_prompt
    assert "Initial prompt body v1" in initial

    # Modifie le fichier après init
    _write_prompt(prompt_path, "Modified prompt v2")

    # Cache toujours en place — la modif n'est PAS prise en compte
    assert agent.system_prompt == initial
    assert "v2" not in agent.system_prompt


def test_hot_reload_picks_up_disk_changes(tmp_path: Path) -> None:
    """Avec hot_reload=True, modifier le fichier change le prompt retourné."""
    settings = Settings(_env_file=None, hot_reload_prompts=True)  # type: ignore[call-arg]
    agent, prompt_path = _build_agent(tmp_path, settings)

    assert "v1" in agent.system_prompt

    # Modifie le fichier
    _write_prompt(prompt_path, "Modified prompt v2 — hot reloaded")

    # La nouvelle version est lue
    new_prompt = agent.system_prompt
    assert "v2 — hot reloaded" in new_prompt
    assert "v1" not in new_prompt


def test_hot_reload_falls_back_to_cache_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si le fichier prompt disparait temporairement (write atomique 2-temps,
    suppression accidentelle), on retombe sur le cache au lieu de crasher."""
    settings = Settings(_env_file=None, hot_reload_prompts=True)  # type: ignore[call-arg]
    agent, prompt_path = _build_agent(tmp_path, settings)

    cached = agent.system_prompt  # capture v1

    # Supprime le fichier
    prompt_path.unlink()

    # Doit retourner le cache, pas crasher
    assert agent.system_prompt == cached


def test_hot_reload_setting_default_is_false() -> None:
    """Rétrocompat : le défaut doit être False (pas de surcoût en production
    sans opt-in explicite)."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.hot_reload_prompts is False
