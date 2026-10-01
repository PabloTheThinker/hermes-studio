// electron-builder beforePack hook (electron-builder.json "beforePack").
//
// The AppImage target copies every library in its toolset's lib/x64 into usr/lib. Four of them
// back features Hermes Studio does not use (no Tray, Notification, badge or app indicator
// anywhere in desktop/): libappindicator, libindicator (LGPL), libgconf and libnotify. They would
// also need their exact source shipped, so they are left out. electron-builder has no option for
// this, so its AppImage tool lookup is wrapped to hand over a copy of lib/x64 without them.
// libXss and libXtst (MIT) stay. The linux CI job checks the AppImage's usr/lib and ldd.
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const EXCLUDED = ["libappindicator.so.1", "libindicator.so.7", "libgconf-2.so.4", "libnotify.so.4"];

exports.EXCLUDED = EXCLUDED;
exports.default = async function beforePack(context) {
  if (context.electronPlatformName !== "linux") return;
  const linux = require("app-builder-lib/out/toolsets/linux");
  if (linux.getAppImageTools.hermesWithoutExtraLibs) return;
  const original = linux.getAppImageTools;
  const wrapped = async (...args) => {
    const tools = await original(...args);
    const libs = fs.readdirSync(tools.runtimeLibraries);
    const missing = EXCLUDED.filter((f) => !libs.includes(f));
    if (missing.length) {
      throw new Error(`AppImage toolset lib dir changed (no ${missing.join(", ")}): review scripts/electron-builder-before-pack.js`);
    }
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "appimage-lib-"));
    for (const f of libs) {
      if (!EXCLUDED.includes(f)) fs.copyFileSync(path.join(tools.runtimeLibraries, f), path.join(dir, f));
    }
    console.log(`  • AppImage usr/lib: ${libs.filter((f) => !EXCLUDED.includes(f)).join(", ")} (left out: ${EXCLUDED.join(", ")})`);
    return { ...tools, runtimeLibraries: dir };
  };
  wrapped.hermesWithoutExtraLibs = true;
  linux.getAppImageTools = wrapped;
};
