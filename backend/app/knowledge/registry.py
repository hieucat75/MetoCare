"""KnowledgeRegistry — single access point for all medical knowledge cards.

Cards are loaded from YAML files in the configured knowledge_base_path.
Never hardcode file paths in business logic.
Registry is a singleton per process; call reset_registry() in tests.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .schema import KnowledgeCard

logger = logging.getLogger("metocare.knowledge")

# Configurable path — override with KNOWLEDGE_BASE_PATH env var
DEFAULT_KNOWLEDGE_PATH = Path(__file__).parent / "cards"


class KnowledgeRegistry:
    def __init__(self, knowledge_base_path: Path | None = None) -> None:
        self._path = knowledge_base_path or Path(
            os.getenv("KNOWLEDGE_BASE_PATH", str(DEFAULT_KNOWLEDGE_PATH))
        )
        self._cards: dict[str, KnowledgeCard] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load_all()

    def _load_all(self) -> None:
        """Load all YAML cards from knowledge_base_path recursively."""
        if not self._path.exists():
            logger.warning("Knowledge base path does not exist: %s", self._path)
            self._loaded = True
            return

        for yaml_file in self._path.rglob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                card = KnowledgeCard.from_dict(data)
                if card.knowledge_id in self._cards:
                    logger.warning(
                        "Duplicate knowledge_id '%s' in %s — skipping",
                        card.knowledge_id,
                        yaml_file,
                    )
                    continue
                self._cards[card.knowledge_id] = card
                logger.debug("Loaded knowledge card: %s v%s", card.knowledge_id, card.version)
            except Exception as e:
                logger.error("Failed to load knowledge card %s: %s", yaml_file, e)

        self._loaded = True
        logger.info(
            "KnowledgeRegistry loaded %d cards from %s", len(self._cards), self._path
        )

    def lookup(self, knowledge_id: str, language: str = "vi") -> KnowledgeCard | None:
        """Return card by knowledge_id and language, or None if not found."""
        self._ensure_loaded()
        card = self._cards.get(knowledge_id)
        if card and card.language == language and card.status != "deprecated":
            return card
        return None

    def search(self, query: str, language: str = "vi") -> list[KnowledgeCard]:
        """Simple text search across knowledge_id, tags, display_name_vi, short_summary_vi."""
        self._ensure_loaded()
        q = query.lower()
        results = []
        for card in self._cards.values():
            if card.language != language or card.status == "deprecated":
                continue
            if (
                q in card.knowledge_id.lower()
                or q in card.display_name_vi.lower()
                or q in card.short_summary_vi.lower()
                or any(q in tag.lower() for tag in card.tags)
            ):
                results.append(card)
        return results

    def related_cards(self, knowledge_id: str) -> list[KnowledgeCard]:
        """Return all KnowledgeCards referenced in related_cards list of given card."""
        self._ensure_loaded()
        card = self._cards.get(knowledge_id)
        if not card:
            return []
        result = []
        for rid in card.related_cards:
            related = self._cards.get(rid)
            if related and related.status != "deprecated":
                result.append(related)
        return result

    def version(self, knowledge_id: str) -> str | None:
        """Return version string of card, or None if not found."""
        self._ensure_loaded()
        card = self._cards.get(knowledge_id)
        return card.version if card else None

    def cards_for_insight(self, insight_id: str) -> list[KnowledgeCard]:
        """Return knowledge cards relevant to a specific insight card_id.

        Exact match first, then tag match.
        Returns only approved cards (or internal_review for dev).
        """
        self._ensure_loaded()
        result = []
        # Exact match
        card = self._cards.get(insight_id)
        if card and card.status not in ("deprecated", "draft"):
            result.append(card)
        # Tag match (insight_id as tag)
        for c in self._cards.values():
            if c.knowledge_id == insight_id:
                continue
            if (
                insight_id in c.tags
                and c.status not in ("deprecated", "draft")
                and c not in result
            ):
                result.append(c)
        return result[:3]  # Max 3 cards per insight — keep prompt size bounded

    def cards_for_patient_report(self, report: Any) -> list[KnowledgeCard]:
        """Return all relevant cards for a PatientInsightReport.

        Uses insight card_ids to lookup knowledge cards.
        Deduplicates. Returns max 5 cards to keep prompt size bounded.
        """
        self._ensure_loaded()
        from app.services.narrative_input import _get

        insights = _get(report, "insights", []) or []
        processed_insights: set[str] = set()  # track which insight card_ids we've processed
        seen_cards: set[str] = set()          # track which knowledge card ids we've added
        result: list[KnowledgeCard] = []

        for insight in insights:
            card_id = _get(insight, "card_id", "")
            if not card_id or card_id in processed_insights:
                continue
            processed_insights.add(card_id)
            cards = self.cards_for_insight(card_id)
            for c in cards:
                if c.knowledge_id not in seen_cards:
                    seen_cards.add(c.knowledge_id)
                    result.append(c)
                if len(result) >= 5:
                    return result

        return result

    def all_cards(self) -> list[KnowledgeCard]:
        """Return all loaded cards (for QA/testing)."""
        self._ensure_loaded()
        return list(self._cards.values())


# Singleton
_registry: KnowledgeRegistry | None = None


def get_registry(knowledge_base_path: Path | None = None) -> KnowledgeRegistry:
    # Not thread-safe; acceptable for current single-process app lifecycle.
    # Add a threading.Lock if multi-threaded registry initialization is needed.
    global _registry
    if _registry is None:
        _registry = KnowledgeRegistry(knowledge_base_path)
    return _registry


def reset_registry() -> None:
    """Test helper."""
    global _registry
    _registry = None
