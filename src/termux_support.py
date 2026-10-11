"""
smolfiddle fork: Termux / Termux:X11 (LXQt) platform support.

This module is ADDITIVE ONLY — it must never change behaviour on
non-Termux systems. All helpers return neutral values (False / None / [])
when Termux is not detected, so upstream code paths run untouched.

Upstream files (utils.py, patcher.py) call into here behind tiny guards.
If this file is missing (e.g. upstream merge without the fork), callers
fall back to upstream behaviour via try/except ImportError.
"""

import logging
import os
from typing import List, Optional

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_CHROME_CANDIDATES = (
    # pkg install chromium (x11-repo) — current aarch64 layout
    "/data/data/com.termux/files/usr/lib/chromium/chrome",
    "/data/data/com.termux/files/usr/bin/chromium-browser",
    "/data/data/com.termux/files/usr/bin/chromium",
)
TERMUX_CHROMEDRIVER_CANDIDATES = (
    # chromium package ships a matched chromedriver binary
    "/data/data/com.termux/files/usr/bin/chromedriver",
    "/data/data/com.termux/files/usr/lib/chromium/chromedriver",
)


def is_termux() -> bool:
    """True when running inside Termux (phone/tablet, Android)."""
    if os.path.exists("/data/data/com.termux"):
        return True
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" in prefix:
        return True
    return False


def is_termux_x11() -> bool:
    """True when Termux:X11 display is available (LXQt session, etc.)."""
    return is_termux() and bool(os.environ.get("DISPLAY"))


def should_skip_xvfb() -> bool:
    """Xvfb binary does not exist in Termux — Termux:X11 is the X server."""
    return is_termux()


def get_chrome_path() -> Optional[str]:
    """Termux Chromium path, or None when not on Termux / not found.

    Priority: $CHROME_BIN env override, then known Termux candidates.
    """
    if not is_termux():
        return None
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and os.path.exists(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin
    for candidate in TERMUX_CHROME_CANDIDATES:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def get_chromedriver_path() -> Optional[str]:
    """Termux chromedriver path, or None when not on Termux / not found."""
    if not is_termux():
        return None
    for candidate in TERMUX_CHROMEDRIVER_CANDIDATES:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _env_true(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def get_extra_chrome_args() -> List[str]:
    """Extra Chromium flags needed on Termux/Android. Empty elsewhere.

    All opt-in/opt-out via env so upstream defaults never change:
      TERMUX_DISABLE_GPU=true (default on Termux: no /dev/dri in Android)
      TERMUX_SINGLE_PROCESS=false (opt-in: helps Android 32-process limit)
      TERMUX_JITLESS=false (opt-in: needed on unrooted Android 10+ where
        SELinux W^X blocks V8 JIT mmap(PROT_EXEC), else SIGSEGV/139)
    """
    if not is_termux():
        return []
    args = []
    if _env_true("TERMUX_DISABLE_GPU", True):
        args.append("--disable-gpu")
    # Hides navigator.webdriver at birth; Cloudflare flags Termux
    # Chromium builds otherwise (verified: hard challenges fail without).
    args.append("--disable-blink-features=AutomationControlled")
    if _env_true("TERMUX_SINGLE_PROCESS", False):
        args.append("--single-process")
    if _env_true("TERMUX_JITLESS", False):
        args.append("--js-flags=--jitless")
    return args


def stealth_enabled() -> bool:
    """CDP webdriver-trace cleanup on/off. Default on in Termux.

    Set TERMUX_STEALTH=false to A/B test challenge behavior with and
    without the cleanup. Always False off-Termux (upstream untouched).
    """
    if not is_termux():
        return False
    return _env_true("TERMUX_STEALTH", True)


def get_webgl_spoof():
    """WebGL vendor/renderer override, or None to leave the truth in place.

    Software GL (SwiftShader/Lavapipe) strings mark the browser as
    automation-friendly; the phone's real GPU (e.g. Mali-G52) is what a
    genuine mobile browser reports. Master switch TERMUX_SPOOF_WEBGL
    (default on in Termux), strings via TERMUX_WEBGL_VENDOR (default
    "ARM") and TERMUX_WEBGL_RENDERER (default "Mali-G52" — override for
    Adreno/Apple devices). Always None off-Termux.
    Returns (vendor, renderer) or None.
    """
    if not is_termux():
        return None
    if not _env_true("TERMUX_SPOOF_WEBGL", True):
        return None
    vendor = os.environ.get("TERMUX_WEBGL_VENDOR", "ARM")
    renderer = os.environ.get("TERMUX_WEBGL_RENDERER", "Mali-G52")
    return vendor, renderer


def get_forced_user_agent(chrome_major=None):
    """User-Agent override, or None for the browser default.

    Strict sites may tier desktop-Linux UAs from mobile-carrier IPs into
    hard challenges while serving mobile UAs an easy tier (the phone's
    Firefox passes where desktop-UA Chromium stalls). Two knobs:
      TERMUX_USER_AGENT=<full string> — explicit override, wins.
      TERMUX_MOBILE_UA=true — Pixel-style Android template using the
        detected Chromium major (TERMUX_ANDROID_VER, default 14).
    Always None off-Termux.
    """
    if not is_termux():
        return None
    explicit = os.environ.get("TERMUX_USER_AGENT", "").strip()
    if explicit:
        return explicit
    if _env_true("TERMUX_MOBILE_UA", False):
        major = chrome_major or "154"
        android_ver = os.environ.get("TERMUX_ANDROID_VER", "14")
        return (
            "Mozilla/5.0 (Linux; Android %s; Pixel 8) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/%s.0.0.0 Mobile Safari/537.36"
        ) % (android_ver, major)
    return None


def log_display_mode(headless: bool):
    """One-line log so Termux:X11 vs headless vs Xvfb is always obvious."""
    if not is_termux():
        return
    display = os.environ.get("DISPLAY")
    if headless:
        logging.info("Termux detected: using native headless (Xvfb skipped)")
    elif display:
        logging.info(f"Termux detected: using Termux:X11 display {display} (LXQt)")
    else:
        logging.warning("Termux detected with HEADLESS=false but no $DISPLAY — "
                        "start Termux:X11 or set HEADLESS=true")
