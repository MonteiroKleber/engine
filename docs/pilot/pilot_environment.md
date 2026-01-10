# Pilot Environment

## Pilot Identifier
- **Pilot ID**: `PILOT-2026-001`
- **Environment**: Development/Validation

## System Information

### Platform
- **OS**: Linux 6.8.0-84-generic
- **Python**: 3.x (venv active)
- **Engine Version**: Current main branch

### Directory Structure
```
/home/bazari/engine/
├── piloto-atendimento/          # Pilot project directory
│   ├── input/                   # IDL input files
│   ├── output/                  # Generated artifacts
│   ├── episodes/                # Episode store
│   └── auditpack/               # Generated audit packs
├── wizard/                      # Wizard CLI module
├── episodes/                    # Episode store module
└── main.py                      # Main pipeline entry
```

## Pre-Execution Checks

### Engine Status
- [x] All tests pass (2537 expected)
- [x] No uncommitted changes to core modules
- [x] Episode store clean at start

### Dependencies
- [x] Python virtual environment active
- [x] All required modules importable
- [x] CLI tools accessible

## Execution Commands Reference

### Episode A - Initial Generation
```bash
# A1: Start wizard session
python -m wizard.wizard_cli start

# A2: Export to IDL
python -m wizard.wizard_cli export --format idl_draft --output piloto-atendimento/input/atendimento.json

# A3: Run pipeline
python main.py --input piloto-atendimento/input/atendimento.json --output piloto-atendimento/output --project atendimento

# A4: Approve episode
python -m episodes.episodes_cli approve <episode_id>

# A5: Release
python main.py --release --episode <episode_id>

# A6: Verify
python -m episodes.episodes_cli list
python -m episodes.episodes_cli show <episode_id>
```

### Episode B - Governed Change
```bash
# B1: Create change request
python -m episodes.episodes_cli change --previous <episode_a_id> --input piloto-atendimento/input/atendimento_v2.json

# B2: Run change pipeline
python main.py --change-request <cr_id> --output piloto-atendimento/output

# B3: Approve change
python -m episodes.episodes_cli approve <episode_b_id>

# B4: Release change
python main.py --release --episode <episode_b_id>
```

### AuditPack Generation
```bash
# Generate AuditPack
python -m episodes.episodes_cli auditpack --episode <episode_id> --output piloto-atendimento/auditpack/

# Verify offline
unzip -l piloto-atendimento/auditpack/<auditpack>.zip
sha256sum -c manifest.sha256
```

## Validation Checkpoints

| Checkpoint | Verification Method |
|------------|---------------------|
| Gate 1 (Schema) | RunLog shows `gate1_passed: true` |
| Gate 2 (IR) | RunLog shows `gate2_passed: true` |
| Contract Gate | ContractLedger entries created |
| Approval Gate | RunLog shows `approval_status: approved` |
| Impact Gate | Change diff within limits |
| Release Gate | `release_ok: true` in telemetry |
