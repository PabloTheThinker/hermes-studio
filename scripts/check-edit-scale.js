// Edit page at scale (manual check, not run in CI): node scripts/check-edit-scale.js [clips=400]
// Builds a project with N clips made by N one-split history entries (no media files: the page
// shows clips without proxies), starts `hermes-studio studio` on a throwaway HOME, and times in
// Chromium: opening the project (timeline drawn) and one split from the keyboard (the next entry
// drawn). Prints JSON; fails on page errors or when either takes over 3 s.
let chromium;
try { ({ chromium } = require("playwright")); } catch { ({ chromium } = require(require("child_process").execSync("npm root -g").toString().trim() + "/playwright")); }
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const REPO = path.resolve(__dirname, ".."), N = +(process.argv[2] || 400);
const HOME = fs.mkdtempSync(path.join(os.tmpdir(), "hs-scale-")), TOKEN = "5ca1e".repeat(12) + "abcd", PORT = 8772;
const build = `
import os
from hermes_studio import oplog as O, project as P, timeline as T
S = T.TICK_RATE
d = T.new_timeline("big")
d["media"] = {"m1": {"path": os.path.expanduser("~/talk.mp4"), "dur": (${N} + 1) * 2 * S, "fps": [30, 1]}}
next(t for t in d["tracks"] if t["id"] == "V1")["items"] = [{"id": "c0", "type": "clip", "media": "m1", "src": [0, (${N} + 1) * 2 * S], "at": 0, "fade_in": 0, "fade_out": 0}]
pd = P.create_project(d)
log = O.Oplog.load(d, pd / "oplog.jsonl")
ses = O.Session(O.Actor("human", "user"))
last = "c0"
for i in range(${N}):
    r = log.call(ses, "timeline_apply", {"base_version": log.version, "client_op_id": f"s{i}", "summary": f"Split {i}",
        "ops": [{"op": "split_clip", "id": last, "at": (i + 1) * 2 * S}]})
    last = next(it["id"] for it in log.doc["tracks"][[t["id"] for t in log.doc["tracks"]].index("V1")]["items"] if it["src"][0] == (i + 1) * 2 * S)
print(log.version)
`;
const env = { ...process.env, HOME, HERMES_STUDIO_UI_TOKEN: TOKEN };
const t0 = Date.now();
const ver = execFileSync(path.join(REPO, ".venv/bin/python"), ["-c", build], { env, cwd: REPO, stdio: ["ignore", "pipe", "inherit"] }).toString().trim();
const buildMs = Date.now() - t0;
const srv = spawn(path.join(REPO, ".venv/bin/hermes-studio"), ["studio", "--port", String(PORT)], { env, stdio: ["ignore", "pipe", "pipe"] });
let log = ""; srv.stdout.on("data", (b) => (log += b)); srv.stderr.on("data", (b) => (log += b));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  for (let i = 0; i < 60 && !log.includes("Hermes Studio"); i++) await sleep(250);
  const browser = await chromium.launch(), page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; page.on("pageerror", (e) => errs.push(e.message));
  await page.addInitScript((t) => { window.studio = { uiToken: async () => t }; }, TOKEN);
  let a = Date.now();
  await page.goto(`http://127.0.0.1:${PORT}/#/edit/big`);
  await page.waitForFunction((n) => document.querySelectorAll(".it.clip").length === n + 1, N, { timeout: 120000 });
  const openMs = Date.now() - a;
  await page.click("#ed-ruler", { position: { x: 40 + 61 * 60, y: 10 } }).catch(() => {}); // inside a clip
  await page.evaluate(() => { document.getElementById("ed-scroll").scrollLeft = 0; });
  await page.click("#ed-ruler", { position: { x: 40 + 3 * 60, y: 10 } }); // 3 s: inside the second clip
  a = Date.now(); await page.keyboard.press("s");
  await page.waitForFunction((n) => document.querySelectorAll(".it.clip").length === n + 2, N, { timeout: 120000 });
  const splitMs = Date.now() - a;
  const out = { clips: N + 1, entries: +ver, build_ms: buildMs, open_ms: openMs, split_ms: splitMs, errors: errs };
  console.log(JSON.stringify(out));
  if (errs.length || openMs > 3000 || splitMs > 3000) process.exitCode = 1;
  await browser.close(); srv.kill();
})().catch((e) => { console.error("FAIL", e.message.split("\n")[0], log.slice(-800)); srv.kill(); process.exit(1); });
