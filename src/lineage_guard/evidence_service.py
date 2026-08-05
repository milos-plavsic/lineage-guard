from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lineage_guard.evidence_chain import (
    DetachedAttestation,
    verify_attestation,
    verify_evidence_chain,
)
from lineage_guard.immune_memory import ImmuneMemoryRecord


class EvidenceQueryService:
    """Bounded, read-only verification surface for untrusted evidence bundles."""

    def verify_chain(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not isinstance(records, (list, tuple)):
            raise ValueError("records must be an array")
        parsed = tuple(ImmuneMemoryRecord.from_dict(record) for record in records)
        return verify_evidence_chain(parsed).as_dict()

    def get_record_state(
        self, records: Sequence[Mapping[str, Any]], record_digest: str
    ) -> dict[str, Any]:
        verification = self.verify_chain(records)
        if not verification["valid"]:
            raise ValueError("evidence chain is invalid")
        state = next(
            (
                item["state"]
                for item in verification["states"]
                if item["record_digest"] == record_digest
            ),
            None,
        )
        if state is None:
            raise KeyError("record digest is absent from the evidence chain")
        return {"record_digest": record_digest, "state": state}

    def verify_detached_attestation(
        self, attestation: Mapping[str, Any], secret: str
    ) -> dict[str, Any]:
        if not isinstance(attestation, Mapping):
            raise ValueError("attestation must be an object")
        if not isinstance(secret, str):
            raise ValueError("secret must be text")
        try:
            parsed = DetachedAttestation(**attestation)
        except TypeError as error:
            raise ValueError("attestation is malformed") from error
        return {
            "record_digest": parsed.record_digest,
            "key_id": parsed.key_id,
            "valid": verify_attestation(parsed, secret=secret.encode()),
        }
