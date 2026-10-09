// Pure path checks for the main process (no Electron here, so they can be run on their own).
const fs = require("fs");
const path = require("path");

// The project ids the engine makes and accepts (timeline.ID_RE): one plain folder name.
const PROJECT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

// The real path of a finished render, or null: `rel` (render_status's path, relative to the
// project) must resolve, after links, to an .mp4 (a render) or .otio (an OTIO export) directly in
// <root>/<projectId>/exports/.
function renderFile(root, projectId, rel) {
  if (typeof projectId !== "string" || typeof rel !== "string" || !PROJECT_ID.test(projectId)) return null;
  try {
    const realRoot = fs.realpathSync(root);
    const real = fs.realpathSync(path.resolve(realRoot, projectId, rel));
    const inside = path.relative(realRoot, real);
    if (!inside || inside.startsWith("..") || path.isAbsolute(inside)) return null;
    const parts = inside.split(path.sep);
    return parts.length === 3 && parts[0] === projectId && parts[1] === "exports" && /\.(mp4|otio)$/.test(real) ? real : null;
  } catch {
    return null;
  }
}

module.exports = { renderFile, PROJECT_ID };
