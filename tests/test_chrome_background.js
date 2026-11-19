// Run the production script with a hidden/loading DOM and deterministic timers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
const intervals = new Map();
const timeouts = new Map();
let nextID = 0;
let stateReads = 0;
const document = {
  hidden: true,
  readyState: 'loading',
  getElementById: () => null,
  querySelector: () => null,
  addEventListener: (name, callback) => { listeners[name] = callback; },
};
const window = {
  addEventListener: () => {},
  pywebview: { api: { window_state: () => { stateReads++; return null; } } },
};
vm.runInNewContext(fs.readFileSync('ui/chrome.js', 'utf8'), {
  document, window, console,
  setInterval: (callback, delay) => { intervals.set(++nextID, {callback, delay}); return nextID; },
  clearInterval: id => intervals.delete(id),
  setTimeout: (callback, delay) => { timeouts.set(++nextID, {callback, delay}); return nextID; },
  clearTimeout: id => timeouts.delete(id),
  cancelAnimationFrame: () => {},
});
assert.equal(intervals.size, 1, 'hidden startup retains only player reporting');
assert.equal(typeof listeners.visibilitychange, 'function', 'visibility lifecycle is installed');
document.hidden = false;
listeners.visibilitychange();
assert.equal(intervals.size, 3, 'visible page has player, theme and window timers');
assert.equal(stateReads, 1, 'restore synchronizes window state immediately');
listeners.visibilitychange();
assert.equal(intervals.size, 3, 'duplicate events do not leak timers');
document.hidden = true;
listeners.visibilitychange();
assert.equal(intervals.size, 1, 'hiding cancels visual timers but retains player reporting');
assert.ok(intervals.has(window.__nmShellTimer));
window.__nmShellRefreshWindowState();
assert.equal(stateReads, 1, 'hidden page does not poll window state');
assert.equal(timeouts.size, 0, 'hiding cancels pending visual work');
document.hidden = false;
listeners.visibilitychange();
assert.equal(intervals.size, 3);
assert.equal(stateReads, 2);
console.log('Background lifecycle passed');
