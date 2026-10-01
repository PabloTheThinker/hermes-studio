# Third-party license texts

These texts ship inside the desktop app (`resources/licenses/` and
`resources/engine/licenses/`), next to `NOTICE`, which says which component
uses which license.

| File | License | Used by |
|---|---|---|
| `FFmpeg-GPL.txt` | GNU GPL v3 | FFmpeg executables (BtbN `gpl` build); libx264/libx265 in the PyAV wheel |
| `LGPL-3.0.txt` | GNU LGPL v3 (adds to the GPL v3 text) | FFmpeg libraries bundled in the PyAV wheel |
| `LGPL-2.1.txt` | GNU LGPL v2.1 | FFmpeg libraries bundled in the opencv-python-headless wheel |

Hermes Studio's own code is MIT (`LICENSE`).
