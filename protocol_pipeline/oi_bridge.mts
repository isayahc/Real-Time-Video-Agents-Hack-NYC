/** Native OpenIndustries import/portable export plus actual local stdio MCP room creation.
 * No LLM, cloud sign-in, geometry invention or room-file mutation is performed.
 */
import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

async function main(): Promise<void> {
  const root = resolve(process.argv[2]), output = resolve(process.argv[3]);
  const {importForm} = await import(pathToFileURL(resolve(root, 'src/lib/form.ts')).href);
  const {makeManifest, readManifest, hydrateManifest} = await import(pathToFileURL(resolve(root, 'src/lib/workspace.ts')).href);
  const job = JSON.parse(await readFile(resolve(output, 'build-input.json'), 'utf8'));
  const raw = await readFile(resolve(output, 'apparatus.forma.json'));
  const asset = importForm(JSON.parse(raw.toString()), 'apparatus.forma.json', createHash('sha256').update(raw).digest('hex'));
  const child = spawn(process.execPath, [resolve(root, 'server/astra-mcp.mjs')], {
    cwd: root, env: {...process.env, ASTRA_ROOT: root}, stdio: ['pipe', 'pipe', 'pipe'],
  });
  child.stderr.resume();
  const lines = createInterface({input: child.stdout});
  let sequence = 0;
  const pending = new Map<number, {resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>}>();
  const fail = (): void => {
    for (const waiter of pending.values()) {clearTimeout(waiter.timer); waiter.reject(new Error('MCP connection failed'));}
    pending.clear();
  };
  child.on('error', fail); child.on('exit', fail); child.stdin.on('error', fail);
  lines.on('line', line => {
    let message: any;
    try {message = JSON.parse(line);} catch {fail(); return;}
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id); clearTimeout(waiter.timer);
    if (message.error) waiter.reject(new Error('MCP protocol error')); else waiter.resolve(message.result);
  });
  const rpc = (method: string, params: unknown): Promise<any> => new Promise((resolveResult, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {pending.delete(id); reject(new Error('MCP timeout'));}, 15000);
    pending.set(id, {resolve: resolveResult, reject, timer});
    child.stdin.write(JSON.stringify({jsonrpc: '2.0', id, method, params}) + '\n');
  });
  const call = async (name: string, args: unknown): Promise<any> => {
    const result = await rpc('tools/call', {name, arguments: args});
    if (result.isError) throw new Error('MCP room tool failed');
    return result.structuredContent ?? JSON.parse(result.content.find((item: any) => item.type === 'text').text);
  };
  try {
    const initialized = await rpc('initialize', {protocolVersion: '2024-11-05', capabilities: {}, clientInfo: {name: 'mapped-protocol-pipeline', version: '0.1.0'}});
    if (!initialized.capabilities?.tools) throw new Error('MCP tools unavailable');
    child.stdin.write(JSON.stringify({jsonrpc: '2.0', method: 'notifications/initialized'}) + '\n');
    const discovered = await rpc('tools/list', {});
    for (const tool of ['astra.create_room', 'astra.read_room']) {
      if (!discovered.tools.some((item: any) => item.name === tool)) throw new Error('Required room tool missing');
    }
    const room = await call('astra.create_room', {name: job.scene.name, width: job.scene.room_m[0], depth: job.scene.room_m[1], height: job.scene.room_m[2]});
    const read = await call('astra.read_room', {id: room.id});
    if (read.document.id !== room.id) throw new Error('MCP room identity mismatch');
    const workspace = {room: read.document.room, items: [{id: 'apparatus', name: asset.name, asset,
      visible: true, position: job.scene.position_m, rotation: job.scene.rotation_deg}],
      animation: {duration: 3, loop: true, tracks: []}};
    const manifest = makeManifest(workspace, true);
    const reopened = hydrateManifest(readManifest(manifest), []);
    if (reopened.items.length !== 1 || reopened.items[0].missing) throw new Error('Portable scene roundtrip failed');
    if (reopened.items[0].asset.parts.length !== asset.parts.length) throw new Error('Imported geometry was not preserved');
    const report = {mode: 'local_native_import_and_mcp_room', room_id: room.id,
      mcp_room_is_empty_shell: true, portable_scene_has_apparatus: true,
      cloud_scene_created: false, instances: 1, parts: asset.parts.length,
      retained_bom_lines: asset.formProject?.ir?.bom?.length ?? 0,
      representation: [...new Set(asset.parts.map((part: any) => part.metadata?.representation))],
      warnings: asset.warnings ?? [], portable_roundtrip: true,
      placement_is_planning_assumption: true};
    await writeFile(resolve(output, 'apparatus.oi.json'), JSON.stringify(manifest), {flag: 'wx'});
    await writeFile(resolve(output, 'oi-result.json'), JSON.stringify(report, null, 2) + '\n', {flag: 'wx'});
  } finally {
    fail(); lines.close(); child.stdin.end(); child.kill();
  }
}
main().catch(() => {process.exitCode = 1;});
