(function () {
  "use strict";

  var ICON = "__NM_ICON_DATA_URI__";
  var STYLE_ID = "nm-shell-style";
  var BAR_ID = "nm-shell-bar";
  var BAR_HEIGHT = 38;
  var WINDOW_RADIUS = 12;
  var ROUNDED_WINDOW = "__NM_ROUNDED_WINDOW__" === "true";
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

  var DARK_FG = { r: 24, g: 32, b: 49, a: 1 };
  var LIGHT_FG = { r: 245, g: 247, b: 250, a: 1 };
  var BLACK_FG = { r: 0, g: 0, b: 0, a: 1 };
  var WHITE_FG = { r: 255, g: 255, b: 255, a: 1 };

  function rgba(color, alpha) {
    return "rgba(" + Math.round(color.r) + ", " + Math.round(color.g) + ", " +
      Math.round(color.b) + ", " + Math.max(0, Math.min(1, alpha)).toFixed(4) + ")";
  }

  function mixColor(first, second, amount) {
    var t = Math.max(0, Math.min(1, amount));
    return {
      r: first.r + (second.r - first.r) * t,
      g: first.g + (second.g - first.g) * t,
      b: first.b + (second.b - first.b) * t,
      a: 1
    };
  }

  function averageColor(colors) {
    var total = 0;
    var r = 0;
    var g = 0;
    var b = 0;
    colors.forEach(function (color) {
      if (!color) return;
      total += 1;
      r += color.r;
      g += color.g;
      b += color.b;
    });
    if (!total) return null;
    return { r: r / total, g: g / total, b: b / total, a: 1 };
  }

  function toLinear(value) {
    var scaled = value / 255;
    return scaled <= 0.04045 ? scaled / 12.92 : Math.pow((scaled + 0.055) / 1.055, 2.4);
  }

  function lab(color) {
    var r = toLinear(color.r);
    var g = toLinear(color.g);
    var b = toLinear(color.b);
    var x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047;
    var y = r * 0.2126 + g * 0.7152 + b * 0.0722;
    var z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883;
    function pivot(value) {
      return value > 0.008856 ? Math.cbrt(value) : 7.787 * value + 16 / 116;
    }
    var fx = pivot(x);
    var fy = pivot(y);
    var fz = pivot(z);
    return { L: 116 * fy - 16, a: 500 * (fx - fy), b: 200 * (fy - fz) };
  }

  function deltaE(first, second) {
    if (!first || !second) return 60;
    var a = lab(first);
    var b = lab(second);
    return Math.sqrt(
      Math.pow(a.L - b.L, 2) + Math.pow(a.a - b.a, 2) + Math.pow(a.b - b.b, 2)
    );
  }

  function bestForegroundFor(backgrounds) {
    function pick(candidates) {
      var best = candidates[0];
      var bestScore = -1;
      candidates.forEach(function (candidate) {
        var score = Infinity;
        backgrounds.forEach(function (background) {
          if (background) score = Math.min(score, contrastRatio(candidate, background));
        });
        if (!isFinite(score)) score = 0;
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      });
      return { color: best, score: bestScore };
    }
    var standard = pick([DARK_FG, LIGHT_FG]);
    return standard.score >= 4.6 ? standard.color : pick([BLACK_FG, WHITE_FG]).color;
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
    var bodyColor = pageBaseColor ||
      parseColor(getComputedStyle(document.body).backgroundColor) ||
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

  var THEME_FRACTIONS = [0, 0.02, 0.05, 0.09, 0.13, 0.15, 0.18, 0.24, 0.32, 0.45, 0.6, 0.75, 0.9, 1];
  var THEME_MIN_MS = 360;
  var THEME_MAX_MS = 640;
  var THEME_SKIP_DELTA_E = 1;
  var THEME_SAMPLE_GAP_MS = 500;
  var THEME_MAX_STOPS = 24;
  var BOTTOM_CACHE_MS = 2000;
  var themeState = { current: null, from: null, to: null, started: 0, duration: 0, frame: 0 };
  var bottomThemeCache = { time: 0, color: null };
  var themeSampleTimer = 0;
  var lastThemeSampleAt = 0;
  var shellFrame = null;
  var pageBaseColor = null;

  function prefersReducedMotion() {
    try {
      return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (error) {
      return false;
    }
  }

  function colorAtPercent(stops, percent) {
    if (!stops || !stops.length) return { r: 247, g: 249, b: 252, a: 1 };
    if (percent <= stops[0].percent) return stops[0].color;
    for (var i = 1; i < stops.length; i += 1) {
      var previous = stops[i - 1];
      var next = stops[i];
      if (percent <= next.percent) {
        var span = next.percent - previous.percent;
        var amount = span > 0 ? (percent - previous.percent) / span : 0;
        return mixColor(previous.color, next.color, amount);
      }
    }
    return stops[stops.length - 1].color;
  }

  function sampleTop() {
    var width = Math.max(1, window.innerWidth);
    var y = Math.max(0, Math.min(window.innerHeight - 1, BAR_HEIGHT + 2));
    var samples = THEME_FRACTIONS.map(function (fraction) {
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
    return samples;
  }

  function sampleBottom() {
    var now = Date.now();
    if (now - bottomThemeCache.time < BOTTOM_CACHE_MS) return bottomThemeCache.color;
    var color = null;
    var bar = footer();
    if (bar) {
      var rect = bar.getBoundingClientRect();
      if (rect.width > 8 && rect.height > 8 && rect.height < window.innerHeight * 0.6 &&
          rect.bottom > BAR_HEIGHT + 4 && rect.top < window.innerHeight - 4) {
        var y = Math.max(
          BAR_HEIGHT + 4,
          Math.min(window.innerHeight - 5, rect.top + rect.height * 0.5)
        );
        var width = Math.max(1, window.innerWidth);
        var fractions = [0.03, 0.2, 0.5, 0.8, 0.97];
        color = averageColor(fractions.map(function (fraction) {
          var x = Math.max(0, Math.min(width - 1, Math.round(fraction * (width - 1))));
          return colorAt(x, y);
        }));
      }
    }
    bottomThemeCache = { time: now, color: color };
    return color;
  }

  function tintAlpha(top, bottom) {
    if (!top || !bottom) return 0;
    if (deltaE(top, bottom) <= 5) return 0.7;
    var low = 0;
    var high = 0.7;
    for (var i = 0; i < 28; i += 1) {
      var middle = (low + high) / 2;
      if (deltaE(mixColor(top, bottom, middle), top) <= 5) low = middle;
      else high = middle;
    }
    return low;
  }

  function themeModel() {
    var top = sampleTop();
    var mean = averageColor(top.map(function (sample) { return sample.color; })) ||
      { r: 247, g: 249, b: 252, a: 1 };
    var bottom = sampleBottom();
    var alpha = tintAlpha(mean, bottom);
    return {
      top: top,
      mean: mean,
      tint: alpha > 0.001 ? { color: bottom, alpha: alpha } : null
    };
  }

  function backgroundFor(model) {
    var stops = model.top.map(function (sample) {
      return rgb(sample.color) + " " + sample.percent.toFixed(2) + "%";
    }).join(", ");
    var base = "linear-gradient(90deg, " + stops + ")";
    if (!model.tint) return base;
    var color = model.tint.color;
    var alpha = model.tint.alpha;
    return "linear-gradient(180deg, " + rgba(color, alpha) + " 0%, " +
      rgba(color, alpha * 0.82) + " 52%, " + rgba(color, 0) + " 100%), " + base;
  }

  function tintAt(model, fraction) {
    if (!model.tint) return null;
    var amount = Math.max(0, Math.min(1, fraction));
    var alpha = amount <= 0.52
      ? model.tint.alpha * (1 - 0.18 * (amount / 0.52))
      : model.tint.alpha * 0.82 * (1 - (amount - 0.52) / 0.48);
    return alpha > 0.001 ? { color: model.tint.color, alpha: alpha } : null;
  }

  function modelColorAt(model, percent, verticalFraction) {
    var base = colorAtPercent(model.top, percent);
    var tint = tintAt(model, verticalFraction);
    return tint ? mixColor(base, tint.color, tint.alpha) : base;
  }

  function setStyleIfChanged(bar, name, value) {
    if (bar.style.getPropertyValue(name) !== value) bar.style.setProperty(name, value);
  }

  function applyForeground(model, bar) {
    var width = Math.max(1, window.innerWidth);
    var titlePercent = width > 1 ? (Math.min(width - 1, 80) / (width - 1)) * 100 : 0;
    var controlPercent = width > 1 ? (Math.max(0, width - 66) / (width - 1)) * 100 : 100;
    var titleBackgrounds = [
      modelColorAt(model, titlePercent, 0),
      modelColorAt(model, titlePercent, 0.5)
    ];
    var controlBackgrounds = [
      modelColorAt(model, controlPercent, 0),
      modelColorAt(model, controlPercent, 0.5)
    ];
    var titleForeground = bestForegroundFor(titleBackgrounds);
    var controlForeground = bestForegroundFor(controlBackgrounds);
    var controlColor = modelColorAt(model, controlPercent, 0.5);
    var controlLum = luminance(controlColor);
    setStyleIfChanged(bar, "--nm-bar-fg", rgb(titleForeground));
    setStyleIfChanged(bar, "--nm-title-fg", rgb(titleForeground));
    setStyleIfChanged(bar, "--nm-control-fg", rgb(controlForeground));
    setStyleIfChanged(bar, "--nm-accent", controlLum > 0.52 ? "#ec4141" : "#ff6b6b");
    setStyleIfChanged(bar, "--nm-accent-fg", controlLum > 0.52 ? "#ffffff" : "#1a1011");
    if (shellFrame) {
      shellFrame.style.boxShadow = titleForeground === LIGHT_FG || titleForeground === WHITE_FG
        ? "inset 0 0 0 1px rgba(255, 255, 255, .12)"
        : "inset 0 0 0 1px rgba(0, 0, 0, .08)";
    }
  }

  function applyTheme(model) {
    var bar = document.getElementById(BAR_ID);
    if (!bar || !model) return;
    bar.style.setProperty("--nm-bar-bg", backgroundFor(model));
    applyForeground(model, bar);
  }

  function interpolateStops(first, second, amount) {
    if (!first || !second) return first || second || [];
    var seen = {};
    var percents = [];
    first.concat(second).forEach(function (stop) {
      var key = stop.percent.toFixed(2);
      if (seen[key]) return;
      seen[key] = true;
      percents.push(Number(key));
    });
    percents.sort(function (a, b) { return a - b; });
    if (percents.length > THEME_MAX_STOPS) {
      percents = [];
      for (var i = 0; i < THEME_MAX_STOPS; i += 1) {
        percents.push((i / (THEME_MAX_STOPS - 1)) * 100);
      }
    }
    return percents.map(function (percent) {
      return {
        percent: percent,
        color: mixColor(colorAtPercent(first, percent), colorAtPercent(second, percent), amount)
      };
    });
  }

  function interpolateTint(first, second, amount) {
    var from = first || { color: second ? second.color : { r: 0, g: 0, b: 0, a: 1 }, alpha: 0 };
    var to = second || { color: from.color, alpha: 0 };
    var alpha = from.alpha + (to.alpha - from.alpha) * amount;
    if (alpha <= 0.001) return null;
    return { color: mixColor(from.color, to.color, amount), alpha: alpha };
  }

  function interpolateModel(first, second, amount) {
    return {
      top: interpolateStops(first.top, second.top, amount),
      mean: mixColor(first.mean, second.mean, amount),
      tint: interpolateTint(first.tint, second.tint, amount)
    };
  }

  function themeDistance(first, second) {
    var distance = deltaE(first.mean, second.mean);
    var firstTint = first.tint || { color: first.mean, alpha: 0 };
    var secondTint = second.tint || { color: second.mean, alpha: 0 };
    var tintDistance = deltaE(firstTint.color, secondTint.color) *
      Math.max(firstTint.alpha, secondTint.alpha);
    return Math.max(distance, tintDistance);
  }

  function stepTheme(now) {
    var elapsed = themeState.duration > 1
      ? (now - themeState.started) / themeState.duration
      : 1;
    var amount = Math.max(0, Math.min(1, elapsed));
    var eased = amount * amount * (3 - 2 * amount);
    var model = interpolateModel(themeState.from, themeState.to, eased);
    themeState.current = model;
    applyTheme(model);
    if (amount < 1) {
      themeState.frame = requestAnimationFrame(stepTheme);
      return;
    }
    themeState.frame = 0;
    themeState.current = themeState.to;
    applyTheme(themeState.to);
  }

  function startTheme(next, immediate) {
    if (!themeState.current) {
      themeState.current = next;
      applyTheme(next);
      return;
    }
    var distance = themeDistance(themeState.current, next);
    if (distance < THEME_SKIP_DELTA_E && !immediate) return;
    if (immediate || document.hidden || prefersReducedMotion()) {
      if (themeState.frame) cancelAnimationFrame(themeState.frame);
      themeState.frame = 0;
      themeState.current = next;
      applyTheme(next);
      return;
    }
    var duration = Math.max(THEME_MIN_MS, Math.min(THEME_MAX_MS, THEME_MIN_MS + 8 * distance));
    themeState.from = themeState.current;
    themeState.to = next;
    themeState.started = performance.now();
    themeState.duration = duration;
    if (!themeState.frame) themeState.frame = requestAnimationFrame(stepTheme);
  }

  function sampleTheme(immediate) {
    var bar = document.getElementById(BAR_ID);
    if (!bar) return;
    lastThemeSampleAt = Date.now();
    if (document.hidden && !immediate) return;
    try {
      startTheme(themeModel(), !!immediate);
    } catch (error) {
      logError("主题采样失败：" + (error && error.message ? error.message : error));
    } finally {
      if (bar.getAttribute("data-nm-theme-ready") !== "1") {
        bar.setAttribute("data-nm-theme-ready", "1");
      }
    }
  }

  function scheduleThemeSample() {
    if (themeSampleTimer) return;
    var wait = Math.max(0, THEME_SAMPLE_GAP_MS - (Date.now() - lastThemeSampleAt));
    themeSampleTimer = setTimeout(function () {
      themeSampleTimer = 0;
      sampleTheme();
    }, wait);
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
      "  visibility: hidden;",
      "}",
      "#nm-shell-bar[data-nm-theme-ready='1'] { visibility: visible; }",
      "html.nm-window-rounded { clip-path: inset(0 round " + WINDOW_RADIUS + "px); }",
      "html.nm-window-maximized { clip-path: none; }",
      "html.nm-window-rounded, html.nm-window-rounded body {",
      "  background-color: transparent !important;",
      "  background-image: none !important;",
      "}",
      "#nm-shell-backdrop {",
      "  position: fixed; inset: 0; z-index: -2147483648; pointer-events: none;",
      "}",
      "#nm-shell-frame {",
      "  position: fixed; inset: 0; z-index: 2147483647; pointer-events: none;",
      "  border-radius: " + WINDOW_RADIUS + "px;",
      "  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .08);",
      "}",
      "html.nm-window-maximized #nm-shell-frame { display: none; }",
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

  function applyWindowShape(maximized) {
    var root = document.documentElement;
    if (!root) return;
    if (!ROUNDED_WINDOW) {
      root.classList.remove("nm-window-rounded", "nm-window-maximized");
      return;
    }
    root.classList.toggle("nm-window-maximized", !!maximized);
    root.classList.toggle("nm-window-rounded", !maximized);
    if (shellFrame) shellFrame.style.display = maximized ? "none" : "block";
  }

  function updateMaximizeIcon(maximized) {
    maximizedState = !!maximized;
    applyWindowShape(maximizedState);
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

  function capturePageBase() {
    var backdrop = document.getElementById("nm-shell-backdrop");
    if (!document.body) return;
    var bodyStyle = getComputedStyle(document.body);
    var htmlStyle = getComputedStyle(document.documentElement);
    var base = layerColor(document.body) || layerColor(document.documentElement) ||
      { r: 247, g: 249, b: 252, a: 1 };
    pageBaseColor = { r: base.r, g: base.g, b: base.b, a: 1 };
    if (!backdrop) return;
    var image = bodyStyle.backgroundImage;
    if (!image || image === "none") image = htmlStyle.backgroundImage;
    var color = bodyStyle.backgroundColor;
    if (!color || color === "rgba(0, 0, 0, 0)") color = htmlStyle.backgroundColor;
    backdrop.style.backgroundImage = image && image !== "none" ? image : "none";
    backdrop.style.backgroundColor = color && color !== "rgba(0, 0, 0, 0)"
      ? color
      : rgb(pageBaseColor);
    backdrop.style.backgroundSize = bodyStyle.backgroundSize;
    backdrop.style.backgroundPosition = bodyStyle.backgroundPosition;
    backdrop.style.backgroundRepeat = bodyStyle.backgroundRepeat;
  }

  function installShellFrame() {
    if (!document.body || !ROUNDED_WINDOW) return;
    var backdrop = document.getElementById("nm-shell-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.id = "nm-shell-backdrop";
      backdrop.setAttribute("aria-hidden", "true");
      document.body.appendChild(backdrop);
    }
    capturePageBase();
    if (shellFrame) return;
    shellFrame = document.createElement("div");
    shellFrame.id = "nm-shell-frame";
    shellFrame.setAttribute("aria-hidden", "true");
    document.body.appendChild(shellFrame);
  }

  function installBar() {
    if (!document.body) return;
    installStyle();
    installResizeZones();
    installShellFrame();
    applyWindowShape(maximizedState);
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

    sampleTheme(true);
    refreshWindowState();
    if (ROUNDED_WINDOW) {
      safeCall("page_transparent").catch(function () {});
    }
    setInterval(scheduleThemeSample, 1000);
    setInterval(refreshWindowState, 15000);
    watchThemeChanges();
  }

  function watchThemeChanges() {
    if (typeof MutationObserver !== "function") return;
    var observer = new MutationObserver(scheduleThemeSample);
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
    window.addEventListener("popstate", scheduleThemeSample);
    window.addEventListener("hashchange", scheduleThemeSample);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) sampleTheme(true);
    });
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
