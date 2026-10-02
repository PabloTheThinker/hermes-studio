# CI stalls at "Install" (ffmpeg): diagnosis and fix

Repo: PabloTheThinker/hermes-studio · workflow `ci` (`.github/workflows/ci.yml`), job `test`
Researched Thu Oct 1, 2026, read-only (no reruns, nothing pushed). All times ET.

**Recommendation: stop using apt for ffmpeg in CI. Install the same pinned BtbN static FFmpeg that the desktop app already ships (`desktop.yml`), check its sha256, cache it with `actions/cache`, and split pip into its own step with pip caching, timeouts and visible output.**

## 1. What CI does today

- `runs-on: ubuntu-latest`. Today that resolves to **ubuntu-24.04**, image `20260927.320.1`. The job timeout is `timeout-minutes: 15` and steps have no timeout of their own.
- There is one silent step called `Install`:
  ```
  sudo apt-get update -qq && sudo apt-get install -y -qq ffmpeg >/dev/null
  python -m pip install -q --upgrade pip
  python -m pip install -q -e ".[reframe,dev]"
  ```
- ffmpeg is **not** preinstalled on that image. It isn't in the [Ubuntu2404 readme for 20260927.320](https://github.com/actions/runner-images/blob/ubuntu24/20260927.320/images/ubuntu/Ubuntu2404-Readme.md). `curl` and `xz-utils` are preinstalled.
- What the tests need from ffmpeg: `tests/test_look.py::test_progress_bar_grows_with_time` runs `ffmpeg` with `lavfi color`, `-filter_complex` (the progress-bar chain from `look.post_chain`), an mp4 encode and a `rawvideo` gray crop. If ffmpeg isn't on PATH, that test **skips**. `tests/test_cli_contract.py::test_doctor_json_shape` runs `doctor`, which looks for `ffmpeg`, `ffprobe` and the `ass` filter (libass). The app code also uses libx264, aac, `subtitles`/`ass`, `loudnorm` and `afftdn`. I checked that the pinned BtbN build has all of these.
- Annotation on today's runs: *"The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026"* ([runner-images#14748](https://github.com/actions/runner-images/issues/14748), whose title says November). The static build doesn't depend on which Ubuntu the runner uses.

## 2. Diagnosis (today's 40 `test` job attempts, from `gh api` step timings and job logs)

**Stalls (job hit the 15-minute timeout inside `Install`; Lint and Tests were skipped):**

| Run (attempt) | Trigger | Install started → cancelled | Result |
|---|---|---|---|
| 36889334309 (1) | push to `main` (#36) | 12:05:32 → 12:20:43 PM (911 s) | **never re-run**, so that `main` commit has no green ci |
| 36890895604 (1) | PR `feat/editor-s2-oplog` | 12:17:50 → 12:33:00 PM (910 s) | attempt 2 passed but was slow: Install 284 s |
| 36906747726 (1) | PR `fix/ripple-trim-crossfade` | 2:25:50 → 2:41:00 PM (910 s) | attempt 2 passed: Install 37 s |

All three show the annotation "The job has exceeded the maximum execution time of 15m0s". The log for each has nothing between the step header and `##[error]The operation was canceled.`

**Was it apt or pip?** Very likely apt. The logs never show the step's own output, so here is how I worked it out. After `apt-get install` finishes, Ubuntu's needrestart hook prints "Running kernel seems to be up-to-date … No services need to be restarted" to stderr, which isn't sent to /dev/null. That banner shows up in **all 37** successful Install steps, at the point where apt ends and pip starts. It is **missing from all 3** stalled ones. So in each stall, `apt-get update`/`install` never finished and pip never started. I **can't** tell from the logs whether the hang was in `apt-get update`, the .deb download or dpkg, because `-qq >/dev/null` hides it. A mirror problem is the likely cause: the stalls and the slow runs bunch together between about 9:50 AM and 2:40 PM ET. That's an inference, not something I proved.

**Measured split of the Install step** (37 successful attempts; apt = step start → needrestart banner, pip = banner → step end):

| | median | typical range | worst |
|---|---|---|---|
| apt ffmpeg | **32 s** | 18–62 s | 7 attempts > 60 s: 102, 231, 252, 267, 431, **499 s** |
| pip | **18 s** | 14–22 s | one outlier: **296 s** (run 36823380324, 2:10 AM) |
| stalled apt | **≥ 910 s** (killed by the job timeout) | | |

Today apt used about 46 min of runner time on successful attempts (2,748 s total) and about 46 min on the 3 stalls (2,731 s), roughly **1.5 h in all**. pip was slow once too, so it should get its own timeout as well.

## 3. Recommendation and why

Use **BtbN FFmpeg-Builds `autobuild-2026-09-30-13-08`, `linux64-gpl-9.0` (ffmpeg n9.0.2-17-g2a571b6068)**, downloaded by a fixed URL, checked against its sha256 on every run, and cached with `actions/cache`.

- **No Ubuntu mirrors involved.** On a cache hit it makes no network call at all. On a miss it downloads one 151 MB file from GitHub Releases.
- **Pinned and checked.** It's an exact build with a sha256, and the check runs on cache hits too.
- **Already trusted here.** It's the same build, URL and sha256 as `desktop.yml` (`FFMPEG_LINUX_URL` / `FFMPEG_LINUX_SHA256`) and `NOTICE`, so CI tests against the ffmpeg users actually get.
- **Won't break with the runner.** It's a static build, so the coming Ubuntu 26 switch doesn't affect it.
- **Checked on this box.** I downloaded it today: sha256 `68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269`, which matches the desktop.yml pin. It has `ass`, `subtitles`, `drawbox`, `crop`, `loudnorm`, `afftdn`, `libx264` and `aac`. The full test suite passed with it on PATH: **613 passed, 0 skipped** on `main` @ e274051, Python 3.13. CI uses 3.12.
- **Old release stays up.** BtbN keeps month-end autobuild releases long term; the list goes back to 2024-11-30. Daily builds are only kept about 2 weeks. `2026-09-30` is a month-end tag, so the URL should keep working, and the cache covers short outages.

## 4. YAML ready to paste (`.github/workflows/ci.yml`)

The full proposed file is next to this doc as `ci.proposed.yml`. It parses, and I ran its ffmpeg script locally for a cache miss, a cache hit, a wrong sha and a wrong version. Changes:

**a) Add top-level `env`** (after `concurrency:`):
```yaml
env:
  # Same BtbN static FFmpeg the desktop app ships (desktop.yml). Keep the two in sync.
  FFMPEG_LINUX_URL: https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-30-13-08/ffmpeg-n9.0.2-17-g2a571b6068-linux64-gpl-9.0.tar.xz
  FFMPEG_LINUX_SHA256: 68ee646831adaae2495618346f3bba94ff207ff83bbd34d643e7004730d66269
  FFMPEG_VERSION: n9.0.2-17-g2a571b6068
```

**b) Replace the `setup-python` step and the `Install` step in job `test` with:**
```yaml
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - name: FFmpeg cache
        id: ffmpeg-cache
        uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: ~/.cache/ffmpeg-dl
          key: ffmpeg-linux64-${{ env.FFMPEG_LINUX_SHA256 }}
      - name: FFmpeg (pinned, sha256-verified)
        timeout-minutes: 3
        run: |
          set -euo pipefail
          f="$HOME/.cache/ffmpeg-dl/ffmpeg.tar.xz"
          mkdir -p "$(dirname "$f")" "$RUNNER_TEMP/ffmpeg"
          if [ -f "$f" ]; then
            echo "ffmpeg: using cached archive"
          else
            echo "ffmpeg: cache miss, downloading $FFMPEG_LINUX_URL"
            curl -fSL --retry 5 --retry-all-errors --connect-timeout 15 --max-time 120 \
              --speed-limit 200000 --speed-time 20 -o "$f" "$FFMPEG_LINUX_URL"
          fi
          echo "$FFMPEG_LINUX_SHA256  $f" | sha256sum -c -
          tar -xJf "$f" -C "$RUNNER_TEMP/ffmpeg" --strip-components=2 --wildcards '*/bin/ffmpeg' '*/bin/ffprobe'
          echo "$RUNNER_TEMP/ffmpeg" >> "$GITHUB_PATH"
          v="$("$RUNNER_TEMP/ffmpeg/ffmpeg" -hide_banner -version)"
          echo "${v%%$'\n'*}"
          [[ "$v" == "ffmpeg version $FFMPEG_VERSION"* ]] || { echo "::error::unexpected ffmpeg version"; exit 1; }
          grep -qE '^ \S+ ass ' <<<"$("$RUNNER_TEMP/ffmpeg/ffmpeg" -hide_banner -filters)" || { echo "::error::ffmpeg lacks libass"; exit 1; }
          echo "ffmpeg: libass ok"
      - name: Python deps
        timeout-minutes: 6
        run: |
          python -m pip install --progress-bar off --timeout 30 --retries 5 --upgrade pip
          python -m pip install --progress-bar off --timeout 30 --retries 5 -e ".[reframe,dev]"
```

**c) Change `Tests`** to `run: pytest -q -rs`. Then a skipped ffmpeg test shows up in the log instead of passing quietly.

Notes:
- Action SHAs: `actions/cache` v6.1.0 = `55cc8345…` (latest release, resolved today via the API). `setup-python` stays at the pinned v7.0.0, which supports `cache: pip` + `cache-dependency-path`.
- The sha256 is checked even on a cache hit. A bad or mismatched download fails the step, and `actions/cache` only saves after a successful job, so a bad file never gets cached.
- On a cache miss, curl gives up on a stalled transfer (under 200 KB/s for 20 s) and retries up to 5 times, and each try is capped at 120 s. The 3-minute step timeout is the hard stop. A stall now costs at most 3 min instead of 15, and the log names the step that stalled.
- pip now has its own 6-minute timeout (worst seen today: 296 s), `--timeout 30 --retries 5` per request, and normal output, so a hang shows the package it was on.

**Optional guard:** `test_ci_ffmpeg_pin.py`, next to this doc, goes in `tests/`. It fails if ci.yml's pin drifts from desktop.yml. It passes and ruff is clean against the proposed file.

## 5. Keeping it reproducible / bumping the version

- Everything is pinned: release tag, file name, sha256 and expected version string. The cache key is the sha256, so a bump creates a new cache entry automatically. Unused entries expire after 7 days. The 151 MB file uses about 1.5% of the 10 GB repo cache limit.
- To bump it, do it together with the desktop bump, since `NOTICE` and `packaging/` follow the same pin:
  1. Pick a **month-end** `autobuild-YYYY-MM-DD-HH-MM` tag on https://github.com/BtbN/FFmpeg-Builds/releases. Daily tags get deleted after about 2 weeks.
  2. `curl -fL -o ff.tar.xz <linux64-gpl URL> && sha256sum ff.tar.xz`, and get the version string from `tar -xJf ff.tar.xz && */bin/ffmpeg -version | head -1`.
  3. Update `FFMPEG_LINUX_URL`, `FFMPEG_LINUX_SHA256` and `FFMPEG_VERSION` in ci.yml, and the same pins in desktop.yml/NOTICE. The optional guard test catches it if one is missed.

## 6. Time saved (based on today's measured numbers)

- **New ffmpeg step on a cache hit:** 1.4 s on this box to check and extract (0.13 s sha256, about 1.5 s to pull 2 binaries out of the .xz). Add the cache restore of 151 MB on the runner and I estimate **about 5–10 s**. That's not measured on GitHub yet.
- **Normal run:** apt median 32 s → about 8 s, so **about 25 s saved per run**.
- **Slow-mirror runs** (7 of 37 today): **about 1.5–8 min saved each** (apt took 102–499 s).
- **Stalled run:** saves **about 15 min of timeout plus a manual re-run**. It also stops a `main` push from staying red/cancelled, like 36889334309.
- **Today in total:** about 91 min of apt time (46 min on successful attempts plus 46 min of stalls) would have been about 5 min.
- **pip cache:** probably a few seconds off the 18 s median. I didn't measure that.

## 7. How Prove can verify

1. **First run on the PR:** the `FFmpeg (pinned, sha256-verified)` log shows `ffmpeg: cache miss, downloading …`, then `…/ffmpeg.tar.xz: OK`, `ffmpeg version n9.0.2-17-g2a571b6068-20260930 …` and `ffmpeg: libass ok`. The `Post FFmpeg cache` step shows the cache saved under key `ffmpeg-linux64-68ee6468…`.
2. **Second run (re-push or another PR after merge):** `FFmpeg cache` shows the cache restored from key `ffmpeg-linux64-68ee6468…`, and the step prints `ffmpeg: using cached archive`. setup-python also reports a pip cache restore.
3. **Tests:** they pass with the same count as before (636 on the latest PR run, 36906747726 attempt 2), and the `pytest -q -rs` output has **no** `SKIPPED … ffmpeg not installed`.
4. **Timings:** `gh api repos/PabloTheThinker/hermes-studio/actions/runs/<id>/jobs --jq '.jobs[]|select(.name=="test").steps[]|[.name,.started_at,.completed_at]'` should show the ffmpeg step at about 10 s or less on a hit and `Python deps` around 20 s.
5. **No apt left:** `grep -n apt-get .github/workflows/ci.yml` returns nothing.
6. **Negative check (optional, on a scratch branch):** change one character of `FFMPEG_LINUX_SHA256`. The step should fail with `sha256sum: WARNING … did NOT match` within seconds.

## 8. Alternatives considered

- **Cache apt .debs** (awalsh128/cache-apt-pkgs-action or actions/cache on `/var/cache/apt`): still needs `apt-get update`/mirrors on a cache miss and when the key changes. Ubuntu's ffmpeg version moves with the image, so it isn't pinned, and it breaks when ubuntu-latest moves to 26.04.
- **johnvansickle static:** good builds, but the site serves only "latest". Old versions move around, so a fixed URL+sha breaks. It's also not hosted on GitHub.
- **setup-ffmpeg actions** (FedericoCarboni v3.1, last release Feb 2024; AnimMouse v1.2.5): convenient, but they choose and fetch the binary themselves. The checksum isn't in our YAML, and it's a different build from the one the app ships.
- **Keep apt but harden it (the fallback if BtbN is ever unreachable):** put it in its own step with `timeout-minutes: 4` and a retry loop:
  ```yaml
      - name: FFmpeg (apt fallback)
        timeout-minutes: 4
        run: |
          o="-o Acquire::Retries=3 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 -o Dpkg::Use-Pty=0"
          for i in 1 2 3; do
            timeout 90 sudo apt-get $o update -q && timeout 150 sudo apt-get $o install -y --no-install-recommends ffmpeg && break
            echo "apt attempt $i failed or stalled; retrying"; sleep 10
          done
          ffmpeg -hide_banner -version | head -1
  ```
  This caps a stall at about 4 min and shows where it stalled. It still depends on mirrors and isn't pinned.

## Not verified

- I didn't run the proposed workflow on GitHub (read-only task). Cache-hit timing on the runner is an estimate; the box numbers are measured.
- I couldn't tell where apt hung: `update`, download or dpkg. The output was silenced.
- The mirror-outage cause is inferred from timing clusters, not seen in any log.
- I ran the tests locally on Python 3.13 against `main`, not on 3.12 or the PR branches.
- I didn't check the `--no-install-recommends` effect on Ubuntu's ffmpeg package (fallback only).
