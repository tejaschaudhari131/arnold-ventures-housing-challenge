/* Keyboard and button controls for the Stateframe executive slide deck */
(function () {
  "use strict";

  var slides = Array.prototype.slice.call(document.querySelectorAll(".slide"));
  var singleMode = false;
  var index = 0;

  var modeBtn = document.getElementById("deck-mode");
  var prevBtn = document.getElementById("deck-prev");
  var nextBtn = document.getElementById("deck-next");
  var printBtn = document.getElementById("deck-print");
  var counter = document.getElementById("deck-counter");

  function render() {
    document.body.classList.toggle("deck-single", singleMode);
    slides.forEach(function (slide, i) {
      slide.hidden = singleMode ? i !== index : false;
    });
    if (prevBtn) prevBtn.hidden = !singleMode;
    if (nextBtn) nextBtn.hidden = !singleMode;
    if (modeBtn) {
      modeBtn.textContent = singleMode ? "Show all " + slides.length + " slides" : "Slide-by-slide view";
    }
    if (counter) {
      counter.textContent = singleMode
        ? ("Slide " + (index + 1) + " of " + slides.length)
        : ("All " + slides.length + " slides");
    }
  }

  function step(delta) {
    if (!slides.length) return;
    index = Math.max(0, Math.min(slides.length - 1, index + delta));
    render();
  }

  if (modeBtn) {
    modeBtn.addEventListener("click", function () {
      singleMode = !singleMode;
      render();
    });
  }
  if (prevBtn) prevBtn.addEventListener("click", function () { step(-1); });
  if (nextBtn) nextBtn.addEventListener("click", function () { step(1); });
  if (printBtn) {
    printBtn.addEventListener("click", function () {
      window.print();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (!singleMode) return;
    if (event.key === "ArrowRight" || event.key === "PageDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      index = 0;
      render();
    } else if (event.key === "End") {
      event.preventDefault();
      index = slides.length - 1;
      render();
    }
  });

  render();
})();
