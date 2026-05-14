"""Logging — structuré avec structlog, sortie console (dev) ou JSON (prod)."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def setup_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configure structlog et le logging Python standard."""
    global _configured
    if _configured:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> Any:
    """Retourne un logger structuré nommé (le nom est bind comme contexte 'logger').

    Le type de retour est `Any` car structlog renvoie un `BoundLoggerLazyProxy`
    qui n'a pas de stub propre — on accepte le compromis plutôt que de wrapper.
    """
    if not _configured:
        setup_logging()
    log = structlog.get_logger()
    if name:
        log = log.bind(logger=name)
    return log
