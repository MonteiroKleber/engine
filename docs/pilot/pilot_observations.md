# Pilot Observations

## Pilot Identifier
- **Pilot ID**: `PILOT-2026-001`
- **Execution Date**: 2026-01-08

## Execution Observations

### Episode A - Initial Generation

**What Worked Well:**
1. Natural language input was successfully parsed and converted to structured artifacts
2. All governance gates passed on first attempt
3. Entity extraction correctly identified 7 entities with 35 operations
4. Pipeline completed in 70ms (well under performance contract of 5000ms)
5. Episode creation and finalization worked correctly
6. Approval flow registered properly with full audit trail

**Observations:**
1. The wizard CLI provides good structured input capture, but for this pilot we used direct natural language input to demonstrate the full intake flow
2. Artifact versioning incremented correctly (SRS v3 due to prior test runs in same store)
3. ContractLedger properly registered all artifact hashes

### Episode B - Governed Change

**What Worked Well:**
1. Change Request schema validation caught all required fields
2. Impact Gate correctly validated the scope was within limits
3. Previous episode linkage was properly validated (requires approved status)
4. CR hash is immutably linked to episode
5. All invariants from CR were preserved (backward compatible change)
6. New use case CheckSLABreach was properly added

**Observations:**
1. The change command creates a new episode in pending status, ready for artifact registration
2. Pipeline execution is separate from episode creation (artifacts generated then registered)
3. Episode B correctly shows input_mode as "draft" since CR was processed with updated IDL Draft

### AuditPack Generation

**What Worked Well:**
1. AuditPacks are complete and self-contained
2. SHA256 checksums verify correctly offline
3. README_AUDIT.md provides clear instructions for auditors
4. index.json contains full metadata for programmatic verification
5. Episode B includes change_request directory with CR document

**Observations:**
1. AuditPack root hash differs from episode root hash (expected - approval added after finalization)
2. Both packs include all contracts and approval records
3. Pack sizes are reasonable (68KB for Episode A, 45KB for Episode B)

## Governance Findings

### Gates Functioning Correctly

| Gate | Behavior Observed |
|------|-------------------|
| Schema Validation | Rejected invalid drafts, accepted valid inputs |
| SRS Validation | Verified all requirements are properly structured |
| IR Validation | Ensured domain model is complete |
| Policy Check | Applied all configured policies |
| Impact Gate | Validated change scope within limits |
| Approval Gate | Blocked release until approval registered |

### No Bypass Possible

The following safeguards were observed:
1. Episode finalization locks the episode (EpisodeImmutableError on modification attempts)
2. Approval Gate blocks proceeding without explicit approval
3. Change episodes require previous_episode_id to be approved
4. All hashes are computed deterministically (not user-providable)

## Performance Metrics

| Metric | Episode A | Episode B | Contract |
|--------|-----------|-----------|----------|
| Pipeline Duration | 70ms | 48ms | <5000ms |
| Entities Extracted | 7 | 4 | - |
| Operations Generated | 35 | 20 | - |
| Tasks Created | 56 | 32 | - |
| AuditPack Size | 68KB | 45KB | - |

## Recommendations

### For Production Deployment

1. **Episode Store Location**: Consider configuring episode store on separate persistent volume for durability
2. **Approval Integration**: Integrate approval workflow with enterprise SSO for identity verification
3. **Change Request Templates**: Provide CR templates for common change types
4. **Monitoring**: Add telemetry dashboards for episode creation/approval rates

### For Audit Process

1. **Offline Verification**: Auditors can verify packs without system access
2. **Chain Validation**: Verify previous_episode_id links form valid chain
3. **CR Traceability**: Match CR hash in manifest to external CR tracking system
4. **Temporal Ordering**: Verify created_at timestamps are sequential

## Issues Encountered

### None Critical

1. **Minor**: Integrity verification after approval shows hash mismatch (expected - approval adds file)
   - **Resolution**: This is correct behavior for append-only store; AuditPack computes fresh hash

2. **Minor**: Must manually register contracts to episode after pipeline run
   - **Recommendation**: Consider automatic episode creation from pipeline run

## Conclusion

The pilot demonstrated that the governance system works as designed:
- Episodes are immutable after finalization
- Approvals are explicitly tracked
- Changes are linked to previous episodes
- All artifacts are hash-verified
- AuditPacks enable offline verification

The system is ready for enterprise use with proper operational procedures.
