/* bond-esign panel script: plain ES2017, no dependencies besides the global SignaturePad. */
(function () {
  "use strict";

  var INK = "#111111";
  var MAX_RATIO = 2; /* backing store: at most 2x the CSS size */
  var MAX_PX_W = 2400; /* and at most the server limit of 2400x1200 pixels */
  var MAX_PX_H = 1200;

  function setup(form) {
    var allowDrawn = form.getAttribute("data-allow-drawn") === "1";
    var allowTyped = form.getAttribute("data-allow-typed") === "1";
    var modeInput = form.querySelector("[data-bond-esign-mode]");
    var pngInput = form.querySelector("[data-bond-esign-png]");
    var consent = form.querySelector('input[name="consent_accepted"]');
    var nameInput = form.querySelector('input[name="typed_name"]');
    var submit = form.querySelector('button[type="submit"]');
    var tablist = form.querySelector('[role="tablist"]');
    var drawPanel = form.querySelector('[role="tabpanel"].bond-esign__draw');
    var typePanel = form.querySelector('[role="tabpanel"].bond-esign__type');
    var canvas = form.querySelector("canvas");
    var clearBtn = form.querySelector(".bond-esign__clear");
    var preview = form.querySelector("[data-bond-esign-preview]");
    var pad = null;
    var lastWidth = 0;
    var lastHeight = 0;
    var mode = "typed";

    if (allowDrawn && canvas && typeof window.SignaturePad === "function" && canvas.getContext) {
      try {
        pad = new window.SignaturePad(canvas, { penColor: INK, backgroundColor: "rgba(0,0,0,0)" });
      } catch (err) {
        pad = null;
      }
    }
    if (!pad && !allowTyped) {
      return; /* nothing usable: leave the server markup alone */
    }

    function sizeCanvas() {
      // the content box (the bounding rect would include the border and over-size the backing store)
      var w = Math.round(canvas.clientWidth);
      var h = Math.round(canvas.clientHeight);
      if (!w || !h) {
        return;
      }
      // the server refuses a PNG over 2400x1200: the backing store never exceeds that, nor 2x the CSS size
      var dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), MAX_RATIO, MAX_PX_W / w, MAX_PX_H / h);
      var data = JSON.parse(JSON.stringify(pad.toData()));
      var ratio = lastWidth ? w / lastWidth : 1;
      var ratioY = lastHeight ? h / lastHeight : 1;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      var ctx = canvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
      pad.clear();
      if (data.length) {
        if (ratio !== 1 || ratioY !== 1) {
          data.forEach(function (group) {
            (group.points || []).forEach(function (pt) {
              pt.x *= ratio;
              pt.y *= ratioY;
            });
          });
        }
        pad.fromData(data);
      }
      lastWidth = w;
      lastHeight = h;
    }

    var pending = false;
    function onResize() {
      if (pending || !pad) {
        return;
      }
      pending = true;
      window.requestAnimationFrame(function () {
        pending = false;
        sizeCanvas();
        update();
      });
    }

    function update() {
      var hasName = nameInput.value.trim() !== "";
      var inked = mode === "drawn" && pad && !pad.isEmpty();
      var ok = consent.checked && ((mode === "drawn" && inked) || (mode === "typed" && hasName));
      submit.disabled = !ok;
      if (preview) {
        preview.textContent = nameInput.value;
      }
    }

    function setMode(next) {
      if ((next === "drawn" && !pad) || (next === "typed" && !allowTyped)) {
        return;
      }
      mode = next;
      modeInput.value = next;
      if (drawPanel) {
        drawPanel.hidden = next !== "drawn";
      }
      if (typePanel) {
        typePanel.hidden = next !== "typed";
      }
      nameInput.required = next === "typed";
      if (tablist) {
        Array.prototype.forEach.call(tablist.querySelectorAll('[role="tab"]'), function (tab) {
          var on = tab.getAttribute("data-mode") === next;
          tab.setAttribute("aria-selected", on ? "true" : "false");
          tab.tabIndex = on ? 0 : -1;
        });
      }
      if (next === "drawn") {
        sizeCanvas();
      }
      update();
    }

    if (pad) {
      if (drawPanel) {
        drawPanel.hidden = false;
      }
      if (tablist) {
        tablist.hidden = false;
      }
      pad.addEventListener("endStroke", update);
      if (clearBtn) {
        clearBtn.addEventListener("click", function () {
          pad.clear();
          update();
        });
      }
      window.addEventListener("resize", onResize);
      window.addEventListener("orientationchange", onResize);
    } else {
      if (drawPanel) {
        drawPanel.hidden = true;
      }
      if (tablist) {
        tablist.hidden = true;
      }
    }

    if (tablist && pad) {
      var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
      tabs.forEach(function (tab, i) {
        tab.addEventListener("click", function () {
          setMode(tab.getAttribute("data-mode"));
        });
        tab.addEventListener("keydown", function (ev) {
          var step = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
          if (!step) {
            return;
          }
          ev.preventDefault();
          var target = tabs[(i + step + tabs.length) % tabs.length];
          setMode(target.getAttribute("data-mode"));
          target.focus();
        });
      });
    }

    consent.addEventListener("change", update);
    nameInput.addEventListener("input", update);
    nameInput.addEventListener("change", update);

    form.addEventListener("submit", function (ev) {
      if (submit.disabled) {
        ev.preventDefault();
        return;
      }
      if (mode === "drawn" && pad && !pad.isEmpty()) {
        pngInput.value = pad.toDataURL("image/png");
      } else {
        pngInput.value = "";
      }
      /* Disable after the browser has collected the form data, so the post still goes through. */
      window.setTimeout(function () {
        submit.disabled = true;
      }, 0);
    });

    /* A page restored from the back-forward cache keeps the disabled button: re-evaluate. */
    window.addEventListener("pageshow", update);

    setMode(pad ? "drawn" : "typed");
    if (!pad || !allowTyped) {
      /* keep the typed panel/draw panel state consistent when only one mode exists */
      update();
    }
  }

  function init() {
    Array.prototype.forEach.call(document.querySelectorAll("form[data-bond-esign]"), setup);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
