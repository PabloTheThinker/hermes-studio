// Bridge between the app's own pages and the app: retry starting the engine; the Edit page's token,
// file dialog and dropped files' paths.
const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("studio", {
  retry: () => ipcRenderer.invoke("retry"),
  // The Edit page's token, in memory only (main checks the asking page is the desk).
  uiToken: () => ipcRenderer.invoke("ui-token"),
  // The Edit page's Browse button (a file dialog) and drag-and-drop (a dropped file's path).
  pickFile: () => ipcRenderer.invoke("pick-file"),
  pathOf: (file) => {
    try {
      return webUtils.getPathForFile(file) || null;
    } catch {
      return null;
    }
  },
});
