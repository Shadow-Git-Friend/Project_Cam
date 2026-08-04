"""Session report rendering (markdown; PDF/HTML conversion happens upstream).

Hard rules honoured here (see CLAUDE.md Academy constraints):
- timestamps rendered in Asia/Almaty;
- every KPI line carries its uncertainty or confidence — a metric with no
  confidence field is refused rather than silently printed;
- units metric-only.

The renderer is deliberately string-based (no Jinja2 dependency) so it works
on the minimal install; the dashboard consumes the same dict via the API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ALMATY = ZoneInfo("Asia/Almaty")

_LABELS = {
    "en": {
        "title": "Session Report",
        "player": "Player",
        "generated": "Generated",
        "physical": "Physical load",
        "readiness": "Injury & readiness",
        "confidence": "confidence",
    },
    "ru": {
        "title": "Отчёт о тренировке",
        "player": "Игрок",
        "generated": "Сформирован",
        "physical": "Физическая нагрузка",
        "readiness": "Риск травм и готовность",
        "confidence": "достоверность",
    },
    "kk": {
        "title": "Жаттығу есебі",
        "player": "Ойыншы",
        "generated": "Құрылған уақыты",
        "physical": "Физикалық жүктеме",
        "readiness": "Жарақат қаупі және дайындық",
        "confidence": "сенімділік",
    },
}


def _require_confidence(name: str, payload: dict) -> str:
    conf = payload.get("confidence")
    if conf is None:
        raise ValueError(
            f"metric block '{name}' has no confidence field — refusing to publish it"
        )
    return str(conf)


def render_session_report(
    player_id: str,
    physical: dict,
    acwr_result: dict | None = None,
    session_start_utc: datetime | None = None,
    lang: str = "en",
) -> str:
    """Render one player's session as markdown.

    physical: `PhysicalLoadSummary.to_dict()`; acwr_result: `AcwrResult.to_dict()`.
    """
    if lang not in _LABELS:
        raise ValueError(f"lang must be one of {sorted(_LABELS)}")
    tr = _LABELS[lang]
    start = session_start_utc or datetime.now(timezone.utc)
    stamp = start.astimezone(ALMATY).strftime("%Y-%m-%d %H:%M %Z")

    phys_conf = _require_confidence("physical", physical)
    lines = [
        f"# {tr['title']} — {tr['player']} {player_id}",
        f"{tr['generated']}: {stamp} (Asia/Almaty)",
        "",
        f"## {tr['physical']} ({tr['confidence']}: {phys_conf})",
        f"- Distance: {physical['total_distance_m']:.0f} m "
        f"± {physical['total_distance_sigma_m']:.0f} m",
        f"- HSR (>19.8 km/h): {physical['hsr_distance_m']:.0f} m",
        f"- Sprint (>25.2 km/h): {physical['sprint_distance_m']:.0f} m "
        f"in {physical['sprint_count']} sprints",
        f"- Max speed: {physical['max_speed_kmh']:.1f} km/h "
        f"± {physical['speed_sigma_kmh']:.1f} km/h",
        f"- Accel/decel events (>2.5 m/s²): "
        f"{len(physical['accelerations'])}/{len(physical['decelerations'])}",
        f"- Metabolic power (mean): {physical['metabolic_power_mean_wkg']:.1f} W/kg",
        f"- Player-load equivalent: {physical['player_load_eq']:.1f} a.u.",
    ]

    if acwr_result is not None:
        acwr_conf = _require_confidence("acwr", acwr_result)
        ratio = acwr_result["ratio"]
        ratio_txt = f"{ratio:.2f}" if ratio is not None else "n/a"
        lines += [
            "",
            f"## {tr['readiness']} ({tr['confidence']}: {acwr_conf})",
            f"- ACWR (7:28): {ratio_txt} — {acwr_result['band']} "
            f"({acwr_result['days_observed']} days observed)",
        ]

    lines.append("")
    return "\n".join(lines)
