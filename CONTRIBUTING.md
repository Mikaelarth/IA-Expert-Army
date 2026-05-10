# Contributing to IA-Expert-Army

Thanks for considering contributing! This project follows a few opinionated rules to keep the codebase **« pro et propre »**.

## Quick start (5 min)

```powershell
git clone https://github.com/MikaelArth/IA-Expert-Army.git
cd IA-Expert-Army
uv sync                                        # installs deps + Python 3.12+
copy .env.example .env                         # then edit ANTHROPIC_API_KEY
uv run python scripts/check_setup.py           # verify everything is wired
uv run pytest tests/unit/                      # should be all green
```

## Before you push

```powershell
uv run pytest tests/unit/                      # all tests must pass
```

If you've added a new agent, new guild, or new prompt: **add a regression test** that documents the expected behavior. Look at `tests/unit/test_research_agents.py` for the pattern.

## Architecture in 30 seconds

The project is organized in 4 layers (see [ADR-001](docs/adr/001-four-layer-architecture.md)):

```
Couche 4 — Apprentissage  (PatternMiner + SkillExtractor + RAG)
Couche 3 — Infrastructure (FileMemory + VectorMemory + Sandbox + Budget)
Couche 2 — 4 Guildes      (Engineering · Research · Creative · Business)
Couche 1 — Direction      (Chief Orchestrator · Quality Guardian)
```

Read the ADRs in [docs/adr/](docs/adr/) before proposing structural changes.

## Code conventions

- **Type hints partout** : Python 3.12+ syntax (`list[str]`, `int | None`).
- **Pas de commentaires qui paraphrasent le code** : un commentaire explique le *pourquoi*, pas le *quoi*.
- **Imports triés** : stdlib → tiers → projet (auto-sortable via `ruff check --select I --fix`).
- **Pas d'effets de bord à l'import** : configuration via Settings, pas via constantes globales.
- **Pas de `print()`** : utiliser `structlog` via `get_logger()`.
- **Erreurs explicites** : pas de `except: pass`. Un except attrape un type précis et logge ou re-raise.

## Adding a new agent

1. Create the system prompt in `prompts/<guild>/<role>.md` with YAML frontmatter (cf. existing prompts for the schema).
2. Subclass `BaseAgent` in `src/guilds/<guild>/agents.py`. Set `DEFAULT_MAX_TOKENS` generously (8192 for reviewers/synthesizers, 4096 for planners). See [ADR-005](docs/adr/005-saturation-detection-and-prevention.md).
3. Add the role name to `PatternMiner.AGENT_WHITELIST` in `src/learning/pattern_miner.py` (history shows we forget this — there's a regression test that catches it).
4. Add the role to the appropriate `Workflow` and update `MissionRouter` keywords.
5. Write a `tests/unit/test_<guild>_agents.py` covering : model tier, max_tokens floor, prompt loads, classifier routes correctly.

## Adding a new guild

Same as agents, plus:
- New `<Guild>Workflow` class with linear pipeline + 1× repair loop.
- New `<Guild>MissionResult` Pydantic model.
- Update `MissionRouter._build_routing_decision()` and `MissionRouter.run()` for dispatch.
- New keyword set in `_<GUILD>_KEYWORDS`.
- New regression test for the routing.

## Mining policy

The PatternMiner has 5 strict eligibility filters (see [ADR-006](docs/adr/006-mining-strategy-and-eligibility.md)). **Don't lower them.** If your role can't be mined yet, that's a signal you need more APPROVED missions, not laxer filters.

## Cost discipline

A mission costs $0.20–$1.50 in Claude API depending on complexity. The default daily cap is $50. Before a session of heavy experimentation:
- Set `DAILY_BUDGET_USD` in `.env` to a sane value
- Use `uv run python scripts/budget.py status` to monitor

If you hit the cap mid-session, that's the BudgetController doing its job. Either bump the cap deliberately or wait for tomorrow's reset.

## Reporting bugs

Open a GitHub issue with:
1. The mission title + description that triggered it
2. The relevant episode markdown from `data/memory/episodes/`
3. Whether `saturated: true` appears in any episode metadata (if yes, that's almost certainly the cause — see [ADR-005](docs/adr/005-saturation-detection-and-prevention.md))

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
