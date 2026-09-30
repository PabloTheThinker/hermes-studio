// Bridge between the first-run page and the app. Exposes one call: start the engine.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("studio", {
  startEngine: () => ipcRenderer.invoke("start-engine"),
});
