# Threat Model & Abuse Model

**Document Version:** 1.0
**Schema:** threat_model.v1
**Last Updated:** 2024-01-15

---

## 1. Scope

This threat model covers the **Bazari Engine** pipeline from input to release, including:

- **Intake**: Natural language, IDL Draft, and IDL input processing
- **Gates**: Contract Gate, Impact Gate, Approval Gate, Legacy Gate
- **Episodes**: Append-only execution records with integrity hashes
- **Approvals**: Human sign-off mechanism with audit trail
- **Change Requests**: Traceable modifications to existing episodes
- **AuditPack**: Verifiable ZIP archives for offline audit
- **Wizard**: Session-based onboarding flow
- **Blueprints**: Registry with integrity verification

### Out of Scope

- Infrastructure-level threats (network, OS, hardware)
- Cloud provider security
- User workstation security
- Social engineering attacks on operators
- Physical access attacks

### Trust Boundaries

| Boundary | Trust Level | Description |
|----------|-------------|-------------|
| User Input | Untrusted | All input specifications (natural, draft, IDL) |
| File System | Semi-trusted | Local file system access |
| Engine Core | Trusted | Pipeline orchestration and gates |
| Episode Store | Trusted | Append-only storage with integrity verification |
| Approval Authority | Trusted | Human approvers with valid credentials |

---

## 2. Assets

### Primary Assets

| Asset | Criticality | Description |
|-------|-------------|-------------|
| Episodes | HIGH | Immutable execution records with integrity hashes |
| RunLog | HIGH | Canonical execution log with `final_status`, `blocked_reason`, `error_codes` |
| Approvals | HIGH | Signed approval records linking approver to episode |
| Contracts | MEDIUM | IDL, SRS, IR, OpenAPI, Plan artifacts |
| AuditPack | HIGH | Verifiable ZIP for compliance and audit |
| Blueprint Registry | MEDIUM | Registered blueprints with content hashes |
| Generated Code | MEDIUM | Backend, frontend, database artifacts |

### Integrity Guarantees

| Mechanism | Asset Protected | Hash Algorithm |
|-----------|-----------------|----------------|
| `episode_root_hash_sha256` | Episode directory | SHA256 |
| `content_hash_sha256` | Individual contracts | SHA256 |
| `cr_hash_sha256` | Change requests | SHA256 |
| `root_hash_sha256` | AuditPack index | SHA256 |

---

## 3. Threat Actors

### TA-01 — Malicious Operator

**Profile:** Internal user with legitimate access attempting to bypass controls.

- Motivation: Deploy unauthorized changes, bypass approval process
- Capabilities: Full CLI access, file system access
- Constraints: Cannot modify engine binaries, logs are externally auditable

### TA-02 — Compromised Input

**Profile:** Attacker-controlled input specification.

- Motivation: Inject malicious code, access sensitive data
- Capabilities: Control over input text/JSON
- Constraints: Input is validated, gates block forbidden patterns

### TA-03 — Tampered Artifacts

**Profile:** Post-generation modification of artifacts.

- Motivation: Inject backdoors into generated code
- Capabilities: File system write access
- Constraints: Integrity hashes detect modifications, episodes are append-only

### TA-04 — Forged Approvals

**Profile:** Unauthorized approval injection.

- Motivation: Bypass human review gate
- Capabilities: File system access to approval directory
- Constraints: Approval must reference valid episode_id, verified at runtime

### TA-05 — Blueprint Tampering

**Profile:** Modification of registered blueprints.

- Motivation: Inject malicious patterns into generated systems
- Capabilities: File system access to registry
- Constraints: Content hash verification detects modifications

---

## 4. Threats by Category

### 4.1 Input Manipulation

#### T-01 — Path Traversal in Input

**Description:** Attacker includes `../` sequences in input paths to escape allowed directories.

**Vector:** Input specification containing path traversal patterns.

**Impact:** Access to files outside intended scope; potential read/write of sensitive files.

**Status:** IMPOSSÍVEL

**Defense mechanism:** Impact Gate explicitly checks for `..` in all paths via `_check_path_traversal()` function. Any path containing `..` is blocked with `IMPACT_FORBIDDEN_PATH`.

**Evidence generated:** RunLog contains `blocked_reason: "IMPACT_FORBIDDEN_PATH"` and error in `errors[]` array.

---

#### T-02 — Forbidden Path Injection

**Description:** Input attempts to reference or create files in security-sensitive paths.

**Vector:** Input containing patterns like `.env`, `secrets/`, `private_key`, `.git/`.

**Impact:** Exposure of credentials; modification of repository state.

**Status:** IMPOSSÍVEL

**Defense mechanism:** Both Impact Gate and AuditPack enforce `FORBIDDEN_PATTERNS` list:
- `.env`, `.env.local`, `.env.production`, `.env.development`
- `secrets/`, `.secrets`, `credentials/`
- `private_key`, `private_keys/`, `.pem`, `.key`
- `id_rsa`, `id_ed25519`
- `api_key`, `apikey`, `token`, `tokens/`
- `password`, `passwd`
- `aws_access_key`, `aws_secret`
- `.git/`, `.gitignore`

**Evidence generated:**
- Impact Gate: `blocked_reason: "IMPACT_FORBIDDEN_PATH"` in RunLog
- AuditPack: `AUDITPACK_SECURITY_BLOCKED` error code

---

#### T-03 — Schema Bypass via Malformed Input

**Description:** Malformed JSON bypasses schema validation.

**Vector:** Input with missing required fields or invalid types.

**Impact:** Pipeline failure; potential undefined behavior.

**Status:** DETECTÁVEL

**Defense mechanism:** JSON Schema validation at intake with `jsonschema.validate()`. Schema versions enforced: `idl_draft.v1`, `idl.v1`, `change_request.v1`.

**Evidence generated:** RunLog contains `blocked_reason: "GATE1_FAILED"` or `"GATE2_BLOCKED"` with schema error details.

---

#### T-04 — Impact Scope Violation

**Description:** Change request attempts to modify files outside declared scope.

**Vector:** CR with `target: "backend"` but patch affecting `frontend/` paths.

**Impact:** Unauthorized code changes; scope creep.

**Status:** DETECTÁVEL

**Defense mechanism:** Impact Gate validates paths against `TARGET_PATH_MAPPING`:
```python
TARGET_PATH_MAPPING = {
    "frontend": ["apps/web/", "frontend/", "ui/", ...],
    "backend": ["services/", "backend/", "api/", ...],
    "db": ["db/", "migrations/", "database/", ...],
    ...
}
```

**Evidence generated:** `blocked_reason: "IMPACT_OUT_OF_SCOPE"` with affected paths listed.

---

#### T-05 — Overly Broad Changes

**Description:** Single change request affects too many files or directories.

**Vector:** CR that would modify 30+ files across 5+ top-level directories.

**Impact:** Unreviewed mass changes; potential for hidden malicious modifications.

**Status:** DETECTÁVEL

**Defense mechanism:** Impact Gate enforces limits:
- `MAX_AFFECTED_FILES = 25`
- `MAX_UNIQUE_TOP_DIRS = 4`

**Evidence generated:** `blocked_reason: "IMPACT_TOO_BROAD"` with metrics in RunLog.

---

### 4.2 Integrity Attacks

#### T-06 — Episode Tampering

**Description:** Direct modification of files within a finalized episode.

**Vector:** File system access to `.engine/episodes/<id>/` directory.

**Impact:** Falsified execution record; broken audit trail.

**Status:** DETECTÁVEL

**Defense mechanism:** Episode Store computes `episode_root_hash_sha256` from sorted file contents. Verification via `verify_integrity()` recomputes hash and compares.

**Evidence generated:** `verify_integrity()` returns `(False, "Hash mismatch: expected sha256:..., got sha256:...")`.

---

#### T-07 — Contract Hash Mismatch

**Description:** Modified contract artifact without updating hash.

**Vector:** Direct file modification of `contracts/*.json`.

**Impact:** Inconsistent state between artifacts and recorded hashes.

**Status:** DETECTÁVEL

**Defense mechanism:** ContractLedger tracks `content_hash_sha256` for each artifact. Contract Gate validates hashes at runtime.

**Evidence generated:** RunLog contains `contract_gate_ok: false` with `contract_gate_error` details.

---

#### T-08 — AuditPack Manipulation

**Description:** Modification of AuditPack ZIP contents after generation.

**Vector:** File modification within extracted ZIP.

**Impact:** Falsified audit evidence; compliance violations.

**Status:** DETECTÁVEL

**Defense mechanism:** AuditPack contains:
- `index.json` with `root_hash_sha256` computed from `<path>\n<sha256>\n` blob
- `hashes/sha256sums.txt` for standard verification
- `README_AUDIT.md` with offline verification instructions

**Evidence generated:** `sha256sum -c hashes/sha256sums.txt` shows `FAILED` for tampered files.

---

#### T-09 — Blueprint Registry Tampering

**Description:** Modification of registered blueprint without registry update.

**Vector:** Direct file modification in `blueprints/registry/blueprints/`.

**Impact:** Malicious blueprint patterns applied to generated systems.

**Status:** DETECTÁVEL

**Defense mechanism:** Registry stores `content_hash_sha256` for each blueprint. `verify_registry()` recomputes hashes and compares.

**Evidence generated:** `RegistryIntegrityError` raised with `"INTEGRITY: <blueprint_id>: hash mismatch"`.

---

#### T-10 — Legacy Artifact Tampering

**Description:** Modification of legacy inventory or human_process files.

**Vector:** Direct file modification of legacy bundle files.

**Impact:** Falsified legacy context; incorrect generation decisions.

**Status:** DETECTÁVEL

**Defense mechanism:** Legacy Gate validates:
- `schema_version` matches expected (`legacy_inventory.v1`, `human_process.v1`)
- `content_hash_sha256` is present and matches computed hash
- Hash verification uses canonical JSON (sorted keys, no whitespace)

**Evidence generated:** RunLog contains `legacy_contract_gate_ok: false` with `LEGACY_INTEGRITY_FAILED` error code.

---

### 4.3 Approval Bypass

#### T-11 — Missing Approval

**Description:** Attempt to release episode without required approval.

**Vector:** CLI command bypassing approval check.

**Impact:** Unapproved code released to production.

**Status:** IMPOSSÍVEL

**Defense mechanism:** Approval Gate checks for valid approval before release. `GateResult.BLOCKED` returned with `blocked_reason: "APPROVAL_REQUIRED"`.

**Evidence generated:** RunLog contains `blocked_reason: "APPROVAL_REQUIRED"`.

---

#### T-12 — Approval Episode Mismatch

**Description:** Approval file with different `episode_id` than target episode.

**Vector:** Copy approval from one episode to another.

**Impact:** Unauthorized release of different code.

**Status:** IMPOSSÍVEL

**Defense mechanism:** Approval Gate verifies `approval.episode_id == episode.episode_id`. Mismatch returns `APPROVAL_INVALID`.

**Evidence generated:** `blocked_reason: "APPROVAL_INVALID"` in RunLog.

---

#### T-13 — Forged Approval Record

**Description:** Creation of fake approval file without proper authorization.

**Vector:** Manual creation of `approval.json` with fabricated approver.

**Impact:** Bypass of human review; accountability loss.

**Status:** DETECTÁVEL

**Defense mechanism:** Approval records contain:
- `approval_id` (unique identifier)
- `approver.name`, `approver.role`, `approver.org`
- `decision` (approve/reject)
- `reason`
- `volatile.timestamp`

Current implementation uses manual signature scheme. Audit trail preserved.

**Evidence generated:** Approval file present but can be traced. For stronger guarantee, external signature verification recommended.

---

### 4.4 Change Request Manipulation

#### T-14 — CR Previous Episode Mismatch

**Description:** Change request references different episode than CLI argument.

**Vector:** CR with `previous_episode_id: "exec-wrong"` but CLI specifies `--previous-episode-id exec-abc123`.

**Impact:** Broken chain of custody; confusion in episode lineage.

**Status:** IMPOSSÍVEL

**Defense mechanism:** Change CLI validates `CR.previous_episode_id == --previous-episode-id`. Mismatch raises `CR_PREVIOUS_MISMATCH` error.

**Evidence generated:** Error message: `"INTEGRITY: CR.previous_episode_id 'exec-wrong' does not match argument 'exec-abc123'"`.

---

#### T-15 — CR Hash Tampering

**Description:** Modification of change request after hash computation.

**Vector:** Edit CR file after initial validation.

**Impact:** Falsified change request; broken audit trail.

**Status:** DETECTÁVEL

**Defense mechanism:** CR hash computed from canonical JSON (`sort_keys=True`, `separators=(",", ":")`). Hash stored in episode manifest `links.cr_hash_sha256`.

**Evidence generated:** Episode manifest contains original `cr_hash_sha256`. Recomputation from modified CR will not match.

---

### 4.5 Episode Store Attacks

#### T-16 — Episode Overwrite

**Description:** Attempt to recreate episode with same ID.

**Vector:** CLI command to create episode that already exists.

**Impact:** Loss of original execution record.

**Status:** IMPOSSÍVEL

**Defense mechanism:** `create_episode()` checks `exists(episode_id)` first. Raises `EpisodeDuplicateError` if already present.

**Evidence generated:** Error: `"GOVERNANCE: Episode already exists: <episode_id>"`.

---

#### T-17 — Modification of Finalized Episode

**Description:** Attempt to modify episode after finalization.

**Vector:** API call to register artifact on finalized episode.

**Impact:** Integrity violation; falsified record.

**Status:** IMPOSSÍVEL

**Defense mechanism:** All mutating operations check `is_finalized()`. Raises `EpisodeImmutableError` if episode has non-placeholder root hash.

**Evidence generated:** Error: `"GOVERNANCE: Episode is immutable: <episode_id>"`.

---

### 4.6 Wizard and Session Attacks

#### T-18 — Session Schema Bypass

**Description:** Invalid session file bypasses wizard validation.

**Vector:** Malformed session JSON.

**Impact:** Wizard malfunction; undefined behavior.

**Status:** DETECTÁVEL

**Defense mechanism:** Session schema validation with `WIZARD_SCHEMA_INVALID` error code. Wizard CLI validates before operations.

**Evidence generated:** Error code `WIZARD_SCHEMA_INVALID` in wizard runlog.

---

#### T-19 — Blueprint Not Found

**Description:** Session references non-existent blueprint ID.

**Vector:** Session with `blueprint_id` not in registry.

**Impact:** Export failure; workflow interruption.

**Status:** DETECTÁVEL

**Defense mechanism:** Registry lookup validates blueprint exists. `WIZARD_BLUEPRINT_NOT_FOUND` returned if not found.

**Evidence generated:** Error code `WIZARD_BLUEPRINT_NOT_FOUND` in wizard output.

---

---

## 5. Abuse Scenarios

### A-01 — Rogue Developer Bypass

**Scenario:** Developer attempts to deploy unauthorized feature by:
1. Creating CR with broad scope declaration
2. Including hidden changes in affected paths
3. Seeking rubber-stamp approval

**Defenses Triggered:**
1. Impact Gate blocks if paths exceed `MAX_AFFECTED_FILES` or `MAX_UNIQUE_TOP_DIRS`
2. Impact Gate validates each path against declared target scope
3. Approval audit trail captures approver identity and reason

**Evidence:** RunLog with `IMPACT_TOO_BROAD` or `IMPACT_OUT_OF_SCOPE`, approval record with approver details.

---

### A-02 — Post-Release Artifact Tampering

**Scenario:** Attacker gains file system access and modifies generated code after approval:
1. Accesses `/home/bazari/generated/<project>/`
2. Injects backdoor into `backend/src/` files
3. Attempts to claim code was from approved episode

**Defenses Triggered:**
1. Episode contains `repo_hash_sha256` of generated repository
2. AuditPack contains contracts with original hashes
3. Any comparison against episode reveals modifications

**Evidence:** `verify_integrity()` fails with hash mismatch. AuditPack provides baseline for comparison.

---

### A-03 — Fake Legacy Integration

**Scenario:** Operator attempts to inject false legacy context:
1. Creates fake `legacy_inventory.v1.json` with fabricated systems
2. Provides bundle to engine

**Defenses Triggered:**
1. Legacy Gate validates `schema_version`
2. Legacy Gate verifies `content_hash_sha256` matches computed hash
3. If ledger provided, hash must match ledger entry

**Evidence:** `LEGACY_INTEGRITY_FAILED` or `LEGACY_SCHEMA_INVALID` in RunLog.

---

### A-04 — AuditPack Forgery for Compliance

**Scenario:** Bad actor attempts to present modified AuditPack to auditors:
1. Extracts legitimate AuditPack
2. Modifies episode files
3. Rezips and presents to auditor

**Defenses Triggered:**
1. `sha256sums.txt` checksums will not match
2. `index.json` root hash will not match
3. README provides offline verification scripts

**Evidence:** Auditor runs verification, detects hash mismatch.

---

### A-05 — Approval Without Review

**Scenario:** Approver creates approval record without actually reviewing:
1. Uses CLI to approve episode immediately after creation
2. Provides generic reason

**Defenses Triggered:**
1. Approval record captures timestamp
2. Approval record requires explicit reason
3. Episode timeline shows approval timing relative to creation

**Evidence:** Audit trail shows approval timestamp. Human audit can identify rubber-stamping patterns.

---

---

## 6. Security Invariants

### SI-01 — Episode Immutability

**Invariant:** Once an episode is finalized (has valid `episode_root_hash_sha256`), no modifications are permitted.

**Enforcement:** `is_finalized()` check in all mutating operations. `EpisodeImmutableError` raised on violation.

**Test:** `tests/test_episodes.py::test_episode_immutable_after_finalization`

---

### SI-02 — Deterministic Hash Computation

**Invariant:** Hash computation produces identical output for identical input across all invocations.

**Enforcement:** All hashing uses:
- Canonical JSON: `sort_keys=True`, `separators=(",", ":")`
- SHA256 algorithm
- Excluded volatile fields: `created_at_volatile`, `computed_at`, `extracted_at`

**Test:** `tests/test_canonical_hash.py`

---

### SI-03 — Approval-Episode Binding

**Invariant:** An approval is valid only for the episode whose `episode_id` it references.

**Enforcement:** `approval_gate.py` verifies `approval.episode_id == episode.episode_id`.

**Test:** `tests/test_episodes.py::test_approval_episode_id_mismatch`

---

### SI-04 — CR-Episode Chain Integrity

**Invariant:** Change request's `previous_episode_id` must match CLI argument and previous episode must exist.

**Enforcement:** `change_cli.py` validates both conditions before creating change episode.

**Test:** `tests/test_change_request.py::test_cr_previous_mismatch`

---

### SI-05 — Forbidden Path Exclusion

**Invariant:** No artifact containing forbidden patterns can be included in episode or AuditPack.

**Enforcement:** `FORBIDDEN_PATTERNS` checked in Impact Gate and AuditPack builder.

**Test:** `tests/test_impact_gate.py::test_forbidden_patterns`, `tests/test_auditpack.py::test_security_check`

---

### SI-06 — Contract Ledger Consistency

**Invariant:** All artifacts in ContractLedger have valid `content_hash_sha256` that matches file content.

**Enforcement:** Contract Record computed at save time. Contract Gate validates at runtime.

**Test:** `tests/test_contract_record_ledger.py`

---

### SI-07 — Blueprint Registry Integrity

**Invariant:** All blueprints in registry have content hash matching actual file content.

**Enforcement:** `verify_registry()` recomputes hashes and compares. `RegistryIntegrityError` on mismatch.

**Test:** `tests/test_blueprint_registry.py::test_integrity_verification`

---

### SI-08 — Error Code Parity

**Invariant:** Every error message has a corresponding `error_code` in 1:1 relationship.

**Enforcement:** All error-generating functions pair `errors[]` with `error_codes[]` arrays.

**Test:** `tests/test_runlog_blocked_reason_always_present.py`

---

---

## 7. Known Limitations

### KL-01 — Manual Signature Scheme

**Description:** Current approval implementation uses manual signature scheme without cryptographic verification.

**Risk:** Approval records can be created by anyone with file system access.

**Mitigation:** Audit trail captures all approval details. External signature verification recommended for high-security deployments.

**Status:** Documented limitation. Future enhancement: integrate with PKI or external signing service.

---

### KL-02 — File System Trust

**Description:** System assumes file system integrity between operations.

**Risk:** Attacker with write access could modify files between hash computation and verification.

**Mitigation:** Integrity verification before all critical operations. AuditPack provides point-in-time snapshot.

**Status:** Acceptable risk for target deployment model. Consider encrypted storage for high-security.

---

### KL-03 — No Real-Time Monitoring

**Description:** Integrity violations detected only when explicitly checked.

**Risk:** Tampering may go undetected until next verification.

**Mitigation:** Regular integrity verification recommended. External monitoring integration possible.

**Status:** Documented limitation. Observability pipeline can integrate with alerting.

---

### KL-04 — Timestamp Volatility

**Description:** Timestamps are excluded from hash computation for determinism.

**Risk:** Timestamps can be falsified without hash detection.

**Mitigation:** Timestamps are marked `_volatile` by convention. Critical sequencing uses episode ordering, not timestamps.

**Status:** By design. Timestamps are for human reference only.

---

### KL-05 — Single Approver Model

**Description:** Current model requires single approval. No multi-party approval support.

**Risk:** Single point of failure for approval authority.

**Mitigation:** Organizational controls around approver selection. Future enhancement: configurable approval policies.

**Status:** Documented limitation. Sufficient for current use case.

---

---

## 8. Executive Conclusion

The Bazari Engine implements a **defense-in-depth** security model with the following key properties:

### Integrity Guarantees

1. **Append-Only Episodes**: Once created, episodes cannot be modified. All mutations are detected via `episode_root_hash_sha256`.

2. **Deterministic Hashing**: All artifacts use canonical JSON serialization with SHA256 hashing, ensuring reproducible verification.

3. **Gate Chain**: Multiple independent gates (Contract, Impact, Approval, Legacy) provide layered validation with specific `blocked_reason` values.

### Audit Trail

1. **Complete Provenance**: Every execution produces a RunLog with `execution_id`, `final_status`, `blocked_reason`, and `error_codes`.

2. **AuditPack**: Verifiable ZIP archives provide offline audit capability with embedded verification instructions.

3. **Episode Chaining**: Change requests create linked episodes with `previous_episode_id` and `cr_hash_sha256`.

### Known Attack Surfaces

| Attack Vector | Status | Evidence |
|---------------|--------|----------|
| Path Traversal | IMPOSSÍVEL | Impact Gate blocks |
| Forbidden Paths | IMPOSSÍVEL | Impact Gate + AuditPack blocks |
| Episode Tampering | DETECTÁVEL | Root hash verification |
| Approval Bypass | IMPOSSÍVEL | Gate requires valid approval |
| CR Mismatch | IMPOSSÍVEL | Previous episode validation |
| Blueprint Tampering | DETECTÁVEL | Registry hash verification |

### Residual Risks

1. **Manual Signatures**: Approval cryptographic binding relies on organizational trust, not cryptographic proof.

2. **File System Trust**: Between-operation tampering theoretically possible but detectable at verification.

3. **Single Approver**: No built-in multi-party approval requirement.

### Compliance Readiness

The system provides artifacts compatible with:
- **SOC2**: AuditPack with verifiable hashes, approval trail
- **ISO27001**: Immutable episode records, integrity verification
- **Internal Audit**: Complete RunLog with deterministic `error_codes`

### Recommendation

The current security posture is **appropriate for institutional software generation** with the following operational requirements:

1. Run `verify_integrity()` before critical operations
2. Generate AuditPack for all production releases
3. Establish organizational controls around approval authority
4. Consider external signature verification for high-security deployments

---

*Document generated for Bazari Engine security audit.*
