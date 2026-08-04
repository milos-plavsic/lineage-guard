from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

from lineage_guard.consistency import LineageRead, ReadConsistency, lineage_receipt
from lineage_guard.domain import Asset, LineageTarget
from lineage_guard.immune_memory import ImmuneMemoryRecord, encode_memory, parse_memories


class McpIntegrationError(RuntimeError):
    """Raised when the MCP server cannot provide a safe, usable response."""


MAX_TOOL_PAYLOAD_BYTES = 2_000_000

_SAFE_ENVIRONMENT_KEYS = frozenset(
    {
        "HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LOCALAPPDATA",
        "NO_PROXY",
        "PATH",
        "PATHEXT",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "UV_CACHE_DIR",
        "WINDIR",
        "XDG_CACHE_HOME",
    }
)


class ToolSession(Protocol):
    async def list_tools(self) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class StdioMcpConfig:
    gms_url: str
    token: str
    command: str = "uvx"
    package: str = "mcp-server-datahub@0.6.0"
    enable_mutations: bool = False

    def environment(self) -> dict[str, str]:
        # Do not expose unrelated CI or developer secrets to the child process.
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in _SAFE_ENVIRONMENT_KEYS
        }
        environment.update(
            {
                "DATAHUB_GMS_URL": self.gms_url,
                "DATAHUB_GMS_TOKEN": self.token,
                "TOOLS_IS_MUTATION_ENABLED": str(self.enable_mutations).lower(),
            }
        )
        return environment


@asynccontextmanager
async def open_stdio_session(config: StdioMcpConfig) -> AsyncIterator[ToolSession]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as error:
        raise McpIntegrationError(
            "MCP support is not installed; run `uv sync --extra mcp`."
        ) from error

    parameters = StdioServerParameters(
        command=config.command,
        args=[config.package],
        env=config.environment(),
    )
    try:
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            await session.initialize()
            yield session
    except OSError as error:
        raise McpIntegrationError(f"Could not start DataHub MCP server: {error}") from error


class DataHubMcpGraph:
    REQUIRED_READ_TOOLS = frozenset({"get_lineage", "get_entities"})
    REQUIRED_WRITE_TOOLS = frozenset({"update_description", "add_tags"})
    FIELD_PATH_TOOL = "get_lineage_paths_between"
    MAX_FIELD_PATH_CHECKS = 20
    NATIVE_MEMORY_TOOLS = frozenset({"save_document", "search_documents"})

    def __init__(
        self,
        session: ToolSession,
        assets: Mapping[str, Asset],
        targets: tuple[LineageTarget, ...],
        *,
        source_urn: str = "",
        max_hops: int = 0,
        max_results: int = 0,
        source_field: str | None = None,
        consistency: ReadConsistency | None = None,
        memory_documents: tuple[str, ...] = (),
        native_memory: bool = False,
    ) -> None:
        self._session = session
        self._assets = dict(assets)
        self._targets = targets
        self._source_urn = source_urn
        self._max_hops = max_hops
        self._max_results = max_results
        self._source_field = source_field
        self._consistency = consistency or ReadConsistency()
        self._memory_documents = memory_documents
        self._native_memory = native_memory
        self._pending: list[tuple[str, dict[str, Any]]] = []
        self._completed: list[tuple[str, dict[str, Any]]] = []

    @classmethod
    async def load(
        cls,
        session: ToolSession,
        source_urn: str,
        *,
        max_hops: int = 5,
        max_results: int = 100,
        source_field: str | None = None,
    ) -> DataHubMcpGraph:
        available = {tool.name for tool in (await session.list_tools()).tools}
        missing = cls.REQUIRED_READ_TOOLS - available
        if missing:
            raise McpIntegrationError(f"DataHub MCP server is missing tools: {sorted(missing)}")

        lineage_result = await session.call_tool(
            "get_lineage",
            {
                "urn": source_urn,
                "upstream": False,
                "max_hops": max_hops,
                "max_results": max_results,
            },
        )
        lineage = _tool_payload(lineage_result)
        search_results = _bounded_lineage_results(lineage, max_results)
        targets = tuple(_lineage_target(item) for item in search_results)
        if source_field:
            field_result = await session.call_tool(
                "get_lineage",
                {
                    "urn": source_urn,
                    "column": source_field,
                    "upstream": False,
                    "max_hops": max_hops,
                    "max_results": max_results,
                },
            )
            field_payload = _tool_payload(field_result)
            affected = {
                _lineage_target(item).urn
                for item in _bounded_lineage_results(field_payload, max_results)
            }
            if (
                not affected
                and cls.FIELD_PATH_TOOL in available
                and len(targets) <= cls.MAX_FIELD_PATH_CHECKS
            ):
                affected = await cls._exact_field_path_targets(
                    session, source_urn, source_field, targets
                )
            targets = tuple(
                LineageTarget(
                    target.urn,
                    target.distance,
                    (source_field,) if target.urn in affected else (),
                    False,
                )
                for target in targets
            )
        urns = [source_urn, *(target.urn for target in targets)]
        entities_result = await session.call_tool("get_entities", {"urns": urns})
        entities_payload = _tool_payload(entities_result)
        entities = entities_payload if isinstance(entities_payload, list) else [entities_payload]
        assets = {_asset(entity).urn: _asset(entity) for entity in entities}
        missing_entities = set(urns) - assets.keys()
        if missing_entities:
            raise McpIntegrationError(
                f"DataHub returned incomplete entity context: {sorted(missing_entities)}"
            )
        native_memory = available >= cls.NATIVE_MEMORY_TOOLS
        memory_documents: tuple[str, ...] = ()
        if native_memory:
            memory_documents = await cls._load_memory_documents(session, source_urn)
        return cls(
            session,
            assets,
            targets,
            source_urn=source_urn,
            max_hops=max_hops,
            max_results=max_results,
            source_field=source_field,
            memory_documents=memory_documents,
            native_memory=native_memory,
        )

    @staticmethod
    async def _load_memory_documents(session: ToolSession, source_urn: str) -> tuple[str, ...]:
        subject_key = sha256(source_urn.encode()).hexdigest()[:20]
        result = await session.call_tool(
            "search_documents",
            {"query": f'"lineage-guard-memory-{subject_key}"', "num_results": 100},
        )
        payload = _tool_payload(result)
        search_results = payload.get("searchResults", []) if isinstance(payload, Mapping) else []
        if not isinstance(search_results, list) or len(search_results) > 100:
            raise McpIntegrationError("DataHub returned invalid immune-memory document results")
        urns = []
        for item in search_results:
            entity = item.get("entity") if isinstance(item, Mapping) else None
            urn = entity.get("urn") if isinstance(entity, Mapping) else None
            if not isinstance(urn, str) or not urn.startswith("urn:li:document:"):
                raise McpIntegrationError("DataHub returned malformed immune-memory document")
            urns.append(urn)
        if not urns:
            return ()
        entities = _tool_payload(await session.call_tool("get_entities", {"urns": urns}))
        values = entities if isinstance(entities, list) else [entities]
        if len(values) != len(urns):
            raise McpIntegrationError("DataHub returned incomplete immune-memory documents")
        return tuple(_document_text(value) for value in values)

    @classmethod
    async def _exact_field_path_targets(
        cls,
        session: ToolSession,
        source_urn: str,
        source_field: str,
        targets: tuple[LineageTarget, ...],
    ) -> set[str]:
        affected = set()
        for target in targets:
            result = await session.call_tool(
                cls.FIELD_PATH_TOOL,
                {
                    "source_urn": source_urn,
                    "target_urn": target.urn,
                    "source_column": source_field,
                    "target_column": source_field,
                    "direction": "downstream",
                },
            )
            try:
                payload = _tool_payload(result)
            except McpIntegrationError:
                continue
            if _confirms_exact_field_path(payload, source_urn, target.urn, source_field):
                affected.add(target.urn)
        return affected

    def get_asset(self, urn: str) -> Asset:
        try:
            return self._assets[urn]
        except KeyError as error:
            raise LookupError(f"Asset not present in MCP snapshot: {urn}") from error

    def get_downstream_lineage(
        self, urn: str, max_hops: int, *, field: str | None = None
    ) -> tuple[LineageTarget, ...]:
        del urn
        del field
        return tuple(target for target in self._targets if target.distance <= max_hops)

    def read_downstream_lineage(
        self, urn: str, max_hops: int, *, field: str | None = None
    ) -> LineageRead:
        """Return lineage with a fail-closed, content-addressed epistemic receipt."""
        if urn != self._source_urn:
            raise LookupError(f"MCP snapshot was loaded for a different source: {urn}")
        if max_hops > self._max_hops:
            raise ValueError("Receipt scope exceeds the MCP snapshot hop bound")
        if field != self._source_field:
            raise ValueError("Receipt field does not match the MCP snapshot field scope")
        targets = self.get_downstream_lineage(urn, max_hops, field=field)
        receipt = lineage_receipt(
            source_urn=urn,
            max_hops=max_hops,
            max_results=self._max_results,
            source_field=field,
            targets=targets,
            consistency=self._consistency,
        )
        return LineageRead(targets, receipt)

    def append_incident_summary(self, urn: str, summary: str) -> None:
        self._queue(
            "update_description",
            {"entity_urn": urn, "operation": "append", "description": summary},
        )

    def get_immune_memories(self, urn: str) -> tuple[ImmuneMemoryRecord, ...]:
        asset = self.get_asset(urn)
        descriptions = (*self._memory_documents, asset.description)
        records = []
        seen = set()
        for description in descriptions:
            for record in parse_memories(description):
                if record.subject_urn == urn and record.record_digest not in seen:
                    records.append(record)
                    seen.add(record.record_digest)
        return tuple(records)

    def append_immune_memory(self, urn: str, record: ImmuneMemoryRecord) -> None:
        if record.subject_urn != urn:
            raise ValueError("immune memory subject does not match the target asset")
        existing = self.get_immune_memories(urn)
        if record.record_digest in {item.record_digest for item in existing}:
            return
        block = encode_memory(record)
        if self._native_memory:
            subject_key = sha256(urn.encode()).hexdigest()[:20]
            self._queue(
                "save_document",
                {
                    "document_type": "Decision",
                    "title": f"LineageGuard {record.record_type.value}: {record.incident_id}",
                    "content": f"lineage-guard-memory-{subject_key}\n\n{block}",
                    "topics": ["lineage-guard", "immune-memory", record.record_type.value],
                    "related_assets": [urn],
                },
            )
        else:
            self._queue(
                "update_description",
                {"entity_urn": urn, "operation": "append", "description": block},
            )

    def add_tag(self, urn: str, tag: str) -> None:
        if not tag.startswith("urn:li:tag:"):
            raise ValueError("DataHub tags must be supplied as tag URNs")
        self._queue("add_tags", {"tag_urns": [tag], "entity_urns": [urn]})

    def _queue(self, name: str, arguments: dict[str, Any]) -> None:
        operation = (name, arguments)
        if operation not in self._pending and operation not in self._completed:
            self._pending.append(operation)

    async def flush(self) -> None:
        if not self._pending:
            return
        available = {tool.name for tool in (await self._session.list_tools()).tools}
        required = set(self.REQUIRED_WRITE_TOOLS)
        if any(name == "save_document" for name, _ in self._pending):
            required.add("save_document")
        missing = required - available
        if missing:
            raise McpIntegrationError(
                "Mutation tools are unavailable. Set TOOLS_IS_MUTATION_ENABLED=true "
                f"for the MCP server. Missing: {sorted(missing)}"
            )
        # Tag addition is idempotent; description append is not. Execute the
        # append last so a failed tag prerequisite cannot create duplicates on retry.
        self._pending.sort(key=lambda operation: operation[0] == "update_description")
        while self._pending:
            name, arguments = self._pending[0]
            result = await self._session.call_tool(name, arguments)
            if getattr(result, "isError", False):
                raise McpIntegrationError(
                    f"DataHub MCP mutation failed: {name}; "
                    f"{len(self._pending)} operation(s) remain retryable"
                )
            self._completed.append(self._pending.pop(0))


def _document_text(entity: Any) -> str:
    if not isinstance(entity, Mapping):
        raise McpIntegrationError("DataHub returned malformed immune-memory document content")
    info = entity.get("documentInfo") or entity.get("info") or {}
    contents = info.get("contents") if isinstance(info, Mapping) else None
    text = contents.get("text") if isinstance(contents, Mapping) else None
    if not isinstance(text, str):
        raise McpIntegrationError("DataHub immune-memory document has no textual content")
    return text


def _bounded_lineage_results(payload: Any, max_results: int) -> list[Mapping[str, Any]]:
    downstreams = payload.get("downstreams", {}) if isinstance(payload, Mapping) else {}
    search_results = downstreams.get("searchResults", [])
    if not isinstance(search_results, list) or len(search_results) > max_results:
        raise McpIntegrationError("DataHub returned an invalid lineage result count")
    total = downstreams.get("total")
    if isinstance(total, int) and total > len(search_results):
        raise McpIntegrationError("DataHub lineage response is truncated")
    if len(search_results) == max_results and total is None:
        raise McpIntegrationError(
            "DataHub lineage may be truncated at max_results; increase the bound or narrow scope"
        )
    if not all(isinstance(item, Mapping) for item in search_results):
        raise McpIntegrationError("DataHub returned malformed lineage entries")
    return search_results


def _confirms_exact_field_path(payload: Any, source_urn: str, target_urn: str, field: str) -> bool:
    if not isinstance(payload, Mapping):
        return False
    source = payload.get("source")
    target = payload.get("target")
    paths = payload.get("paths")
    if (
        not isinstance(source, Mapping)
        or source.get("urn") != source_urn
        or source.get("column") != field
        or not isinstance(target, Mapping)
        or target.get("urn") != target_urn
        or target.get("column") != field
        or not isinstance(paths, list)
        or not paths
        or payload.get("pathCount") != len(paths)
    ):
        return False
    for path_object in paths:
        nodes = path_object.get("path") if isinstance(path_object, Mapping) else None
        if not isinstance(nodes, list) or len(nodes) < 2:
            continue
        first, last = nodes[0], nodes[-1]
        first_parent = first.get("parent") if isinstance(first, Mapping) else None
        last_parent = last.get("parent") if isinstance(last, Mapping) else None
        if (
            isinstance(first, Mapping)
            and isinstance(last, Mapping)
            and isinstance(first_parent, Mapping)
            and isinstance(last_parent, Mapping)
            and first.get("fieldPath") == field
            and last.get("fieldPath") == field
            and first_parent.get("urn") == source_urn
            and last_parent.get("urn") == target_urn
        ):
            return True
    return False


def _tool_payload(result: Any) -> Any:
    if getattr(result, "isError", False):
        raise McpIntegrationError("DataHub MCP tool returned an error")
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if len(json.dumps(structured).encode()) > MAX_TOOL_PAYLOAD_BYTES:
            raise McpIntegrationError("DataHub MCP structured payload exceeds the safety limit")
        return structured.get("result", structured) if isinstance(structured, dict) else structured
    text_parts = [item.text for item in getattr(result, "content", []) if hasattr(item, "text")]
    if not text_parts:
        raise McpIntegrationError("DataHub MCP tool returned no structured or textual payload")
    rendered = "".join(text_parts)
    if len(rendered.encode()) > MAX_TOOL_PAYLOAD_BYTES:
        raise McpIntegrationError("DataHub MCP textual payload exceeds the safety limit")
    try:
        return json.loads(rendered)
    except json.JSONDecodeError as error:
        raise McpIntegrationError("DataHub MCP tool returned invalid JSON") from error


def _lineage_target(item: Mapping[str, Any]) -> LineageTarget:
    entity = item.get("entity") or {}
    urn = entity.get("urn")
    degree = item.get("degree")
    if not isinstance(urn, str) or not isinstance(degree, int | str):
        raise McpIntegrationError("Malformed lineage result from DataHub MCP")
    distance = 3 if str(degree) == "3+" else int(degree)
    return LineageTarget(urn, distance)


def _asset(entity: Mapping[str, Any]) -> Asset:
    urn = entity.get("urn")
    if not isinstance(urn, str):
        raise McpIntegrationError("DataHub entity is missing its URN")
    properties = entity.get("properties") or {}
    name = properties.get("name") or entity.get("name") or urn
    description = properties.get("description") or entity.get("description") or ""
    ownership = entity.get("ownership") or {}
    owners = tuple(
        assignment.get("owner", {}).get("properties", {}).get("displayName")
        or assignment.get("owner", {}).get("properties", {}).get("name")
        or assignment.get("owner", {}).get("urn", "unknown")
        for assignment in ownership.get("owners", [])
    )
    tags = tuple(
        association.get("tag", {}).get("properties", {}).get("name")
        or association.get("tag", {}).get("urn", "unknown")
        for association in (entity.get("globalTags") or {}).get("tags", [])
    )
    usage = entity.get("usageStats") or {}
    usage_count = int(usage.get("totalSqlQueries") or usage.get("totalQueries") or 0)
    return Asset(urn, str(name), str(description), owners, tags, usage_count)
