// Bridge between the app's own pages and the app. One call: try starting the engine again.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studio", {
  retry: () => ipcRenderer.invoke("retry"),
});
