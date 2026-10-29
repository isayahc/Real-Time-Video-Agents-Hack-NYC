// SPDX-License-Identifier: MPL-2.0
/** Import executed physics observations through native OI assets/timeline APIs. */
import {readFile, writeFile, readdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

async function main(): Promise<void> {
  const root = resolve(process.argv[2]), run = resolve(process.argv[3]);
  const commit = execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim();
  if (commit !== '9b34ec217563e2a6788d5e60d9cc74c0bcd21330') throw new Error('OI checkout differs from pinned adapter');
  execFileSync('git', ['diff', '--exit-code', 'HEAD', '--', 'src/lib', 'package-lock.json'], {cwd: root, stdio: 'pipe'});
  const {importForm} = await import(pathToFileURL(resolve(root, 'src/lib/form.ts')).href);
  const {makeManifest, readManifest, hydrateManifest, evaluateWorkspace} = await import(pathToFileURL(resolve(root, 'src/lib/workspace.ts')).href);
  const {Matrix4, Vector3, Euler} = await import(pathToFileURL(resolve(root, 'node_modules/three/build/three.module.js')).href);
  const basis = new Matrix4().set(1,0,0,0, 0,0,1,0, 0,-1,0,0, 0,0,0,1);
  const inverse = basis.clone().invert();
  const matrix = (rows: number[][]) => new Matrix4().set(...rows.flat());
  const documents: Record<string, any> = {}, assets: Record<string, any> = {};
  for (const file of (await readdir(resolve(run, 'assets'))).filter(f => f.endsWith('.forma.json')).sort()) {
    const name = file.replace('.forma.json', ''), raw = await readFile(resolve(run, 'assets', file));
    documents[name] = JSON.parse(raw.toString());
    assets[name] = importForm(documents[name], file, createHash('sha256').update(raw).digest('hex'));
  }
  const staticPoses = JSON.parse(await readFile(resolve(run, 'assets/static-poses.json'), 'utf8'));
  function pose(name: string, transform: number[][]): {position: number[]; rotation: number[]} {
    const converted = basis.clone().multiply(matrix(transform)).multiply(inverse);
    const position = new Vector3(...assets[name].originOffset).applyMatrix4(converted).toArray();
    const rotation = new Euler().setFromRotationMatrix(converted, 'XYZ').toArray().slice(0, 3).map((v: number) => v * 180 / Math.PI);
    return {position, rotation};
  }
  const summary = JSON.parse(await readFile(resolve(run, 'summary.json'), 'utf8'));
  const reports = [];
  for (const result of summary.results) {
    const directory = resolve(run, result.case), raw = await readFile(resolve(directory, 'frames.json'));
    const frames = JSON.parse(raw.toString());
    const names = Object.keys(assets);
    const items = names.map(name => ({id: name, name, asset: assets[name], visible: true,
      ...pose(name, staticPoses[name] ?? frames[0].poses[name])}));
    const tracks = names.filter(name => !staticPoses[name]).map(name => ({id: `${name}:instance`, instanceId: name,
      keys: frames.map((f: any, i: number) => ({id: `${name}-${i}`, time: f.time_s, ...pose(name, f.poses[name])}))}));
    const portable = makeManifest({room: [2,2,2], items, animation: {duration: frames.at(-1).time_s, loop: false, tracks}}, true);
    const reopened = hydrateManifest(readManifest(portable), []);
    if (reopened.items.some((i: any) => i.missing) || reopened.items.length !== names.length) throw new Error('OI roundtrip lost geometry');
    let checkedVertices = 0, maximum = 0;
    for (const item of reopened.items) {
      const source = documents[item.id].project_ir.cad_model.meshes[0], part = item.asset.parts[0];
      if (item.asset.parts.length !== 1 || part.metadata.representation !== 'CAD mesh' ||
          part.vertices.length !== source.vertices.length || JSON.stringify(part.indices) !== JSON.stringify(source.faces))
        throw new Error('OI mesh topology changed');
    }
    // Validate every recorded timestamp, including rotated links, and spread
    // vertex samples across each actual CAD mesh after native scene roundtrip.
    for (const f of frames) {
      const evaluated = evaluateWorkspace(reopened.items, reopened.animation, f.time_s);
      for (let index = 0; index < reopened.items.length; index++) {
        const item = reopened.items[index], value = evaluated[index];
        const source = documents[item.id].project_ir.cad_model.meshes[0], part = item.asset.parts[0];
        const actual = new Matrix4().makeRotationFromEuler(new Euler(...value.rotation.map((v: number) => v * Math.PI / 180), 'XYZ'));
        actual.setPosition(...value.position);
        const expected = basis.clone().multiply(matrix(staticPoses[item.id] ?? f.poses[item.id]));
        const vertexCount = source.vertices.length / 3;
        for (const vertex of [0, Math.floor(vertexCount/3), Math.floor(2*vertexCount/3), vertexCount-1]) {
          const offset = vertex * 3;
          const a = new Vector3(...part.vertices.slice(offset, offset+3)).applyMatrix4(actual);
          const b = new Vector3(...source.vertices.slice(offset, offset+3).map((v: number) => v / 1000)).applyMatrix4(expected);
          maximum = Math.max(maximum, a.distanceTo(b)); checkedVertices++;
        }
      }
    }
    // OI serializes XYZ Euler angles; Three.js near-gimbal-lock conversion
    // approximates angles. Bound the resulting mesh drift to 0.01 mm.
    if (maximum > 1e-5) throw new Error(`OI frame conversion drift: ${maximum} m`);
    const replay = JSON.stringify(portable);
    await writeFile(resolve(directory, 'replay.oi.json'), replay, {flag: 'wx'});
    reports.push({case: result.case, replay_sha256: createHash('sha256').update(replay).digest('hex'), executed_frames_sha256: createHash('sha256').update(raw).digest('hex'),
      frame_count: frames.length, item_count: items.length, key_count: tracks.reduce((n: number, t: any) => n+t.keys.length, 0),
      checked_vertices: checkedVertices, maximum_world_vertex_error_m: maximum});
  }
  const report = {bridge_sha256: createHash('sha256').update(await readFile(process.argv[1])).digest('hex'), status: 'native_oi_executed_replay_verified', oi_commit: commit, reports,
    outcome_source: 'PyBullet state evaluator; OI timeline is replay only',
    source_frame: 'Z-up metres', oi_frame: 'Y-up metres [x,z,-y]', oi_euler_units: 'XYZ degrees', maximum_allowed_vertex_error_m: 1e-5,
    rotation_limit: 'Native XYZ Euler near-gimbal-lock conversion can introduce micrometre-scale drift',
    physical_execution: false, live_provider_execution: false};
  await writeFile(resolve(run, 'oi-report.json'), JSON.stringify(report, null, 2)+'\n', {flag: 'wx'});
  console.log(JSON.stringify(report));
}
main().catch(error => {console.error(error); process.exitCode = 1;});
