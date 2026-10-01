# Third-party license texts

These texts ship inside the desktop app (`resources/licenses/` and
`resources/engine/licenses/`), next to `NOTICE`, which says which component
uses which license.

| File | License | Used by |
|---|---|---|
| `FFmpeg-GPL.txt` | GNU GPL v3 | FFmpeg executables (BtbN `gpl` build); libx264/libx265 in the PyAV wheel; libgfortran (with the GCC runtime exception) |
| `LGPL-3.0.txt` | GNU LGPL v3 (adds to the GPL v3 text) | FFmpeg libraries bundled in the PyAV wheel |
| `LGPL-2.1.txt` | GNU LGPL v2.1 | FFmpeg libraries bundled in the opencv-python-headless wheel; libquadmath |
| `GCC-RLE-3.1.txt` | GCC Runtime Library Exception 3.1 (from gcc-16.2.0 `COPYING.RUNTIME`) | GCC runtime libraries (libgcc, libstdc++, libgomp, libgfortran) linked into or shipped with FFmpeg, PyAV, OpenCV, numpy and ctranslate2 |
| `Rust-std-MIT.txt` | MIT (rust-lang/rust `LICENSE-MIT` at d080e7dff1b0) | Rust standard library compiled into rav1e and librsvg in the FFmpeg executables |
| `Rust-std-Apache-2.0.txt` | Apache License 2.0 (rust-lang/rust `LICENSE-APACHE` at d080e7dff1b0) | same; the Rust standard library is MIT OR Apache-2.0 |
| `winpthreads.txt` | MIT and BSD-3-Clause (mingw-w64 v14.0.0 `mingw-w64-libraries/winpthreads/COPYING`) | `libwinpthread-1.dll` in the PyAV Windows wheel |
| `zlib.txt` | zlib License (zlib 1.3.2 `LICENSE`) | `zlib1.dll` in the PyAV Windows wheel |
| `OpenTimelineIO.txt` | Apache License 2.0 (OpenTimelineIO 0.18.1 `LICENSE.txt` and `NOTICE.txt`), plus the BSD-3-Clause / MIT texts of the Imath, RapidJSON and pybind11 code compiled into it | the `opentimelineio` wheel in the engine (timeline export) |

Hermes Studio's own code is MIT (`LICENSE`).
