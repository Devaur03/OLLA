"""
PURPOSE: Named-entity extraction on chunks (COMPARISON_README §10.12).

Uses spaCy's `en_core_web_sm` model when available. spaCy and its model are
*optional* — if either is missing the service degrades to a no-op so that
deployments without it keep working. Enable via ENABLE_ENTITY_EXTRACTION=true.

Extracted entities are stored on `chunks.entities` (JSONB) and enable queries
like "find chunks mentioning a PERSON named ...".
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class EntityService:
    """Lazy-loading spaCy NER wrapper. Safe to instantiate even if spaCy absent."""

    _nlp = None            # shared spaCy pipeline (loaded once)
    _load_failed = False   # remember failure so we do not retry every call

    def __init__(self) -> None:
        self.enabled = settings.enable_entity_extraction

    def _ensure_model(self) -> bool:
        """Load the spaCy model on first use. Returns True if usable."""
        if EntityService._nlp is not None:
            return True
        if EntityService._load_failed or not self.enabled:
            return False
        try:
            import spacy  # noqa: PLC0415 — optional dependency, imported lazily

            EntityService._nlp = spacy.load(
                "en_core_web_sm", disable=["lemmatizer", "tagger", "parser"]
            )
            logger.info("EntityService: loaded spaCy en_core_web_sm")
            return True
        except Exception as e:  # noqa: BLE001
            EntityService._load_failed = True
            logger.warning(
                "EntityService: spaCy unavailable (%s) — entity extraction disabled. "
                "Install with: pip install spacy && python -m spacy download en_core_web_sm",
                e,
            )
            return False

    def extract(self, text: str) -> list[dict]:
        """
        Return a de-duplicated list of {"text", "label"} entity dicts.
        Returns [] when extraction is disabled or unavailable.
        """
        if not text or not self.enabled or not self._ensure_model():
            return []
        try:
            doc = EntityService._nlp(text[:100_000])  # cap for very long inputs
            seen: set[tuple[str, str]] = set()
            out: list[dict] = []
            for ent in doc.ents:
                key = (ent.text.strip(), ent.label_)
                if key[0] and key not in seen:
                    seen.add(key)
                    out.append({"text": key[0], "label": key[1]})
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("EntityService: extraction failed: %s", e)
            return []
