# Screenshot sources: shotcut

All files are real images downloaded with curl on Oct 1, 2026 (ET) from the official URLs below (static images converted to PNG; GIFs kept as-is). Own captures, if any, are listed separately.

| File | Image URL | Found on page | What it shows |
|---|---|---|---|
| 01-main-window-18.11.png | https://www.shotcut.org/assets/img/screenshots/Shotcut-18.11.18.png | https://www.shotcut.org/ | Main window (18.11 release screenshot on homepage) |
| 02-editing-group.png | https://www.shotcut.org/assets/img/editing-group.jpg | https://www.shotcut.org/features/ | Editing features collage |
| 03-waveforms.png | https://www.shotcut.org/assets/img/waveforms.png | https://www.shotcut.org/features/ | Audio waveforms on timeline |
| 04-mac-monitor.png | https://www.shotcut.org/assets/img/shotcut_mac_monitor.png | https://www.shotcut.org/features/ | Main window on macOS |
| 05-external-monitoring.png | https://www.shotcut.org/assets/img/external-monitoring.png | https://www.shotcut.org/features/ | External monitoring |

## Own captures (made on the research box, Oct 1, 2026 ET)

App: Shotcut 25.03.29 (Debian trixie apt `shotcut 25.03.29+ds-1`, MLT 7.30.0).

Method: Run under Xvfb :99 (1600x1000) + openbox, captured with ImageMagick `import -window root`. Test clip: ffmpeg testsrc2 + 440 Hz sine, 20 s, appended twice with `A`, split with `S`. The preview monitor stayed black under Xvfb/llvmpipe (MLT OpenGL widget initialised, but no frame was painted); timeline thumbnails render.

| File | What it shows |
|---|---|
| 10-own-main-window-split-clip-history.png | main window split clip history |
| 11-own-filters-add-menu.png | filters add menu |
| 12-own-export-presets.png | export presets |
| 13-own-keyframes-panel.png | keyframes panel |
| 14-own-color-layout.png | color layout |
| 15-own-audio-layout.png | audio layout |
| 16-own-logging-layout.png | logging layout |
| 17-own-editing-layout-return.png | editing layout return |
