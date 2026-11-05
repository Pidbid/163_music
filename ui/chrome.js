(function () {
  "use strict";

  var ICON = "__NM_ICON_DATA_URI__";
  var STYLE_ID = "nm-shell-style";
  var BAR_ID = "nm-shell-bar";
  var BAR_HEIGHT = 38;
  var MIN_WIDTH = 940;
  var MIN_HEIGHT = 620;
  var DRAG_THRESHOLD = 4;
  var DOUBLE_CLICK_MS = 340;

  if (window.__nmShellInstalled && document.getElementById(BAR_ID)) return;
  window.__nmShellInstalled = true;

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function safeCall(method, args) {
    var bridge = api();
    if (!bridge || typeof bridge[method] !== "function") return Promise.resolve(null);
    try {
      return Promise.resolve(bridge[method].apply(bridge, args || []));
    } catch (error) {
      return Promise.reject(error);
    }
  }

  function logError(message) {
    try {
      console.warn("[nm-shell]", message);
    } catch (error) {
      // A page with a broken console must not break window controls.
    }
    safeCall("log_client_error", [String(message)]).catch(function () {});
  }

  function clean(value) {
    return String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  }

  function parseClock(value) {
    var parts = clean(value).split(":");
    if (parts.length !== 2 && parts.length !== 3) return null;
    var numbers = [];
    for (var i = 0; i < parts.length; i += 1) {
      if (!/^\d+$/.test(parts[i])) return null;
      numbers.push(parseInt(parts[i], 10));
    }
    var seconds = numbers[numbers.length - 1];
    var minutes = numbers[numbers.length - 2];
    if (seconds >= 60) return null;
    if (numbers.length === 3) {
      if (minutes >= 60) return null;
      return numbers[0] * 3600 + minutes * 60 + seconds;
    }
    return minutes * 60 + seconds;
  }

  function parsePercent(value) {
    var text = clean(value);
    if (text.slice(-1) === "%") text = text.slice(0, -1).trim();
    if (!text) return null;
    var number = Number(text);
    if (!isFinite(number) || number < 0 || number > 100) return null;
    return number;
  }

  function parseColor(value) {
    var text = String(value || "").trim();
    var hex = text.match(/^#([0-9a-f]{3,8})$/i);
    if (hex) {
      var digits = hex[1];
      if (digits.length === 3 || digits.length === 4) {
        digits = digits.split("").map(function (digit) { return digit + digit; }).join("");
      }
      if (digits.length !== 6 && digits.length !== 8) return null;
      return {
        r: parseInt(digits.slice(0, 2), 16),
        g: parseInt(digits.slice(2, 4), 16),
        b: parseInt(digits.slice(4, 6), 16),
        a: digits.length === 8 ? parseInt(digits.slice(6, 8), 16) / 255 : 1
      };
    }
    var match = text.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    var parts = match[1].split(",").map(function (part) {
      return Number(part.trim());
    });
    if (parts.length < 3 || parts.some(function (part) { return !isFinite(part); })) return null;
    return {
      r: Math.max(0, Math.min(255, parts[0])),
      g: Math.max(0, Math.min(255, parts[1])),
      b: Math.max(0, Math.min(255, parts[2])),
      a: parts.length > 3 ? Math.max(0, Math.min(1, parts[3])) : 1
    };
  }

  function composite(foreground, background) {
    var alpha = foreground.a == null ? 1 : foreground.a;
    return {
      r: foreground.r * alpha + background.r * (1 - alpha),
      g: foreground.g * alpha + background.g * (1 - alpha),
      b: foreground.b * alpha + background.b * (1 - alpha),
      a: 1
    };
  }

  function luminance(color) {
    function channel(value) {
      var scaled = value / 255;
      return scaled <= 0.03928 ? scaled / 12.92 : Math.pow((scaled + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  }

  function rgb(color) {
    return "rgb(" + Math.round(color.r) + ", " + Math.round(color.g) + ", " + Math.round(color.b) + ")";
  }

  function contrastRatio(a, b) {
    var first = luminance(a);
    var second = luminance(b);
    var lighter = Math.max(first, second);
    var darker = Math.min(first, second);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function bestForeground(background) {
    var dark = { r: 24, g: 32, b: 49, a: 1 };
    var light = { r: 245, g: 247, b: 250, a: 1 };
    return contrastRatio(dark, background) >= contrastRatio(light, background) ? dark : light;
  }

  function parseGradient(value) {
    var text = String(value || "");
    if (!text || text === "none" || text.indexOf("gradient(") === -1) return null;
    var matches = text.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,8}/g);
    if (!matches) return null;
    var colors = matches.map(parseColor).filter(Boolean);
    if (!colors.length) return null;
    var total = 0;
    var r = 0;
    var g = 0;
    var b = 0;
    var a = 0;
    colors.forEach(function (color) {
      var weight = Math.max(0.0001, color.a);
      total += weight;
      r += color.r * weight;
      g += color.g * weight;
      b += color.b * weight;
      a += color.a * weight;
    });
    if (!total) return null;
    return { r: r / total, g: g / total, b: b / total, a: Math.min(1, a / total) };
  }

  function layerColor(element) {
    try {
      var style = getComputedStyle(element);
      var gradient = parseGradient(style.backgroundImage);
      if (gradient) return gradient;
      var color = parseColor(style.backgroundColor);
      if (color && color.a > 0.001) return color;
    } catch (error) {
      return null;
    }
    return null;
  }

  function colorAt(x, y) {
    var bodyColor = parseColor(getComputedStyle(document.body).backgroundColor) ||
      { r: 247, g: 249, b: 252, a: 1 };
    var result = { r: bodyColor.r, g: bodyColor.g, b: bodyColor.b, a: 1 };
    var stack = document.elementsFromPoint(x, y);
    // The stack is topmost-first; walk it bottom-up and skip the root, whose
    // background is already the base. Page theme layers below the DOM content
    // (for example the app background gradient) then survive the composite.
    for (var i = stack.length - 1; i >= 0; i -= 1) {
      var element = stack[i];
      if (element === document.body || element === document.documentElement) continue;
      if (element.id === BAR_ID || element.closest("#" + BAR_ID) ||
          element.classList.contains("nm-resize")) {
        continue;
      }
      var color = layerColor(element);
      if (color) result = composite(color, result);
    }
    return result;
  }

  function sampleTheme() {
    var bar = document.getElementById(BAR_ID);
    if (!bar) return;
    var width = Math.max(1, window.innerWidth);
    var y = Math.min(window.innerHeight - 1, BAR_HEIGHT + 2);
    var fractions = [0, 0.02, 0.05, 0.09, 0.13, 0.15, 0.18, 0.24, 0.32, 0.45, 0.6, 0.75, 0.9, 1];
    var samples = fractions.map(function (fraction) {
      var x = Math.max(0, Math.min(width - 1, Math.round(fraction * (width - 1))));
      return { percent: fraction * 100, color: colorAt(x, y) };
    });
    // Match the page's sidebar edge exactly instead of smoothing across it.
    var sidebar = document.getElementById("page_pc_main_tab");
    var sidebarWidth = sidebar ? sidebar.getBoundingClientRect().width : 0;
    var boundary = sidebarWidth > 8 && sidebarWidth < width - 8
      ? (sidebarWidth / width) * 100
      : 0;
    if (boundary > 1) {
      var leftX = Math.max(0, Math.round(sidebarWidth - 2));
      var rightX = Math.min(width - 1, Math.round(sidebarWidth + 2));
      samples = samples.filter(function (sample) {
        return Math.abs(sample.percent - boundary) > 0.8;
      });
      samples.push({ percent: boundary - 0.05, color: colorAt(leftX, y) });
      samples.push({ percent: boundary + 0.05, color: colorAt(rightX, y) });
      samples.sort(function (a, b) { return a.percent - b.percent; });
    }
    var first = samples[0].color;
    var solid = samples.every(function (sample) {
      return Math.abs(sample.color.r - first.r) +
        Math.abs(sample.color.g - first.g) +
        Math.abs(sample.color.b - first.b) < 12;
    });
    var background = solid ? rgb(first) : "linear-gradient(90deg, " + samples.map(function (sample) {
      return rgb(sample.color) + " " + sample.percent.toFixed(1) + "%";
    }).join(", ") + ")";
    var titleColor = colorAt(Math.min(width - 1, 80), y);
    var controlColor = colorAt(Math.max(0, width - 66), y);
    var titleForeground = bestForeground(titleColor);
    var controlForeground = bestForeground(controlColor);
    var controlLum = luminance(controlColor);
    bar.style.setProperty("--nm-bar-bg", background);
    bar.style.setProperty("--nm-bar-fg", rgb(titleForeground));
    bar.style.setProperty("--nm-title-fg", rgb(titleForeground));
    bar.style.setProperty("--nm-control-fg", rgb(controlForeground));
    bar.style.setProperty("--nm-accent", controlLum > 0.52 ? "#ec4141" : "#ff6b6b");
    bar.style.setProperty("--nm-accent-fg", controlLum > 0.52 ? "#ffffff" : "#1a1011");
  }

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      "#topArea, *:has(> #topArea) { display: none !important; }",
      "#root > div:first-child {",
      "  position: relative !important;",
      "  top: " + BAR_HEIGHT + "px !important;",
      "  height: calc(100vh - " + BAR_HEIGHT + "px) !important;",
      "  box-sizing: border-box !important;",
      "}",
      "#nm-shell-bar {",
      "  position: fixed; top: 0; left: 0; right: 0; height: " + BAR_HEIGHT + "px;",
      "  z-index: 2147483646; box-sizing: border-box; display: flex; align-items: stretch;",
      "  color: var(--nm-bar-fg, rgba(40, 50, 72, .88));",
      "  background: var(--nm-bar-bg, #f7f9fc);",
      "  font: 12px/1 -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',",
      "    'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif;",
      "  user-select: none; -webkit-user-select: none;",
      "  transition: background .22s ease, color .22s ease;",
      "}",
      "#nm-shell-bar .nm-drag {",
      "  flex: 1; min-width: 0; height: 100%; display: flex; align-items: center; gap: 8px;",
      "  padding: 0 13px; cursor: default;",
      "}",
      "#nm-shell-bar .nm-logo {",
      "  width: 18px; height: 18px; border-radius: 5px; flex: 0 0 auto;",
      "  pointer-events: none; box-shadow: 0 0 0 1px rgba(255, 255, 255, .18), 0 1px 3px rgba(0, 0, 0, .26);",
      "}",
      "#nm-shell-bar .nm-title {",
      "  font-size: 12px; font-weight: 600; letter-spacing: .01em;",
      "  color: var(--nm-title-fg, inherit);",
      "  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;",
      "}",
      "#nm-shell-bar .nm-actions {",
      "  display: flex; align-items: stretch; height: 100%;",
      "  color: var(--nm-control-fg, inherit);",
      "}",
      "#nm-shell-bar .nm-btn {",
      "  appearance: none; border: 0; background: transparent; color: inherit;",
      "  width: 44px; height: 100%; padding: 0; display: inline-flex;",
      "  align-items: center; justify-content: center; cursor: pointer; opacity: .66;",
      "  transition: background .16s ease, opacity .16s ease, transform .12s ease;",
      "}",
      "#nm-shell-bar .nm-btn:hover {",
      "  opacity: 1; background: color-mix(in srgb, currentColor 8%, transparent);",
      "}",
      "#nm-shell-bar .nm-btn:active { transform: scale(.92); }",
      "#nm-shell-bar .nm-btn:focus-visible {",
      "  outline: 2px solid var(--nm-accent, #ec4141); outline-offset: -3px;",
      "}",
      "#nm-shell-bar .nm-btn.close:hover {",
      "  background: var(--nm-accent, #ec4141); color: var(--nm-accent-fg, #fff); opacity: 1;",
      "}",
      "#nm-shell-bar .nm-btn svg { width: 14px; height: 14px; display: block; }",
      ".nm-resize { position: fixed; z-index: 2147483647; background: transparent; touch-action: none; }",
      "#nm-resize-n { top: 0; left: 14px; right: 14px; height: 4px; cursor: ns-resize; }",
      "#nm-resize-s { bottom: 0; left: 14px; right: 14px; height: 5px; cursor: ns-resize; }",
      "#nm-resize-w { left: 0; top: 14px; bottom: 14px; width: 5px; cursor: ew-resize; }",
      "#nm-resize-e { right: 0; top: 14px; bottom: 14px; width: 5px; cursor: ew-resize; }",
      "#nm-resize-nw { top: 0; left: 0; width: 14px; height: 14px; cursor: nwse-resize; }",
      "#nm-resize-ne { top: 0; right: 0; width: 14px; height: 14px; cursor: nesw-resize; }",
      "#nm-resize-sw { bottom: 0; left: 0; width: 14px; height: 14px; cursor: nesw-resize; }",
      "#nm-resize-se { bottom: 0; right: 0; width: 14px; height: 14px; cursor: nwse-resize; }",
      "@media (prefers-reduced-motion: reduce) {",
      "  #nm-shell-bar .nm-btn, #nm-shell-bar .nm-btn:active { transition: none; transform: none; }",
      "}"
    ].join("\n");
    (document.head || document.documentElement).appendChild(style);
  }

  function icon(path) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.35");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    var pathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    pathEl.setAttribute("d", path);
    svg.appendChild(pathEl);
    return svg;
  }

  var MAXIMIZE_PATH = "M3.5 3.5h9v9h-9z";
  var RESTORE_PATH = "M5.5 3.5h7v7 M3.5 5.5h7v7h-7z";
  var MINIMIZE_PATH = "M3 8h10";
  var CLOSE_PATH = "M4.1 4.1l7.8 7.8 M11.9 4.1l-7.8 7.8";
  var maximizedState = false;
  var windowActionBusy = false;

  function updateMaximizeIcon(maximized) {
    maximizedState = !!maximized;
    var button = document.querySelector('#nm-shell-bar [data-action="toggle_maximize"]');
    if (!button) return;
    button.replaceChildren(icon(maximized ? RESTORE_PATH : MAXIMIZE_PATH));
    button.title = maximized ? "还原" : "最大化";
    button.setAttribute("aria-label", button.title);
  }

  function refreshWindowState() {
    safeCall("window_state").then(function (state) {
      if (state) updateMaximizeIcon(!!state.maximized);
    }).catch(function () {});
  }
  window.__nmShellRefreshWindowState = refreshWindowState;

  var stateSyncTimer = null;
  function refreshWindowStateSoon() {
    clearTimeout(stateSyncTimer);
    stateSyncTimer = setTimeout(refreshWindowState, 80);
  }
  window.addEventListener("resize", refreshWindowStateSoon);
  window.addEventListener("focus", refreshWindowState);

  function invokeWindowAction(action) {
    if (windowActionBusy) return;
    windowActionBusy = true;
    safeCall("main_action", [action]).then(function (ok) {
      if (ok) setTimeout(refreshWindowState, 60);
      windowActionBusy = false;
    }).catch(function (error) {
      windowActionBusy = false;
      logError("窗口操作失败：" + (error && error.message ? error.message : error));
    });
  }

  function toggleMaximize() {
    invokeWindowAction("toggle_maximize");
  }

  function windowButton(action, label, path, extraClass) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "nm-btn" + (extraClass ? " " + extraClass : "");
    button.dataset.action = action;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.appendChild(icon(path));
    button.addEventListener("pointerdown", function (event) {
      event.stopPropagation();
    });
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      invokeWindowAction(action);
    });
    return button;
  }

  function capturePointer(target, pointerId) {
    try {
      target.setPointerCapture(pointerId);
    } catch (error) {
      // Pointer capture is an enhancement; keyboard/old engines may reject it.
    }
  }

  function releasePointer(target, pointerId) {
    try {
      if (target.hasPointerCapture && target.hasPointerCapture(pointerId)) {
        target.releasePointerCapture(pointerId);
      }
    } catch (error) {
      // The pointer may already have been released by the compositor.
    }
  }

  function startResize(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    var captureTarget = event.currentTarget;
    var pointerId = event.pointerId;
    var direction = captureTarget.dataset.dir || "";
    var startX = event.screenX;
    var startY = event.screenY;
    var start = null;
    var latest = null;
    var frame = 0;
    var active = true;

    function removeListeners() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      window.removeEventListener("blur", onCancel);
      captureTarget.removeEventListener("lostpointercapture", onCancel);
    }

    function cleanup() {
      if (!active) return;
      active = false;
      removeListeners();
      releasePointer(captureTarget, pointerId);
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    }

    function flush() {
      frame = 0;
      if (!active || !latest) return;
      var bounds = latest;
      latest = null;
      safeCall("set_window_bounds", [bounds.x, bounds.y, bounds.width, bounds.height]);
    }

    function applyLatest() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      if (latest) {
        var bounds = latest;
        latest = null;
        safeCall("set_window_bounds", [bounds.x, bounds.y, bounds.width, bounds.height]);
      }
    }

    function onMove(moveEvent) {
      if (!active) return;
      if (!(moveEvent.buttons & 1)) {
        onUp();
        return;
      }
      if (!start) return;
      var dx = moveEvent.screenX - startX;
      var dy = moveEvent.screenY - startY;
      var x = start.x;
      var y = start.y;
      var width = start.width;
      var height = start.height;
      if (direction.indexOf("e") !== -1) width = Math.max(MIN_WIDTH, start.width + dx);
      if (direction.indexOf("w") !== -1) {
        width = Math.max(MIN_WIDTH, start.width - dx);
        x = start.x + (start.width - width);
      }
      if (direction.indexOf("s") !== -1) height = Math.max(MIN_HEIGHT, start.height + dy);
      if (direction.indexOf("n") !== -1) {
        height = Math.max(MIN_HEIGHT, start.height - dy);
        y = start.y + (start.height - height);
      }
      latest = {
        x: Math.round(x),
        y: Math.round(y),
        width: Math.round(width),
        height: Math.round(height)
      };
      if (!frame) frame = requestAnimationFrame(flush);
    }

    function onUp() {
      if (!active) return;
      applyLatest();
      cleanup();
    }

    function onCancel() {
      latest = null;
      cleanup();
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    window.addEventListener("blur", onCancel);
    captureTarget.addEventListener("lostpointercapture", onCancel);
    capturePointer(captureTarget, pointerId);

    safeCall("begin_system_resize", [direction]).then(function (started) {
      if (!active) return;
      if (started) {
        cleanup();
        refreshWindowState();
        return;
      }
      safeCall("prepare_resize").then(function (bounds) {
        if (!active) return;
        if (!bounds || typeof bounds.width !== "number" || typeof bounds.height !== "number") {
          cleanup();
          return;
        }
        start = bounds;
      }).catch(function (error) {
        cleanup();
        logError("调整窗口大小失败：" + (error && error.message ? error.message : error));
      });
    }).catch(function (error) {
      cleanup();
      logError("调整窗口大小失败：" + (error && error.message ? error.message : error));
    });
  }

  function startMove(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    var captureTarget = event.currentTarget;
    var pointerId = event.pointerId;
    var startX = event.screenX;
    var startY = event.screenY;
    var start = null;
    var latest = null;
    var lastPointer = { x: startX, y: startY };
    var frame = 0;
    var active = true;
    var nativeRequested = false;

    function removeListeners() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      window.removeEventListener("blur", onCancel);
      captureTarget.removeEventListener("lostpointercapture", onCancel);
    }

    function cleanup() {
      if (!active) return;
      active = false;
      removeListeners();
      releasePointer(captureTarget, pointerId);
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    }

    function flush() {
      frame = 0;
      if (!active || !latest) return;
      var next = latest;
      latest = null;
      safeCall("move_window", [next.x, next.y]);
    }

    function applyLatest() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      if (latest) {
        var next = latest;
        latest = null;
        safeCall("move_window", [next.x, next.y]);
      }
    }

    function updateLatest() {
      if (!start) return;
      latest = {
        x: Math.round(start.x + lastPointer.x - startX),
        y: Math.round(start.y + lastPointer.y - startY)
      };
      if (!frame) frame = requestAnimationFrame(flush);
    }

    function beginNativeMove() {
      nativeRequested = true;
      safeCall("begin_system_move").then(function (started) {
        if (!active) return;
        if (started) {
          cleanup();
          refreshWindowState();
          return;
        }
        safeCall("get_window_bounds").then(function (bounds) {
          if (!active) return;
          if (!bounds || typeof bounds.x !== "number" || typeof bounds.y !== "number") {
            cleanup();
            return;
          }
          start = bounds;
          updateLatest();
        }).catch(function (error) {
          cleanup();
          logError("移动窗口失败：" + (error && error.message ? error.message : error));
        });
      }).catch(function (error) {
        cleanup();
        logError("移动窗口失败：" + (error && error.message ? error.message : error));
      });
    }

    function onMove(moveEvent) {
      if (!active) return;
      if (!(moveEvent.buttons & 1)) {
        onUp();
        return;
      }
      lastPointer = { x: moveEvent.screenX, y: moveEvent.screenY };
      if (!nativeRequested) {
        var dx = lastPointer.x - startX;
        var dy = lastPointer.y - startY;
        if (Math.sqrt(dx * dx + dy * dy) < DRAG_THRESHOLD) return;
        beginNativeMove();
        return;
      }
      updateLatest();
    }

    function onUp() {
      if (!active) return;
      applyLatest();
      cleanup();
    }

    function onCancel() {
      latest = null;
      cleanup();
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    window.addEventListener("blur", onCancel);
    captureTarget.addEventListener("lostpointercapture", onCancel);
    capturePointer(captureTarget, pointerId);
  }

  function installResizeZones() {
    if (document.getElementById("nm-resize-n")) return;
    ["n", "s", "w", "e", "nw", "ne", "sw", "se"].forEach(function (direction) {
      var zone = document.createElement("div");
      zone.id = "nm-resize-" + direction;
      zone.className = "nm-resize";
      zone.dataset.dir = direction;
      zone.title = "调整窗口大小";
      zone.addEventListener("pointerdown", startResize);
      document.body.appendChild(zone);
    });
  }

  function installBar() {
    if (!document.body) return;
    installStyle();
    installResizeZones();
    if (document.getElementById(BAR_ID)) {
      sampleTheme();
      return;
    }

    var bar = document.createElement("div");
    bar.id = BAR_ID;
    bar.setAttribute("role", "banner");

    var drag = document.createElement("div");
    drag.className = "nm-drag";
    drag.title = "拖动窗口 · 双击最大化";
    var logo = document.createElement("img");
    logo.className = "nm-logo";
    logo.alt = "";
    logo.draggable = false;
    logo.src = ICON;
    var title = document.createElement("span");
    title.className = "nm-title";
    title.textContent = "网易云音乐";
    drag.appendChild(logo);
    drag.appendChild(title);

    var lastPointerDown = 0;
    drag.addEventListener("pointerdown", function (event) {
      if (event.button !== 0) return;
      var now = Date.now();
      if (now - lastPointerDown < DOUBLE_CLICK_MS) {
        lastPointerDown = 0;
        event.preventDefault();
        event.stopPropagation();
        toggleMaximize();
        return;
      }
      lastPointerDown = now;
      startMove(event);
    });

    var actions = document.createElement("div");
    actions.className = "nm-actions";
    actions.appendChild(windowButton("minimize", "最小化", MINIMIZE_PATH));
    actions.appendChild(windowButton("toggle_maximize", "最大化", MAXIMIZE_PATH));
    actions.appendChild(windowButton("close", "隐藏到托盘", CLOSE_PATH, "close"));

    bar.appendChild(drag);
    bar.appendChild(actions);
    document.body.appendChild(bar);

    sampleTheme();
    refreshWindowState();
    setInterval(sampleTheme, 1000);
    setInterval(refreshWindowState, 15000);
    watchThemeChanges();
  }

  function watchThemeChanges() {
    if (typeof MutationObserver !== "function") return;
    var observer = new MutationObserver(function () { sampleTheme(); });
    if (document.body) {
      observer.observe(document.body, { attributes: true, attributeFilter: ["class", "style"] });
    }
    if (document.documentElement) {
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] });
    }
    var app = document.querySelector("#root > div:first-child");
    if (app) {
      observer.observe(app, { attributes: true, attributeFilter: ["class", "style"] });
    }
    window.__nmShellThemeObserver = observer;
    window.addEventListener("popstate", sampleTheme);
    window.addEventListener("hashchange", sampleTheme);
  }

  function isRendered(element) {
    if (!element) return false;
    var rect = element.getBoundingClientRect();
    var style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 &&
      style.visibility !== "hidden" && style.display !== "none";
  }

  function footer() {
    // The page keeps a hidden vinyl-mode copy of the player bar with duplicate
    // ids. Anchor on the visible play button so the visible footer wins.
    var buttons = document.querySelectorAll("#btn_pc_minibar_play");
    for (var i = 0; i < buttons.length; i += 1) {
      if (!isRendered(buttons[i])) continue;
      var owner = buttons[i].closest("footer") || buttons[i].closest("#page_pc_mini_bar");
      if (owner) return owner;
    }
    var minis = document.querySelectorAll("#page_pc_mini_bar");
    for (var j = 0; j < minis.length; j += 1) {
      if (!isRendered(minis[j])) continue;
      return minis[j].closest("footer") || minis[j];
    }
    return document.querySelector("footer.Container_col456s") || document.querySelector("footer");
  }

  function reactProps(element) {
    if (!element) return null;
    var keys = Object.keys(element).filter(function (key) {
      return key.indexOf("__reactInternalInstance$") === 0 || key.indexOf("__reactFiber$") === 0;
    });
    var node = keys.length ? element[keys[0]] : null;
    for (var depth = 0; node && depth < 14; depth += 1, node = node.return) {
      var props = node.memoizedProps;
      if (props && typeof props === "object" && ("resourceName" in props || "curPlaying" in props)) {
        return props;
      }
    }
    return null;
  }

  function httpUrl(value) {
    var text = clean(value);
    return /^https?:\/\//i.test(text) ? text : "";
  }

  function playerState() {
    var bar = footer();
    if (!bar) return null;
    var mini = bar.matches("#page_pc_mini_bar") ? bar : bar.querySelector("#page_pc_mini_bar");
    var props = reactProps(mini || bar);
    var titleBox = bar.querySelector('[class*="songPlayInfo"] .title') || bar.querySelector(".title");
    var titleText = "";
    var artistText = "";
    if (titleBox) {
      var spans = titleBox.querySelectorAll(":scope > span");
      if (spans.length) titleText = clean(spans[0].innerText);
      if (spans.length >= 3) artistText = clean(spans[2].innerText);
      if (!artistText) {
        var author = bar.querySelector(".author");
        artistText = author ? clean(author.innerText) : "";
      }
    }

    var title = titleText || (props && props.resourceName ? clean(props.resourceName) : "");
    var artists = [];
    if (props && Array.isArray(props.resourceArtists)) {
      artists = props.resourceArtists.map(function (artist) {
        return clean(artist && artist.name);
      }).filter(Boolean);
    }
    if (!artists.length && artistText) {
      artists = artistText.split(/\s*\/\s*/).filter(Boolean);
    }

    var songId = null;
    if (props) {
      songId = props.onlineResourceId ||
        (props.curPlaying && (props.curPlaying.trackId || props.curPlaying.resourceId)) || null;
    }
    songId = songId == null ? null : String(songId).replace(/\D/g, "");
    if (!songId) songId = null;

    var duration = props && Number(props.resourceDuration) || 0;
    if (!isFinite(duration) || duration < 0) duration = 0;

    var slider = bar.querySelector('[class*="StyledSliderContainer"]');
    var percent = null;
    if (slider && slider.style) {
      percent = parsePercent(
        slider.style.getPropertyValue("--track-precent") ||
        slider.style.getPropertyValue("--track-percent")
      );
    }
    var clockNodes = bar.querySelectorAll('[class*="miniBarTimeTextStyle"]');
    var current = clockNodes.length ? parseClock(clockNodes[0].innerText) : null;
    var total = clockNodes.length > 1 ? parseClock(clockNodes[1].innerText) : null;
    if (!duration && total) duration = total;
    var position = percent !== null && duration > 0 ? (percent / 100) * duration : (current || 0);

    var playIcon = bar.querySelector('#btn_pc_minibar_play [role="img"]');
    var playing = false;
    if (playIcon) {
      var label = playIcon.getAttribute("aria-label") || "";
      playing = label === "pause" || playIcon.classList.contains("cmd-icon-pause");
    }

    var cover = "";
    var image = bar.querySelector(".miniVinylWrapper img") || bar.querySelector("img");
    if (image) cover = httpUrl(image.currentSrc || image.src);
    var album = "";
    if (props && props.curPlaying && props.curPlaying.track && props.curPlaying.track.album) {
      album = clean(props.curPlaying.track.album.name);
    }

    if (!title && !songId) return null;
    return {
      title: title,
      artists: artists,
      album: album,
      song_id: songId,
      duration: duration,
      position: position,
      playing: playing,
      cover: cover
    };
  }

  function playerAction(name) {
    var bar = footer();
    if (!bar) return false;
    if (name === "prev" || name === "next") {
      var button = bar.querySelector('[aria-label="' + (name === "prev" ? "pre" : "next") + '"]');
      if (button) {
        (button.closest("button") || button).click();
        setTimeout(function () { reportPlayerState(true); }, 260);
        return true;
      }
      return false;
    }
    if (name === "toggle" || name === "play_pause") {
      var play = bar.querySelector("#btn_pc_minibar_play") ||
        document.getElementById("btn_pc_minibar_play");
      if (play) {
        play.click();
        setTimeout(function () { reportPlayerState(true); }, 260);
        return true;
      }
    }
    return false;
  }

  window.__nmPlayer = { action: playerAction, state: playerState };

  var lastPlayerKey = "";
  var lastPlayerSent = 0;
  function reportPlayerState(force) {
    var state = playerState();
    if (!state) return;
    var key = JSON.stringify([
      state.title,
      state.artists,
      state.song_id,
      state.playing,
      Math.round(state.duration)
    ]);
    var now = Date.now();
    if (!force && key === lastPlayerKey) {
      var interval = state.playing ? 1000 : 5000;
      if (now - lastPlayerSent < interval) return;
    }
    lastPlayerKey = key;
    lastPlayerSent = now;
    safeCall("update_player_state", [state]).catch(function (error) {
      logError("同步播放状态失败：" + (error && error.message ? error.message : error));
    });
  }

  var playerTimer = setInterval(function () { reportPlayerState(false); }, 1000);
  window.__nmShellTimer = playerTimer;
  window.addEventListener("pywebviewready", function () {
    reportPlayerState(true);
    refreshWindowState();
  }, { once: true });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      installBar();
      reportPlayerState(true);
    }, { once: true });
  } else {
    installBar();
    reportPlayerState(true);
  }
})();
