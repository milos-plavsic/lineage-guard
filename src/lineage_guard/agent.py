from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Protocol

from lineage_guard.adapters.mcp import (
    DataHubMcpGraph,
    StdioMcpConfig,
    ToolSession,
    open_stdio_session,
)
from lineage_guard.domain import Action, IncidentReport
from lineage_guard.enforcement import EnforcementReceipt
from lineage_guard.events import QualityEvent
from lineage_guard.journal import ClaimDisposition, EventJournal, JournalError
from lineage_guard.remediation import RemediationGenerator
from lineage_guard.service import IncidentAnalyzer


class EventConflictError(RuntimeError):
    """Raised when an event ID is reused with a different payload."""


class EventBusyError(RuntimeError):
    """Raised when another worker currently owns the event lease."""


class Enforcer(Protocol):
    def enforce(self, report: IncidentReport) -> EnforcementReceipt: ...


SessionFactory = Callable[[StdioMcpConfig], AbstractAsyncContextManager[ToolSession]]


class IncidentAgent:
    """Durable observe-contextualize-decide-act agent with deterministic authority."""

    def __init__(
        self,
        journal: EventJournal,
        mcp_config: StdioMcpConfig,
        *,
        artifacts_root: Path | None = None,
        enforcer: Enforcer | None = None,
        session_factory: SessionFactory = open_stdio_session,
    ) -> None:
        if enforcer is not None and not mcp_config.enable_mutations:
            raise ValueError("orchestrator enforcement requires mutation approval")
        self._journal = journal
        self._mcp_config = mcp_config
        self._artifacts_root = artifacts_root
        self._enforcer = enforcer
        self._session_factory = session_factory

    async def process(self, event: QualityEvent) -> dict[str, Any]:
        claim = self._journal.claim(event)
        if claim.disposition == ClaimDisposition.DUPLICATE:
            if claim.result is None:
                raise JournalError("completed event has no durable result")
            return {**claim.result, "duplicate": True}
        if claim.disposition == ClaimDisposition.CONFLICT:
            raise EventConflictError("event ID was already used for a different payload")
        if claim.disposition == ClaimDisposition.BUSY:
            raise EventBusyError("event is already being processed")

        try:
            async with self._session_factory(self._mcp_config) as session:
                graph = await DataHubMcpGraph.load(
                    session,
                    event.signal.asset_urn,
                    source_field=event.signal.field,
                )
                analyzer = IncidentAnalyzer(graph)
                report = analyzer.analyze(event.signal)
                self._journal.record_transition(
                    event.event_id,
                    "context_resolved",
                    {"downstream_assets": len(report.decisions)},
                )
                counts = {
                    action: sum(decision.action == action for decision in report.decisions)
                    for action in Action
                }
                self._journal.record_transition(
                    event.event_id,
                    "decision_recorded",
                    {str(action): count for action, count in counts.items()},
                )
                if self._artifacts_root is not None:
                    RemediationGenerator().write(report, self._artifacts_root / report.incident_id)
                    self._journal.record_transition(
                        event.event_id, "artifacts_generated", {"count": 3}
                    )
                receipt = None
                if self._mcp_config.enable_mutations:
                    if self._enforcer is not None:
                        receipt = await asyncio.to_thread(self._enforcer.enforce, report)
                        self._journal.record_transition(
                            event.event_id,
                            "containment_enforced",
                            {"receipt_id": receipt.receipt_id},
                        )
                    analyzer.apply_writeback(report, approved=True)
                    await graph.flush()
                    self._journal.record_transition(event.event_id, "datahub_updated")
            result = {
                "schema_version": 1,
                "event_id": event.event_id,
                "incident_id": report.incident_id,
                "status": ("applied" if self._mcp_config.enable_mutations else "proposed"),
                "duplicate": False,
                "enforcement_receipt_id": receipt.receipt_id if receipt else None,
                "report": report.as_dict(),
            }
            self._journal.complete(event.event_id, report.incident_id, result)
            return result
        except Exception as error:
            self._journal.fail(event.event_id, type(error).__name__[:128])
            raise
