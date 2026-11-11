/* Clip transform keyframes at clip-local seconds — easing via HSEase (easing.py). */
(function () {
  "use strict";

  const E = () => window.HSEase;

  function at(kfs, t) {
    const H = E();
    if (!kfs || kfs.length < 2 || !H) {
      return { x: 0, y: 0, scale: 1, rotate: 0, opacity: 1 };
    }
    return {
      x: H.interpScalar(kfs, "x", t),
      y: H.interpScalar(kfs, "y", t),
      scale: H.interpScalar(kfs, "scale", t),
      rotate: H.interpScalar(kfs, "rotate", t),
      opacity: H.interpScalar(kfs, "opacity", t),
    };
  }

  const api = { at };
  if (typeof window !== "undefined") window.HSKf = api;
  if (typeof module !== "undefined") module.exports = api;
})();
