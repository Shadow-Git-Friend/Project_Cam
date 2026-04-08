# Workflow Rules

## Read-First Strategy
- Always read the relevant script/config before proposing changes
- Never modify code you haven't read in the current session

## Change Process
- Plan before coding; propose approach and get approval for non-trivial changes
- Prefer incremental, testable steps with rollback paths
- Report assumptions, risks, and validation checks

## Testing Order
1. Dry-run / offline first (process_4cam_to_3d.py with recorded clips)
2. Ablation / evaluation on recorded sequences (record_test_sequence.py → ablation_ema_adaptive.py)
3. Live viewer without BLM (visual verification)
4. BLM aim-only with --no-shoot-enabled
5. BLM controlled fire only after S4 safety tests pass

## Git Hygiene
- Commit with clear, descriptive messages
- Keep Parallel_working/ changes in separate commits from garage_lab_combined/
- Never force-push without explicit approval

## Do Not Auto-Read
- venv/
- Large raw outputs and captures
- Old archives unless needed for a specific task
