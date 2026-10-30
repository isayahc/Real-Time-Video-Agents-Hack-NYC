# SPDX-License-Identifier: MPL-2.0
"""Export recorded GR00T/SONIC run evidence as an inference-free static site."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import shutil
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .models import StrictModel
from .pipeline import sha256
from .snapshots import contained_file


class ReplayArtifact(StrictModel):
    """One explicitly selected, checksummed file permitted in the public export."""

    path: str = Field(pattern=r'^artifacts/[A-Za-z0-9_./-]+$')
    role: Literal['observations', 'actions', 'controller_trace', 'video', 'frame', 'diagnostic']
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    bytes: int = Field(gt=0)
    caption: str = Field(min_length=1)

    @model_validator(mode='after')
    def portable_path(self) -> Self:
        """Keep media passive and paths canonical, excluding reserved site files."""
        path = Path(self.path)
        allowed = {'video': {'.mp4', '.webm'}, 'frame': {'.png', '.jpg', '.jpeg'}}
        if '..' in path.parts or path.as_posix() != self.path or path.suffix not in allowed.get(
                self.role, {'.json', '.jsonl', '.txt'}):
            raise ValueError('Use canonical artifact paths and a supported passive file type')
        return self


class ReplayStage(StrictModel):
    """Producer-recorded model identity and explicit artifact consumption links."""

    status: Literal['not_run', 'failed', 'completed'] = 'not_run'
    model_id: str | None = Field(default=None, min_length=1)
    revision: str | None = Field(default=None, min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def execution_identity(self) -> Self:
        """Never infer completed execution from model configuration alone."""
        if self.status == 'completed' and not all((self.model_id, self.revision, self.inputs, self.outputs)):
            raise ValueError('Completed stages need model identity, pinned revision, inputs and outputs')
        if self.status == 'not_run' and (self.inputs or self.outputs):
            raise ValueError('An unexecuted stage cannot claim consumed or produced artifacts')
        return self


class GPUReplay(StrictModel):
    """A finalized simulation receipt; physical execution is outside this format."""

    schema_version: Literal[1] = 1
    kind: Literal['humanoid-gpu-replay'] = 'humanoid-gpu-replay'
    run_id: str = Field(pattern=r'^[A-Za-z0-9_-]+$')
    recorded_at: AwareDatetime
    status: Literal['blocked', 'failed', 'completed']
    evidence: Literal['no_execution', 'recorded_inference_simulation', 'synthetic_test']
    task: str = Field(min_length=1)
    embodiment: Literal['UNITREE_G1_SONIC'] = 'UNITREE_G1_SONIC'
    gpu: str = Field(min_length=1)
    simulator: str | None = Field(default=None, min_length=1)
    source_revision: str = Field(min_length=1)
    gr00t: ReplayStage = Field(default_factory=ReplayStage)
    sonic: ReplayStage = Field(default_factory=ReplayStage)
    outcome: Literal['not_evaluated', 'success', 'failure', 'unknown'] = 'not_evaluated'
    limitations: list[str] = Field(min_length=1)
    attribution: list[str] = Field(default_factory=list)
    artifacts: list[ReplayArtifact] = Field(default_factory=list)

    @model_validator(mode='after')
    def evidence_links(self) -> Self:
        """Require retained lineage before labeling the combined run completed."""
        files = {a.path: a for a in self.artifacts}
        if len(files) != len(self.artifacts):
            raise ValueError('Artifact paths must be unique')
        for stage in (self.gr00t, self.sonic):
            if any(p not in files for p in stage.inputs + stage.outputs):
                raise ValueError('Stage references must exist in the artifact index')
        if self.evidence == 'no_execution':
            if self.status != 'blocked' or any(s.status != 'not_run' for s in (self.gr00t, self.sonic)):
                raise ValueError('No-execution evidence must remain blocked with both stages not run')
            if self.outcome != 'not_evaluated' or any(a.role != 'diagnostic' for a in self.artifacts):
                raise ValueError('No-execution evidence cannot contain results or execution media')
        if self.status == 'blocked' and self.evidence != 'no_execution':
            raise ValueError('Use failed status to retain a partially executed run')
        if self.status == 'completed':
            if not self.simulator or any(s.status != 'completed' for s in (self.gr00t, self.sonic)):
                raise ValueError('Completed replay requires both stages and a simulator identity')
            observations = {p for p in self.gr00t.inputs if files[p].role == 'observations'}
            actions = {p for p in self.gr00t.outputs if files[p].role == 'actions'}
            traces = {p for p in self.sonic.outputs if files[p].role == 'controller_trace'}
            media = {p for p in self.sonic.outputs if files[p].role in {'video', 'frame'}}
            if not observations or not actions.intersection(self.sonic.inputs) or not traces or not media:
                raise ValueError('Require observations → shared actions → controller trace and simulation media')
        if self.outcome == 'success' and self.status != 'completed':
            raise ValueError('Incomplete runs cannot claim task success')
        return self


def verify_replay(manifest: Path) -> GPUReplay:
    """Validate schema and every selected artifact without executing run contents."""
    run = GPUReplay.model_validate_json(manifest.read_text(encoding='utf-8'))
    for artifact in run.artifacts:
        path = contained_file(manifest.parent, artifact.path)
        if path.stat().st_size != artifact.bytes or sha256(path) != artifact.sha256:
            raise ValueError(f'Artifact checksum mismatch: {artifact.path}')
    return run


def render_replay(run: GPUReplay) -> str:
    """Render an escaped, script-free viewer that works directly from disk or Vercel."""
    escape = html.escape
    label = {
        'no_execution': 'Blocked · no GR00T or SONIC execution',
        'recorded_inference_simulation': 'Recorded inference + simulation · saved playback',
        'synthetic_test': 'Synthetic test fixture · not model inference evidence',
    }[run.evidence]
    stages = ''.join(
        f'<tr><th scope="row">{name}</th><td>{escape(role)}</td><td>{stage.status}</td>'
        f'<td>{escape(stage.model_id or "Not run")}<br>{escape(stage.revision or "No checkpoint executed")}</td></tr>'
        for name, role, stage in (
            ('GR00T', 'Observations + task → compatible actions', run.gr00t),
            ('SONIC', 'Compatible actions → humanoid whole-body control', run.sonic)))
    media = []
    links = []
    for artifact in run.artifacts:
        caption = escape(artifact.caption)
        url = escape(artifact.path, quote=True)
        if artifact.role == 'video':
            media.append(f'<figure><video controls playsinline preload="metadata" aria-label="{caption}" '
                         f'src="{url}"></video><figcaption>{caption}</figcaption></figure>')
        elif artifact.role == 'frame':
            media.append(f'<figure><img loading="lazy" src="{url}" alt="{caption}">'
                         f'<figcaption>{caption}</figcaption></figure>')
        links.append(f'<li><a href="{url}">{caption}</a> · {artifact.role} · {artifact.bytes:,} bytes'
                     f'<br><code>{artifact.sha256}</code></li>')
    limitations = ''.join(f'<li>{escape(text)}</li>' for text in run.limitations)
    attribution = ''.join(f'<li>{escape(text)}</li>' for text in run.attribution)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GR00T + SONIC · saved GPU run</title>
<style>
:root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#101d1c;color:#eaf0e9}}
body{{max-width:1000px;margin:auto;padding:28px 20px;line-height:1.6}}h1{{font-size:clamp(28px,5vw,44px)}}
a{{color:#cee7a4}}p,li{{color:#bdcec7}}.notice{{border-left:4px solid #cee7a4;padding:16px;background:#20352e}}
section{{border-top:1px solid #344943;margin-top:24px;padding-top:16px}}.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;min-width:580px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #344943}}
video,img{{max-width:100%;max-height:65vh;background:#080e0d}}figure{{margin:20px 0}}code,dd,li{{overflow-wrap:anywhere}}
dt{{font-weight:600}}dd{{margin:0 0 12px}}footer{{font-size:14px;margin-top:28px}}
</style></head><body>
<p>Mapped Assembly · Physical AI · saved GPU run</p><h1>GR00T + SONIC</h1>
<div class="notice"><strong>{label}</strong><br>Status: {run.status} · Task outcome: {run.outcome}</div>
<p>{escape(run.task)}</p><p>GPU inference runs separately. This page serves saved files only; viewing it makes no model calls.</p>
<section><h2>Execution layers</h2><div class="scroll"><table><thead><tr><th>Layer</th><th>Responsibility</th><th>Recorded status</th><th>Model / revision</th></tr></thead><tbody>{stages}</tbody></table></div></section>
<section><h2>Saved results</h2>{''.join(media) or '<p>No simulation media has been recorded for this receipt.</p>'}</section>
<section><h2>Run provenance</h2><dl><dt>Run / recorded time</dt><dd>{escape(run.run_id)} · {escape(run.recorded_at.isoformat())}</dd>
<dt>GPU</dt><dd>{escape(run.gpu)}</dd><dt>Embodiment / simulator</dt><dd>{run.embodiment} / {escape(run.simulator or 'Not run')}</dd>
<dt>Project revision</dt><dd>{escape(run.source_revision)}</dd></dl>
<p><a href="run.json">Run manifest and artifact links</a> · <a href="checksums.json">Published file checksums</a></p>
<details><summary>Retained artifacts ({len(run.artifacts)})</summary><ul>{''.join(links)}</ul></details></section>
<section><h2>Limitations and blockers</h2><ul>{limitations}</ul></section>
<section><h2>Attribution</h2><ul>{attribution or '<li>No third-party media included.</li>'}</ul></section>
<footer>Recorded status is supplied by the run producer. Export verifies file integrity and artifact links, not model behavior.
Simulation is not physical execution. Run completion does not establish task success.</footer></body></html>
'''


def export_replay(manifest: Path, output: Path) -> GPUReplay:
    """Create a new allowlisted static export; preserve existing outputs on failure."""
    run = verify_replay(manifest)
    output.mkdir(parents=True, exist_ok=False)
    for artifact in run.artifacts:
        source = contained_file(manifest.parent, artifact.path)
        target = output / artifact.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if target.stat().st_size != artifact.bytes or sha256(target) != artifact.sha256:
            raise ValueError(f'Artifact changed during copy: {artifact.path}')
    (output / 'run.json').write_text(run.model_dump_json(indent=2) + '\n', encoding='utf-8')
    (output / 'index.html').write_text(render_replay(run), encoding='utf-8')
    config = {'framework': None, 'buildCommand': None, 'outputDirectory': '.', 'headers': [
        {'source': '/(.*)', 'headers': [
            {'key': 'X-Content-Type-Options', 'value': 'nosniff'},
            {'key': 'Content-Security-Policy', 'value': "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; media-src 'self'; base-uri 'none'; frame-ancestors 'none'"}]}]}
    (output / 'vercel.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    index = [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)}
             for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'vercel.json']
    (output / 'checksums.json').write_text(json.dumps(index, indent=2) + '\n', encoding='utf-8')
    return run


def main() -> None:
    """Export an existing finalized receipt; never start inference or cloud resources."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run = export_replay(args.manifest, args.output)
    print(f'{run.run_id}: {run.status} ({run.evidence}) -> {args.output / "index.html"}')


if __name__ == '__main__':
    main()
