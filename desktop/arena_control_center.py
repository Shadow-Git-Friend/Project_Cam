#!/usr/bin/env python3
"""Project Cam Arena Control Center — one-window launcher for the live rig."""

from __future__ import annotations

import argparse
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_venv_python(repo_root=REPO_ROOT, fallback=sys.executable) -> str:
    root = Path(repo_root)
    for relative in ("venv/bin/python", ".venv/bin/python"):
        candidate = root / relative
        if candidate.exists():
            return str(candidate)
    return str(fallback)


def build_live_command(
    *,
    repo_root,
    script,
    multi_people=1,
    face_id=False,
    auto_orbit=False,
    limb_heat=False,
    primary_person="",
):
    command = ["bash", str(Path(repo_root) / script)]
    if int(multi_people) > 1:
        command += ["--multi-person", str(int(multi_people))]
    if face_id:
        command.append("--face-id")
        if str(primary_person).strip():
            command += ["--primary-person", str(primary_person).strip()]
    if auto_orbit:
        command.append("--auto-orbit")
    if limb_heat:
        command.append("--limb-heat")
    return command


def build_face_enroll_command(*, repo_root, python, name, camera="0"):
    return [
        str(python),
        str(Path(repo_root) / "Parallel_working/scripts/face_enroll.py"),
        "--camera",
        str(camera),
        "--name",
        str(name),
    ]


def build_model_setup_command(repo_root, python):
    return [
        str(python),
        str(Path(repo_root) / "Parallel_working/scripts/download_face_models.py"),
    ]


@dataclass(frozen=True)
class LaunchSpec:
    title: str
    description: str
    script: str
    accent: str


ORANGE = "#ff9848"
CYAN = "#55d9ff"
GREEN = "#63e69a"
RED = "#ff655e"
BG = "#100f12"
PANEL = "#19171d"
CARD = "#211e26"
CARD_HOVER = "#2b2731"
EDGE = "#3d3745"
TEXT = "#f2edf7"
DIM = "#9a919f"
FAINT = "#625b69"
LOG_BG = "#09090b"

LAUNCHES = (
    LaunchSpec(
        "6-CAMERA CINEMATIC ARENA",
        "Fast mirrored skeleton · multi-person ready",
        "Parallel_working/run_live_usb6_mirrored_skeleton.sh",
        ORANGE,
    ),
    LaunchSpec(
        "6-CAMERA + BLM AIM OVERLAY",
        "Pose + UDP target + aim visualization; no direct firing",
        "Parallel_working/run_live_usb6_blm.sh",
        ORANGE,
    ),
    LaunchSpec(
        "4-CAMERA YOLO-POSE",
        "Classic calibrated arena fallback",
        "Parallel_working/run_live_parallel_yolopose.sh",
        CYAN,
    ),
    LaunchSpec(
        "RECORD 3D SESSION",
        "Clean SIGINT stop preserves MP4 finalization",
        "Parallel_working/run_record_3d.sh",
        RED,
    ),
)


class ArenaControlCenter:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.python = resolve_venv_python()
        self.proc = None
        self.proc_title = ""
        self.messages = queue.Queue()
        self.closing = False

        root.title("Project Cam — Arena Control Center")
        root.geometry("1120x760")
        root.minsize(940, 640)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        family = self._font_family()
        self.title_font = (family, 18, "bold")
        self.section_font = (family, 9, "bold")
        self.card_font = (family, 11, "bold")
        self.body_font = (family, 9)
        self.log_font = (family, 10)

        self.multi_enabled = tk.BooleanVar(root, value=True)
        self.multi_people = tk.IntVar(root, value=4)
        self.face_id = tk.BooleanVar(root, value=False)
        self.auto_orbit = tk.BooleanVar(root, value=False)
        self.limb_heat = tk.BooleanVar(root, value=False)
        self.primary_person = tk.StringVar(root, value="")
        self.enroll_name = tk.StringVar(root, value="")
        self.camera_source = tk.StringVar(root, value="0")
        self.status = tk.StringVar(root, value="IDLE")
        self.command = tk.StringVar(root, value="")
        self.launch_buttons = []

        self._build()
        self._log("Project Cam control center ready", "sys")
        self._log(f"repo: {REPO_ROOT}", "dim")
        self._log(f"python: {self.python}", "dim")
        self.root.after(60, self._pump)

    def _font_family(self):
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return "monospace"
        for family in ("JetBrains Mono", "Fira Code", "DejaVu Sans Mono"):
            if family in available:
                return family
        return "monospace"

    def _build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 8))
        tk.Label(
            header, text="PROJECT CAM", font=self.title_font, bg=BG, fg=ORANGE
        ).pack(side="left")
        tk.Label(
            header, text="  /  ARENA CONTROL CENTER", font=self.title_font,
            bg=BG, fg=TEXT,
        ).pack(side="left")
        tk.Label(
            header, text="LOCAL · MULTI-VIEW · 3D", font=self.body_font,
            bg=BG, fg=FAINT,
        ).pack(side="right")

        body = tk.PanedWindow(
            self.root, orient="horizontal", bg=EDGE, sashwidth=2,
            borderwidth=0, showhandle=False,
        )
        body.pack(fill="both", expand=True, padx=18)
        left = tk.Frame(body, bg=BG, width=470)
        right = tk.Frame(body, bg=BG)
        body.add(left, minsize=430)
        body.add(right, minsize=380)

        self._section(left, "LAUNCH")
        for spec in LAUNCHES:
            self._launch_card(left, spec)

        self._section(left, "TRACKING OPTIONS")
        options = tk.Frame(left, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        options.pack(fill="x", pady=(0, 8))
        self._checkbox(options, "Multiple people", self.multi_enabled)
        spin = tk.Spinbox(
            options, from_=2, to=6, textvariable=self.multi_people, width=3,
            bg=CARD, fg=TEXT, buttonbackground=CARD, justify="center",
            relief="flat", font=self.body_font,
        )
        spin.pack(anchor="w", padx=30, pady=(0, 3))
        self._checkbox(options, "Local Face ID labels (not authentication)", self.face_id)
        self._checkbox(options, "Auto-orbit 3D camera", self.auto_orbit)
        self._checkbox(options, "Limb speed heat", self.limb_heat)
        self._entry_row(options, "Primary name", self.primary_person)

        self._section(left, "LOCAL FACE GALLERY")
        face = tk.Frame(left, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        face.pack(fill="x")
        self._entry_row(face, "Name", self.enroll_name)
        self._entry_row(face, "Camera", self.camera_source)
        actions = tk.Frame(face, bg=PANEL)
        actions.pack(fill="x", padx=8, pady=(4, 8))
        self._action_button(actions, "DOWNLOAD MODELS", self.setup_models, CYAN).pack(side="left")
        self._action_button(actions, "ENROLL", self.enroll_face, GREEN).pack(side="left", padx=6)
        self._action_button(actions, "LIST", self.list_faces, DIM).pack(side="left")

        self._section(right, "MISSION LOG")
        self.log = tk.Text(
            right, bg=LOG_BG, fg=TEXT, font=self.log_font, relief="flat",
            state="disabled", wrap="word", padx=10, pady=10,
        )
        self.log.pack(fill="both", expand=True)
        for tag, color in (("sys", CYAN), ("err", RED), ("cmd", ORANGE), ("dim", DIM)):
            self.log.tag_configure(tag, foreground=color)

        footer = tk.Frame(self.root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        footer.pack(fill="x", padx=18, pady=(8, 16))
        tk.Label(
            footer, textvariable=self.status, bg=PANEL, fg=GREEN,
            font=self.section_font, anchor="w",
        ).pack(side="left", padx=10, pady=9)
        tk.Entry(
            footer, textvariable=self.command, state="readonly",
            readonlybackground=PANEL, fg=DIM, relief="flat", font=self.body_font,
        ).pack(side="left", fill="x", expand=True, padx=10)
        self.stop_button = tk.Button(
            footer, text="■ STOP", command=self.stop, state="disabled",
            bg="#3b171a", fg=RED, activebackground="#572126",
            relief="flat", font=self.card_font, padx=18,
        )
        self.stop_button.pack(side="right", padx=8, pady=5)

    def _section(self, parent, text):
        tk.Label(
            parent, text=text, bg=BG, fg=FAINT, font=self.section_font, anchor="w"
        ).pack(fill="x", pady=(8, 4))

    def _launch_card(self, parent, spec):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        frame.pack(fill="x", pady=(0, 6))
        button = tk.Button(
            frame, text="▶  " + spec.title, command=lambda: self.launch_live(spec),
            anchor="w", bg=CARD, fg=spec.accent, activebackground=CARD_HOVER,
            activeforeground=TEXT, relief="flat", font=self.card_font, padx=10,
        )
        button.pack(fill="x", pady=(5, 0))
        tk.Label(
            frame, text=spec.description, bg=CARD, fg=DIM,
            font=self.body_font, anchor="w", padx=14,
        ).pack(fill="x", pady=(0, 6))
        self.launch_buttons.append(button)

    def _checkbox(self, parent, text, variable):
        tk.Checkbutton(
            parent, text=text, variable=variable, bg=PANEL, fg=TEXT,
            activebackground=PANEL, activeforeground=TEXT, selectcolor=CARD,
            relief="flat", font=self.body_font, anchor="w",
        ).pack(fill="x", padx=8, pady=2)

    def _entry_row(self, parent, label, variable):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=8, pady=3)
        tk.Label(row, text=label, width=13, anchor="w", bg=PANEL, fg=DIM,
                 font=self.body_font).pack(side="left")
        tk.Entry(row, textvariable=variable, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=self.body_font).pack(
            side="left", fill="x", expand=True, ipady=2
        )

    def _action_button(self, parent, text, command, color):
        button = tk.Button(
            parent, text=text, command=command, bg=CARD, fg=color,
            activebackground=CARD_HOVER, activeforeground=TEXT,
            relief="flat", font=self.section_font, padx=8, pady=4,
        )
        self.launch_buttons.append(button)
        return button

    def launch_live(self, spec):
        people = self.multi_people.get() if self.multi_enabled.get() else 1
        command = build_live_command(
            repo_root=REPO_ROOT,
            script=spec.script,
            multi_people=people,
            face_id=self.face_id.get(),
            auto_orbit=self.auto_orbit.get(),
            limb_heat=self.limb_heat.get(),
            primary_person=self.primary_person.get(),
        )
        self._spawn(command, spec.title)

    def setup_models(self):
        self._spawn(build_model_setup_command(REPO_ROOT, self.python), "FACE MODEL SETUP")

    def enroll_face(self):
        name = self.enroll_name.get().strip()
        if not name:
            self._log("Enter a name before enrollment", "err")
            return
        command = build_face_enroll_command(
            repo_root=REPO_ROOT, python=self.python, name=name,
            camera=self.camera_source.get().strip() or "0",
        )
        self._spawn(command, f"ENROLL {name}")

    def list_faces(self):
        command = [
            self.python,
            str(REPO_ROOT / "Parallel_working/scripts/face_enroll.py"),
            "--list",
        ]
        self._spawn(command, "FACE GALLERY")

    def _spawn(self, command, title):
        if self.proc is not None and self.proc.poll() is None:
            self._log("A pipeline is already running; stop it first", "err")
            return
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=dict(os.environ, PYTHONUNBUFFERED="1"),
            )
        except OSError as exc:
            self._log(f"Launch failed: {exc}", "err")
            self.proc = None
            return
        self.proc_title = title
        self.command.set(shlex.join(command))
        self.status.set("RUNNING  /  " + title)
        self._log("$ " + shlex.join(command), "cmd")
        self._set_interlock(True)
        threading.Thread(target=self._read_child, args=(self.proc,), daemon=True).start()

    def _read_child(self, process):
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self.messages.put(("line", line.rstrip()))
        finally:
            self.messages.put(("exit", process.wait()))

    def stop(self):
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
            self._log("SIGINT sent; waiting for clean shutdown", "sys")
            self.stop_button.configure(state="disabled")
        except OSError as exc:
            self._log(f"Stop failed: {exc}", "err")

    def _set_interlock(self, running):
        state = "disabled" if running else "normal"
        for button in self.launch_buttons:
            button.configure(state=state)
        self.stop_button.configure(state="normal" if running else "disabled")

    def _pump(self):
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "line":
                    self._log(str(payload))
                else:
                    code = int(payload)
                    self._log(f"{self.proc_title} exited with code {code}",
                              "sys" if code in (0, 130, -2) else "err")
                    self.status.set("IDLE" if code in (0, 130, -2) else f"EXITED {code}")
                    self.proc = None
                    self._set_interlock(False)
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(60, self._pump)

    def _log(self, text, tag=None):
        self.log.configure(state="normal")
        prefix = time.strftime("%H:%M:%S ") if tag else ""
        self.log.insert("end", prefix + str(text) + "\n", tag or "")
        self.log.configure(state="disabled")
        self.log.see("end")

    def close(self):
        self.closing = True
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
            except OSError:
                pass
        self.root.destroy()


def build_parser():
    parser = argparse.ArgumentParser(description="Project Cam desktop control center")
    parser.add_argument("--check", action="store_true",
                        help="Print resolved paths without opening a display.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.check:
        print("Project Cam control center")
        print(f"repo={REPO_ROOT}")
        print(f"python={resolve_venv_python()}")
        print(f"DISPLAY={os.environ.get('DISPLAY', '(unset)')}")
        for spec in LAUNCHES:
            state = "OK" if (REPO_ROOT / spec.script).is_file() else "MISSING"
            print(f"{state} {spec.script}")
        return 0
    try:
        root = tk.Tk(className="project-cam")
    except tk.TclError as exc:
        print(f"Cannot open Project Cam window: {exc}", file=sys.stderr)
        return 1
    ArenaControlCenter(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

