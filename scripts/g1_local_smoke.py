"""Bounded local GR00T action-chunk -> SONIC ONNX -> MuJoCo diagnostic.

This experimental runner uses separate Python environments for GR00T and the
CPU simulator. It never controls hardware or uses a paid inference endpoint.
Controller constants/order follow NVIDIA's Apache-2.0 policy_parameters.hpp.
BonesSeed-V2's legacy observation layout and FSQ snapping follow LeSONIC's
documented injector; this is an integration diagnostic, not task validation.
"""
from __future__ import annotations

import argparse
import ast
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any


def digest(path: Path) -> str:
    """Hash an artifact without retaining its entire contents in memory."""
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path: Path, value: Any) -> None:
    """Write finite JSON into a new artifact, refusing accidental overwrites."""
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def parameters(header: Path) -> dict[str, Any]:
    """Read numeric controller constants using a restricted arithmetic parser."""
    import numpy as np

    names: dict[str, float] = {}

    def number(node: ast.AST) -> float:
        """Evaluate only numeric constants, known names and simple arithmetic."""
        if isinstance(node, ast.Constant) and type(node.value) in (float, int):
            return float(node.value)
        if isinstance(node, ast.Name):
            return names[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -number(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = number(node.left), number(node.right)
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
        raise ValueError('Unsupported controller constant expression')

    text = re.sub(r'//[^\n]*', '', header.read_text())
    for name, expression in re.findall(r'const double (\w+)\s*=\s*([^;]+);', text):
        names[name] = number(ast.parse(expression.strip(), mode='eval').body)
    result = {}
    for name in ('default_angles', 'kps', 'kds', 'g1_action_scale',
                 'isaaclab_to_mujoco', 'mujoco_to_isaaclab'):
        match = re.search(r'\b' + name + r'\s*=\s*\{([^}]+)\}', text)
        if match is None:
            raise ValueError(f'Missing upstream controller parameter: {name}')
        values = [number(ast.parse(x.strip(), mode='eval').body)
                  for x in match.group(1).split(',') if x.strip()]
        result[name] = np.asarray(values, dtype=int if 'to_' in name else float)
        if len(values) != 29 or not np.isfinite(result[name]).all():
            raise ValueError('Expected 29 finite controller parameters')
    if not np.array_equal(result['mujoco_to_isaaclab'][result['isaaclab_to_mujoco']], np.arange(29)):
        raise ValueError('Controller joint mappings are not inverses')
    return result


def simulator(root: Path) -> tuple[Any, Any, Any, dict[str, Any]]:
    """Load upstream G1 geometry and its exact controller constants on CPU."""
    os.environ['MUJOCO_GL'] = 'osmesa'
    import mujoco

    deploy = root / 'GR00T-WholeBodyControl/gear_sonic_deploy'
    model = mujoco.MjModel.from_xml_path(str(deploy / 'g1/scene_29dof.xml'))
    model.opt.timestep = .002
    data = mujoco.MjData(model)
    config = parameters(deploy / 'src/g1/g1_deploy_onnx_ref/include/policy_parameters.hpp')
    if model.nq != 36 or model.nv != 35 or model.nu != 29:
        raise ValueError('Expected the upstream free-base, 29-DoF G1 model')
    return mujoco, model, data, config


def capture(mujoco: Any, model: Any, data: Any, output: Path, *, ego: bool) -> None:
    """Render actual simulator geometry; never synthesize an observation image."""
    from PIL import Image

    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(camera)
    if ego:
        camera.lookat[:] = data.qpos[:3] + [.8, 0, -.4]
        camera.distance, camera.azimuth, camera.elevation = .65, 180, -25
    else:
        camera.lookat[:] = data.qpos[:3]
        camera.lookat[2] = .65
        camera.distance, camera.azimuth, camera.elevation = 2.7, 135, -12
    with mujoco.Renderer(model, height=480, width=640) as renderer:
        renderer.update_scene(data, camera=camera)
        Image.fromarray(renderer.render()).save(output)


def prepare(root: Path, output: Path) -> None:
    """Save a standing initial condition and its rendered camera/state inputs."""
    import numpy as np

    output.mkdir(parents=True, exist_ok=False)
    mujoco, model, data, config = simulator(root)
    data.qpos[7:] = config['default_angles']
    # Initialization only: 0.5 simulated seconds of standing PD before observation.
    for _ in range(250):
        data.ctrl[:] = config['kps'] * (config['default_angles'] - data.qpos[7:]) - config['kds'] * data.qvel[6:]
        mujoco.mj_step(model, data)
    if data.qpos[2] < .4 or not np.isfinite(data.qpos).all():
        raise ValueError('Standing initialization failed; no model inference attempted')
    capture(mujoco, model, data, output / 'observation.png', ego=True)
    capture(mujoco, model, data, output / 'before.png', ego=False)
    rotation = data.xmat[model.body('pelvis').id].reshape(3, 3)
    # This checkpoint was trained with raw IsaacLab order padded to 43, then
    # sliced under anatomical labels. Preserve that legacy layout explicitly.
    legacy = np.pad(data.qpos[7:][config['mujoco_to_isaaclab']], (0, 14))
    slices = {'left_leg': (0, 6), 'right_leg': (6, 12), 'waist': (12, 15),
              'left_arm': (15, 22), 'left_hand': (22, 29),
              'right_arm': (29, 36), 'right_hand': (36, 43)}
    state = {key: legacy[a:b].tolist() for key, (a, b) in slices.items()}
    state['projected_gravity'] = (rotation.T @ np.array([0., 0., -1.])).tolist()
    save(output / 'observation.json', {
        'qpos': data.qpos.tolist(), 'qvel': data.qvel.tolist(), 'state': state,
        'image': 'observation.png', 'image_sha256': digest(output / 'observation.png'),
        'prompt': 'squat', 'initialization': '0.5s standing PD, excluded from learned rollout',
        'layout': 'LeSONIC BonesSeed legacy IsaacLab29 padded43; no gravity override',
        'camera': 'MuJoCo approximate forward/downward view; not calibrated to training camera',
    })
    print('SIMULATION_OBSERVATION_READY', flush=True)


def infer(root: Path, output: Path) -> None:
    """Run one real GR00T action chunk with BF16 loading and retain raw output."""
    from dotenv import load_dotenv
    import numpy as np
    from PIL import Image
    import torch

    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=True)
    sys.path.insert(0, str(root / 'Isaac-GR00T'))
    from gr00t.policy.gr00t_policy import Gr00tPolicy

    document = json.loads((output / 'observation.json').read_text())
    if digest(output / document['image']) != document['image_sha256']:
        raise ValueError('Observation image checksum changed')
    started = time.perf_counter()
    policy = Gr00tPolicy(model_path=str(root / 'checkpoints/gr00t-bonesseed-v2'),
                         embodiment_tag='UNITREE_G1_SONIC', device='cuda:0')
    loaded = time.perf_counter()
    torch.manual_seed(0)
    observation = {
        'video': {'ego_view': np.asarray(Image.open(output / document['image']).convert('RGB'))[None, None]},
        'state': {key: np.asarray(value, dtype=np.float32)[None, None] for key, value in document['state'].items()},
        'language': {'annotation.human.task_description': [[document['prompt']]]},
    }
    action, _ = policy.get_action(observation)
    torch.cuda.synchronize()
    if action['motion_token'].shape != (1, 40, 64) or any(not np.isfinite(v).all() for v in action.values()):
        raise ValueError('Invalid GR00T action chunk')
    save(output / 'actions.json', {
        'model_id': 'wsagi/GR00T-N1.7-G1-SONIC-BonesSeed-V2',
        'revision': 'b2c6b57e0780ead42cf12cdcdf1d67dd210e142d',
        'observation_sha256': digest(output / 'observation.json'),
        'actions': {key: value.tolist() for key, value in action.items()},
        'seed': 0, 'load_seconds': loaded - started,
        'inference_seconds': time.perf_counter() - loaded,
        'peak_gpu_bytes': torch.cuda.max_memory_allocated(),
        'runtime': {'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(), 'precision': 'bfloat16'},
    })
    print('REAL_GR00T_ACTION_CHUNK_RECORDED', flush=True)


def simulate(root: Path, output: Path) -> None:
    """Apply one GR00T chunk through SONIC feedback control in actual physics."""
    import imageio.v2 as imageio
    import numpy as np
    import onnxruntime as ort
    from PIL import Image

    obs = json.loads((output / 'observation.json').read_text())
    actions = json.loads((output / 'actions.json').read_text())
    if actions['observation_sha256'] != digest(output / 'observation.json'):
        raise ValueError('Actions do not belong to this observation')
    tokens = np.asarray(actions['actions']['motion_token'], dtype=np.float32)[0]
    if tokens.shape != (40, 64) or not np.isfinite(tokens).all():
        raise ValueError('Expected 40 finite 64-dimensional motion tokens')
    mujoco, model, data, config = simulator(root)
    data.qpos[:], data.qvel[:] = obs['qpos'], obs['qvel']
    mujoco.mj_forward(model, data)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    decoder = root / 'checkpoints/sonic-original/model_decoder.onnx'
    session = ort.InferenceSession(str(decoder), options, providers=['CPUExecutionProvider'])
    if session.get_inputs()[0].shape != [1, 994]:
        raise ValueError('SONIC decoder observation shape mismatch')
    history: deque[Any] = deque(maxlen=10)
    previous = np.zeros(29)
    trace = []
    camera = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(camera)
    camera.lookat[:], camera.distance, camera.azimuth, camera.elevation = [0, 0, .65], 2.7, 135, -12
    with mujoco.Renderer(model, height=480, width=640) as renderer, imageio.get_writer(
            output / 'simulation.mp4', fps=50, codec='libx264', pixelformat='yuv420p') as writer:
        for index, token in enumerate(tokens):
            rotation = data.xmat[model.body('pelvis').id].reshape(3, 3)
            entry = [data.qvel[3:6].copy(),
                     (data.qpos[7:] - config['default_angles'])[config['mujoco_to_isaaclab']],
                     data.qvel[6:][config['mujoco_to_isaaclab']], previous.copy(),
                     rotation.T @ np.array([0., 0., -1.])]
            history.append(entry)
            while len(history) < 10:
                history.appendleft(entry)
            snapped = np.clip(np.round(token * 16) / 16, -1., 1.)
            decoder_input = np.concatenate([snapped] + [np.concatenate([h[k] for h in history]) for k in range(5)]).astype(np.float32)
            tick = time.perf_counter()
            previous = session.run(None, {'obs_dict': decoder_input[None]})[0][0]
            latency = time.perf_counter() - tick
            if previous.shape != (29,) or not np.isfinite(previous).all():
                raise ValueError('Invalid SONIC joint action')
            target = previous[config['isaaclab_to_mujoco']] * config['g1_action_scale'] + config['default_angles']
            for _ in range(10):
                data.ctrl[:] = config['kps'] * (target - data.qpos[7:]) - config['kds'] * data.qvel[6:]
                mujoco.mj_step(model, data)
            renderer.update_scene(data, camera=camera)
            frame = renderer.render()
            writer.append_data(frame)
            trace.append({'step': index, 'time_s': (index + 1) * .02,
                          'token_raw': token.tolist(), 'token_consumed': snapped.tolist(),
                          'decoder_input_sha256': hashlib.sha256(decoder_input.tobytes()).hexdigest(),
                          'joint_target_rad': target.tolist(), 'qpos': data.qpos.tolist(),
                          'qvel': data.qvel.tolist(), 'decoder_seconds': latency})
            if data.qpos[2] < .4 or not np.isfinite(data.qpos).all():
                break
        Image.fromarray(frame).save(output / 'after.png')
    save(output / 'controller-trace.json', {
        'actions_sha256': digest(output / 'actions.json'), 'decoder_sha256': digest(decoder),
        'decoder_runtime': 'ONNX Runtime CPUExecutionProvider', 'simulator': mujoco.__version__,
        'steps': trace, 'fallen': bool(data.qpos[2] < .4), 'task_outcome': 'not_evaluated',
        'limitations': ['Single open-loop action chunk with SONIC state feedback; no GR00T replanning.',
                        'Approximate camera and legacy checkpoint state layout; transfer quality unvalidated.',
                        'Hand action outputs retained but not actuated on the 29-DoF rubber-hand model.',
                        'No physical execution, real-time throughput or squat-success claim.'],
    })
    print(f'SONIC_SIMULATION_RECORDED: {len(trace)} control steps; task not evaluated', flush=True)


def main() -> None:
    """Select an explicit bounded phase and preserve all failure evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['prepare', 'infer', 'simulate'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    {'prepare': prepare, 'infer': infer, 'simulate': simulate}[args.phase](args.root, args.output)


if __name__ == '__main__':
    main()
