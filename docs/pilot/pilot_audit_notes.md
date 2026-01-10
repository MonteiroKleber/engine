# Pilot Audit Notes

## Pilot Identifier
- **Pilot ID**: `PILOT-2026-001`
- **Execution Date**: 2026-01-08

## Episode Summary

### Episode A - Initial Generation
| Attribute | Value |
|-----------|-------|
| Episode ID | `atendimento_3b5e0202` |
| Execution ID | `atendimento_3b5e0202` |
| Input Mode | natural |
| Status | approved |
| Created At | 2026-01-08T21:45:22Z |
| Root Hash | `sha256:79282e2cbf99cece9ef30981f054dca552f7731f11f8e595c325755cbc3a1aed` |

**Contracts Registered:**
- SRS: `sha256:e5f418adf945d1d7428cddc8962e9ba7e7ae99a0026e438ff8aa632559443a08`
- IR: `sha256:00ce5c1ead76ec04e2042a331613aee817b755ccb7bb4b539bf07879aeaf0ecb`
- OpenAPI: `sha256:cfd472f28a66d66eab7694ad1c2a525631e7c0f9180a551c5eea0eb6696e26ea`
- PLAN: `sha256:8b72dfc20c7956f614645181ab5493ba70259708c106780cfed9e39b5d782f3f`

**Approval:**
- Approver: Pilot Validation Team (Tech Lead)
- Organization: Bazari Enterprise
- Decision: approve
- Approval ID: `appr-5264bdbd`

### Episode B - Governed Change
| Attribute | Value |
|-----------|-------|
| Episode ID | `change-7e8adef6` |
| Execution ID | `change-7e8adef6` |
| Input Mode | draft |
| Status | approved |
| Created At | 2026-01-08T21:46:59Z |
| Root Hash | `sha256:5d51d09e42319463bdb0d2168b6c17adafab089d1a8f0838e58a23dd117d2198` |
| Previous Episode | `atendimento_3b5e0202` |
| Change Request | `CR-SLA-001` |

**Change Request Details:**
- CR Hash: `sha256:9b7811164a10f568d9e3c67d11fac94e441ba5cb9888fa1a1dc248fb3cbdb1d9`
- Target: backend
- Entities Affected: Ticket
- Use Cases Added: CheckSLABreach
- Risk Level: low

**Contracts Registered (v2):**
- SRS v4: `sha256:4e3b82b7440ce9f9595204b...`
- IR v2: `sha256:4702910cf3e7b2fc2ebdd69...`
- OpenAPI v2: `sha256:914ae35241b4d3a5b23bb93...`
- PLAN v2: `sha256:00da5b75560e40fb7d13c3f...`

**Approval:**
- Approver: Pilot Validation Team (Tech Lead)
- Organization: Bazari Enterprise
- Decision: approve
- Approval ID: `appr-4f9fc671`

## AuditPack Verification

### Episode A AuditPack
- **File**: `piloto-atendimento/auditpack/episode_a.zip`
- **Pack Root Hash**: `sha256:d3a8a5d5e124926e4f1ebd53dd7c2acec0ef521386752922d2ed186847e276ca`
- **Total Files**: 7
- **Size**: 68,171 bytes
- **Checksum Verification**: PASSED (7/7 files OK)

### Episode B AuditPack
- **File**: `piloto-atendimento/auditpack/episode_b.zip`
- **Pack Root Hash**: `sha256:28f0d56dabf999e386be57f434795576b7629ce934ce99c63b4984de948d99ad`
- **Total Files**: 8
- **Size**: 44,709 bytes
- **Has Change Request**: Yes
- **Checksum Verification**: PASSED (8/8 files OK)

## Governance Gates Verified

| Gate | Episode A | Episode B |
|------|-----------|-----------|
| Schema Validation | PASS | PASS |
| SRS Validation | PASS | PASS |
| IR Validation | PASS | PASS |
| OpenAPI Validation | PASS | PASS |
| RBAC Validation | PASS | PASS |
| Plan Validation | PASS | PASS |
| Policy Check | PASS | PASS |
| Contracts Policy | PASS | PASS |
| Plan Policy | PASS | PASS |
| Impact Gate | N/A | PASS |
| Approval Gate | PASS | PASS |

## Chain of Custody

```
Episode A (atendimento_3b5e0202)
    │
    ├── Input: Natural language description
    ├── Output: SRS v3, IR v1, OAS v1, RBAC v1, PLAN v1
    ├── Approval: appr-5264bdbd
    │
    └── Episode B (change-7e8adef6)
            │
            ├── CR: CR-SLA-001
            ├── Previous: atendimento_3b5e0202 (linked)
            ├── Input: IDL Draft v2 with sla_deadline
            ├── Output: SRS v4, IR v2, OAS v2, RBAC v2, PLAN v2
            └── Approval: appr-4f9fc671
```

## Offline Verification Commands

```bash
# Extract and verify Episode A
unzip episode_a.zip -d verify_a
cd verify_a
sha256sum -c auditpack/hashes/sha256sums.txt

# Extract and verify Episode B
unzip episode_b.zip -d verify_b
cd verify_b
sha256sum -c auditpack/hashes/sha256sums.txt
```

## Notes

1. Both episodes properly chain through `previous_episode_id`
2. Change Request CR-SLA-001 is immutably linked via `cr_hash_sha256`
3. All artifacts are traceable via SHA256 hashes
4. AuditPacks are self-contained and offline-verifiable
5. No governance gates were bypassed
