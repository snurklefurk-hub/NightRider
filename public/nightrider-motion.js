(function () {
  "use strict";
  var scene = document.createElement("div");
  scene.className = "parallax-scene";
  scene.setAttribute("aria-hidden", "true");
  scene.innerHTML = '<div class="parallax-stars"></div><div class="parallax-sun"></div><div class="parallax-horizon"></div><div class="parallax-grid"></div>';
  document.body.insertBefore(scene, document.body.firstChild);

  var stars = scene.querySelector(".parallax-stars");
  var sun = scene.querySelector(".parallax-sun");
  var horizon = scene.querySelector(".parallax-horizon");
  var grid = scene.querySelector(".parallax-grid");
  var sheet = document.querySelector(".sheet");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var queued = false;

  function paint() {
    queued = false;
    if (reduced) return;
    var depth = Math.max(window.scrollY || 0, sheet ? sheet.scrollTop : 0);
    stars.style.transform = "translate3d(0," + Math.min(depth * 0.025, 70) + "px,0)";
    sun.style.transform = "translate3d(-50%," + Math.min(depth * 0.045, 110) + "px,0)";
    horizon.style.transform = "translate3d(0," + Math.min(depth * 0.075, 150) + "px,0)";
    grid.style.transform = "perspective(420px) rotateX(63deg) translate3d(0," + Math.min(depth * 0.12, 190) + "px,0)";
  }

  function queuePaint() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(paint);
  }

  window.addEventListener("scroll", queuePaint, { passive: true });
  if (sheet) sheet.addEventListener("scroll", queuePaint, { passive: true });
  window.addEventListener("resize", queuePaint, { passive: true });
  queuePaint();
})();
