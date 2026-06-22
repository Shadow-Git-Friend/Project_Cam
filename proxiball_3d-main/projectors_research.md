# Video Projectors for a CV‑Driven Football Training Facility — Research Brief

**Author:** Research compilation prepared for the Proxiball 3D project
**Scope:** Feasibility, hardware choices, software stack, and design constraints for adding **ceiling‑mounted video projectors** to a computer‑vision–driven football training arena (an affordable Footbonaut/Footbot/skills.lab alternative).

---

## 0. Executive summary

A projector‑augmented wall (and optionally floor) is the most cost‑effective way to add the *visual‑target* layer that Footbonaut‑class commercial systems use, **without buying their LED panels or proprietary touch frames**. The recommended stack:

- **Projection surface:** matte white, semi‑rigid impact‑rated fabric stretched over a steel frame (golf‑simulator–grade ImpactWhite/Carl's Place style), with optional foam back‑padding to kill rebound. Gain ≈ 0.8–1.0, viewing angle ≥ 170°. Avoid glossy paint, ALR screens, and high‑gain materials — they break the diffuse Lambertian assumption the CV pipeline relies on.
- **Projectors:** **laser, short‑throw, ≥ 6 000 ANSI lumens, WUXGA/4K, ≥ 120 Hz, ≤ 16 ms input lag.** Ceiling‑mount, edge‑blended, with software warp (Christie Mystique, VIOSO, Scalable, or open‑source equivalents).
- **Impact detection stays in CV.** The projector is *output only*. Ball position in 3D comes from your existing multi‑camera detector; the wall plane is calibrated by homography to the projector coordinate frame, so a 3D impact point is rendered as an animation at the right pixel within one display frame.
- **Lighting:** the room can stay reasonably bright. With 6 000+ lumens projectors and the wall illuminance kept around **80–150 lux** at the projection surface, the projected image stays readable while the cameras still get enough exposure on the ball. Indirect, uniform LED lighting (no spots on the wall) is the key.
- **Latency budget:** target **end‑to‑end ≤ 80 ms** from impact frame capture to animated pixel on the wall (camera ≤ 5 ms, detection ≤ 30 ms, render+display ≤ 40 ms). Anything under ~120 ms reads as "instant" to the player.

The rest of this document supports each of those numbers and lays out a build plan.

---

## 1. Reference systems (what we are competing with)

### 1.1 Footbonaut (Borussia Dortmund, Hoffenheim) — the gold standard

- 14 m × 14 m cage. Player stands in the centre of a circle of **72 panels**: 8 ball launchers and 64 light‑up grid targets. ([Bundesliga overview][bundesliga-footbonaut])
- A red square signals where the ball is coming from, green tells the player where to pass it. Ball speeds up to 100 km/h (62 mph), typical 60–70 km/h. Reaction, vision, precision drills.
- Created by Christian Güttler (Berlin); used from U9 through senior team at BVB. ([Wikipedia][wiki-footbonaut])
- The "targets" are physical LED panels — that is the expensive part. Replacing those LED targets with **projected zones on a single continuous wall** is exactly our cost‑down move.

### 1.2 Footbot (Poland, commercial)

- Robotic feeder, ball speeds up to **150 km/h**, cannon angles 0–30°, ball detection up to **300 km/h**. Personal dashboards, adaptive difficulty. ([Footbot.eu][footbot-eu])
- Footbot uses a *target ring* like Footbonaut, not projection. Useful as a benchmark for launcher specs we already match.

### 1.3 skills.lab Arena (Anton Paar SportsTec, Austria)

- **The closest commercial analogue to what you are designing.** 320 m² hall, automated ball machines, **360° projection on screens driven by 5 high‑performance projectors**, plus cameras for ball + player tracking. 6 interactive screens display moving players, targets, and game scenarios. ([skills‑lab.com][skillslab-corp], [Teledyne case study][teledyne-fc-bayern])
- Used at FC Bayern Munich Campus, RB Leipzig, RB Salzburg, etc. Peer‑reviewed reliability study published in *Sensors / PMC*. ([PMC 12131152][pmc-skillslab])
- Confirms the architecture: **launchers + projection walls + camera tracking + scenario library = the canonical design.**

### 1.4 SoccerBot 360 (Germany — Ralf Rangnick's project at Hoffenheim/RB)

- Circular cage, 10 m perimeter (≈ 90 m² interior). **Six full‑HD projectors** render a **360° real‑time 3D scene**. Motion sensors and high‑speed cameras drive the interaction. Norwich City bought one for ~£750 000. ([SoccerBot360][soccerbot360], [Sempre Milan][soccerbot-explained])
- Cognitive training emphasis (reaction, anticipation, attention, cognitive flexibility) rather than only ball striking.

### 1.5 MultiBall (Germany — KraftBlock)

- A **stainless‑steel sensor frame** attached to a white wall, paired with a projector. Claims **100 %** ball‑impact detection, **2.5 cm accuracy**, **40 ms** latency, sub‑system designed with proprietary IR sensors so it works **outdoors / in bright light**. 45+ games. ([MultiBall technology page][multiball-tech])
- Important takeaway: they explicitly chose **sensor frame > camera detection** for reliability in bright environments. **Our differentiator is that we already have a robust CV detector, so we don't need the frame** — but we have to engineer around the lighting trade‑offs MultiBall avoided.

### 1.6 Lü Interactive Playground (Quebec)

- School‑gym product. **3D camera + laser projector + sound + dynamic lighting** turn any gym wall into an interactive surface. Ball detection on the wall via the 3D camera; **no sensor hardware on the wall itself**. ([Lü Interactive][lu-interactive], [Exergame product page][lu-exergame])
- This is essentially our architecture but for schools. Confirms that **pure‑CV impact detection on a projected wall is a shipped, working product**.

### 1.7 Other systems worth knowing

| System | What's different | Why we care |
|---|---|---|
| **Elite Skills Arena** (UK) | Targets + camera tracking, used by Premier League academies | Pricing benchmark |
| **TOCA Soccer / Touch Trainer** | Robotic feeder, screen‑based drills | Drill format library |
| **t‑wall / Touch Wall** | LED grid (no projector) | What we deliberately do *not* build |
| **LYMB.iO** | Interactive sports + gaming walls | Game design references |
| **PlaySight SmartCourt** | Multi‑camera capture, analytics overlays | Analytics overlay design |

---

## 2. How real‑time CV ↔ projector synchronisation works

This is the part the professor is really asking about: *how does the system know where the ball touched, and how does it animate the touch in real time?*

### 2.1 Pipeline

```
[High‑speed cameras] ──► [Ball detector (your existing model)] ──► [3D ball position estimator]
                                                                          │
                                                                          ▼
                                                            [Wall‑plane intersection test]
                                                                          │
                                                                          ▼
                                                            [3D→projector pixel mapping]
                                                                          │
                                                                          ▼
                                                            [Render engine emits impact FX]
                                                                          │
                                                                          ▼
                                                            [Projector → wall]
```

The whole loop must close in roughly one human reaction window (≤ 100–120 ms) to feel "instant".

### 2.2 The three coordinate frames

1. **Camera frame** — pixels in each camera's image; what your YOLO/detector outputs.
2. **World frame** — metric 3D coordinates of the arena (origin commonly at the centre of the floor).
3. **Projector frame** — pixels in the rendered scene. Each projector also has its own intrinsics and a pose in the world frame.

You need two calibrations:

- **Camera ↔ world**: the multi‑view extrinsic calibration you already do (checkerboard / ChArUco / known target points). Triangulation gives 3D ball positions. ([3D ball tracking, two cameras][3d-ball-tracking-two-cam])
- **Projector ↔ world**: treat the projector as an inverse camera. Project a known pattern (asymmetric circles, Gray‑code, or structured stripes) onto the wall and observe it with the calibrated cameras. Recover the projector's intrinsics + pose + (importantly) **lens distortion** using **local homographies per checkerboard corner**, since global homographies cannot model projector lens distortion. ([Moreno & Taubin, projector‑camera calibration][moreno-taubin])

Once both are calibrated, a 3D point on the wall plane maps deterministically to a pixel in each projector. If the wall is approximately flat, a single **homography per projector** can be used at runtime (very fast, no 3D required at render time).

### 2.3 Detecting "impact"

You don't need a dedicated impact sensor if you already have a 3D ball trajectory. Three signal types:

1. **Plane intersection** — the most robust. Compute the ball's instantaneous 3D position and velocity from triangulation; when the position crosses the wall plane (z ≈ z_wall), declare contact and record the (x, y) on the wall. With ≥ 120 fps cameras you can also linearly interpolate between the last "approaching" and first "departing" frame for sub‑frame accuracy.
2. **Optical‑flow / derivative spike** — at the moment of impact the ball's velocity reverses and the derivative of the trajectory shows a sharp peak. Useful as a **confirmation flag** to suppress false positives (e.g. ball passing close to but not touching the wall). ([OpenCV impact‑detection thread][opencv-impact])
3. **Audio trigger (optional)** — a contact mic or piezo on the wall fires within ~1 ms of impact. Can be used to *gate* the CV detection window. Cheap insurance for noisy detections.

For our setup, **(1) primary + (2) confirmation** is the right combination. Audio is optional but adds robustness at very low cost.

### 2.4 Latency budget

| Stage | Realistic ms | How to keep it low |
|---|---|---|
| Camera exposure + readout | 2–8 | Global‑shutter machine‑vision cameras at 120–240 fps, short exposure |
| USB3/GigE transport | 1–4 | Direct PCIe frame grabber or 10 GbE for high‑res |
| Detector inference | 5–25 | YOLOv8/v12‑n or a TensorRT‑exported tiny model on GPU |
| Triangulation + plane test | < 1 | Simple linear algebra |
| Render + composite | 5–16 | Game‑engine (Unity/Unreal/Godot) or shader‑only renderer, vsync‑aware |
| Projector input lag | 4–25 | **Pick a projector with rated input lag ≤ 16 ms** (ViewSonic LS921WU is 16 ms @ 120 Hz; many golf‑sim projectors publish this number) |
| Projector display refresh | 8–17 (depends on refresh) | 120 Hz refresh halves this vs 60 Hz |
| **Total target** | **≤ 80 ms** | Achievable on commodity hardware |

Anything ≤ 100–120 ms reads as instant. Above ~150 ms players start "feeling" the lag.

### 2.5 Software stack suggestions

- **Detection / tracking:** keep what you have (PyTorch/TensorRT, multi‑camera triangulation).
- **Render engine:** Unity (HDRP) or Unreal Engine — both have mature multi‑display, warp/blend, and shader pipelines and large game‑dev talent pools. Godot is the open‑source option. For purely 2D overlays, **TouchDesigner** or **OpenFrameworks** are well‑proven.
- **Warp & blend:** Christie Mystique, **VIOSO**, **Scalable Display**, NVIDIA Warp & Blend, or open‑source **Splash** (Switzerland). Auto‑alignment from a single camera saves days of manual work. ([VIOSO][vioso], [NVIDIA Warp and Blend][nvidia-warp])
- **Networking:** the detection PC and the render PC can be the same machine, or split across two PCs over 10 GbE / TSN with a UDP/OSC packet per impact event. Same‑machine is simpler.

---

## 3. Wall: the surface, the structure, the impact behaviour

### 3.1 What you are trying to achieve simultaneously

1. **Good diffuse projection** — uniform, high‑contrast image, no hotspots, ≥ 170° viewing.
2. **Survives ball impact** — repeated 50–100 km/h footballs, no tearing, no progressive sag.
3. **Doesn't dent CV detection** — predictable colour, no reflections of the projector lamp back into the cameras.
4. **Doesn't bounce the ball unpredictably** — ideally absorbs some energy so the rebound is consistent and player can play a follow‑up shot.

### 3.2 Recommended construction (front projection)

A four‑layer wall — borrowed almost directly from the golf‑simulator industry, which has solved this problem for 100+ mph projectiles:

| Layer | Material | Role |
|---|---|---|
| 1. Front (player‑facing) | **Tightly woven impact polyester** (Elite Screens ImpactWhite 350 / Carl's Place 3‑layer / Vividstorm impact fabric). Gain 0.8–1.0, matte, white, 170°+ viewing. Rated for 150–250 mph balls. | Projection surface + first impact layer ([ImpactWhite product page][impactwhite], [Carl's Place premium screens][carls-place]) |
| 2. Middle | High‑density polyester or knitted polymer | Dampens noise + absorbs impact energy |
| 3. Foam | 25–50 mm closed‑cell EVA / PE foam | Cuts rebound, protects players |
| 4. Frame | Powder‑coated steel tube (40×40 mm) | Tensions the front fabric, anchors to wall studs |

Mount the assembly with a 30–50 mm air gap behind the foam to dissipate impact further.

### 3.2b Budget alternatives for a prototype

The golf-sim grade construction above is the permanent-facility recommendation. For a research prototype, a football at 60–80 km/h is far gentler than a golf ball at 150+ mph — you have much cheaper options.

| Option | Materials | Approx. cost (4 m × 3 m wall) | Projection quality | Durability |
|---|---|---|---|---|
| **A. White canvas + timber frame** | Heavy cotton duck canvas (theatre/artist grade) stapled over a 40×40 mm timber frame. 25 mm yoga mat / camping foam glued behind. | $80–150 | Excellent — matte white fabric is a near-ideal projection surface | Good. Won't tear from footballs. May sag slowly over months; re-tension as needed. |
| **B. Matte PVC banner + frame** | Outdoor advertising banner material (matte white, not gloss). Same timber frame. Add foam pad behind. | $50–120 | Good — slight texture visible up close, fine for drills | Excellent. Waterproof, easy to wipe clean. |
| **C. Plywood + foam gym mat** | 12 mm plywood sheet, painted matte white. 50 mm gymnastics foam mat leaned or velcro'd against it. Stretch a white spandex cover over the foam face so the projection surface is smooth. | $80–150 | Good — flat and rigid base gives a very even image | Very good. Solid, won't sag. Heavier to move. |
| **D. White spandex on a frame** | Spandex/lycra fabric (white) stretched on a timber or steel frame. No foam needed — the stretch of the fabric absorbs impact naturally. | $60–100 | Adequate — slightly softer image because the fabric diffuses light more. Fine for coloured targets, not ideal for fine text. | Good. Naturally absorbs impact and snaps back. |

**Honest recommendation:** Build **Option A or C** for your first test wall. Total cost under $200 including frame. Validate the whole CV ↔ projector pipeline on it. Only upgrade to proper impact-screen fabric (section 3.2) when you move to a permanent installation running full training days.

> **Key point:** none of these options use glossy, ALR, or curved surfaces — they all stay within the "safe zone" described in section   3.3 below.

### 3.3 Alternatives and what to avoid

- **Projection paint on drywall.** Cheap, OK image, but the wall itself rings on impact and drywall cracks within weeks. Only viable for the *non‑target* areas of the room.
- **ALR / CLR screens.** Tempting because they reject ceiling light. **Do not use them.** They are directional — they only look correct from a narrow viewing cone, which breaks for a player moving around the arena. They also confuse cameras because the wall's apparent brightness depends on viewing angle. ([Sound & Vision UST + ALR][sv-ust-alr])
- **Glossy paint / vinyl.** Specular highlights destroy the CV detection of the ball when it crosses the wall — the detector starts firing on the reflection of the projector lamp.
- **Curved walls.** Possible, but they require **non‑linear warping** and break the single‑homography shortcut. Plan for flat walls in v1; revisit for v2.

### 3.4 Rear vs front projection

| | Front projection | Rear projection |
|---|---|---|
| Shadows from player | Yes — every time the player steps near the wall | None |
| Space needed behind wall | None | 2–4 m (short‑throw) or more |
| Image brightness | High | ~30 % loss through the screen |
| Cost | Lower | ~20–40 % higher |
| Calibration | Simpler | Requires aligned rear room geometry |
| **Verdict for our case** | **Pick this for v1**. We are space‑constrained and the player will only block one wall at a time. | Consider for one "showcase" wall in v2. |

Sources: ProjectorCentral, Stewart Filmscreen. ([ProjectorCentral front vs rear][pc-front-rear], [Stewart Filmscreen front vs rear][stewart-front-rear])

### 3.5 Floor projection

Yes — you can absolutely "project cones on the floor". Two practical patterns:

- **Tactical overlays during drills** — cones, ladders, passing lanes, "press to here" arrows, defender shadows. The skills.lab Arena does exactly this.
- **Real‑time feedback** — heat map of where the player stood, last sprint vector, energy zones.

Constraints unique to floor projection:

- The player **stands on the projection**, so a *single* projector creates a hard shadow under their feet. Either accept that (the shadow is small) or use **two overlapping projectors with edge blending** so the shadow is filled by the second projector.
- Use a **matte, non‑slip floor finish** (sports vinyl like Mondo, Gerflor Taraflex, or matte‑coated wood). High gloss = glare into cameras and players.
- Floor‑mounted ceiling projectors should be **very short‑throw** (throw ratio ≤ 0.4) so they sit close to the ceiling and don't get hit by a high ball.

---

## 4. Projector selection

### 4.1 Required spec sheet

| Parameter | Target | Why |
|---|---|---|
| Light source | **Laser phosphor / RGB laser** | 20 000+ h lifetime, no lamp changes, instant on/off, stable colour |
| Brightness | **≥ 6 000 ANSI lumens** per projector (for ~150‑inch wall image in 100–200 lux gym ambient) | Calculated below |
| Throw ratio | **0.5 – 0.9 (short throw)** for walls, **0.25 – 0.4 (ultra‑short)** for floors | Lets you ceiling‑mount close to the wall and avoid the ball striking the projector |
| Resolution | **WUXGA (1920×1200) minimum, 4K UHD preferred** | Crisp targets and animations at large size |
| Refresh / input lag | **≥ 120 Hz refresh, ≤ 16 ms input lag** | Latency budget |
| Lens shift + warp | **H/V shift, geometric warp, edge blend** built‑in | Multi‑projector alignment |
| Orientation | **360° / portrait‑capable, dust‑sealed IP6X optical engine** | Ceiling/angled mounts in a dusty sports hall |
| Inputs | 2× HDMI 2.0 + HDBaseT | Long cable runs from the control rack |
| Connectivity | LAN control (PJ‑Link / Crestron) | Centralised on/off, brightness, source switching |

### 4.2 Concrete candidate models (early 2026 market)

| Model | Lumens | Resolution | Throw | Input lag | Notable |
|---|---|---|---|---|---|
| **ViewSonic LS921WU** | 6 000 ANSI | WUXGA | 0.81–0.89 | 16 ms @ 120 Hz | Good price/perf, sports‑oriented. ([Datasheet][viewsonic-ls921wu]) |
| **Optoma ZU607TST** | 6 000 ANSI | WUXGA | Short | Low | IP6X sealed, 30 000 h laser, 24/7‑rated. Popular in golf sims. ([Optoma ZU607TST][optoma-zu607tst]) |
| **Optoma ZK608TST** | 6 000 ANSI | **4K UHD** | Short | Low | Same chassis at 4K. ([Optoma ZK608TST][optoma-zk608tst]) |
| **Epson PowerLite L695SE** | 6 000 ANSI | WUXGA (4K enhancement) | 0.5–0.7 + 1.4× zoom | Low | Strong colour brightness (3LCD). ([Epson L695SE][epson-l695se]) |
| **BenQ LU935 / LU951ST** | 6 000 / 5 200 ANSI | WUXGA | Std / Short | Low | Common in indoor sports installs. ([BenQ LU935][benq-lu935]) |
| **Panasonic PT‑RZ‑series** (RZ690, RZ790) | 6 000–7 000 ANSI | WUXGA | Optional lenses | Low | Industrial‑grade, expensive but bullet‑proof for production deployments. |

**Indicative pricing (Q2 2026):** ~$3 000–$6 000 per projector for the first four; $8 000–$15 000 for Panasonic/Christie industrial units. Plan for **3–6 projectors** depending on coverage.

### 4.3 How many lumens? (Worked example)

Rule of thumb: for a projected image to read well, the projected illuminance on the screen should be **at least 2–3× the ambient illuminance** on the screen (for matte gain 1.0 screens).

- Wall area covered by one projector: 4 m × 3 m = 12 m².
- Ambient illuminance on the wall (uniform indirect LED gym lighting): ~100 lux.
- Required projected illuminance: ~300 lux on the screen.
- Required luminous flux on the screen: 300 lux × 12 m² = **3 600 lumens *on screen***.
- Account for **screen gain (0.85)** and **typical 25 % losses** (warp/blend overlap, edge falloff, ageing): 3 600 / 0.85 / 0.75 ≈ **5 650 ANSI lumens** required at the projector.
- ⇒ a **6 000 ANSI lumens** unit is the right minimum. If you want to push ambient to 200 lux (very bright gym), step up to 8 000–10 000 ANSI per projector or accept a smaller image per unit.

References: BenQ lumens guide, MKLights gym lighting guide, ViewSonic projector brightness primer. ([BenQ lumens guide][benq-lumens], [MKLights sports lighting][mklights-sports], [ViewSonic lumens explainer][viewsonic-lumens])

### 4.4 Number of projectors and placement

For an arena similar to skills.lab (4 walls, ~5 m high, 8–12 m wide each):

- **4 wall projectors** (one per wall, edge‑blend not strictly needed if each wall has one projector).
- **+ 2 floor projectors** for tactical overlays, edge‑blended along the centre line so they cover the whole floor without a single shadow point under the player.
- Total: **6 projectors** — matches what SoccerBot 360 and skills.lab Arena actually deploy.

Placement principles:

- **Mount close to the ceiling, behind the player's line of action**, so the ball never travels between the projector and the screen on a normal shot. Short‑throw lens helps here.
- Keep the **projector's exit pupil out of the camera frame** to avoid lamp flare. Hood the lens with a black snoot if needed.
- Use **rigid steel mounts**, not the consumer arm mounts — sports halls vibrate.
- Cable runs in **HDBaseT** (Cat6A) to a central rack; avoids 15 m HDMI failures.
- **Heat:** 6 000‑lumen lasers dissipate ~400–600 W. Plan for ventilation in the ceiling void.

### 4.5 Edge blending and warp

When two projectors overlap (which they should, by 10–20 % of width, on long walls or the floor):

- Software in the render engine, or hardware in the projector, multiplies a **soft‑edge gradient mask** on each projector so brightness adds to a flat 100 % in the overlap.
- **Geometric warp** corrects for keystone and mild wall curvature.
- **Camera‑assisted auto‑calibration** (Christie Mystique, VIOSO, Scalable) projects structured light onto the wall, observes it with a calibration camera, and solves warp+blend automatically in minutes. ([Christie Mystique playing‑surface][christie-mystique], [Scalable Display][scalable-display])

### 4.6 What about LED video walls instead?

LED wall would solve brightness and contrast in one shot — but at **5–10× the cost per m²** and you cannot kick a ball into it (yet). Projection is the right tool for a kickable target wall.

---

## 5. Lighting conditions — can the room stay bright?

**Short answer: yes, partly.** It will not be a black‑box cinema, but it cannot be full daylight either.

### 5.1 Constraints

- **Cameras** want ~200–500 lux of *diffuse* light on the ball for crisp 120–240 fps imaging at low ISO. Less than ~100 lux and you start trading exposure for motion blur.
- **Projectors** want *low light on the wall* for contrast — ideally < 100 lux of ambient on the projection surface.
- **Players** want enough light to see the ball and not trip — sport halls are normally 300–500 lux floor.

These three pull in different directions; the trick is **directional lighting**.

### 5.2 Recommended lighting design

1. **No fixtures aimed at the projection walls.** Use **indirect LED uplighting** (uplit to a white ceiling that re‑radiates light onto the floor). This gives ~300 lux on the floor for the players and cameras but only ~80–150 lux on the walls — within the projector's headroom.
2. **CRI ≥ 90, 5 000 K LEDs**, flicker‑free (driver PWM ≥ 20 kHz) so the high‑speed cameras don't see banding.
3. **Block any windows** that line up with the projection walls (blackout shades on rolls).
4. **Black‑out the area immediately behind/around the wall frames** (matte black paint or curtain) so stray bounces don't lift the wall's black level.
5. **Zoned dimming.** A scene preset for "calibration", "drill", and "demo / open day" — drill mode dims wall‑side fixtures to 30–50 %, demo mode lifts them.

With this layout the room **feels like a normal indoor sports hall, not a cinema**. That matches the experience inside skills.lab Arena and the Lü Playground.

### 5.3 What you definitely cannot do

- Direct sunlight onto the wall — washes the image to grey.
- Stage spots or coloured floods anywhere near the wall — projector contrast collapses.
- 50/60 Hz fluorescent or cheap LED tubes — flicker beats with 120 fps cameras.

---

## 6. Calibration workflow (operational checklist)

Document this and put it in the arena run‑book; you will redo it any time projectors are bumped.

1. **Geometry survey.** Measure wall dimensions, mount projectors, confirm beam clears player zone.
2. **Camera intrinsic calibration.** Standard checkerboard, OpenCV.
3. **Camera extrinsic / multi‑camera calibration.** ChArUco board moved through the play volume; bundle‑adjust.
4. **Define wall planes** in the world frame (3–4 ChArUco markers temporarily taped to each wall, captured, then removed).
5. **Projector calibration.** For each projector: project Gray‑code pattern → cameras observe → recover projector intrinsics + extrinsics using **local‑homography method** (Moreno & Taubin). Cross‑check with a manual ChArUco alignment.
6. **Warp + blend.** Use VIOSO / Mystique / Scalable's auto‑align with a wide‑angle calibration camera. Save the warp profile per projector.
7. **End‑to‑end latency test.** Shoot 10 calibration shots at the wall, log the timestamp of the highest‑velocity frame and the timestamp the impact animation was actually rendered. Tune until p95 ≤ 80 ms.
8. **Drift monitoring.** Run a 30 s structured‑light recheck every morning; reject the day if RMS reprojection error > 2 px.

---

## 7. Applications you can ship on top of this stack

Order them by how much new code each one needs.

### Tier A — easy wins, mostly content not code

- **Footbonaut‑style target drills.** Project a 4×4 grid of squares on each wall. One square goes red ("incoming"), another goes green ("pass here"). Score = hit the green within X seconds at velocity ≥ V.
- **Reactive moving targets.** Squares slide / fade / shrink — train decision speed.
- **Pattern recognition.** Show three symbols, only one is "correct" — passes only count to that one.
- **Cooperative wall games for groups.** MultiBall‑style — clear a row, pop balloons, defend a goal.
- **Goal‑frame animations.** A photoreal goal with keeper, projected on a wall — train shot placement against a moving keeper.

### Tier B — modest new code, big training value

- **Match scenarios.** A defender silhouette runs across the wall; the player must pass to the opposite side. Drives "scan before you receive".
- **Pressure simulation.** Audio + visual stimuli (a crowd, a press indicator) layered onto the drill.
- **Off‑the‑ball cueing.** The wall shows where the player should *be*, not where to pass — useful for positional / tactical drills.
- **Floor cone overlays.** Tactical setups (rondo zones, pressing triggers) projected onto the floor — change drills without touching a physical cone.

### Tier C — flagship features that justify a paper

- **Real‑time tactical feedback.** Show the player their last sprint speed / pass speed / accuracy as a HUD on the floor as they reset between reps.
- **AI opponent.** A virtual defender projected on the wall, whose pose adapts to the player's body orientation (your CV pipeline already has pose data).
- **Match clip recreation.** Convert a Bundesliga clip into a wall scenario the player has to solve — like skills.lab does for FC Bayern.
- **Adaptive difficulty.** Reinforcement‑learning loop that tunes ball launch parameters + target position based on the player's recent accuracy.
- **Multi‑player competition mode.** Two players, two walls, shared score — turns the lab into a content engine.

---

## 8. Cost ballpark (rough order of magnitude, USD, Q2 2026)

| Item | Qty | Unit | Subtotal |
|---|---:|---:|---:|
| 6 000‑lumen WUXGA laser short‑throw projector | 4 (walls) | $4 000 | $16 000 |
| 6 000‑lumen ultra‑short‑thqffffrow projector (floor) | 2 | $5 000 | $10 000 |
| Heavy‑duty ceiling mounts + HDBaseT extenders + cabling | 6 | $400 | $2 400 |
| Impact projection screen fabric + steel frame + foam | 4 walls × 12 m² | $200 / m² | $9 600 |
| Calibration camera (industrial USB3, wide lens) | 1 | $800 | $800 |
| Render PC (RTX 4080‑class) + display capture card | 1 | $3 500 | $3 500 |
| Warp & blend software (VIOSO Anyblend or similar) | 1 | $3 000 | $3 000 |
| Indirect LED lighting kit + dimming controller | 1 | $4 000 | $4 000 |
| Misc cable, racks, cooling, install labour | — | — | $5 000 |
| **Total (4 walls + 2 floor zones)** | | | **≈ $54 000** |

For reference, SoccerBot 360 retails around **£600 000–£750 000** (~$760k–$950k). Even doubling our estimate for contingency, we are **at least an order of magnitude cheaper** — the project's core thesis.

---

## 9. Risks and open questions

1. **Ball occluding the projection on the way in.** A ball mid‑flight casts a small moving shadow on the wall. Mitigation: short‑throw projectors mounted high so the shadow falls on a non‑target zone of the wall during the last 0.5 m of flight.
2. **Camera ↔ projector cross‑talk.** If a camera's exposure straddles a projector frame transition you get banding. Either **synchronise camera trigger to projector vsync** (most industrial cameras support GPIO trigger) or use a **DLP projector running at ≥ 240 Hz** so the banding integrates out.
3. **Player safety against the wall.** Foam back‑layer plus rounded frame edges. Verify rebound velocity for a 100 km/h strike stays below the threshold that could injure a follow‑up player.
4. **Maintenance.** Laser projectors are 20 000 h+, but **dust filters** in a sports hall clog fast. Plan monthly filter checks; favour IP6X‑sealed optical engines (Optoma ZU/ZK series, Panasonic).
5. **Calibration drift.** Vibration from a thumping ball over months *will* move the projectors. Bake the daily recheck into the morning routine.
6. **Floor projector blow‑outs from stray balls.** Even an UST mounted near the ceiling can take a deflection. Add a **clear polycarbonate hood** on the lens path of floor projectors.
7. **Concurrent‑use bandwidth.** Six 4K streams at 120 Hz is a *lot* of pixels. Distribute renders across 2 GPUs if you go to 4K everywhere; WUXGA on a single RTX 4080 is comfortable.
8. **Sound design.** Often forgotten — a kick that doesn't *thump* on the speakers feels disconnected from the wall animation. Budget for a 2.1 PA tied to the impact event.

---

## 10. Recommended next steps for the team

1. **Pilot a single wall first.** One 4 m × 3 m impact‑screen wall + one 6 000‑lumen short‑throw projector + your existing CV stack. Validate the latency budget and lighting design in‑situ before scaling.
2. **Build the calibration tooling once, properly.** Project‑Gray‑code → solve homography → save profile. This is the most reusable code you will write for the whole projector subsystem.
3. **Pick the render engine early.** Unity HDRP with NDI/Spout outputs to a warp/blend tool is a low‑risk path; TouchDesigner is faster to prototype but harder to ship as a product.
4. **Reach out to skills.lab and Lü** for academic collaboration — both have published reliability studies and may welcome a low‑cost open‑hardware variant for university labs.
5. **Plan the publication.** A short paper on *"Pure‑CV impact detection on a projected football wall, with a $54k BOM vs $750k commercial systems"* is the natural research output and a strong thesis chapter.

---

## Sources

### Reference systems
- [Bundesliga — What is a Footbonaut?](https://www.bundesliga.com/en/bundesliga/news/what-is-a-footbonaut-borussia-dortmund-hoffenheim-training-8257)
- [Wikipedia — Footbonaut](https://en.wikipedia.org/wiki/Footbonaut)
- [Footbot.eu — product](https://footbot.eu/)
- [skills.lab Corporate](https://skills-lab.com/)
- [skills.lab Arena reliability study (PMC 12131152)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12131152/)
- [Teledyne FLIR — Vision‑based sports analytics (skills.lab case study)](https://www.teledynevisionsolutions.com/learn/learning-center/machine-vision/vision-based-sports-analytics/)
- [FC Bayern — How does the Skills.Lab at the Bayern Campus work?](https://fcbayern.com/en/news/2021/03/how-does-the-new-skills.lab-at-the-fc-bayern-campus-work)
- [SoccerBot360](https://www.soccerbot360.de/en/)
- [Sempre Milan — SoccerBot360 explained](https://sempremilan.com/soccerbot360-explained-rangnicks-brainchild-designed-to-coach-players-like-never-before)
- [Pink'Un — Norwich City and SoccerBot360](https://www.pinkun.com/news/22695421.norwich-city-soccerbot360-inside-track-canaries-want-750-000-aid/)
- [MultiBall — technology](https://multi-ball.com/pages/technology)
- [MultiBall — hardware](https://multi-ball.com/pages/multiball-hardware)
- [Lü Interactive](https://play-lu.com/)
- [Lü Interactive at Exergame](https://exergame.com/lu-interactive-playground/)
- [Elite Skills Arena](https://eliteskillsarena.com/)
- [LYMB.iO](https://lymb.io/)

### Projection technology
- [ProjectorCentral — Front vs Rear projection](https://www.projectorcentral.com/Front-vs-Rear-Projection.htm)
- [Stewart Filmscreen — Front vs Rear projection](https://www.stewartfilmscreen.com/en/news/whats-the-difference-between-front-rear-projection-screens)
- [Elite Screens — ImpactWhite 350](https://elitescreens.com/products/impactwhite-350/)
- [Elite Screens — GolfSim Bay Series](https://elitescreens.com/products/golfsim-bay-series/)
- [Carl's Place — Premium Golf Impact Screens](https://shop.carlofet.com/premium-golf-impact-screens)
- [ProjectorCentral — How to choose a golf‑sim impact screen](https://www.projectorcentral.com/how-to-choose-golf-sim-impact-screen.htm)
- [Sound & Vision — UST projectors and ALR screens](https://www.soundandvision.com/content/ultra-short-throw-projectors-and-ambient-light-rejecting-screens-perfect-together)
- [BenQ — Projector brightness & lumens](https://www.benq.com/en-us/knowledge-center/knowledge/projector-brightness-lumens.html)
- [ViewSonic — What are projector lumens?](https://www.viewsonic.com/library/tech/what-are-lumens-and-how-to-use-them-to-choose-a-projector/)
- [Christie Digital — Playing‑surface projection mapping](https://www.christiedigital.com/solutions/projection-mapping/playing-surface-mapping/)
- [Christie Digital — Warping & Blending](https://www.christiedigital.com/products/warping-blending/)
- [VIOSO](https://vioso.com/)
- [Scalable Display — Warp and Blend](https://www.scalabledisplay.com/projector-warp-and-blend/)
- [NVIDIA — Warp and Blend developer page](https://developer.nvidia.com/warp-and-blend)

### Projector candidates
- [ViewSonic LS921WU](https://www.viewsonic.com/us/ls921wu-1920-x-1200-resolution-6-000-ansi-lumens-0-81-0-89-throw-ratio.html)
- [Optoma ZU607TST (via Golf2U)](https://www.golf-2-u.com/products/optoma-zu607tst-6000-lumens-wuxga-short-throw-golf-simulator-projector)
- [Optoma ZK608TST 4K (via Indoor Golf Outlet)](https://indoorgolfoutlet.com/products/optoma-zk608tst-4k-6000-lumens-uhd-short-throw-golf-simulator-projector)
- [Epson PowerLite L695SE](https://www.golf-2-u.com/products/epson-l695se-powerlite-6000-lumen-wuxga-short-throw-3lcd-laser-projector-with-4k-enhancement)
- [BenQ LU935](https://indoorgolfoutlet.com/products/benq-lu935-6000-lumens-normal-throw-laser-golf-simulator-projector)

### CV impact detection and calibration
- [arXiv 2302.00123 — Soccer ball detection with multiple cameras](https://arxiv.org/abs/2302.00123)
- [Wu et al. — Multi‑camera 3D ball tracking framework (IET Image Processing)](https://ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/iet-ipr.2020.0757)
- [3D tracking of a soccer ball using two synchronized cameras (Springer)](https://link.springer.com/chapter/10.1007/978-3-540-77255-2_22)
- [Real‑time modelling of 3D soccer ball trajectories (Strathclyde)](https://strathprints.strath.ac.uk/29273/1/1237_all.pdf)
- [Moreno & Taubin — Simple, accurate, robust projector‑camera calibration (Brown)](http://mesh.brown.edu/calibration/files/Simple,%20Accurate,%20and%20Robust%20Projector‑Camera%20Calibration.pdf)
- [Brown Mesh — Projector‑camera calibration software](http://mesh.brown.edu/calibration/)
- [OpenCV Q&A — Detecting a thrown object hitting a wall](https://answers.opencv.org/question/147682/detecting-a-thrown-object-hitting-a-wall-in-front-of-the-camera/)
- [PyImageSearch — Ball tracking with OpenCV](https://pyimagesearch.com/2015/09/14/ball-tracking-with-opencv/)
- [Tennis ball tracking using YOLOv12 (MDPI 2025)](https://www.mdpi.com/2673-4591/134/1/25)

### Lighting
- [BenQ — Lumens for daylight/outdoor projection](https://www.benq.com/en-us/knowledge-center/knowledge/projectors-for-daytime-outdoors.html)
- [MKLights — How many lumens for sports lighting](https://www.mklights.com/BLOGS/how-many-lumens-do-you-need-for-sports-lighting.html)
- [Sports Venue Calculator — Commercial gym lighting guide](https://sportsvenuecalculator.com/knowledge/led-sports-lighting/commercial-gym-weight-room-lighting/)

[bundesliga-footbonaut]: https://www.bundesliga.com/en/bundesliga/news/what-is-a-footbonaut-borussia-dortmund-hoffenheim-training-8257
[wiki-footbonaut]: https://en.wikipedia.org/wiki/Footbonaut
[footbot-eu]: https://footbot.eu/
[skillslab-corp]: https://skills-lab.com/
[teledyne-fc-bayern]: https://www.teledynevisionsolutions.com/learn/learning-center/machine-vision/vision-based-sports-analytics/
[pmc-skillslab]: https://pmc.ncbi.nlm.nih.gov/articles/PMC12131152/
[soccerbot360]: https://www.soccerbot360.de/en/
[soccerbot-explained]: https://sempremilan.com/soccerbot360-explained-rangnicks-brainchild-designed-to-coach-players-like-never-before
[multiball-tech]: https://multi-ball.com/pages/technology
[lu-interactive]: https://play-lu.com/
[lu-exergame]: https://exergame.com/lu-interactive-playground/
[3d-ball-tracking-two-cam]: https://link.springer.com/chapter/10.1007/978-3-540-77255-2_22
[moreno-taubin]: http://mesh.brown.edu/calibration/files/Simple,%20Accurate,%20and%20Robust%20Projector‑Camera%20Calibration.pdf
[opencv-impact]: https://answers.opencv.org/question/147682/detecting-a-thrown-object-hitting-a-wall-in-front-of-the-camera/
[impactwhite]: https://elitescreens.com/products/impactwhite-350/
[carls-place]: https://shop.carlofet.com/premium-golf-impact-screens
[sv-ust-alr]: https://www.soundandvision.com/content/ultra-short-throw-projectors-and-ambient-light-rejecting-screens-perfect-together
[pc-front-rear]: https://www.projectorcentral.com/Front-vs-Rear-Projection.htm
[stewart-front-rear]: https://www.stewartfilmscreen.com/en/news/whats-the-difference-between-front-rear-projection-screens
[viewsonic-ls921wu]: https://www.viewsonic.com/us/ls921wu-1920-x-1200-resolution-6-000-ansi-lumens-0-81-0-89-throw-ratio.html
[optoma-zu607tst]: https://www.golf-2-u.com/products/optoma-zu607tst-6000-lumens-wuxga-short-throw-golf-simulator-projector
[optoma-zk608tst]: https://indoorgolfoutlet.com/products/optoma-zk608tst-4k-6000-lumens-uhd-short-throw-golf-simulator-projector
[epson-l695se]: https://www.golf-2-u.com/products/epson-l695se-powerlite-6000-lumen-wuxga-short-throw-3lcd-laser-projector-with-4k-enhancement
[benq-lu935]: https://indoorgolfoutlet.com/products/benq-lu935-6000-lumens-normal-throw-laser-golf-simulator-projector
[benq-lumens]: https://www.benq.com/en-us/knowledge-center/knowledge/projector-brightness-lumens.html
[mklights-sports]: https://www.mklights.com/BLOGS/how-many-lumens-do-you-need-for-sports-lighting.html
[viewsonic-lumens]: https://www.viewsonic.com/library/tech/what-are-lumens-and-how-to-use-them-to-choose-a-projector/
[christie-mystique]: https://www.christiedigital.com/solutions/projection-mapping/playing-surface-mapping/
[scalable-display]: https://www.scalabledisplay.com/projector-warp-and-blend/
[vioso]: https://vioso.com/
[nvidia-warp]: https://developer.nvidia.com/warp-and-blend
