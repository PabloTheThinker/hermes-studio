# How Hermes Studio frames a face

Turning a 16:9 video into a 9:16 short throws away about two thirds of the picture. What
decides whether a clip looks professional is where the face ends up in the part you keep.
This note sets out the rules `hermes_studio/framing.py` follows and where each one comes from.

## Detection

- **YuNet** (OpenCV Zoo, MIT, bundled at 230 KB) replaces the old Haar cascade as the default.
  It is more accurate on real footage, finds small faces such as corner facecams, and gives
  five landmarks per face. That means we know where the **eyes** are and which way the
  **head is turned**, which a plain box can't tell us. On OpenCV builds without
  `FaceDetectorYN`, Studio falls back to Haar.
- Nine frames are sampled across each clip. `main_subject()` follows one person through
  them, so a poster, a game character or a passer-by can't pull the crop away.

## Composition (talking head, Speaker/Fill layout)

| Rule | Value | Why |
|---|---|---|
| Eye line | 36% from the top | Upper-third rule for vertical video. It also keeps the eyes clear of the top UI strip (~120 px of 1920 on Shorts). |
| Headroom | crop never starts below the forehead | Cutting off the top of the head is the most common auto-crop failure. |
| Horizontal home | 47% (slightly left of centre) | Shorts, TikTok and Reels stack buttons down the right edge (~96 px of 1080). |
| Lead room | up to 7% toward the gaze | A head turned to one side needs space in front of it, not behind it. |
| Face size | about 20% of frame height | Reads as a close talking head. Small faces get zoomed in. |
| Upscale cap | 2.2× | Zooming further turns source pixels to mush. |

## Camera

Following Google AutoFlip, which decides between a still camera and tracking:

- **Still subject** (face moves less than 6% of the frame width across the clip): one
  **locked** crop. Micro-tracking a person sitting still looks amateur.
- **Moving subject**: a **smooth pan** between the sampled positions, capped at 18% of
  the source width per second.
- **Jump** (a second speaker, or a big move of more than 22% of the width): a **hard cut**
  halfway between samples, never a whip pan across the room.

Pan keys are mapped through the tight-cut time map, so they stay in sync after filler is removed.

## Streams (Split layout)

- **Facecam** detection: a small face (under 16% of the frame width) sitting off-centre or
  low in the frame. That is the Twitch/Kick webcam tile.
- The **face band** shows the cam tile tightly, with the eyes about 40% down the band.
  A speaker who is actually in the frame gets head and shoulders instead.
- The **content band** is full height, nudged away from the camera corner.
- Face on **top** (the default, and the standard for gaming shorts) or **bottom**. The band
  takes 20–60% of the height, 35% by default. A manual camera box overrides detection.
- Both bands stay locked: gameplay moves, but the frame does not.

## Sources

- YouTube Shorts safe zone, 1080×1920: top ~120 px, bottom ~300 px, right ~96 px
  (postplanify.com, reformat.video, pod2reels.com Shorts safe-zone guides, 2026).
- Vertical framing, eye line and headroom (clickyapps.com vertical framing guide; toneproduction.net).
- Stationary vs. tracking camera: Google AutoFlip. Rule-of-thirds eye line and lead room
  from head yaw: fralapo/clippyme `docs/reframe-improvements-research.md`.
- Facecam detection pitfalls (games contain faces, small cams starve detectors, and a
  stable tile beats a face cluster): zoupyu.com engineering post, Aug 2026, and clip-farm.com.
- Face detector comparison: opencv.org, "Cascade Classifier vs YuNet".
