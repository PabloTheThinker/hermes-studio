# Design editor v2: functions first

**Goal:** bring the Hermes Studio Design editor up to the function set people actually use in Canva, Photoshop and Pixlr, with the controls where the hand expects them.

**What the research says (2026-10-01):**
- Canva's daily tools are Adjust (brightness, contrast, saturation, temperature, blur, sharpen, auto), crop, filters, position (align, distribute, tidy), copy style, and keyboard shortcuts (T/R/C/L, Ctrl+D/G, arrows, Ctrl+] / [).
- Photoshop and Photopea live on layers, blend modes (multiply, screen, overlay, soft light), and non-destructive adjustments (levels, curves).
- Pixlr E is the same idea in a browser: adjust sliders, blend modes, crop, layers. Pixlr X proves the quick path: one rail, big controls, done in a minute.

**Already shipped (PR #30, merged f80cb1c):** drag/resize/rotate, text effects, drop shadows, layers panel, align, distribute, lock, group, crop, background removal, photo looks, five sizes, templates.

**This round, in order:**
1. Photo adjust, non-destructive: brightness, contrast, saturation, warmth, blur, sharpen, plus auto. Stored on the layer, so it survives a reload and an agent edit.
2. Blend modes on every layer: multiply, screen, overlay, soft light. The two renderers must agree.
3. Copy style and paste style, the paint-roller workflow.
4. Keyboard: T text, R rectangle, C circle, L line, Ctrl+D duplicate, Ctrl+G group, Ctrl+] / [ layer order, arrows nudge.
5. A floating mini-toolbar on the selection, so the common actions are at the hand, not in a side panel.

**Explicitly not this round:** stock libraries, AI generation, animation, curves, masks, clone stamp. Each is its own project.

**Proof:** a render test per blend mode and per adjustment, then a browser drive of adjust, blend, copy style and the shortcuts, looked at by eye.
