// UI catalog. Deliberately holds NO filesystem paths: the repo root, the python
// interpreter and every script live in the Rust resolver
// (src-tauri/src/launch_profiles.rs), so the frontend cannot name a program to
// run. What is here is the profile id plus the text a coach reads.
import type { ProfileId } from "./launch";

export type Launch = {
  title: string;
  desc: string;
  profile_id: ProfileId;
  danger?: boolean;
};

export const LAUNCHES: Launch[] = [
  {
    title: "6-CAMERA CINEMATIC ARENA",
    desc: "Fast mirrored skeleton · runs degraded from 2 cameras",
    profile_id: "free_view_usb6",
  },
  {
    title: "6-CAMERA + BLM AIM OVERLAY",
    desc: "Pose + UDP target + aim visualization; no direct firing",
    profile_id: "blm_overlay_usb6",
  },
  {
    title: "4-CAMERA YOLO-POSE",
    desc: "Classic calibrated arena fallback",
    profile_id: "yolo_pose_4cam",
  },
  {
    title: "RECORD 3D SESSION",
    desc: "Clean SIGINT stop preserves MP4 finalization",
    profile_id: "record_3d",
    danger: true,
  },
];

export type Readiness = { label: string; status: string; ready: boolean };

export const UNKNOWN_READINESS: Readiness[] = [
  { label: "CAMERA DEVICES", status: "UNKNOWN", ready: false },
  { label: "CALIBRATION FILES", status: "UNKNOWN", ready: false },
  { label: "FACE MODEL FILES", status: "UNKNOWN", ready: false },
  { label: "GALLERY FILE", status: "UNKNOWN", ready: false },
];
