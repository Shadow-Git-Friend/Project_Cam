# Camera Procurement Deep-Research Report — Project_Cam / Proxiball 3D
### Global-shutter, hardware-synchronised camera upgrade — 2026-05-28

Prepared for: Hanush (MSc ECE, Nazarbayev University) + supervising professor.
Companion docs: `docs/video_analysis_IMG_1962_2026-05-28.md` (evidence) · `cameras.md` (current-rig
bandwidth analysis) · `docs/project_master_brief_for_llm_2026-05-28.md` (whole-project context).

Price tags: **[V]** verified from a named vendor page · **[E]** estimated (typical street price) ·
**[U]** quote-only (vendor lists "contact us"; figure is a market estimate).

---

## 0. PROCUREMENT SUMMARY (send this to the professor)

**What to buy — 4 cameras + lenses + interface + sync, one homogeneous set.**

> **Recommended order (Balanced GigE tier) — total ≈ $1,250–1,650:**
>
> | # | Item | Qty | Unit | Line |
> |---|---|---|---|---|
> | 1 | **HikRobot MV-CS016-10GC** — 1.6 MP Sony IMX273 **global-shutter**, **GigE + PoE**, C-mount, hardware trigger | 4 | ~$210 **[U]** | ~$840 |
> | 2 | C-mount lens, ~6 mm f/1.4, 1/2.9" (HikRobot MVL-HF0628M-6MPE or Computar) | 4 | ~$110 **[E]** | ~$440 |
> | 3 | Quad-port **GigE PoE** NIC (PCIe) *or* 5-port PoE switch + Cat6 | 1 | ~$200 **[E]** | ~$200 |
> | 4 | Cat6 cabling (10 m ×2, 5 m ×2) + ESP32 trigger wiring/opto | — | ~$60 **[E]** | ~$60 |
>
> **Same sensor, premium alternative (max reliability):** 4× **FLIR Blackfly S BFS-U3-16S2C-CS** (or
> the GigE BFS-PGE-16S2C) at **$371 [V]** each → cameras alone ≈ $1,484, total ≈ $2,300–2,600.
>
> **Cheapest blur-fix (Lowest-cost tier):** 4× **HikRobot/Daheng IMX273 USB3** (~$190) + budget lenses,
> reuse existing cabling → total ≈ $900–1,100. Fixes blur; weaker sync + cabling story.

**Why this exact camera:** the **Sony IMX273** is the de-facto 1.6 MP global-shutter machine-vision
sensor. The **same sensor** is sold by FLIR ($371), HikRobot (~$190–210) and Daheng (~$200) — so
HikRobot gives **identical imaging for ~half the FLIR price**. HikRobot is **Hikvision's
machine-vision arm** — the *same brand family as the lab's current DS-E12 cameras* — so the Astana/CIS
distributor channel, Russian-language support and EAC paperwork already exist, and lead time is short.

> ⚠️ **Read before ordering — the cameras are necessary but not sufficient.** The recorded session and
> the system's own telemetry (see `video_analysis_IMG_1962_2026-05-28.md`) show the goal game currently
> fails mostly because the **multi-camera calibration is off** (0 of 14,604 two-camera frames triangulated
> below 200 px), *not* only because of blur. New cameras fix the **hardware ceiling** (no global shutter,
> no sync) that no software can fix — but the team must **also recalibrate** (free) for the system to
> score. Buy the cameras now (long lead time, professor's request) **and** schedule a recalibration.

---

## 1. Key findings (bottom-line decisions)

| Decision | Recommendation | Rationale |
|---|---|---|
| Sensor class | **1.6 MP global shutter, Sony IMX273** | Industry-standard; kills rolling-shutter ball skew; 1.6 MP is ample at arena distance (YOLO resizes to 640 anyway) |
| Interface | **GigE Vision + PoE** | Camera runs are 5–10 m. GigE = 100 m on cheap Cat6, power+data one cable. USB3 needs costly active-optical cables past ~5 m |
| **Sync** | **Hardware trigger from the existing ESP32** | The single biggest accuracy win — eliminates the ±33 ms inter-camera offset that makes moving balls untriangulable |
| Primary camera | **HikRobot MV-CS016-10GC** (IMX273, GigE/PoE) | Same sensor as FLIR at ~½ price; Hikvision family → KZ channel + fast lead time |
| Premium alt. | FLIR Blackfly S 16S2C / Basler ace 2 | Western warranty, IEEE-1588 PTP, mature Linux SDKs |
| Budget alt. | HikRobot/Daheng IMX273 **USB3** | Cheapest path that still fixes the blur |
| Colour vs mono | **Colour** | Drop-in for the existing RGB YOLO ball model (mono is cheaper/faster but needs retraining) |
| Count | **4 (replace all)** | Never mix shutter types in one triangulation rig; keep the array homogeneous |
| Workstation | Add a PCIe **GigE-PoE NIC** (HP Z4 G4 has free slots) | Gives each camera a dedicated 1 Gbit lane — also cures the current USB-2 shared-controller bottleneck |

---

## 2. Why now — the problem this upgrade solves

The current rig is **4× Hikvision DS-E12**: rolling-shutter, **USB 2.0**, all on **one** host
controller, **no hardware sync**, ~**15–18 FPS** ceiling (`cameras.md`). Three consequences, in order
of how much they hurt the goal game (from `video_analysis_IMG_1962_2026-05-28.md`):

1. **No synchronisation** → on a moving ball each camera captures a *different* 3D position, so views
   don't triangulate. *Fixed only by hardware-triggered cameras.*
2. **Rolling shutter** → fast balls smear; bbox centres become ambiguous. *Fixed only by global shutter.*
3. **USB-2 single controller** → bandwidth/FPS ceiling, internal MJPG latency. *Fixed by USB3/GigE with
   per-camera lanes.*

(The current *dominant* failure is actually a **calibration** bug — see the §0 warning — which is a
free software fix and independent of the sensor. This report covers the hardware ceiling the professor
wants to start procuring against.)

---

## 3. Requirements envelope

| Spec | Target | Why |
|---|---|---|
| Shutter | **Global** | Non-negotiable for a flying ball |
| Sensor / resolution | 1.6–2.3 MP (IMX273 / IMX392 / AR0234) | 4K is wasted; YOLO input is 640 px; smaller frames = lower latency + bandwidth |
| Frame rate | **≥ 60 fps** (120+ ideal) | Ball travel/frame shrinks 4× vs 15 fps; better Kalman tracking |
| Interface | **GigE+PoE** (USB3 acceptable at short range) | 5–10 m runs; see §4 |
| **External trigger** | **Opto-isolated GPIO in** | Hardware sync from ESP32 — the key feature |
| Exposure/gain | Manual lock (no auto-hunting) | Stable detection confidence |
| Lens mount | **C-mount** | Standard machine-vision optics |
| Lens FOV | cover play volume from each position | ~6 mm for 1/2.9" at ~6 m (see §8) |
| SDK on Linux | GenICam (Aravis/Harvester) + vendor SDK | Integrates via a `CameraSource` wrapper |
| Price | tiered (see §6) | Professor: global shutter ASAP, avoid multi-thousand |

---

## 4. Interface decision — GigE vs USB3 (the key call for 5–10 m runs)

**Bandwidth math** (1.6 MP colour, 8-bit raw Bayer ≈ 1.48 MB/frame):

| FPS | Per camera | 4 cameras |
|---|---|---|
| 30 | ~356 Mbit/s | ~1.4 Gbit/s |
| 60 | ~712 Mbit/s | ~2.85 Gbit/s |

- **USB3 (5 Gbit/s per controller):** plenty of bandwidth, **but** passive cable maxes ~3 m, active
  copper ~5 m; **10 m needs an active-optical USB3 cable (~$90–150 each) [E]**. The lab's existing
  "USB3 active" extension cables currently negotiate only USB-2 with the DS-E12 — SuperSpeed integrity
  over 10 m is **not guaranteed** and may need fibre. Also the PC's camera-side USB is USB-2 today → a
  USB3 PCIe card is required, and 4 cams on one controller re-creates a shared-bandwidth bottleneck.
- **GigE Vision + PoE (recommended):** **100 m on ordinary Cat6**, one cable carries power *and* data.
  A 1 Gbit lane carries ~712 Mbit/s → **one camera per GigE lane at 60 fps**. Use a **quad-port GigE
  PoE NIC** (each camera its own dedicated lane — also fixes the current shared-controller problem) or
  a small PoE switch (fine at ≤30 fps, or use link aggregation / a 2.5–10 GbE uplink for higher fps).

**Verdict:** **GigE+PoE** for this lab's cable distances and the desire to avoid the USB-2 bottleneck
recurring. USB3 only if every camera can sit within ~5 m of the PC.

---

## 5. Worldwide camera comparison

All are C-mount global-shutter machine-vision cameras with opto-isolated hardware trigger unless noted.
**Bold = shortlisted.** Note how many share the **IMX273** — identical imaging, very different price.

| Camera | Sensor | Res / Shutter | Max FPS | Interface | ~Price (1 pc) | KZ access | Notes |
|---|---|---|---|---|---|---|---|
| **HikRobot MV-CS016-10UC/GC** | IMX273 | 1.6 MP GS | 226–249 | USB3 / **GigE-PoE** | **~$186–210 [V/U]** | **Easy** (Hikvision family) | Best value; same sensor as FLIR |
| **Daheng MER2-160-227U3C / -G** | IMX273 | 1.6 MP GS | 227 | USB3 / GigE | **~$200–280 [U]** | Good (China) | get-cameras/VA Imaging resellers |
| **FLIR Blackfly S BFS-16S2C** | IMX273 | 1.6 MP GS | 226 | **USB3 / GigE-PoE** | **$371 [V]** | Via DigiKey/Edmund | IEEE-1588; gold-standard SDK |
| Basler ace 2 a2A1920-51gcPRO | IMX392 | 2.3 MP GS | 51 | GigE-PoE | $499 [V] | Via distributor | 1920×1200; lower fps |
| LUCID Triton TRI016S | IMX273 | 1.6 MP GS | ~118 | GigE-PoE | from $315 [V] | Via Edmund | IP67 rugged |
| Allied Vision Alvium 1800 U/G-240 | IMX392 | 2.3 MP GS | ~119 | USB3 / GigE | ~$400–550 [E] | Via distributor | Compact, flexible |
| The Imaging Source DFK 33UX273 | IMX273 | 1.6 MP GS | 226 | USB3 | ~$450 [E] | Limited | — |
| XIMEA xiC MC023 | IMX392 | 2.3 MP GS | ~166 | USB3 | ~$600+ [E] | Limited | Tiny, premium |
| e-con See3CAM_24CUG | AR0234 | 2.3 MP GS | 120 | USB3.1 | ~$250–350 [U] | Online | Colour GS, UVC-friendly |
| Arducam AR0234 USB3 | AR0234 | 2.3 MP GS | 80 | USB3 | ~$100–130 [E] | AliExpress | Consumer; M12 lens, weak trigger |
| Luxonis OAK-* | OV9282/AR0234 | 1–2.3 MP GS | 120 | USB3 | ~$150–250 [E] | Online | On-board AI; different paradigm |
| *Current:* Hikvision DS-E12 | — | 2 MP **rolling** | 15–30 | USB2 | ~$40 | owned | The baseline being replaced |

---

## 6. The three budget tiers (all-in: 4 cameras + lenses + interface + sync)

### Tier A — Lowest cost (~$900–1,100) — "professor's not-thousands" option
- 4× **HikRobot/Daheng IMX273 USB3** (~$190) — global shutter fixes the blur.
- 4× budget C-mount lens (~$70–110).
- Reuse existing active USB cables (accept SuperSpeed-over-10 m risk) + USB3 PCIe card (~$40).
- ESP32 trigger wiring (~$15).
- **Trade-off:** USB sync over long cable is fiddly; bandwidth risk if all 4 on one controller; may
  need a fibre USB3 extender on the 10 m runs (then cost approaches Tier B).

### Tier B — Balanced GigE (~$1,250–1,650) — **recommended**
- 4× **HikRobot MV-CS016-10GC** GigE-PoE IMX273 (~$210).
- 4× C-mount ~6 mm f/1.4 lens (~$110).
- Quad-port **GigE-PoE NIC** or 5-port PoE switch + Cat6 (~$200).
- ESP32 → opto trigger wiring (~$15–60).
- **Why:** fixes blur **and** sync, cheap long cabling, per-camera lanes, KZ-friendly, fast lead time.

### Tier C — Premium (~$2,300–3,200) — max reliability / headroom
- 4× **FLIR Blackfly S BFS-PGE-16S2C** (GigE) or **Basler ace 2** (~$371–499).
- 4× quality lens (Computar/Tamron, ~$145).
- Quad-port GigE-PoE NIC (~$250) + Cat6.
- GPIO sync breakouts (~$45 ea) + wiring.
- **Why:** Western warranty, IEEE-1588 PTP sync, the most mature Linux SDKs, pitch-scale headroom (the
  original deep-research PDF's pick).

---

## 7. Supporting setup costs ("additional expenses")

| Item | Need | ~Cost [tag] |
|---|---|---|
| C-mount lenses ×4 | Required; focal length per position (§8) | $70–180 ea [E] |
| GigE-PoE NIC (quad) **or** PoE switch | GigE path; dedicated lanes | $150–400 [E] |
| USB3 PCIe card (Renesas µPD720201) | only if USB3 path | $30–60 [E] |
| Active-optical USB3 cable, 10 m ×2 | only if USB3 path | $90–150 ea [E] |
| Cat6 cable (5–15 m) ×4 | GigE path | ~$5–12 ea [E] |
| ESP32 trigger wiring + opto-isolator / breakout | Hardware sync | $10–45 [E] |
| Camera mounts/brackets | Reuse existing remount hardware where possible | $0–60 [E] |
| SDK | **Free** — HikRobot MVS / Basler pylon / FLIR Spinnaker / vendor-neutral **Aravis/Harvester (GenICam)** on Linux | $0 |
| Software integration | Add a `CameraSource` abstraction to replace the current `cv2.VideoCapture` UVC path; recalibrate intrinsics for the new sensor/resolution | engineering time |

---

## 8. Two things to get right at order time

**Hardware sync wiring (the highest-value step).** Every shortlisted camera has an opto-isolated GPIO
input. Wire all four trigger lines to **one pulse from the existing ESP32** (3.3 V → opto/level-shift →
trigger), 30–120 Hz, rising-edge; set each camera `TriggerMode=On, TriggerSource=Line0`. Result: all
four expose simultaneously (<1 µs jitter) → the ±33 ms inter-camera offset disappears → moving balls
triangulate. This single change is worth more than any sensor spec.

**Lens focal length (FOV).** HFOV ≈ 2·atan(sensor_width / (2·f)). For a 1/2.9" sensor (≈5.6 mm wide):
- 6 mm → ~50° → covers ~5.6 m at 6 m distance (good for corner-to-corner arena coverage).
- 8 mm → ~38° → covers ~4.2 m at 6 m (narrower; for tighter framing).

Pick per camera position; confirm against the actual mount distance before ordering. (A 2/3" sensor
camera with an 8 mm lens gives ~57°, as in the original PDF's Computar M0814-MP2 choice.)

---

## 9. Where to buy + lead time to Astana

| Component | Channel | Lead time [E] |
|---|---|---|
| HikRobot cameras/lenses | Hikvision/HikRobot CIS distributors (Almaty/Astana); Alibaba; AliExpress | 1–4 wk |
| Daheng cameras | get-cameras.com, VA Imaging, Alibaba, eBay | 2–4 wk |
| FLIR Blackfly S | DigiKey, Edmund Optics, Mouser → forwarder | 2–4 wk |
| Basler / Allied / LUCID | regional distributor or Edmund Optics | 2–6 wk |
| Lenses (Computar/Tamron) | RMA Electronics, B&H, distributor | 2–4 wk |
| PoE NIC / switch / Cat6 | local KZ IT retail | days |
| Active-optical USB3 (if USB3) | L-com, Newnex, Amazon → forwarder | 2–4 wk |

**Brand-channel advantage:** because the lab already runs Hikvision DS-E12, the **HikRobot** order can
go through the same local reseller relationship — fastest path to "start the procedure asap."

---

## 10. Verdict (best option)

**Buy Tier B: 4× HikRobot MV-CS016-10GC (IMX273, GigE-PoE, global shutter) + ~6 mm C-mount lenses +
a quad-port GigE-PoE NIC + Cat6 + ESP32 trigger wiring. ≈ $1,250–1,650.**

It fixes the two hardware ceilings the lab cannot solve in software (no global shutter, no sync), uses
the same proven sensor as the $371 FLIR for ~half the price, plugs into the existing Hikvision KZ
channel for the fastest lead time, and the GigE-PoE backbone also cures the legacy USB-2
shared-controller bottleneck. Step up to **Tier C (FLIR/Basler)** if Western warranty + IEEE-1588 PTP
matter more than cost; drop to **Tier A (USB3)** only if the budget must stay sub-$1,100 and every
camera sits within ~5 m of the PC.

**De-risk:** order **one** camera + lens first, verify it on the rig (SDK, trigger, exposure, a quick
recalibration test), then buy the remaining three. Keep the four cameras identical.

---

## 11. Caveats

- **Verified [V]:** FLIR BFS-U3-16S2C-CS **$371** (Edmund Optics); HikRobot MV-CS016-10UC **~$186–194**
  (Alibaba tiered, IMX273 confirmed); Basler a2A1920-51gcPRO **$499** (Wilco; IMX392 2.3 MP 51 fps GigE
  PoE); LUCID Triton GigE PoE **from $315**; Daheng MER2-160-227U3C is IMX273 1.6 MP 227 fps USB3;
  e-con See3CAM_24CUG is AR0234 1920×1200 120 fps colour GS USB3.1; Arducam AR0234 is 2.3 MP 1920×1200
  80 fps colour GS USB3; Computar M0814-MP2 (8 mm f/1.4 2/3") is a real, widely stocked C-mount lens.
- **Estimated [E]:** HikRobot GigE variant price, lens street prices, PoE NIC/switch, active-optical
  USB3 cable, Cat6, trigger wiring, KZ lead times, bandwidth (computed from sensor specs).
- **Quote-only [U]:** Daheng, e-con and HikRobot-GigE list "contact us"; figures are market estimates —
  request a formal quote (Daheng isales@daheng-imaging.com; e-con sales@e-consystems.com; HikRobot via
  CIS distributor).
- **Unverified:** exact KZ distributor stock/pricing; whether the lab's existing 10 m active cables can
  carry USB3 SuperSpeed (test before relying on the USB3 path).
- **Dependency:** the goal game's current failure is dominated by a **calibration** issue, not the
  sensor — these cameras remove the hardware ceiling but must be paired with a recalibration (free) to
  start scoring. See `video_analysis_IMG_1962_2026-05-28.md`.

---

## 12. Completion table

| Research item | Covered |
|---|---|
| Global-shutter camera models (worldwide) | ✓ §5 |
| Verified prices | ✓ §0, §5, §11 |
| Budget tiers (all three) | ✓ §6 |
| Interface decision (USB3 vs GigE) + bandwidth math | ✓ §4 |
| Hardware synchronisation | ✓ §1, §8 |
| Lens selection / FOV | ✓ §8 |
| Supporting setup costs | ✓ §7 |
| Where to buy + KZ lead times | ✓ §9 |
| Best-option verdict + BoM | ✓ §0, §10 |
| Professor one-pager | ✓ §0 |
| Verified/Estimated/Quote tagging | ✓ §11 |
| Link to evidence + calibration caveat | ✓ §0, §2, §11 |

---

### Sources
- [FLIR BFS-U3-16S2C-CS — Edmund Optics](https://www.edmundoptics.com/p/bfs-u3-16s2c-cs-usb3-blackflyreg-s-color-camera/40164/)
- [FLIR Blackfly S USB3 — Teledyne Vision](https://www.teledynevisionsolutions.com/products/blackfly-s-usb3?vertical=machine+vision&segment=iis)
- [HikRobot MV-CS016-10UC (IMX273) — Alibaba listing](https://www.alibaba.com/product-detail/HIKROBOT-MV-CS016-10UC-1-6MP_1601308533358.html)
- [HikRobot machine vision products](https://www.hikrobotics.com/en/machinevision/visionproduct/)
- [Daheng MER2-160-227U3C (IMX273) — get-cameras](https://www.get-cameras.com/USB3.0-Camera-1.6MP-Color-Sony-IMX273-MER2-160-227U3C)
- [Daheng MER2-U3 series](https://en.daheng-imaging.com/index.php?m=content&c=index&a=prolists&catid=106)
- [Basler ace 2 a2A1920-51gcPRO — Wilco Imaging](https://wilcoimaging.com/products/a2a1920-51gcpro)
- [Basler ace 2 a2A1920-51gcPRO — Edmund Optics](https://www.edmundoptics.com/p/basler-ace2-a2a1920-51gcpro-color-gige-pro-camera/44076/)
- [LUCID Triton GigE PoE](https://thinklucid.com/triton-gige-machine-vision/)
- [e-con See3CAM AR0234 USB3 global shutter](https://www.e-consystems.com/industrial-cameras/ar0234-usb3-global-shutter-camera.asp)
- [Arducam 2.3MP AR0234 colour GS USB3](https://www.arducam.com/arducam-2-3mp-ar0234-color-global-shutter-usb-3-0-camera-module.html)
- [Computar M0814-MP2 8mm f/1.4 lens — B&H](https://www.bhphotovideo.com/c/product/888985-REG/computar_M0814_MP2_2_3_Fixed_Lens.html)
- [GigE PCIe PoE interface card — Edmund Optics](https://www.edmundoptics.com/p/gige-pcie-21x4-2-port-interface-card-with-poe/46625/)
- [Powering USB/GigE cameras — Edmund Optics app note](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/how-to-power-usb-and-gige-cameras/)
