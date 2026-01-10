"""Observability module - Telemetry, Contract Records, and Patch Manifests.

This module provides:
- Canonical hash utilities for deterministic hashing
- Contract records for artifact integrity tracking
- Telemetry events for pipeline observability
- Patch manifests for patch application tracking
"""

from observability.canonical_hash import (
    compute_content_hash_sha256,
    compute_text_hash_sha256,
    compute_file_hash_sha256,
    compute_json_file_hash_sha256,
)

from observability.contract_record import (
    ContractRecord,
    ContractLedger,
)

from observability.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryCounts,
    TelemetryFlags,
    BlockedReason,
    init_telemetry,
    get_telemetry,
)

from observability.patch_manifest import (
    PatchManifest,
    PatchEntry,
    PatchPolicy,
    PatchManifestStore,
    PATCH_MANIFEST_SCHEMA_VERSION,
    verify_manifest_prebuild,
)

__all__ = [
    # Canonical hash
    "compute_content_hash_sha256",
    "compute_text_hash_sha256",
    "compute_file_hash_sha256",
    "compute_json_file_hash_sha256",
    # Contract record
    "ContractRecord",
    "ContractLedger",
    # Telemetry
    "TelemetryEmitter",
    "TelemetryEvent",
    "TelemetryCounts",
    "TelemetryFlags",
    "BlockedReason",
    "init_telemetry",
    "get_telemetry",
    # Patch manifest
    "PatchManifest",
    "PatchEntry",
    "PatchPolicy",
    "PatchManifestStore",
    "PATCH_MANIFEST_SCHEMA_VERSION",
    "verify_manifest_prebuild",
]
