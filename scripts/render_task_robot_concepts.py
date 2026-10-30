# SPDX-License-Identifier: MPL-2.0
"""Pre-render mesh-based SO-101/G1 task concepts; never claim physics execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import mujoco
import mujoco_menagerie as menagerie
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def digest(path: Path) -> str:
    """Hash exact retained source/render bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(output: Path, robot: str, task: str) -> dict:
    """Render authored inverse-kinematic poses with original robot meshes."""
    arm = robot == 'arm'
    entry = menagerie.get('robotstudio_so101' if arm else 'unitree_g1')
    source = entry.path()
    xml = ET.parse(source / ('so101.xml' if arm else 'g1.xml')).getroot()
    xml.find('compiler').set('meshdir', str(source / 'assets'))
    # Keyframes refer to the original model; use the neutral configuration here.
    for key in list(xml.findall('keyframe')):
        xml.remove(key)
    world = xml.find('worldbody')
    top = .72
    if arm:
        world.find("body[@name='base']").set('pos', f'0 0 {top}')
        target = np.array([.24, -.04, top + .06])
        tcp = xml.find(".//site[@name='gripperframe']")
        tcp.set('name', 'task_tcp')
    else:
        target = np.array([.36, -.20, top + .06])
        hand = xml.find(".//body[@name='right_wrist_yaw_link']")
        ET.SubElement(hand, 'site', name='task_tcp', pos='.105 0 0', size='.003', rgba='0 0 0 0')
    visual = xml.find('visual')
    if visual is None:
        visual = ET.SubElement(xml, 'visual')
    ET.SubElement(visual, 'global', offwidth='960', offheight='540')
    ET.SubElement(world, 'light', pos='0 -1 3', dir='0 0 -1', diffuse='.9 .9 .9')
    ET.SubElement(world, 'geom', type='plane', size='3 3 .1', rgba='.12 .17 .19 1')
    ET.SubElement(world, 'geom', type='box', pos=f'.30 0 {top-.035}', size='.40 .34 .035', rgba='.32 .38 .4 1')
    for x in (-.05, .62):
        for y in (-.27, .27):
            ET.SubElement(world, 'geom', type='box', pos=f'{x} {y} .34', size='.018 .018 .34', rgba='.16 .20 .22 1')
    # Workpiece is explicitly a scale/layout proxy, not the filmed gearbox CAD.
    ET.SubElement(world, 'geom', type='box', pos=' '.join(map(str, target-[0, 0, .04])), size='.065 .05 .02', rgba='.65 .69 .72 1')
    for dx in (-.045, .045):
        ET.SubElement(world, 'geom', type='box', pos=' '.join(map(str,target+[dx,0,-.015])), size='.008 .055 .018', rgba='.16 .4 .42 1')
    part = ET.SubElement(world, 'body', name='task_part', mocap='true', pos=' '.join(map(str,target)))
    if task == 'fastening':
        ET.SubElement(part, 'geom', type='cylinder', size='.012 .035', pos='0 0 .035', rgba='.15 .25 .28 1')
        ET.SubElement(part, 'geom', type='cylinder', size='.003 .028', pos='0 0 -.025', rgba='.75 .78 .8 1')
        for dx in (-.022, .022):
            ET.SubElement(world,'geom',type='cylinder',size='.006 .004',pos=' '.join(map(str,target+[dx,0,-.015])),rgba='.85 .7 .3 1')
    else:
        ET.SubElement(part, 'geom', type='cylinder', size='.023 .008', rgba='.75 .58 .22 1')
        for angle in np.linspace(0, 2*np.pi, 16, endpoint=False):
            ET.SubElement(part, 'geom', type='box', size='.005 .003 .008',
                pos=f'{.023*np.cos(angle)} {.023*np.sin(angle)} 0', euler=f'0 0 {angle}', rgba='.75 .58 .22 1')
        ET.SubElement(world, 'geom', type='cylinder', size='.006 .025', pos=' '.join(map(str,target-[0,0,.025])),rgba='.7 .73 .75 1')
    name = f'{task}-{robot}'
    model_path = output / f'{name}.xml'
    ET.ElementTree(xml).write(model_path, encoding='unicode')
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    site = model.site('task_tcp').id
    joints = [j for j in range(model.njnt) if (model.joint(j).name in (
        'shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll') if arm else
        model.joint(j).name.startswith('right_') and any(s in model.joint(j).name for s in ('shoulder', 'elbow', 'wrist')))]
    qids = np.array([model.jnt_qposadr[j] for j in joints])
    dids = np.array([model.jnt_dofadr[j] for j in joints])
    if arm:
        data.qpos[model.joint('shoulder_lift').qposadr] = -.4
        data.qpos[model.joint('elbow_flex').qposadr] = .7
    else:
        data.qpos[model.joint('right_elbow_joint').qposadr] = 1.1
        data.qpos[model.joint('left_elbow_joint').qposadr] = 1.1
    jac = np.zeros((3, model.nv))
    def solve(point: np.ndarray) -> float:
        """Damped position-only IK; no collision, force or balance guarantee."""
        for _ in range(35):
            mujoco.mj_forward(model, data)
            delta = point-data.site_xpos[site]
            if np.linalg.norm(delta) < .001:
                break
            mujoco.mj_jacSite(model, data, jac, None, site)
            selected = jac[:, dids]
            update = selected.T @ np.linalg.solve(selected @ selected.T + np.eye(3)*.0002, delta)
            data.qpos[qids] += np.clip(update, -.06, .06)
            data.qpos[qids] = np.clip(data.qpos[qids],model.jnt_range[joints,0],model.jnt_range[joints,1])
        mujoco.mj_forward(model, data)
        return float(np.linalg.norm(point-data.site_xpos[site]))
    camera = mujoco.MjvCamera()
    camera.lookat[:] = [.18, -.02, .92 if arm else .73]
    camera.distance, camera.azimuth, camera.elevation = (1.05, 135, -24) if arm else (2.2, 135, -18)
    options = mujoco.MjvOption()
    options.geomgroup[3:] = 0
    options.sitegroup[:] = 0
    renderer = mujoco.Renderer(model, height=540, width=960)
    label = 'SO-101' if arm else 'Unitree G1'
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    font = ImageFont.truetype(str(font_path), 19) if font_path.exists() else ImageFont.load_default()
    video = output / f'{name}.mp4'
    poses, residuals = [], []
    pick = target + np.array([-.075, -.08, 0])
    lift = np.array([0, 0, .10])
    waypoints = ([target+lift, target+[0,0,.035], target+[0,0,.035], target+lift,
                  target+[.04,0,.1], target+[.04,0,.035], target+[.04,0,.035], target+lift]
                 if task == 'fastening' else [pick+lift,pick,pick+lift,target+lift,target,target,target+lift,target+lift])
    solve(np.asarray(waypoints[0]))
    with imageio.get_writer(video, fps=24, codec='libx264', quality=8, macro_block_size=2) as writer:
        for frame in range(240):
            phase = frame/239*(len(waypoints)-1)
            k = min(int(phase),len(waypoints)-2)
            u = phase-k
            u = u*u*(3-2*u)
            point = (1-u)*np.asarray(waypoints[k])+u*np.asarray(waypoints[k+1])
            residuals.append(solve(point))
            if arm:
                data.qpos[model.joint('gripper').qposadr] = .1 if task=='fastening' or 1<=phase<4.5 else .7
            data.mocap_pos[0] = data.site_xpos[site] if task=='fastening' or 1<=phase<4.5 else (pick if phase<1 else target)
            mujoco.mj_forward(model,data)
            renderer.update_scene(data,camera=camera,scene_option=options)
            image = Image.fromarray(renderer.render())
            draw = ImageDraw.Draw(image)
            draw.rectangle((0,0,960,62),fill='#10252e')
            draw.text((22,8),f'{label}  /  '+('Guided fastening concept' if task=='fastening' else 'Planet-gear placement concept'),font=font,fill='white')
            draw.text((22,34),'PRE-RUN 3D ANIMATION  ·  Authored motion, not robot execution',font=font,fill='#c7d4d8')
            draw.rectangle((0,508,960,540),fill='#10252e')
            draw.text((22,512),'Proxy workpiece · hypothetical tool coupling · contact / balance / fit unvalidated',font=font,fill='#c7d4d8')
            if frame==100:
                image.save(output/f'{name}.jpg')
            writer.append_data(np.asarray(image))
            poses.append(data.qpos.tolist())
    renderer.close()
    (output/f'{name}-poses.json').write_text(json.dumps(poses),encoding='utf-8')
    shutil.copyfile(source/'LICENSE',output/f'{robot}-LICENSE.txt') if not (output/f'{robot}-LICENSE.txt').exists() else None
    return {'task_id':task,'embodiment':robot,'video':video.name,'poster':f'{name}.jpg',
        'sha256':digest(video),'poster_sha256':digest(output/f'{name}.jpg'),
        'model':entry.display_name,'source_oid':entry.oid,'license':entry.license,
        'source':'https://github.com/google-deepmind/mujoco_menagerie',
        'max_position_residual_m':max(residuals),'frames':240,'fps':24,
        'kind':'prerendered_mesh_concept','physical_validation':False,
        'limitations':['Position-only authored IK, not a trained controller or physics rollout.',
            'Grasp/tool attachment is animated, not contact solved. Workpiece is a proxy.',
            'G1 uses rubber-hand model; dexterity and tool attachment are hypothetical.',
            'No validated collision clearance, torque, balance, throughput or successful assembly.']}


def main() -> None:
    """Create a new immutable local package with four robot/task movies."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    entries = []
    for robot in ('arm','humanoid'):
        for task in ('fastening','planet'):
            entries.append(render(args.output,robot,task))
            (args.output/'manifest.json').write_text(json.dumps({'entries':entries},indent=2),encoding='utf-8')
            print(f'Rendered {task} / {robot}',flush=True)


if __name__ == '__main__':
    main()
