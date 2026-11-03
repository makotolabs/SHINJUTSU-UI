// Headless graph exporter for SHINJUTSU UI
// Runs buildComfyWorkflow() in a lightweight VM context and outputs the UI graph JSON.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const root = process.argv[2] || process.cwd();
const modelPickerValue = process.argv[3] || '';
const requestedModes = (process.argv[4] || 'shinjutsu,cinema,video,soul,images,audio').split(',');

function el(id) {
  const store = { value: '', textContent: '', innerHTML: '', style: {}, dataset: {}, options: [], children: [] };
  return new Proxy(store, {
    get(t, k) {
      if (k === 'value') {
        if (id === 'model-picker') return modelPickerValue;
        if (id === 'prompt-input') return 'SHINJUTSU smoke test prompt';
        if (id === 'comfy-url') return 'http://127.0.0.1:8188';
        return t.value;
      }
      if (k === 'classList') return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
      if (k in t) return t[k];
      if (k === 'querySelectorAll') return () => [];
      if (k === 'querySelector') return () => el('q');
      if (k === 'getAttribute') return () => null;
      if (typeof k === 'string' && /^(add|remove|append|set|focus|click|scroll|insert|replace|dispatch)/.test(k)) return () => {};
      return undefined;
    },
    set(t, k, v) { t[k] = v; return true; }
  });
}

const document = {
  getElementById: (id) => el(id),
  querySelectorAll: () => [],
  querySelector: () => el('q'),
  createElement: () => el('new'),
  addEventListener() {},
  body: el('body'),
  documentElement: el('html'),
};
const ctx = {
  document, console,
  window: {}, navigator: { clipboard: {} },
  localStorage: { getItem: () => null, setItem() {} },
  fetch: async () => ({ ok: false, json: async () => ({}) }),
  setInterval: () => 0, clearInterval() {}, setTimeout: () => 0, clearTimeout() {},
  requestAnimationFrame() {}, WebSocket: function () {}, URL: { createObjectURL: () => '' },
  Blob: function () {}, FileReader: function () {}, Image: function () {}, alert() {},
  location: { origin: 'http://127.0.0.1:8188', pathname: '/shinjutsu' },
};
ctx.window = ctx;
vm.createContext(ctx);
for (const f of ['web/js/models_and_compiler.js', 'web/js/app.js']) {
  const filePath = path.join(root, f);
  if (fs.existsSync(filePath)) {
    const src = fs.readFileSync(filePath, 'utf8');
    vm.runInContext(src, ctx, { filename: f });
  }
}

const out = {};
for (const mode of requestedModes) {
  vm.runInContext(`currentMode = ${JSON.stringify(mode)}; activeExternalWorkflow = null;`, ctx);
  try {
    out[mode] = vm.runInContext('buildComfyWorkflow()', ctx);
  } catch (e) {
    out[mode] = { __error__: String(e && e.stack || e) };
  }
}
process.stdout.write(JSON.stringify(out, null, 2));
