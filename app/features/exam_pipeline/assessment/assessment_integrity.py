"""Tamper-evident assessment result integrity and evidence-chain hashing."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any


class AssessmentIntegrity:
    ALGORITHM = "sha256"
    VERSION = "v1"

    @classmethod
    def _default(cls, value: Any):
        if isinstance(value, datetime):
            return value.isoformat()
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, set):
            return sorted(value)
        raise TypeError(f"Unsupported value: {type(value)!r}")

    @classmethod
    def canonical_bytes(cls, value: Any) -> bytes:
        return json.dumps(value, default=cls._default, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def digest(cls, value: Any) -> str:
        key = os.getenv("ASSESSMENT_INTEGRITY_KEY")
        if key:
            return hmac.new(key.encode("utf-8"), cls.canonical_bytes(value), hashlib.sha256).hexdigest()
        return hashlib.sha256(cls.canonical_bytes(value)).hexdigest()

    @classmethod
    def build_manifest(cls, *, result, evidence_records: list[Any] | None = None) -> dict[str, Any]:
        evidence_records = evidence_records or []
        evidence_hashes = []
        previous = "GENESIS"
        for index, evidence in enumerate(evidence_records):
            payload = {
                "index": index,
                "previous_hash": previous,
                "evidence": cls._safe_evidence(evidence),
            }
            current = cls.digest(payload)
            evidence_hashes.append(current)
            previous = current

        timeline_hashes = []
        previous = "GENESIS"
        for index, event in enumerate(result.timeline):
            payload = {
                "index": index,
                "previous_hash": previous,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "goal_id": event.goal_id,
                "indicator_id": event.indicator_id,
                "details": event.details,
            }
            current = cls.digest(payload)
            timeline_hashes.append(current)
            previous = current

        component = {
            "session_id": result.session_id,
            "student_id": result.student_id,
            "completed": result.completed,
            "goals": result.goals,
            "metrics": result.metrics,
            "evidence_chain_head": previous if evidence_hashes else "GENESIS",
            "evidence_hashes": evidence_hashes,
            "timeline_hashes": timeline_hashes,
        }
        root = cls.digest(component)
        return {
            "version": cls.VERSION,
            "algorithm": "hmac-sha256" if os.getenv("ASSESSMENT_INTEGRITY_KEY") else cls.ALGORITHM,
            "root_hash": root,
            "evidence_count": len(evidence_hashes),
            "evidence_chain_head": evidence_hashes[-1] if evidence_hashes else "GENESIS",
            "timeline_count": len(timeline_hashes),
            "timeline_chain_head": timeline_hashes[-1] if timeline_hashes else "GENESIS",
            "evidence_hashes": evidence_hashes,
            "timeline_hashes": timeline_hashes,
        }

    @classmethod
    def _safe_evidence(cls, evidence: Any) -> dict[str, Any]:
        return {
            "indicator_id": getattr(evidence, "indicator_id", None),
            "achievement_level": getattr(evidence, "achievement_level", None),
            "confidence": getattr(evidence, "confidence", None),
            "evidence_strength": getattr(evidence, "evidence_strength", None),
            "indicator_demonstrated": getattr(evidence, "indicator_demonstrated", None),
            "bloom_level": getattr(evidence, "bloom_level", None),
            "missing_elements": list(getattr(evidence, "missing_elements", []) or []),
        }

    @classmethod
    def verify_manifest(cls, *, result, manifest: dict[str, Any], evidence_records: list[Any] | None = None) -> dict[str, Any]:
        expected = cls.build_manifest(result=result, evidence_records=evidence_records)
        checks = {
            "root_hash": hmac.compare_digest(str(manifest.get("root_hash", "")), str(expected["root_hash"])),
            "evidence_chain": manifest.get("evidence_hashes", []) == expected["evidence_hashes"],
            "timeline_chain": manifest.get("timeline_hashes", []) == expected["timeline_hashes"],
        }
        return {"valid": all(checks.values()), "checks": checks, "algorithm": expected["algorithm"], "version": expected["version"]}
