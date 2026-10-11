# FlareSolverr on Termux (smolfiddle fork)

Runs FlareSolverr natively in Termux on Android, headless out of the box,
optionally headed under LXQt via Termux:X11 for better bypass quality.

Upstream behavior on Docker / desktop / Windows is unchanged — all Termux
logic lives in `src/termux_support.py` and is neutral outside Termux.

Full project record (research, decisions, testing, device results):
`docs/fork-journal.md`.

## Prerequisites

- Termux from GitHub (not Play Store — the Play Store build is outdated).
- ~500 MB free storage. An `aarch64` device is assumed
  (`pkg install chromium` ships `arm`/`x86_64` builds too, same paths).

## Install

Two routes. The official package is easiest; the fork route gives you
native headless (no Xvfb), headed LXQt mode, and the latest fork docs.

### Route A (recommended): official Termux package

```sh
pkg update -y
pkg install -y x11-repo
pkg install -y flaresolverr
flaresolverr &
```

Device-verified 2026-10-11: installs `flaresolverr 3.5.2-1`, starts via
the Xvfb path, solves Google with `"ok"`. Note it installs Python deps
unpinned through pip, which may upgrade shared packages (observed:
selenium 4.47.0 to 4.51.0). If `pkg install` says unable to locate,
your mirror hasn't synced: switch to `packages.termux.dev` via
`termux-change-repo`, or wait a day.

### Route B: this fork (hacker route)

```sh
# 1. Base packages (x11-repo provides chromium)
pkg update -y
pkg install -y x11-repo tur-repo
pkg install -y chromium python

# ...or run the scripted version:
bash termux/install-termux.sh
```

```sh
# 2. Python dependencies (no xvfbwrapper: the fork uses Chromium native
#    headless instead of Xvfb)
pip install -r termux/requirements-termux.txt
```

```sh
# 3. Start (headless default — no X server needed)
HEADLESS=true python src/flaresolverr.py
```

Verify:

```sh
curl -L -X POST 'http://localhost:8191/v1' \
  -H 'Content-Type: application/json' \
  --data-raw '{"cmd":"request.get","url":"https://www.google.com/","maxTimeout":60000}'
```

## Headed mode under LXQt (Termux:X11, better bypass quality)

1. Install the Termux:X11 APK (companion app, same signing source as
   your Termux app) and grant it unrestricted battery usage so Android
   doesn't kill the display server.
2. In Termux (one time per boot; `dbus-launch` is required or the
   session exits immediately):
   ```sh
   pkg install -y termux-x11-nightly lxqt
   pkill -f 'termux-x11' 2>/dev/null; sleep 1  # clear stale servers
   termux-x11 :0 &
   DISPLAY=:0 dbus-launch --exit-with-session lxqt-session &
   ```
   Open the Termux:X11 app to see the desktop. If `termux-x11` says
   "server already running", a server from an earlier start is still
   serving `:0`, which is fine, just use it.
3. Start FlareSolverr headed (`TERMUX_SINGLE_PROCESS=1` is recommended:
   it keeps Chromium to one process, which avoids Android's phantom
   process killer terminating the session; verified on-device):
   ```sh
   TERMUX_SINGLE_PROCESS=1 DISPLAY=:0 HEADLESS=false python src/flaresolverr.py
   ```
   The fork logs `using Termux:X11 display :0 (LXQt)`. If you see
   `HEADLESS=false but no $DISPLAY`, the X server isn't running.

## After a reboot / Termux restart (checklist)

Everything below dies on reboot, so run it fresh each time. Headless
mode needs only step 4.

   ```sh
   # 1. Optional: keep the CPU awake for long solves
   termux-wake-lock
   # 2. Fresh X server (skip for headless mode)
   pkill -f 'termux-x11' 2>/dev/null; pkill -f lxqt-session 2>/dev/null; sleep 1
   termux-x11 :0 &
   sleep 2
   ls $PREFIX/tmp/.X11-unix/   # expect: X0. If missing, the server died:
                               # open the Termux:X11 app, confirm its battery
                               # setting is Unrestricted, and retry.
   # 3. LXQt session (skip for headless mode)
   DISPLAY=:0 dbus-launch --exit-with-session lxqt-session &
   # 4. Latest fork code, then start (headless shown; headed: add DISPLAY=:0
   #    and set HEADLESS=false)
   cd ~/smol && git pull --ff-only
   HEADLESS=true python src/flaresolverr.py
   ```

   If headed startup fails with `cannot connect to chrome`, re-check step 2
   first: a dead X server is the most common cause (Chrome reports
   `Missing X server or $DISPLAY`). Kill stale browsers with
   `pkill -9 -f chrome; pkill -9 -f chromedriver` before retrying.

## If the Termux session dies with signal 9

`[Process completed (signal 9)]` means Android killed the session, not a
FlareSolverr bug. LXQt plus Chromium plus FlareSolverr is heavy for a
phone. Mitigations, in order:

   ```sh
   # 1. Both apps need Unrestricted battery (Settings -> Apps ->
   #    Termux and Termux:X11 -> Battery -> Unrestricted).
   # 2. Fewer processes: collapse Chromium into one process
   TERMUX_SINGLE_PROCESS=1 DISPLAY=:0 HEADLESS=false python src/flaresolverr.py
   # 3. Close heavy apps (browser, camera, games) before a headed run.
   # 4. Fall back to headless, which uses far less RAM:
   HEADLESS=true python src/flaresolverr.py
   ```

   Check free memory with `free -h`. Devices with 4 GB or less should
   prefer headless mode.

## Device-verified results (2026-10-11, Android 14 aarch64, Chromium 154)

- Headless (`HEADLESS=true`): install script clean, startup test passes,
  Google solve `"ok" / "Challenge not detected!"` in ~7.2 s. Sessions
  create, reuse, destroy all pass.
- Headed LXQt (`TERMUX_SINGLE_PROCESS=1 DISPLAY=:0 HEADLESS=false`):
  startup passes, Chromium window visible in Termux:X11, Google solve in
  ~8.1 s. Slightly slower than headless (real X rendering).
- Multi-process headed Chromium gets SIGKilled by Android (phantom
  process limit); single-process is required, not optional.
- Headless is the recommended default; headed is the quality option
  where bypass behavior matters.

## Environment reference

| Variable | Default | Effect |
| --- | --- | --- |
| `HEADLESS` | `true` | `true`: native `--headless=new`, no X needed. `false`: needs `$DISPLAY` (Termux:X11). |
| `DISPLAY` | unset | Set by Termux:X11 (e.g. `:0`). Required for headed mode. |
| `CHROME_BIN` | auto | Override Chromium path. Auto-detects `…/lib/chromium/chrome`, `chromium-browser`, `chromium`. |
| `TERMUX_DISABLE_GPU` | `true` on Termux | Adds `--disable-gpu` (Android has no `/dev/dri`). Set `false` to opt out. |
| `TERMUX_SINGLE_PROCESS` | `false` | Opt-in `--single-process`. Helps on devices with Android's 32-process limit. |
| `TERMUX_JITLESS` | `false` | Opt-in `--js-flags=--jitless`. Needed on unrooted Android 10+ where SELinux W^X blocks V8 JIT (`SIGSEGV`/exit 139). Slower JS, but stable. |
| `PORT` / `HOST` / `LOG_LEVEL` | `8191` / `0.0.0.0` / `info` | Same as upstream. |

## Notes

- The `chromium` package ships a version-matched `chromedriver`; the fork
  uses it directly, so no driver download happens on Termux. After
  `pkg upgrade chromium`, restart FlareSolverr so the new major version
  is picked up.
- Keep the device awake for long sessions (`termux-wake-lock`, from the
  `termux-api` package). Long solves on battery-saver mode time out.
- Do not expose port 8191 to the internet — same warning as upstream.
