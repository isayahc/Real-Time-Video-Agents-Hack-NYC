// SPDX-License-Identifier: MPL-2.0
/** Verify the shared robot mesh/frames through native OI import and portable scene APIs. */
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

async function main(): Promise<void> {
  const root = resolve(process.argv[2]), bundle = resolve(process.argv[3]);
  const {importForm} = await import(pathToFileURL(resolve(root, 'src/lib/form.ts')).href);
  const {makeManifest, readManifest, hydrateManifest} = await import(pathToFileURL(resolve(root, 'src/lib/workspace.ts')).href);
  const raw = await readFile(resolve(bundle, 'robot.forma.json'));
  const contract = await readFile(resolve(bundle, 'robot-contract.json'));
  const document = JSON.parse(raw.toString('utf8'));
  const contractHash = createHash('sha256').update(contract).digest('hex');
  if (document.robot_contract_sha256 !== contractHash) throw new Error('Robot contract hash mismatch');
  const asset = importForm(document, 'robot.forma.json', createHash('sha256').update(raw).digest('hex'));
  const meshes = document.project_ir.cad_model.meshes;
  if (asset.parts.length !== meshes.length) throw new Error('OI lost source mesh instances');
  // OI recenters assets. Place the shared asset back at its originOffset so the
  // source base frame and all attachment/TCP coordinates remain in world space.
  const item = {id: 'so101', name: document.title, asset, visible: true,
    position: [...asset.originOffset], rotation: [0, 0, 0]};
  const portable = makeManifest({room: [2, 2, 2], items: [item],
    animation: {duration: 1, loop: false, tracks: []}}, true);
  const reopened = hydrateManifest(readManifest(portable), []);
  if (reopened.items.length !== 1 || reopened.items[0].missing) throw new Error('OI roundtrip lost the robot');
  const restored = reopened.items[0];
  let maxError = 0, checkedVertices = 0;
  for (let index = 0; index < meshes.length; index++) {
    const source = meshes[index], part = restored.asset.parts[index];
    if (part.metadata.representation !== 'CAD mesh' || part.name !== source.name ||
        part.vertices.length !== source.vertices.length || JSON.stringify(part.indices) !== JSON.stringify(source.faces))
      throw new Error('OI roundtrip changed source mesh topology or identity');
    for (let offset = 0; offset < source.vertices.length; offset += 3) {
      const expected = [source.vertices[offset]/1000, source.vertices[offset+2]/1000, -source.vertices[offset+1]/1000];
      for (let axis = 0; axis < 3; axis++) {
        const actual = part.vertices[offset+axis] + restored.position[axis];
        maxError = Math.max(maxError, Math.abs(actual - expected[axis]));
      }
      checkedVertices++;
    }
  }
  if (maxError > 1e-9) throw new Error(`OI coordinate/centering drift: ${maxError} m`);
  const report = {status: 'native_oi_import_roundtrip_passed',
    oi_commit: execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim(),
    robot_contract_sha256: contractHash, mesh_instances: meshes.length, checked_vertices: checkedVertices,
    maximum_world_vertex_error_m: maxError, source_frame: 'URDF Z-up metres', oi_frame: 'Y-up metres: x,z,-y',
    imported_origin_offset_m: asset.originOffset, scene_item_position_m: restored.position,
    physical_attachment_validated: false, task_simulation_executed: false,
    limitations: ['Static pose import and frame alignment only; no dynamics, contacts or physical task execution.']};
  await writeFile(resolve(bundle, 'robot.oi.json'), JSON.stringify(portable), {flag: 'wx'});
  await writeFile(resolve(bundle, 'oi-report.json'), JSON.stringify(report, null, 2)+'\n', {flag: 'wx'});
  console.log(JSON.stringify(report));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
