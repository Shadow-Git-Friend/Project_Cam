// Training drill catalog. IDs must match DRILL_REGISTRY in
// src/project_cam/training/drills.py (contract-tested in
// tests/test_desktop_training_contracts.py).
//
// Drills launch through the backend's `training_drill` profile, which starts
// the live viewer (UDP joint broadcast) plus the athlete-facing drill board.
// View-only: nothing here can actuate the launcher, and the frontend cannot
// name the script — see src-tauri/src/launch_profiles.rs.

export type DrillRole = "GOALKEEPER" | "FIELD PLAYER";

export type Drill = {
  id: string;
  role: DrillRole;
  title: string;
  tagline: string;
  provenance: string; // why professionals use it
  durationLabel: string;
  /** Semantic workload parameter for this drill. `--rounds` used to carry four
   *  different meanings (holds/reps/sets/rounds); the request now says which. */
  workloadKey:
    | "holds"
    | "reps"
    | "sets"
    | "rounds"
    | "duration_s"
    | "jumps"
    | "hops_per_leg";
  roundsLabel: string;
  roundsDefault: number;
  roundsMin: number;
  roundsMax: number;
  roundsStep: number;
  setup: string[];
  protocol: string[];
  metrics: string[];
};

export const DRILLS: Drill[] = [
  {
    id: "gk_save",
    role: "GOALKEEPER",
    title: "SAVE THE CORNERS",
    tagline: "Reaction save matrix on the four corners",
    provenance:
      "Goalkeeper reaction training follows the save → recover → set cycle used at every professional level. The system enforces it: a new corner only lights up after you are back in a held set position, and the cue fires after a random delay so it cannot be anticipated.",
    durationLabel: "~4 min",
    workloadKey: "rounds",
    roundsLabel: "rounds",
    roundsDefault: 10,
    roundsMin: 5,
    roundsMax: 20,
    roundsStep: 5,
    setup: [
      "Face the drill screen from the center of the arena",
      "Clear the sides — you will step/dive toward LEFT and RIGHT",
      "No ball needed; the four corners are virtual goal corners",
    ],
    protocol: [
      "Get set in the CENTER zone, hands ready — the board arms",
      "A random corner lights after a random delay",
      "Punch either wrist into that corner: HIGH = above your shoulder line, LOW = below knee height",
      "Recover to the center to arm the next round",
    ],
    metrics: [
      "Reaction time per save (cue → wrist in corner)",
      "Save percentage and per-corner breakdown",
      "Weakest corner (your training target for next session)",
      "HIGH/LOW bands self-calibrate to YOUR shoulder/hip height",
    ],
  },
  {
    id: "gk_save_served",
    role: "GOALKEEPER",
    title: "SAVE THE CORNERS · SERVED",
    tagline: "Same corners, but a real ball is the cue",
    provenance:
      "The virtual version cues a corner on this screen, which means the keeper is reacting to a board — something no keeper ever does while facing a shot. Served, the stimulus is the delivery itself and the corner is a measured place in the goal rather than a band relative to your own body, so the reaction time is comparable between athletes and the corner means the same thing for everybody. The board never asks the launcher for anything: the operator serves through the gated launcher console, and this drill measures whatever arrived.",
    durationLabel: "~5 min",
    workloadKey: "rounds",
    roundsLabel: "serves",
    roundsDefault: 10,
    roundsMin: 3,
    roundsMax: 20,
    roundsStep: 1,
    setup: [
      "MEASURE the goal and pass it — the drill refuses a goal that does not fit the room",
      "Launcher at the far end, aimed at the goal, nobody beside the flight path",
      "Ball tracking is enabled automatically for this drill only",
      "SAFETY: serving toward an occupied goal needs the launcher commissioning gates (measured v(RPM) with its spread, validated aiming, an energy limit). Until those pass, serve into an EMPTY goal and keep the keeper out of the room.",
    ],
    protocol: [
      "Get set in the goal mouth, hands ready — the board arms after a short hold",
      "The operator serves. There is no screen cue: watch the ball",
      "Reaction is measured from the serve to your first committed movement",
      "The board plots where the ball actually crossed the goal plane",
    ],
    metrics: [
      "Reaction time per save (serve → first committed movement)",
      "Save rate over serves that actually entered the goal",
      "Per-corner record; centre balls are excluded from it deliberately",
      "Serves that missed the goal, and serves the ball track could not resolve",
      "Measured delivery speed from the cameras",
    ],
  },
  {
    id: "gk_updown",
    role: "GOALKEEPER",
    title: "DOWN-UP RECOVERY",
    tagline: "Classic keeper conditioning — floor to set, on repeat",
    provenance:
      "Down-ups are a staple of professional goalkeeper conditioning: after every save a keeper must be back at set height immediately. The board paces you (GO DOWN / GET UP) and times every recovery.",
    durationLabel: "30–120 s",
    workloadKey: "duration_s",
    roundsLabel: "seconds",
    roundsDefault: 30,
    roundsMin: 15,
    roundsMax: 120,
    roundsStep: 15,
    setup: [
      "Stand in the middle of the arena facing the screen",
      "Optional mat for the floor touches",
      "Stand tall during the countdown — it measures your set height",
    ],
    protocol: [
      "On GO DOWN: drop until your hips pass the red line (self-calibrated)",
      "On GET UP: return above the green SET line and hold it",
      "Repeat at maximum sustainable pace until the timer ends",
    ],
    metrics: [
      "Reps completed and reps per minute",
      "Recovery time per rep (floor → set height)",
      "Best and average recovery across the block",
    ],
  },
  {
    id: "reaction_zones",
    role: "FIELD PLAYER",
    title: "REACTION ZONES",
    tagline: "Projector cues, pelvis-scored lateral reactions",
    provenance:
      "Lateral cue-response drills train the first movement after a visual signal. Project Cam judges the athlete by pelvis position in three equal garage zones, so the result comes from whole-body movement rather than a hand gesture. A random hidden delay prevents timing the cue.",
    durationLabel: "~2 min",
    workloadKey: "rounds",
    roundsLabel: "rounds",
    roundsDefault: 10,
    roundsMin: 5,
    roundsMax: 20,
    roundsStep: 5,
    setup: [
      "Clear the configured lateral arena width and face the projector",
      "The floor is split into LEFT / CENTER / RIGHT zones",
      "Outer targets are zone centres, leaving at least 500 mm to the wall",
    ],
    protocol: [
      "Hold your current zone until the board arms",
      "After a random delay, one of the other two zones lights up",
      "Move your hips into the target zone before the timeout",
      "Tracking loss after GO voids the round; it is repeated, never guessed",
    ],
    metrics: [
      "Average reaction time across successful hits",
      "Hits completed inside the timeout",
      "Per-zone reaction breakdown and weakest zone",
      "Voided rounds are recorded separately from misses",
    ],
  },
  {
    id: "balance",
    role: "FIELD PLAYER",
    title: "SINGLE-LEG BALANCE",
    tagline: "FIFA 11+ stance stability, measured in millimetres",
    provenance:
      "Single-leg balance is Part 2 of FIFA 11+, the injury-prevention programme used across professional football. Postural sway is the standard measure in pro return-to-play testing — the arena tracks your pelvis at ~4 mm precision, so sway is a real number, not a guess.",
    durationLabel: "~2.5 min",
    workloadKey: "holds",
    roundsLabel: "holds",
    roundsDefault: 4,
    roundsMin: 2,
    roundsMax: 8,
    roundsStep: 2,
    setup: [
      "Mark a spot mid-arena; stand on it facing the screen",
      "Holds alternate legs automatically (L → R → L → R)",
      "Advanced: repeat the session with eyes closed",
    ],
    protocol: [
      "Board announces the stance leg, then counts down",
      "Lift the free foot and stand as still as possible for the hold",
      "Every touch-down of the free foot is counted against you",
      "Short rest, then the other leg",
    ],
    metrics: [
      "Pelvis sway RMS in mm (lower is better) + max drift",
      "Touch-downs and % of hold truly on one leg",
      "Left/right asymmetry — flags an unstable side",
    ],
  },
  {
    id: "shuttle",
    role: "FIELD PLAYER",
    title: "PRO-AGILITY SHUTTLE",
    tagline: "The 5-10-5 change-of-direction test, garage-scaled",
    provenance:
      "The 5-10-5 pro-agility shuttle is the standard change-of-direction test in combine and academy testing worldwide. This is the same three-cut pattern scaled to the garage: 2 m out, 4 m across, 2 m home — timed by your hips crossing the lines, with sub-frame interpolation.",
    durationLabel: "~3 min",
    workloadKey: "reps",
    roundsLabel: "reps",
    roundsDefault: 3,
    roundsMin: 1,
    roundsMax: 6,
    roundsStep: 1,
    setup: [
      "Tape a START line mid-arena (long axis) and lines A/B 2 m to each side",
      "Sprint lane must be clear wall-to-wall",
      "The board's mini-map shows your live position vs the lines",
    ],
    protocol: [
      "Stand on the START line — the rep arms itself",
      "On GO: sprint to line A, cut, sprint across to line B, cut, finish through START",
      "Full rest between reps (timer on the board)",
    ],
    metrics: [
      "Total time per rep (±0.07 s at 15 Hz tracking)",
      "Three splits: out / across / home — cut asymmetry shows up here",
      "Best rep and session average",
    ],
  },
  {
    id: "line_hops",
    role: "FIELD PLAYER",
    title: "LATERAL LINE HOPS",
    tagline: "FIFA 11+ quick feet — side-to-side over a line",
    provenance:
      "Jumping side-to-side over a line is a FIFA 11+ Part 3 plyometric used for quick feet and ankle reactive strength. The board counts real crossings of your own start line with a 6 cm hysteresis band, so tracking jitter can never fake a hop.",
    durationLabel: "~1.5 min",
    workloadKey: "sets",
    roundsLabel: "sets",
    roundsDefault: 3,
    roundsMin: 1,
    roundsMax: 5,
    roundsStep: 1,
    setup: [
      "Tape one line on the floor, both feet together beside it",
      "Soft knees, land on the balls of your feet",
      "Wherever you stand at GO becomes the line — no calibration needed",
    ],
    protocol: [
      "Countdown, then hop side-to-side over the line as fast as you can",
      "Keep hopping until the set timer ends",
      "Rest, repeat for every set",
    ],
    metrics: [
      "Hops per set and hop rate (per second)",
      "Best set vs average — fatigue drop-off across sets",
    ],
  },
  {
    id: "cmj",
    role: "FIELD PLAYER",
    title: "COUNTERMOVEMENT JUMP",
    tagline: "Neuromuscular load monitoring, no floor space needed",
    provenance:
      "The countermovement jump is the most widely used neuromuscular monitoring test in professional football: a fall in jump output tracks accumulated fatigue before it shows up in training quality. Project Cam reports PELVIS RISE above the athlete's own standing height, which is not a force-plate jump height — the two correlate but are not the same number, so an athlete is compared to their own baseline, never to published norms.",
    durationLabel: "~1 min",
    workloadKey: "jumps",
    roundsLabel: "jumps",
    roundsDefault: 5,
    roundsMin: 3,
    roundsMax: 10,
    roundsStep: 1,
    setup: [
      "Stand tall and still for the countdown so standing height calibrates",
      "No run-up and no floor space required",
      "Hands on hips keeps the measurement about the legs",
    ],
    protocol: [
      "Dip into a countermovement, then jump as high as you can",
      "Land, settle, and repeat without pausing between jumps",
      "A dip that never becomes a jump is abandoned, not scored",
    ],
    metrics: [
      "Best and mean pelvis rise in millimetres",
      "Drop-off across the set: last third versus first third",
      "Standing pelvis height used for the calibration",
    ],
  },
  {
    id: "hop_symmetry",
    role: "FIELD PLAYER",
    title: "SINGLE-LEG HOP SYMMETRY",
    tagline: "Left-versus-right screening for return to play",
    provenance:
      "Limb symmetry on single-leg hop tests is the conventional criterion informing return-to-sport decisions, usually quoted at 90% or better. Two caveats travel with it and are shown on the board: fewer than half of youth athletes reach 90%, and symmetry can be met while both limbs are weak because the uninjured side also decays during a layoff. Project Cam therefore reports the index alongside both raw distances, as a screening signal and never a clearance decision.",
    durationLabel: "~3 min",
    workloadKey: "hops_per_leg",
    roundsLabel: "hops per leg",
    roundsDefault: 3,
    roundsMin: 2,
    roundsMax: 5,
    roundsStep: 1,
    setup: [
      "Pick one start line and return to it before every hop",
      "About two metres of clear floor ahead of the line",
      "Legs alternate automatically, starting with the left",
    ],
    protocol: [
      "Stand still on the hopping leg, on the line, until the board arms",
      "Hop forward as far as you can and hold the landing still",
      "Walk back to the line to arm the next hop",
    ],
    metrics: [
      "Best and mean distance for each leg, in millimetres",
      "Limb symmetry index and which leg is weaker",
      "Time to stabilise the landing",
    ],
  },
  {
    id: "reactive_cut",
    role: "FIELD PLAYER",
    title: "REACTIVE CUT",
    tagline: "The direction arrives only at the commitment point",
    provenance:
      "Reactive agility — changing direction in response to an unplanned stimulus — is largely independent of pre-planned change-of-direction speed, and it is the quality that better separates skill levels in adolescent players. A set of timing gates can only time a rehearsed shuttle; because Project Cam already tracks the body, it can fire the cue at the moment of commitment and measure the decision itself.",
    durationLabel: "~3 min",
    workloadKey: "reps",
    roundsLabel: "reps",
    roundsDefault: 6,
    roundsMin: 4,
    roundsMax: 12,
    roundsStep: 2,
    setup: [
      "Start behind the line at one end of the arena length",
      "The cue line sits half way down the run-up",
      "Both side gates must stay clear of furniture and walls",
    ],
    protocol: [
      "Hold still behind the start line until the board arms",
      "Run forward; the direction appears only as you cross the cue line",
      "Cut to the cued side and clear that gate before the timeout",
      "Cutting the wrong way is recorded as an error, not discarded",
    ],
    metrics: [
      "Decision time: cue to the first committed lateral movement",
      "Execution time: cue to clearing the gate",
      "Wrong-way cuts, and which side is slower to decide",
    ],
  },
];
