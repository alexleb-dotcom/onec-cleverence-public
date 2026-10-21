#!/usr/bin/env python3
"""Q115 S2 Windows-only OFF-PRODUCTION image-in-use diagnostic regression.

Runs only owned *disposable copied* OneC Orbit WPF EXEs under a mock UI_CONTEXT
launcher. Never calls INSTALL/UPDATE, changes installed roots, or kills unrelated
processes. Validates that tray-hide and another instance still block update.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

if os.name != "nt":
    raise SystemExit("WINDOWS_HOST_REQUIRED")

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "PRODUCT" / "OneCChatWorker"
EXE_SOURCE = PACKAGE / "control-center" / "publish" / "OneCArchitecture.ControlCenter.exe"
PROBE = PACKAGE / "tests" / "Inspect-OrbitUpdaterImageLease.ps1"
LOCK = json.loads((PACKAGE / "runtime.lock.json").read_text(encoding="utf-8"))
EXPECTED = LOCK["components"]["control-center/publish/OneCArchitecture.ControlCenter.exe"]
assert hashlib.sha256(EXE_SOURCE.read_bytes()).hexdigest() == EXPECTED

user32 = ctypes.WinDLL("user32", use_last_error=True)
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]


def windows(pid: int) -> list[int]:
    found = []

    @CALLBACK
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    return found


def until(check, seconds=35):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.25)
    raise AssertionError("ISOLATED_FIXTURE_WINDOW_TIMEOUT")


def probe(image: Path, fixture: Path):
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(PROBE), "-ImagePath", str(image),
        "-FixtureRoot", str(fixture),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=35, check=True,
    )
    try:
        val = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception as e:
        raise AssertionError(f"UNPARSABLE_PREFLIGHT:{result.stdout[-1000:]} {result.stderr[-700:]}") from e
    assert val["schema"] == "ORBIT_UPDATER_IMAGE_LEASE_PREFLIGHT_V1"
    assert val["status"] == "BLOCKED"
    assert val["updater_ready"] is False
    assert val["installed_image_write_permitted"] is False
    assert val["update_invoked"] is False
    assert val["process_terminated"] is False
    assert val["worker_or_s4_touched"] is False
    return val


def main():
    checks = 0

    def require(condition, message):
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    # TemporaryDirectory's cleanup only owns its own paths.
    with tempfile.TemporaryDirectory(prefix="orbit-updater-lease-") as tmp:
        fixture = Path(tmp)
        exe = fixture / EXE_SOURCE.name
        shutil.copy2(EXE_SOURCE, exe)
        require(hashlib.sha256(exe.read_bytes()).hexdigest() == EXPECTED, "fixture EXE byte exact")
        launcher = fixture / "mock-ui-only.ps1"
        launcher.write_text(
            "param([string]$Mode,[string]$WorkerRoot,[string]$ProgramDataRoot,[switch]$Json)\n"
            "$ErrorActionPreference='Stop'\n"
            "if($WorkerRoot -ne $PSScriptRoot -or $ProgramDataRoot -ne $PSScriptRoot){throw 'BAD_FIXTURE_ROOT'}\n"
            "if($Mode -ne 'UI_CONTEXT'){throw 'NO_MUTATIONS_ALLOWED'}\n"
            "[Console]::Write('{}')\n", encoding="utf-8",
        )
        env = os.environ.copy()
        env.update({
            "ONEC_CONTROL_CENTER_LAUNCHER": str(launcher),
            "ONEC_CONTROL_CENTER_WORKER_ROOT": str(fixture),
            "ONEC_CONTROL_CENTER_PROGRAM_DATA": str(fixture),
            "ONEC_CONTROL_CENTER_PREFERENCES_ROOT": str(fixture / "preferences"),
        })
        owned = []
        try:
            clear = probe(exe, fixture)
            require(clear["observed_instance_count"] == 0, "no instance count")
            require("DETACHED_HANDOFF_NOT_IMPLEMENTED" in clear["reasons"], "zero instances never means READY")
            missing = probe(fixture / "OneCOrbit.exe", fixture)
            require("IMAGE_MISSING" in missing["reasons"], "absent image hard block")
            unsafe = probe(exe, fixture / "elsewhere")
            require("IMAGE_OUTSIDE_FIXTURE" in unsafe["reasons"], "image must stay in fixture")

            for i in range(2):
                proc = subprocess.Popen([str(exe)], cwd=fixture, env=env)
                owned.append(proc)
                until(lambda p=proc: p.poll() is None and windows(p.pid))
            require(all(p.poll() is None for p in owned), "both WPF instances running")
            busy = probe(exe, fixture)
            require("IMAGE_IN_USE" in busy["reasons"], "two executable users block handoff")
            require(busy["observed_instance_count"] == 2, "two exact-image PIDs")
            require(set(busy["observed_instance_pids"]) == {p.pid for p in owned}, "exact owner PID identity")

            for hwnd in windows(owned[0].pid):
                require(bool(user32.PostMessageW(hwnd, 0x10, 0, 0)), "posted fixture-only WM_CLOSE")
            until(lambda: not windows(owned[0].pid))
            require(owned[0].poll() is None, "WM_CLOSE hides to tray, not process exit")
            hidden = probe(exe, fixture)
            require(hidden["observed_instance_count"] == 2, "tray-hidden instance still observed")
            require("IMAGE_IN_USE" in hidden["reasons"], "hidden instance hard blocked")

            owned[0].terminate()  # owned fixture ONLY; never installed service or S4
            owned[0].wait(timeout=15)
            require(owned[1].poll() is None, "second fixture remains alive")
            still = probe(exe, fixture)
            require(still["observed_instance_count"] == 1, "single remaining image user")
            require("IMAGE_IN_USE" in still["reasons"], "remaining image user hard block")
            owned[1].terminate()
            owned[1].wait(timeout=15)
            after = probe(exe, fixture)
            require(after["observed_instance_count"] == 0, "both owned fixture processes exited")
            require("DETACHED_HANDOFF_NOT_IMPLEMENTED" in after["reasons"], "no ready even after exit")
            require(hashlib.sha256(exe.read_bytes()).hexdigest() == EXPECTED, "fixture EXE preserved")
            print(
                "ORBIT_UPDATE_IMAGE_LEASE_FIXTURE_PASS "
                f"checks={checks} owned_instances=2 hidden_tray_checked=true "
                "update_invoked=false production_access=false"
            )
        finally:
            for p in owned:
                if p.poll() is None:
                    p.terminate()
                    p.wait(timeout=15)


if __name__ == "__main__":
    main()
