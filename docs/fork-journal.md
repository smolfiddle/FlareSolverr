# Smolfiddle Fork Journal: FlareSolverr on Termux

Complete record of this fork, from research to device-verified release.
If you only want to *use* it, read `termux/README-termux.md` instead.
This file explains *why everything is the way it is*.

- Upstream: `FlareSolverr/FlareSolverr` (base: v3.5.2, commit `76dc404`)
- Fork: `smolfiddle/FlareSolverr` (release: `v3.5.2+smol1`)
- Period covered: 2026-10-11 (single intensive day, desktop plus phone)
- Goal chosen early and kept: **publish for others, headless default,
  Python 3.9 compatible, thin tracking fork**

---

## 1. Research: what FlareSolverr is

FlareSolverr is a proxy server that bypasses Cloudflare and DDoS-GUARD
protection. It idles on port 8191; on each request it launches a real
Chromium via Selenium plus undetected-chromedriver, lets the Cloudflare
JavaScript challenge solve naturally in the browser, then returns the
rendered HTML and clearance cookies as JSON. Clients send
`POST /v1 {"cmd": "request.get", "url": ...}` and reuse the cookies with
plain HTTP clients afterwards.

Three layers:

| Layer | Files | Role |
|---|---|---|
| Web API | `src/flaresolverr.py`, `src/dtos.py` | Bottle plus waitress, `/`, `/health`, `/v1` routes, request/response DTOs |
| Challenge resolution | `src/flaresolverr_service.py`, `src/sessions.py` | Command dispatch, `_evil_logic` challenge loop, persistent `SessionsStorage` |
| Browser automation | `src/utils.py`, vendored `src/undetected_chromedriver/` | WebDriver factory, Chrome discovery, driver patching |

Key design fact that drives all Termux work: upstream never uses
`--headless`. With `HEADLESS=true` it runs head-full Chromium hidden
under **Xvfb** (`start_xvfb_display()`). Termux has no Xvfb in the base
system, so stock FlareSolverr cannot start there. Commands:
`sessions.create/list/destroy`, `request.get/post` with `maxTimeout`,
`session`, `proxy`, `cookies`, `waitInSeconds`, `returnOnlyCookies`,
`returnScreenshot`, `disableMedia`, `tabs_till_verify`.

---

## 2. Starting point: the raw hacks found in the workspace

The workspace contained uncommitted modifications to two files
(plus a `src/utils.py.bak` backup). The exact diff, preserved at the
time at `/tmp/opencode/termux_hacks_reference.diff`:

1. `src/undetected_chromedriver/patcher.py`: added `"android"` to the
   `IS_POSIX` tuple (some Termux Python builds report
   `sys.platform == "android"`).
2. `src/utils.py` `get_webdriver()`: skip `start_xvfb_display()` when
   `/data/data/com.termux` exists; prefer the Termux chromedriver at
   `/data/data/com.termux/files/usr/bin/chromedriver`.
3. `src/utils.py` `get_chrome_exe_path()`: check `$CHROME_BIN`, then the
   Termux Chromium at `.../usr/lib/chromium/chrome`.

Assessment: functionally correct for headless Termux, but hardcoded,
undocumented, untested, and blind to Termux:X11 headed mode. Decision:
reimplement as a clean abstraction rather than committing the hacks.

---

## 3. Fork setup

- Created `smolfiddle/FlareSolverr` as a GitHub fork (parent:
  `FlareSolverr/FlareSolverr`).
- Local remotes: `origin` points at the fork, `upstream` at the
  original. Standard convention, so `git fetch upstream` plus merge
  keeps the fork current.
- Strategy: **thin tracking fork**. `master` mirrors upstream plus
  small additive commits; all Termux code isolated in new files with
  guarded call sites, so upstream merges stay conflict-free.
- Safety net used throughout: `backup/pre-update-2026-10-11` tag on
  the pre-sync state; revert is one `git reset --hard`.

---

## 4. Implementation: the platform abstraction layer

### 4.1 New file: `src/termux_support.py`

Single home for all Termux knowledge. Contract: **every helper is
neutral off-Termux** (`False` / `None` / `[]`), so upstream paths run
byte-identical elsewhere.

| Helper | Purpose |
|---|---|
| `is_termux()` | Detects `/data/data/com.termux` or `$PREFIX` containing `com.termux` |
| `is_termux_x11()` | Termux plus `$DISPLAY` set (LXQt session present) |
| `should_skip_xvfb()` | True on Termux (no Xvfb binary; Termux:X11 is the X server) |
| `get_chrome_path()` | `$CHROME_BIN` override, then known Termux Chromium candidates |
| `get_chromedriver_path()` | Version-matched Termux chromedriver (no download needed) |
| `get_extra_chrome_args()` | `--disable-gpu` default-on; `--single-process` and `--js-flags=--jitless` opt-in via env |
| `log_display_mode(headless)` | One log line making headless vs X11 mode always visible |

Environment variables (also documented in `termux/README-termux.md`):

| Variable | Default | Effect |
|---|---|---|
| `HEADLESS` | `true` | Native `--headless=new`, no X needed; `false` needs `$DISPLAY` |
| `DISPLAY` | unset | Set by Termux:X11 (e.g. `:0`) |
| `CHROME_BIN` | auto | Chromium path override |
| `TERMUX_DISABLE_GPU` | `true` on Termux | `--disable-gpu` (Android has no `/dev/dri`) |
| `TERMUX_SINGLE_PROCESS` | `false` | `--single-process`; **required** for headed mode (see 8.4) |
| `TERMUX_JITLESS` | `false` | `--js-flags=--jitless`; for unrooted Android 10+ SELinux W^X kills |

### 4.2 Minimal guarded edits

`src/utils.py` (import wrapped in `try/except ImportError`, so a
checkout without the fork file still works):

- Extra Chromium args delegated to `get_extra_chrome_args()` (no-op
  off-Termux).
- Headless block: skip Xvfb on Termux with an explanatory log line;
  headed mode on Termux logs the X11 display mode.
- Driver path: Termux chromedriver first, then `/app/chromedriver`
  (Docker), then download logic, unchanged.
- Chrome discovery: Termux lookup first (returns `None`
  off-Termux), then the original order untouched.

`src/undetected_chromedriver/patcher.py`:

- `"android"` added to `IS_POSIX` (commented).
- `_set_platform_name()` maps `android` to `linux64` builds.

Total fork diff vs upstream: **11 files, +605 / -3**
(see inventory in section 10).

### 4.3 Python 3.9 compatibility

Upstream supports Python 3.9 (`flaresolverr.py` enforces the floor).
The first draft of `termux_support.py` used `str | None` annotations
(3.10+ syntax); this was converted to `typing.Optional`/`typing.List`
and every touched file is parse-checked with
`ast.parse(feature_version=(3, 9))` in CI.

---

## 5. Verification

### 5.1 Offline regression suite: `src/test_fork_regression.py`

14 tests, no browser, no network (full `tests.py` needs real Chrome
plus internet, so it stays device/CI-only):

- Termux neutrality off-device plus simulated on-device behavior
  (detection, X11, flag matrix).
- DTO round-trip.
- `controller_v1_endpoint` validation paths (bad cmd, missing cmd,
  missing url, missing postData).
- `SessionsStorage` lifecycle with a stub driver.
- Proxy extension creation.
- Patcher `linux`/`android` mapping plus `IS_POSIX` assertions.
- Guarded-import fallback when `termux_support` is absent.

Result: **14 passed** locally and in CI on Python 3.11 and 3.12.

### 5.2 Linux regression (desktop container)

- `py_compile` clean; all modules import; Termux helpers neutral
  (`is_termux=False`, paths `None`, args `[]`).
- Chrome discovery works (`/bin/google-chrome`, major 139);
  plain `--headless=new --dump-dom` works.
- Full `uc.Chrome()` launch could not run in that container (no Xvfb
  binary; Python `urlopen` to the driver CDN hangs while `curl` to the
  same host succeeds). Both limitations hit upstream identically and
  are environmental, not fork regressions.

### 5.3 Windows analysis (no Windows host available)

Each changed line traced against `os.name == 'nt'` /
`sys.platform == 'win32'`: the `nt` headless branch still wins first,
all Termux helpers return neutral values, `IS_POSIX` stays `False` on
`win32`, the `android` patcher branch is unreachable. No Windows
behavior change. Caveat recorded at the time: the 3.9 annotation fix
(4.3) exists precisely to protect Windows users on older Pythons.

### 5.4 CI journey: red to green

The first CI run failed for an upstream reason, not a fork reason:
upstream pins `websockets==17.0.1`, which requires Python >= 3.11, so
the 3.9/3.10 matrix legs died at `pip install`. Fixed in PR #2:

- Matrix narrowed to 3.11/3.12 with `fail-fast: false`; the 3.9 floor
  is still enforced by the static parse step on every leg.
- `release.yml`, `release-docker.yml`, `autotag.yml` (which need
  `GH_PAT`/Docker secrets that only exist upstream) got
  `github.repository == 'FlareSolverr/FlareSolverr'` guards. These are
  no-ops upstream and keep the fork green on tags and pushes.
- Result: py3.11 plus py3.12 pass, Docker job correctly skipped.

---

## 6. Decisions: upstream PR and Termux recipe

### 6.1 No upstream PR (deliberate)

Checked before deciding: zero Termux issues or PRs exist on
`FlareSolverr/FlareSolverr`; the README scopes source installs to x64
with ARM as Docker-only. A Termux PR would land as out-of-scope
maintenance burden. Verdict: skip; the most that was ever considered
was the one-line `IS_POSIX` gesture, rejected as paper trail without
outcome.

### 6.2 Termux-packages recipe: recon, then restraint

- The official recipe `x11-packages/flaresolverr/` exists (added
  2026-07-18 at 3.5.0, bumped to 3.5.2 on 2026-10-01, `AUTO_UPDATE`).
  It carries its own `0001-android-support.patch` (same `IS_POSIX`
  fix plus freebsd-style system-chromedriver handling) and depends on
  `chromium, xorg-server-xvfb, python-xvfbwrapper`.
- Xvfb-on-Termux was verified viable through independent projects, so
  the recipe's approach is sound; there was no outdated-recipe gap to
  fill and no version bump to offer.
- Decision: no speculative recipe PR. Contribute there only with a
  demonstrated defect. (One materialized: see section 7.)

---

## 7. The missing-binary investigation

Chain of evidence, all verified from a Linux box:

1. `pkg install flaresolverr` on-device: `E: Unable to locate package`
   with `x11-repo` enabled and indexes fetched.
2. Live `termux-x11` aarch64 `Packages` index: **0 entries** for
   flaresolverr (`chromium: 1` as control). Pool dir
   `apt/termux-x11/pool/main/f/flaresolverr/` empty.
3. Recipe integrity confirmed: tarball SHA256 matches the recipe hash
   exactly, the Android patch applies clean, `build.sh` syntax valid.
4. The Oct 1 bump commit (`2071c15`) shows `build (aarch64) success`
   plus `upload success`. So: built fine, never published. A publish
   gap, not a code bug. Today's automated health check (#32468) flags
   the same line.
5. Filed as `smolfiddle`: **termux/termux-packages#32477**
   ("builds green but missing from apt repository"). Maintainer
   **TomJo2000** responded within the hour with revbump PR **#32478**
   (`TERMUX_PKG_REVISION=1`, one line, forces rebuild plus re-upload),
   linked as closing the issue. At time of writing the PR is open and
   the binary not yet published.

---

## 8. Device testing (phone: Android 14, aarch64, Termux from GitHub)

### 8.1 Block 1: system prep and install

- `pkg upgrade -y`: 284 packages, ~1 GB. One unrelated failure:
  `libsynctex` vs `texlive-bin` dpkg file conflict, resolved with
  `apt install -y -o Dpkg::Options::="--force-overwrite" libsynctex`
  followed by a clean second upgrade pass.
- `bash termux/install-termux.sh`: clean end to end. Detected
  Chromium `154.0.8037.97` at `.../lib/chromium/chrome` and matching
  chromedriver `154.0.8037.97` (majors equal, no skew). Python 3.14.6.
- Cosmetic note: the browser binary is `chromium-browser`, not
  `chromium`; detection already covers that name.

### 8.2 Block 2: headless (all green)

- Startup: `Termux detected: using native headless (Xvfb skipped)`,
  Chrome 154 found, `Test successful!`, serving on 8191.
- Google probe: `"status": "ok"`, `"Challenge not detected!"`, full
  HTML, **~7.2 s**.
- Sessions round-trip: create, reuse for a solve, destroy, all `"ok"`.

### 8.3 Block 3: headed LXQt (green after two environmental bugs)

- **Bug A, dead X server.** First headed launches failed with
  `session not created: cannot connect to chrome`; manual Chromium
  launch revealed `Missing X server or $DISPLAY`. Cause: an earlier
  `pkill` plus Android background kills had left no `termux-x11`
  process and no `X0` socket. Fix: restart server, verify the socket,
  keep the Termux:X11 app open with Unrestricted battery. Lesson added
  to the README restart checklist.
- **Bug B, SIGKILL.** With a healthy server, headed startup died with
  `[Process completed (signal 9)]`: Android's process limits killing
  multi-process Chromium on top of a full LXQt session (device has
  7.5 GB RAM, so this is the phantom-process cap, not memory). Fix:
  `TERMUX_SINGLE_PROCESS=1`, after which startup passed in ~7 s and
  no further kills occurred. Now the documented headed default.
- Headed probe: `"ok" / "Challenge not detected!"` in **~8.1 s**,
  Chromium window visible in the Termux:X11 app.
- LXQt startup notes folded into docs along the way: `dbus-launch`
  is required (bare `lxqt-session` exits instantly); xkbcomp,
  LockScreenManager, DPMS, GrabKey and notification-daemon warnings
  are all benign noise.

### 8.4 Reference numbers

Headless ~7.2 s vs headed ~8.1 s on the same device and target.
Headless remains the recommended default; headed is the quality
option. A post-Ctrl+C `ps` zombie check is the one device item still
unrecorded.

---

## 9. Decision log

| Decision | Outcome | Rationale |
|---|---|---|
| Reimplement hacks as abstraction | Done | Hardcoded paths untestable; guards keep upstream intact |
| Fork destination `smolfiddle/FlareSolverr` | Done | Same name, easy upstream sync |
| Publish for others (not personal-only) | Kept | Drives docs, installer, CI investment |
| Headless default, headed LXQt optional | Device-verified | 7.2 s vs 8.1 s; headed needs single-process |
| Keep Python 3.9 compat | Done | Upstream floor; protects Windows users |
| No upstream PR | Deliberate | No demand signal; wrong layer (see 6.1) |
| No speculative recipe PR | Deliberate | Recipe current and sound (see 6.2) |
| Fork leads, pkg heals | Standing strategy | Fork is the working route today; adopt pkg users if/when the binary lands |

---

## 10. Final state inventory

Fork `master` vs `upstream/master` (base `76dc404`): **11 files,
+605 / -3.**

| Change | Type |
|---|---|
| `src/termux_support.py` (new) | Platform abstraction layer |
| `src/utils.py` | Guarded Termux delegation |
| `src/undetected_chromedriver/patcher.py` | `android` POSIX plus `linux64` mapping |
| `src/test_fork_regression.py` (new) | 14 offline tests |
| `termux/requirements-termux.txt` (new) | Deps without `xvfbwrapper` |
| `termux/install-termux.sh` (new) | Idempotent installer with sanity checks |
| `termux/README-termux.md` (new) | User guide, checklist, troubleshooting, results |
| `.github/workflows/fork-regression.yml` (new) | py3.11/3.12 offline CI |
| `release.yml`, `release-docker.yml`, `autotag.yml` | Upstream-only guards (no-op upstream) |
| `docs/fork-journal.md` (this file) | Project record |

History: PR #1 (Termux support) plus PR #2 (CI green), tag
`v3.5.2+smol1`, backup tag `backup/pre-update-2026-10-11`.
Upstream sync flow: fetch, trial-merge on scratch branch, run the
14-test suite, promote on green, revert to backup tag on red.

---

## 11. Open items

1. **Official package watch.** Trigger: `pkg install flaresolverr`
   succeeds or the x11 index gains an entry. Then re-test the probe
   against it and flip `termux/README-termux.md` to recommend `pkg`
   first, fork second. Tracked via termux-packages#32477 / #32478.
2. **Zombie check.** One post-Ctrl+C `ps aux | grep -i chrom` run on
   device, still unrecorded.
3. **Upstream sync.** Run `git fetch upstream` periodically; the
   backup-tag flow from section 3 covers breakage.
4. **Heavier headed loads.** Sustained headed sessions saw one late
   signal 9; if it recurs under load, the next knob is a bare window
   manager instead of full LXQt.
