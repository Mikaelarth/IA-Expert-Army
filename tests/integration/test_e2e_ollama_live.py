"""Test E2E qui touche le VRAI daemon Ollama (slow, nightly).

Ce test n'est PAS exécuté par défaut. Il est marqué `slow` ET skipped si le
daemon Ollama n'est pas joignable. Pour le lancer explicitement :

    uv run pytest tests/integration/test_e2e_ollama_live.py -v --run-slow

Ou via GitHub Actions schedule (cron nightly) :

    OLLAMA_E2E=1 uv run pytest -m slow tests/integration/

Pourquoi ce test existe (audit zéro-dette L3) :
- 603 tests passing dans la suite courante mockent TOUS les appels Ollama via
  `FakeAsyncOpenAI`. Le bénéfice : tests rapides, déterministes, gratuits.
- Le risque : un changement du format de réponse Ollama (ex. ChatCompletion
  vs Completion, refactor du SDK openai) ne serait détecté qu'en prod.
- Ce test fait UN appel réel mini à Ollama (model bulk 14B, prompt court,
  max_tokens=50) pour valider le contrat de réponse.

Coût : ~5-20 s sur Qwen 14B local. Pas de quota cloud (Ollama = $0).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest

from src.core.config import get_settings


def _ollama_daemon_responds() -> bool:
    """True si l'endpoint /api/tags répond — sinon on skip."""
    s = get_settings()
    api_base = s.ollama_base_url.rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(  # noqa: S310 — localhost Ollama
            f"{api_base}/api/tags", timeout=3
        ) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False


def _model_bulk_installed() -> bool:
    """True si model_bulk est pullé."""
    s = get_settings()
    api_base = s.ollama_base_url.rstrip("/").removesuffix("/v1")
    try:
        with urllib.request.urlopen(  # noqa: S310 — localhost Ollama
            f"{api_base}/api/tags", timeout=3
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return False
    installed = {m.get("name") for m in payload.get("models", []) if isinstance(m, dict)}
    return s.model_bulk in installed


# Skip si :
# - OLLAMA_E2E != 1 (variable d'environnement explicite pour activer)
# - daemon down (les pulls/installations sont l'affaire de Setup Wizard, pas du test)
# - model_bulk absent (idem)
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("OLLAMA_E2E") != "1",
        reason="Test E2E live Ollama opt-in — exporter OLLAMA_E2E=1 pour activer.",
    ),
    pytest.mark.skipif(
        not _ollama_daemon_responds(),
        reason="Daemon Ollama non joignable — exécuter `ollama serve` d'abord.",
    ),
    pytest.mark.skipif(
        not _model_bulk_installed(),
        reason="Modèle bulk non pullé — exécuter `ollama pull <model>` d'abord.",
    ),
]


def test_ollama_chat_completion_returns_expected_shape() -> None:
    """Smoke test : un appel ChatCompletion sur model_bulk doit retourner
    une structure parsable (choices[0].message.content non-vide).

    Régression cible : un changement upstream du format de réponse Ollama
    (ex. clé `choices` renommée) casserait toute la chaîne MissionRouter
    sans qu'aucun test mocké ne le détecte.
    """
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(
        base_url=s.ollama_base_url,
        api_key=s.ollama_api_key,
        timeout=60.0,
        max_retries=0,
    )

    response = client.chat.completions.create(
        model=s.model_bulk,
        messages=[
            {
                "role": "system",
                "content": "Tu réponds en un seul mot, en minuscules, sans ponctuation.",
            },
            {"role": "user", "content": "Quelle est la couleur du ciel par beau temps ?"},
        ],
        max_tokens=10,
        temperature=0.0,
    )

    # Contrat structurel attendu (openai SDK ≥1.50)
    assert response.choices, "response.choices doit être non-vide"
    assert response.choices[0].message is not None
    content = response.choices[0].message.content
    assert content is not None, "message.content doit être renseigné"
    assert len(content.strip()) > 0, "message.content doit être non-vide"
    # On accepte large : "bleu", "bleue", " bleu", "le ciel est bleu" — la
    # variabilité du modèle est admise tant que la structure est correcte.


def test_ollama_classifier_e2e_routes_engineering_mission() -> None:
    """Le `LLMGuildClassifier` doit retourner "engineering" sur une mission
    clairement engineering. Vrai appel Ollama, pas mock.
    """
    from src.orchestrator.router import LLMGuildClassifier

    s = get_settings()
    clf = LLMGuildClassifier(s)
    guild = clf.classify(
        title="Crée un endpoint FastAPI /health",
        description="GET /health qui retourne JSON status=ok, status_code=200, "
        "couvert par 2 tests pytest. Utiliser APIRouter + response_model Pydantic.",
    )
    assert guild == "engineering", (
        f"Classifier devait retourner 'engineering' sur mission canon, a retourné {guild!r}"
    )
