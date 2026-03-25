# BLM Stage 2: Aiming Calibration (Yaw/Pitch)

Goal: improve horizontal and vertical aiming before speed tuning/shooting.

## 1) Start 3D reference view (Terminal A)

```bash
cd /home/hanush/Desktop/Project_Cam
./arena_fixed/run_live_visual_invert_only.sh --view-elev 24 --view-azim 135
```

## 2) One-point aim test runner (Terminal B)

Use helper:

```bash
cd /home/hanush/Desktop/Project_Cam
bash arena_fixed/scripts/run_blm_aim_test.sh right_knee 4600 1600 1400 H2
```

Then in runtime terminal type:
- `start`
- wait for one aim event
- `quit`

Each run writes JSONL log into:
- `garage_lab_combined/output/blm_logs/aim_stage2_<label>_<timestamp>.jsonl`

## 3) Horizontal tuning first (keep Z fixed)

Run these points (same height):

1. `H1`: `(4600, 1100, 1400)`
2. `H2`: `(4600, 1600, 1400)`
3. `H3`: `(4600, 2100, 1400)`

Start with:
- `yaw_trim_deg = 0.0`
- `pitch_trim_deg = 0.0`

Adjustment rule:
- if BLM points too much to **east/right** -> decrease yaw trim by `-0.5 deg`
- if BLM points too much to **west/left** -> increase yaw trim by `+0.5 deg`

Keep pitch trim unchanged in this phase.

## 4) Vertical tuning second (keep Y fixed)

Run:

1. `V1`: `(4600, 1600, 500)`
2. `V2`: `(4600, 1600, 900)`
3. `V3`: `(4600, 1600, 1400)`
4. `V4`: `(4600, 1600, 1800)`

Use best yaw trim from step 3.

Adjustment rule:
- if BLM points above target -> decrease pitch trim by `-0.5 deg`
- if BLM points below target -> increase pitch trim by `+0.5 deg`

## 5) Validation set (mixed points)

Validate final trims on:

1. `(4600,1100,500)`
2. `(4600,1600,900)`
3. `(4600,2100,1140)`
4. `(4600,1600,1400)`
5. `(4600,2100,2200)`

## 6) Safety mode for this stage

- always `--no-shoot-enabled`
- always `--aim-only-wheel-rpm 0`
- one target event per run (`--max-target-events 1`)

No live firing in Stage 2.
