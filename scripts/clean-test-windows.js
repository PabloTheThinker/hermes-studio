// Clean-machine test for the Windows installer (runs on a GitHub windows-latest VM).
// 1. Silent-install Hermes-Studio-Setup-*.exe exactly as a user would (per-user).
// 2. Launch the installed app; it must start its OWN engine.
// 3. Run a captions job and a clip job through that engine.
// 4. Screenshot every screen of the real window.
// 5. Quit; the engine must be gone.
// Usage: node scripts/clean-test-windows.js <setup.exe> <sample.mp4> <outDir>
const { execFileSync, execSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { _electron: electron } = require("playwright-core");

const [setup, sampleSrc, outDir] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
// The engine only accepts files in the home folder, a mounted drive or the library.
const sample = path.join(os.homedir(), "sample-test.mp4");
fs.copyFileSync(sampleSrc, sample);
const log = (...a) => console.log(...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function onPath(tool) {
  try {
    execSync(`where ${tool}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

(async () => {
  log("== machine ==", os.release(), os.arch());
  // The runner image ships its own python/ffmpeg; hide them so the app can only use what it carries.
  const cleanPath = [path.join(process.env.SystemRoot, "System32"), process.env.SystemRoot, path.join(process.env.SystemRoot, "System32", "WindowsPowerShell", "v1.0")].join(";");
  process.env.PATH = cleanPath;
  for (const t of ["python", "ffmpeg", "yt-dlp", "hermesclip"]) log(`  ${t}: ${onPath(t) ? "PRESENT (not clean!)" : "absent"}`);

  log("== install ==");
  execFileSync(setup, ["/S"], { stdio: "inherit" });
  const exe = path.join(process.env.LOCALAPPDATA, "Programs", "Hermes Studio", "Hermes Studio.exe");
  if (!fs.existsSync(exe)) throw new Error("not installed at " + exe);
  const engine = path.join(path.dirname(exe), "resources", "engine", "python", "python.exe");
  log("installed:", exe, "| engine inside:", fs.existsSync(engine));
  const lnk = path.join(os.homedir(), "Desktop", "Hermes Studio.lnk");
  const pub = path.join(process.env.PUBLIC || "C:\\Users\\Public", "Desktop", "Hermes Studio.lnk");
  log("desktop shortcut:", fs.existsSync(lnk) || fs.existsSync(pub));

  log("== launch ==");
  const t0 = Date.now();
  const app = await electron.launch({ executablePath: exe, env: { ...process.env, PATH: cleanPath } });
  const win = await app.firstWindow();
  await win.setViewportSize({ width: 1280, height: 820 });
  await sleep(600);
  await win.screenshot({ path: path.join(outDir, "w00-starting.png") });
  for (let i = 0; i < 120 && !/^http:\/\/127\.0\.0\.1:\d+\//.test(win.url()); i++) await sleep(1000);
  const url = win.url();
  log("desk:", url, `(${Math.round((Date.now() - t0) / 1000)}s to ready)`);
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(url)) {
    await win.screenshot({ path: path.join(outDir, "w00-failed.png") });
    const body = await win.evaluate(() => document.body.innerText);
    throw new Error("engine never came up:\n" + body);
  }
  await sleep(2000);

  const api = (p, body) =>
    win.evaluate(
      async ([p, body]) => {
        const r = await fetch(p, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
        return r.json();
      },
      [p, body],
    );
  async function runJob(body, label) {
    const r = await api("/api/jobs", body);
    if (!r.ok) throw new Error(label + " rejected: " + r.error);
    const id = r.job.id;
    for (let i = 0; i < 300; i++) {
      const j = ((await api("/api/jobs")).jobs || []).find((x) => x.id === id);
      if (j && (j.status === "completed" || j.status === "failed")) {
        log(`${label}: ${j.status}${j.error ? " — " + j.error : ""} | clips: ${(j.clips || []).length}`);
        if (j.status !== "completed") throw new Error(label + " failed: " + j.error);
        return j;
      }
      await sleep(2000);
    }
    throw new Error(label + " timed out");
  }

  log("== jobs ==");
  await runJob({ src: sample, mode: "captions", whisper: "tiny", aspect: "9:16" }, "captions job");
  const clip = await runJob({ src: sample, mode: "clip", whisper: "tiny", aspect: "9:16", max_clips: 2, min_sec: 12, max_sec: 25 }, "clip job");

  log("== screens ==");
  const views = ["clips", "library", "jobs", "tools", "tools/captions", "settings"];
  let n = 1;
  for (const v of views) {
    await win.evaluate((x) => { location.hash = "#/" + x; }, v);
    await sleep(1800);
    await win.screenshot({ path: path.join(outDir, `w0${n++}-${v.replace("/", "-")}.png`) });
  }
  await win.evaluate((id) => { location.hash = "#/clips/" + id; }, clip.id);
  await sleep(3000);
  await win.screenshot({ path: path.join(outDir, "w07-clip-results.png") });
  log("screens saved:", fs.readdirSync(outDir).join(", "));

  log("== quit ==");
  await app.close();
  await sleep(4000);
  let left = "";
  try {
    left = execSync(`wmic process where "ExecutablePath like '%Hermes Studio%python.exe'" get ProcessId 2>nul`).toString().replace(/ProcessId|\s/g, "");
  } catch {}
  log(left ? "ENGINE STILL RUNNING AFTER QUIT: " + left : "engine stopped on quit");
  if (left) process.exit(1);
  log("WINDOWS CLEAN TEST PASSED");
})().catch((e) => {
  console.error("FAIL:", e.message);
  process.exit(1);
});
