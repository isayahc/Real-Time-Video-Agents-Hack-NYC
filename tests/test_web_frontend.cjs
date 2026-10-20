/* Execute the shipped UI script with browser APIs stubbed at their boundaries. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../protocol_pipeline/web_static/app.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '../protocol_pipeline/web_static/index.html'), 'utf8');
const preset = 'Qwen/Qwen2.5-VL-72B-Instruct';

async function boot(storage = new Map(), blocked = false, beforeConfig = null) {
 const nodes = new Map();
 const node = id => {
  if (!nodes.has(id)) nodes.set(id, {value: '', files: [], handlers: {},
   addEventListener(type, fn) { this.handlers[type] = fn; },
   replaceChildren() {}, add() {}, classList: {remove() {}, toggle() {}}});
  return nodes.get(id);
 };
 node('vision-model').value = html.match(/id="vision-model"[^>]*value="([^"]+)"/)[1];
 node('frame-count').value = '8';
 const requests = [];
 const context = {document: {getElementById: node, querySelectorAll: () => []},
  localStorage: {
   getItem(key) { if (blocked) throw Error('blocked'); return storage.get(key); },
   setItem(key, value) { if (blocked) throw Error('blocked'); storage.set(key, value); },
   removeItem(key) { if (blocked) throw Error('blocked'); storage.delete(key); }},
  location: {hash: ''}, URL: {createObjectURL: () => 'blob:test', revokeObjectURL() {}},
  URLSearchParams, Option: function() {}, setTimeout, clearTimeout,
  fetch: async (url, options) => {
   if (url === '/api/config') {
    if (beforeConfig) beforeConfig(node);
    return {ok: true, json: async () => ({model: 'compiler/default', vision_model: preset, ffmpeg_available: true, credentials_available: true})};
   }
   if (url === '/api/runs') return {ok: true, json: async () => []};
   requests.push({url, options});
   return {ok: false, json: async () => ({detail: 'Upload captured'})};
  }};
 vm.runInNewContext(source, context);
 await new Promise(resolve => setImmediate(resolve));
 return {node, requests, async submit() {
  node('file').files = [{name: 'test.mp4', size: 10}];
  node('file').handlers.change();
  await node('run-form').handlers.submit({preventDefault() {}});
  return new URLSearchParams(requests.at(-1).url.split('?')[1]);
 }};
}

test('fresh form sends the Nebius vision preset without editing', async () => {
 const app = await boot();
 assert.equal(app.node('vision-model').value, preset);
 assert.equal((await app.submit()).get('vision_model'), preset);
});

test('override survives file selection, reload and saved-run selection', async () => {
 const storage = new Map();
 let app = await boot(storage);
 app.node('vision-model').value = 'custom/vision';
 app.node('vision-model').handlers.input();
 assert.equal((await app.submit()).get('vision_model'), 'custom/vision');
 app = await boot(storage);
 assert.equal(app.node('vision-model').value, 'custom/vision');
 app.node('history').value = 'a'.repeat(32);
 app.node('history').handlers.change();
 await new Promise(resolve => setImmediate(resolve));
 assert.equal(app.node('vision-model').value, 'custom/vision');
 assert.equal((await app.submit()).get('vision_model'), 'custom/vision');
});

test('blocked storage still supports preset and edited model', async () => {
 const app = await boot(new Map(), true);
 assert.equal((await app.submit()).get('vision_model'), preset);
 app.node('vision-model').value = 'private/vision';
 app.node('vision-model').handlers.input();
 assert.equal((await app.submit()).get('vision_model'), 'private/vision');
});

test('late config does not overwrite user input', async () => {
 const app = await boot(new Map(), true, node => {
  node('vision-model').value = 'early/edit';
  node('vision-model').handlers.input();
 });
 assert.equal((await app.submit()).get('vision_model'), 'early/edit');
});
