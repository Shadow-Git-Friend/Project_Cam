#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[2]
ARENA_ROOT = ROOT / "arena_fixed"

SRC_DIMENSIONS = ROOT / "garage_lab_combined" / "cal" / "extrinsics" / "Dimensions.txt"
SRC_EXTRINSICS = ROOT / "garage_lab_combined" / "cal" / "extrinsics" / "extrinsics_final.json"

OUT_DIM_FIXED = ARENA_ROOT / "cal" / "extrinsics" / "Dimensions_fixed.txt"
OUT_DIM_MIRROR = ARENA_ROOT / "cal" / "extrinsics" / "Dimensions_mirrored_y.txt"
OUT_EXTR = ARENA_ROOT / "cal" / "extrinsics" / "extrinsics_fixed.json"

OUT_REPORT_MD = ARENA_ROOT / "reports" / "y_axis_report.md"
OUT_REPORT_JSON = ARENA_ROOT / "reports" / "y_axis_report.json"


@dataclass
class ArenaData:
    y_max_cm: float
    cameras_cm: Dict[str, Tuple[float, float, float]]
    tag_corners_cm: Dict[int, List[Tuple[float, float, float]]]
    raw_text: str


def fmt_num(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s


def parse_arena_dimensions(path: Path) -> ArenaData:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    m_y = re.search(r"Y\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*cm", txt)
    if not m_y:
        raise RuntimeError(f"Cannot parse Y from {path}")
    y_max = float(m_y.group(1))

    cams: Dict[str, Tuple[float, float, float]] = {}
    for m in re.finditer(
        r"^(Cam[A-Za-z0-9_]+)\s*=\s*\(\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*\)\s*$",
        txt,
        flags=re.MULTILINE,
    ):
        cams[m.group(1)] = (float(m.group(2)), float(m.group(3)), float(m.group(4)))

    tag_corners: Dict[int, List[Tuple[float, float, float]]] = {}
    parts = re.split(r"ID=(\d+):", txt)
    for i in range(1, len(parts), 2):
        tag_id = int(parts[i])
        block = parts[i + 1]
        hits = re.findall(
            r"c\d\s*\(\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*\)",
            block,
        )
        if len(hits) < 4:
            continue
        corners = [(float(x), float(y), float(z)) for x, y, z in hits[:4]]
        tag_corners[tag_id] = corners

    return ArenaData(y_max_cm=y_max, cameras_cm=cams, tag_corners_cm=tag_corners, raw_text=txt)


def mirror_y_text(src_text: str, y_max_cm: float) -> str:
    out_lines: List[str] = []
    cam_re = re.compile(
        r"^(Cam[A-Za-z0-9_]+)\s*=\s*\(\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*\)\s*$"
    )
    c_re = re.compile(r"(c\d\s*\(\s*)([\-0-9.]+)(\s*,\s*)([\-0-9.]+)(\s*,\s*)([\-0-9.]+)(\s*\))")

    for line in src_text.splitlines():
        m_cam = cam_re.match(line.strip())
        if m_cam:
            name = m_cam.group(1)
            x = float(m_cam.group(2))
            y = float(m_cam.group(3))
            z = float(m_cam.group(4))
            y_new = y_max_cm - y
            out_lines.append(f"{name} = ({fmt_num(x)}, {fmt_num(y_new)}, {fmt_num(z)})")
            continue

        m_corner = c_re.search(line)
        if m_corner:
            x = float(m_corner.group(2))
            y = float(m_corner.group(4))
            z = float(m_corner.group(6))
            y_new = y_max_cm - y
            repl = (
                f"{m_corner.group(1)}{fmt_num(x)}{m_corner.group(3)}{fmt_num(y_new)}"
                f"{m_corner.group(5)}{fmt_num(z)}{m_corner.group(7)}"
            )
            out_lines.append(c_re.sub(repl, line, count=1))
            continue

        if line.startswith("Origin:"):
            out_lines.append("Origin: North-West (0,0,0)")
            continue
        if line.startswith("East Wall is at Y="):
            out_lines.append("East Wall is at Y=305, 0<X<623")
            continue
        if line.startswith("West Wall is at Y="):
            out_lines.append("West Wall is at Y=0, 0<X<623")
            continue

        out_lines.append(line)

    return "\n".join(out_lines) + "\n"


def avg_tag_y(tag_corners: List[Tuple[float, float, float]]) -> float:
    return sum(c[1] for c in tag_corners) / max(1, len(tag_corners))


def build_report(data: ArenaData) -> dict:
    east_group = [20, 16, 19, 17, 18, 21, 22]
    west_group = [11, 12, 13, 14, 15, 10, 0]

    report = {
        "y_max_cm": data.y_max_cm,
        "expected": {
            "east_near_zero": ["CamEast"] + [f"ID{t}" for t in east_group],
            "west_near_ymax": ["CamWest"] + [f"ID{t}" for t in west_group],
        },
        "actual_y_cm": {"cameras": {}, "tags_avg_y": {}},
        "checks": {},
    }

    for cam in ["CamEast", "CamWest", "CamNorth", "CamSouth"]:
        if cam in data.cameras_cm:
            report["actual_y_cm"]["cameras"][cam] = data.cameras_cm[cam][1]

    for tag_id in sorted(data.tag_corners_cm):
        report["actual_y_cm"]["tags_avg_y"][f"ID{tag_id}"] = avg_tag_y(data.tag_corners_cm[tag_id])

    tol_zero = 20.0
    tol_max = 20.0

    def near_zero(v: float) -> bool:
        return abs(v - 0.0) <= tol_zero

    def near_max(v: float) -> bool:
        return abs(v - data.y_max_cm) <= tol_max

    checks = {}
    if "CamEast" in report["actual_y_cm"]["cameras"]:
        checks["CamEast_near_zero"] = near_zero(report["actual_y_cm"]["cameras"]["CamEast"])
    if "CamWest" in report["actual_y_cm"]["cameras"]:
        checks["CamWest_near_ymax"] = near_max(report["actual_y_cm"]["cameras"]["CamWest"])

    for t in east_group:
        key = f"ID{t}"
        if key in report["actual_y_cm"]["tags_avg_y"]:
            checks[f"{key}_near_zero"] = near_zero(report["actual_y_cm"]["tags_avg_y"][key])
    for t in west_group:
        key = f"ID{t}"
        if key in report["actual_y_cm"]["tags_avg_y"]:
            checks[f"{key}_near_ymax"] = near_max(report["actual_y_cm"]["tags_avg_y"][key])

    report["checks"] = checks
    report["checks_ok_ratio"] = sum(1 for v in checks.values() if v) / max(1, len(checks))
    return report


def report_markdown(report: dict) -> str:
    lines = []
    lines.append("# Y-axis validation report (arena_fixed)")
    lines.append("")
    lines.append(f"- `Ymax`: `{report['y_max_cm']}` cm")
    lines.append("- Expected:")
    lines.append("  - `CamEast + IDs 20,16,19,17,18,21,22` near `Y≈0`")
    lines.append("  - `CamWest + IDs 11,12,13,14,15,10,0` near `Y≈Ymax`")
    lines.append("")
    lines.append("## Camera Y (cm)")
    for k, v in report["actual_y_cm"]["cameras"].items():
        lines.append(f"- `{k}`: `{fmt_num(v)}`")
    lines.append("")
    lines.append("## Tag average Y (cm)")
    for k, v in report["actual_y_cm"]["tags_avg_y"].items():
        lines.append(f"- `{k}`: `{fmt_num(v)}`")
    lines.append("")
    lines.append("## Checks")
    for k, v in report["checks"].items():
        lines.append(f"- `{k}`: `{'OK' if v else 'FAIL'}`")
    lines.append("")
    lines.append(f"- Check pass ratio: `{report['checks_ok_ratio']:.3f}`")
    lines.append("")
    lines.append("## Notes")
    lines.append("- `Dimensions_fixed.txt` keeps East-side `Y=0` convention.")
    lines.append("- `Dimensions_mirrored_y.txt` is generated only as debug alternative.")
    lines.append("- No source files in `garage_lab_combined` were modified.")
    return "\n".join(lines) + "\n"


def main() -> None:
    (ARENA_ROOT / "cal" / "extrinsics").mkdir(parents=True, exist_ok=True)
    (ARENA_ROOT / "reports").mkdir(parents=True, exist_ok=True)
    (ARENA_ROOT / "backups").mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ARENA_ROOT / "backups" / ts
    backup_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(SRC_DIMENSIONS, backup_dir / "Dimensions.source.txt")
    if SRC_EXTRINSICS.exists():
        shutil.copy2(SRC_EXTRINSICS, backup_dir / "extrinsics_final.source.json")

    data = parse_arena_dimensions(SRC_DIMENSIONS)

    # Fixed Y: keep east-side zero as requested.
    shutil.copy2(SRC_DIMENSIONS, OUT_DIM_FIXED)

    # Debug alternative: mirrored Y.
    mirrored_txt = mirror_y_text(data.raw_text, data.y_max_cm)
    OUT_DIM_MIRROR.write_text(mirrored_txt, encoding="utf-8")

    if SRC_EXTRINSICS.exists():
        shutil.copy2(SRC_EXTRINSICS, OUT_EXTR)

    report = build_report(data)
    OUT_REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_REPORT_MD.write_text(report_markdown(report), encoding="utf-8")

    print(f"[OK] fixed dimensions: {OUT_DIM_FIXED}")
    print(f"[OK] mirrored dimensions: {OUT_DIM_MIRROR}")
    if OUT_EXTR.exists():
        print(f"[OK] extrinsics copy: {OUT_EXTR}")
    print(f"[OK] report: {OUT_REPORT_MD}")
    print(f"[OK] backup: {backup_dir}")


if __name__ == "__main__":
    main()
