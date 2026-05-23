"""
PURPOSE: Feedback collection + the learning loop (Phase 6 & 7).

Phase 6 is collection: every feedback event — at answer, citation, chunk, or
source level — is written to the `feedback` table verbatim.

Phase 7 is the loop: recording feedback also *updates ranking signals* so the
next retrieval is better. A chunk marked useful gains usefulness; a domain
flagged bad loses trust; content flagged outdated gets `refresh_needed=TRUE`.

HARD RULE: feedback updates metadata and ranking signals ONLY. It never
rewrites scraped chunk text — that would let one user's opinion corrupt the
corpus for everyone.
"""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request import FeedbackLevel, FeedbackRequest, FeedbackType
from app.services.scoring_service import ScoringService
from app.services.source_trust_service import SourceTrustService, domain_of

logger = logging.getLogger(__name__)

# Feedback types that count as a positive signal; everything else is negative.
_POSITIVE = {FeedbackType.USEFUL}


class FeedbackService:
    """Records feedback events and folds them into ranking signals."""

    def __init__(self, db: AsyncSession, workspace_id: str):
        self.db = db
        self.workspace_id = workspace_id
        self.scoring = ScoringService()
        self.trust = SourceTrustService(db, workspace_id)

    # ----------------------------------------------------------- record

    async def record(self, req: FeedbackRequest) -> tuple[str, list[str]]:
        """
        Persist a feedback event and apply its ranking-signal effects.

        Returns (feedback_id, effects) where `effects` is a human-readable list
        of what was updated — surfaced on the API response for transparency.
        """
        effects: list[str] = []
        feedback_id = str(uuid.uuid4())

        # Resolve the source URL/domain this feedback ultimately points at.
        source_url = await self._resolve_source_url(req)
        source_domain = domain_of(source_url) if source_url else None

        # --- Phase 6: write the event verbatim ----------------------------
        await self.db.execute(
            text(
                """
                INSERT INTO feedback
                    (id, query_id, result_id, chunk_id, source_domain,
                     source_url, level, feedback_type, comment, workspace_id)
                VALUES
                    (:id, :query_id, :result_id, :chunk_id, :domain,
                     :url, :level, :ftype, :comment, :ws)
                """
            ),
            {
                "id": feedback_id,
                "query_id": req.query_id,
                "result_id": req.result_id,
                "chunk_id": req.chunk_id,
                "domain": source_domain,
                "url": source_url,
                "level": req.level.value,
                "ftype": req.feedback_type.value,
                "comment": req.comment,
                "ws": self.workspace_id,
            },
        )
        effects.append(f"recorded {req.feedback_type.value} feedback at {req.level.value} level")

        # --- Phase 7: apply ranking-signal effects ------------------------
        if req.chunk_id:
            applied = await self._apply_chunk_feedback(req)
            effects.extend(applied)

        if source_url:
            await self.trust.apply_feedback(source_url, req.feedback_type.value)
            effects.append(f"adjusted learned trust for {source_domain}")

        if req.feedback_type == FeedbackType.OUTDATED and req.result_id:
            await self._flag_result_refresh(req.result_id)
            effects.append("flagged source result for refresh")

        logger.info(
            "FeedbackService: %s/%s recorded (%s)",
            req.level.value, req.feedback_type.value, feedback_id,
        )
        return feedback_id, effects

    # --------------------------------------------------------- effects

    async def _apply_chunk_feedback(self, req: FeedbackRequest) -> list[str]:
        """Update a chunk's feedback counters + usefulness score."""
        positive = req.feedback_type in _POSITIVE
        col = "positive_feedback_count" if positive else "negative_feedback_count"
        try:
            row = (
                await self.db.execute(
                    text(
                        f"""
                        UPDATE chunks
                        SET {col} = {col} + 1
                        WHERE id = :cid AND workspace_id = :ws
                        RETURNING positive_feedback_count, negative_feedback_count
                        """
                    ),
                    {"cid": req.chunk_id, "ws": self.workspace_id},
                )
            ).first()
            if not row:
                return ["chunk not found — counter update skipped"]

            usefulness = self.scoring.feedback_score(
                int(row.positive_feedback_count), int(row.negative_feedback_count)
            )
            await self.db.execute(
                text("UPDATE chunks SET usefulness_score = :u WHERE id = :cid AND workspace_id = :ws"),
                {"u": usefulness, "cid": req.chunk_id, "ws": self.workspace_id},
            )
            return [
                f"chunk usefulness recomputed → {usefulness:.3f} "
                f"({row.positive_feedback_count}+/{row.negative_feedback_count}-)"
            ]
        except Exception as e:  # noqa: BLE001
            logger.warning("FeedbackService: chunk feedback update failed: %s", e)
            return ["chunk usefulness update failed (non-fatal)"]

    async def _flag_result_refresh(self, result_id: str) -> None:
        try:
            await self.db.execute(
                text("UPDATE results SET refresh_needed = TRUE WHERE id = :rid AND workspace_id = :ws"),
                {"rid": result_id, "ws": self.workspace_id},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("FeedbackService: refresh flag failed: %s", e)

    async def _resolve_source_url(self, req: FeedbackRequest) -> str | None:
        """Find the URL behind this feedback: explicit → result → chunk's result."""
        if req.source_url:
            return req.source_url
        try:
            if req.result_id:
                row = (
                    await self.db.execute(
                        text("SELECT url FROM results WHERE id = :rid AND workspace_id = :ws"),
                        {"rid": req.result_id, "ws": self.workspace_id},
                    )
                ).first()
                if row:
                    return row.url
            if req.chunk_id:
                row = (
                    await self.db.execute(
                        text(
                            "SELECT r.url FROM results r "
                            "JOIN chunks c ON c.result_id = r.id WHERE c.id = :cid AND c.workspace_id = :ws"
                        ),
                        {"cid": req.chunk_id, "ws": self.workspace_id},
                    )
                ).first()
                if row:
                    return row.url
        except Exception as e:  # noqa: BLE001
            logger.warning("FeedbackService: source URL resolution failed: %s", e)
        return None

    # ------------------------------------------------------------ stats

    async def stats(self) -> dict:
        """Aggregate feedback analytics for the dashboard."""
        out: dict = {
            "total": 0, "by_type": {}, "by_level": {}, "satisfaction_rate": 0.0,
            "best_sources": [], "worst_sources": [],
            "most_flagged_chunks": [], "sources_needing_refresh": [],
        }
        try:
            by_type = (
                await self.db.execute(
                    text("SELECT feedback_type, COUNT(*) AS n FROM feedback WHERE workspace_id = :ws GROUP BY feedback_type"),
                    {"ws": self.workspace_id}
                )
            ).fetchall()
            by_level = (
                await self.db.execute(
                    text("SELECT level, COUNT(*) AS n FROM feedback WHERE workspace_id = :ws GROUP BY level"),
                    {"ws": self.workspace_id}
                )
            ).fetchall()
            out["by_type"] = {r.feedback_type: int(r.n) for r in by_type}
            out["by_level"] = {r.level: int(r.n) for r in by_level}
            total = sum(out["by_type"].values())
            out["total"] = total
            positive = out["by_type"].get(FeedbackType.USEFUL.value, 0)
            out["satisfaction_rate"] = round(positive / total, 4) if total else 0.0

            flagged = (
                await self.db.execute(
                    text(
                        """
                        SELECT chunk_id, COUNT(*) AS flags
                        FROM feedback
                        WHERE chunk_id IS NOT NULL
                          AND feedback_type <> 'useful'
                          AND workspace_id = :ws
                        GROUP BY chunk_id
                        ORDER BY flags DESC
                        LIMIT 10
                        """
                    ),
                    {"ws": self.workspace_id}
                )
            ).fetchall()
            out["most_flagged_chunks"] = [
                {"chunk_id": r.chunk_id, "flags": int(r.flags)} for r in flagged
            ]

            refresh = (
                await self.db.execute(
                    text(
                        "SELECT domain, outdated_count FROM source_trust "
                        "WHERE refresh_needed = TRUE AND workspace_id = :ws ORDER BY outdated_count DESC LIMIT 10"
                    ),
                    {"ws": self.workspace_id}
                )
            ).fetchall()
            out["sources_needing_refresh"] = [
                {"domain": r.domain, "outdated_count": int(r.outdated_count)} for r in refresh
            ]

            out["best_sources"] = await self.trust.best_sources(10)
            out["worst_sources"] = await self.trust.worst_sources(10)
        except Exception as e:  # noqa: BLE001
            logger.warning("FeedbackService: stats aggregation failed: %s", e)
        return out
