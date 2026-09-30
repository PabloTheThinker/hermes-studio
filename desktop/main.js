// Hermes Studio desktop window.
// The desk already exists as a local page. This window is the app around it:
// its own frame, a menu, and a graceful screen when the local engine is down.
const { app, BrowserWindow, Menu, shell } = require("electron");
const http = require("http");

const DESK = process.env.HERMES_STUDIO_URL || "http://127.0.0.1:3870/";

function engineUp() {
  return new Promise((resolve) => {
    const req = http.get(DESK, (res) => {
      res.resume();
      resolve(res.statusCode && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function offlinePage() {
  return `data:text/html;charset=utf-8,${encodeURIComponent(`<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
    background:#0b0b0c; color:#f2efe8; font:15px/1.5 Archivo,system-ui,sans-serif; }
  div { max-width:420px; padding:32px; }
  h1 { font-size:20px; font-weight:700; margin:0 0 8px; }
  p { color:rgba(242,239,232,.64); margin:0 0 16px; }
  code { color:#ffc83d; }
</style></head><body><div>
  <h1>Hermes Studio can't reach its engine.</h1>
  <p>The clipping engine isn't running on this computer. Start it, then reopen the app.</p>
  <p><code>hermesclip studio</code></p>
</div></body></html>`)}`;
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 760,
    minHeight: 540,
    backgroundColor: "#0b0b0c",
    title: "Hermes Studio",
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });

  const up = await engineUp();
  if (up) win.loadURL(DESK);
  else win.loadURL(offlinePage());

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

const menu = Menu.buildFromTemplate([
  {
    label: "Hermes Studio",
    submenu: [
      { role: "reload" },
      { role: "toggleDevTools" },
      { type: "separator" },
      { role: "quit" },
    ],
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

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
