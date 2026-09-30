// Hermes Studio desktop app.
// The app ships its own engine (portable Python + hermes-studio + FFmpeg) under
// resources/engine. On open it starts that engine on a free loopback port,
// waits for it, and loads the desk. On quit it stops the engine.
// Dev fallback: HERMES_STUDIO_URL, or build/engine in the repo.
const { app, BrowserWindow, Menu, shell, ipcMain } = require("electron");
const http = require("http");
const net = require("net");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let win = null;
let engine = null;
let engineLog = [];
let deskUrl = process.env.HERMES_STUDIO_URL || null;

function engineDir() {
  const packed = path.join(process.resourcesPath || "", "engine");
  if (app.isPackaged && fs.existsSync(packed)) return packed;
  const dev = path.join(__dirname, "..", "build", "engine");
  return fs.existsSync(dev) ? dev : null;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function up(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(!!res.statusCode && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitFor(url, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await up(url)) return true;
    if (engine && engine.exitCode !== null) return false;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

async function startEngine() {
  const dir = engineDir();
  if (!dir) return { ok: false, error: "This copy of Hermes Studio has no engine inside it." };
  const port = await freePort();
  const win32 = process.platform === "win32";
  const py = win32 ? path.join(dir, "python", "python.exe") : path.join(dir, "python", "bin", "python3");
  const pyBin = win32 ? path.join(dir, "python") : path.join(dir, "python", "bin");
  const env = {
    ...process.env,
    PATH: [path.join(dir, "bin"), pyBin, process.env.PATH || ""].join(path.delimiter),
    PYTHONNOUSERSITE: "1",
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONUTF8: "1",
  };
  delete env.PYTHONPATH;
  delete env.PYTHONHOME;
  engineLog = [];
  engine = spawn(
    py,
    ["-c", "import sys; from hermes_studio.cli import main; sys.exit(main(sys.argv[1:]))", "studio", "--port", String(port)],
    { env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
  );
  const keep = (b) => {
    engineLog.push(...String(b).split("\n").filter(Boolean));
    engineLog = engineLog.slice(-20);
  };
  engine.stdout.on("data", keep);
  engine.stderr.on("data", keep);
  engine.on("error", (e) => keep(e.message));
  const url = `http://127.0.0.1:${port}/`;
  if (await waitFor(url, 45000)) {
    deskUrl = url;
    return { ok: true };
  }
  const why = engineLog.slice(-6).join("\n") || "The engine did not answer in time.";
  stopEngine();
  return { ok: false, error: why };
}

function stopEngine() {
  if (engine && engine.exitCode === null) {
    try {
      if (process.platform === "win32") {
        // Kill the whole tree: the engine may have ffmpeg children mid-render.
        spawn("taskkill", ["/pid", String(engine.pid), "/T", "/F"], { windowsHide: true });
      } else {
        engine.kill("SIGTERM");
      }
    } catch {}
  }
  engine = null;
}

function page(title, body) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(`<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
    background:#0b0b0c; color:#f2efe8; font:15px/1.5 Archivo,system-ui,sans-serif; }
  div { max-width:520px; padding:32px; }
  h1 { font-size:20px; font-weight:700; margin:0 0 8px; }
  p { color:rgba(242,239,232,.64); margin:0 0 16px; }
  pre { color:#ff6b5b; white-space:pre-wrap; font:12px/1.5 ui-monospace,monospace; margin:0 0 16px; }
  button { background:#ffc83d; color:#110c00; border:0; border-radius:999px; padding:8px 18px; font-weight:700; cursor:pointer; }
  .bar { height:3px; width:180px; background:rgba(242,239,232,.12); overflow:hidden; border-radius:3px; }
  .bar i { display:block; height:100%; width:40%; background:#ffc83d; animation:s 1.1s ease-in-out infinite; }
  @keyframes s { from { transform:translateX(-100%) } to { transform:translateX(260%) } }
</style></head><body><div><h1>${title}</h1>${body}</div></body></html>`)}`;
}

const STARTING = page("Starting Hermes Studio", `<p>Warming up the engine on this computer.</p><div class="bar"><i></i></div>`);
const failed = (why) =>
  page(
    "Hermes Studio couldn't start its engine.",
    `<p>Here is what the engine said:</p><pre>${why.replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" })[c])}</pre>
     <button onclick="window.studio.retry()">Try again</button>`,
  );

async function boot() {
  if (deskUrl && (await up(deskUrl))) return win.loadURL(deskUrl);
  win.loadURL(STARTING);
  const r = await startEngine();
  win.loadURL(r.ok ? deskUrl : failed(r.error));
}

ipcMain.handle("retry", () => boot());

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 760,
    minHeight: 540,
    backgroundColor: "#0b0b0c",
    title: "Hermes Studio",
    icon: path.join(__dirname, "..", "resources", "icon.png"),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  boot();
}

const menu = Menu.buildFromTemplate([
  {
    label: "Hermes Studio",
    submenu: [{ role: "reload" }, { role: "toggleDevTools" }, { type: "separator" }, { role: "quit" }],
  },
  {
    label: "View",
    submenu: [{ role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { role: "togglefullscreen" }],
  },
]);

app.whenReady().then(() => {
  Menu.setApplicationMenu(menu);
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", stopEngine);
app.on("window-all-closed", () => {
  stopEngine();
  if (process.platform !== "darwin") app.quit();
});
