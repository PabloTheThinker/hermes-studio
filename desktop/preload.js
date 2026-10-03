// Bridge between the app's own pages and the app: retry starting the engine; the Edit page's token.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studio", {
  retry: () => ipcRenderer.invoke("retry"),
  // The Edit page's token, in memory only (main checks the asking page is the desk).
  uiToken: () => ipcRenderer.invoke("ui-token"),
});
