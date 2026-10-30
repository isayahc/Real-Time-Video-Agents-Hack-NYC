# SPDX-License-Identifier: MPL-2.0
"""Operator-facing process reviews over existing accounting and investment services."""
from __future__ import annotations

import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Literal
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field, model_validator

from .alternatives import AlternativeSet, evaluate_alternatives
from .evaluation import ProcessEvaluationInput, UNITS, evaluate_process
from .models import EngineeringValue, StrictModel
from .pipeline import sha256
from .snapshots import allocate_snapshot, atomic_json, contained_file, file_index, read_json

ROOT = Path(__file__).resolve().parents[1]
EXTRA_UNITS = {'first_pass_count': 'count', 'rework_count': 'count', 'setup_s': 's',
               'cleanup_s': 's', 'changeover_s': 's', 'interventions': 'count',
               'sop_deviations': 'count', 'water_l': 'L'}
FIELDS = {**UNITS, **EXTRA_UNITS}
PRIMARY = ('accepted_outputs_per_hour', 'labor_s_per_accepted',
           'first_pass_yield', 'cost_usd_per_accepted')


class Quantity(StrictModel):
    """Retain simulation versus measurement even when the legacy adapter uses assumed."""

    value: float | None = Field(default=None, ge=0)
    unit: str
    kind: Literal['measured', 'simulated', 'estimated', 'unknown'] = 'unknown'
    source: str = ''

    @model_validator(mode='after')
    def provenance(self) -> Quantity:
        """Reject unsourced values and never coerce an unknown to zero."""
        if (self.value is None) != (self.kind == 'unknown'):
            raise ValueError('Unknown values must be blank; known values need an evidence type')
        if self.value is not None and not self.source.strip():
            raise ValueError('Every known value requires an evidence source')
        if self.unit == 'count' and self.value is not None and not self.value.is_integer():
            raise ValueError('Counts must be whole numbers')
        return self

    def accounting(self) -> EngineeringValue:
        """Adapt without claiming simulation or estimates are physical measurements."""
        return EngineeringValue(value=self.value, unit=self.unit,
            basis='unknown' if self.value is None else 'measured' if self.kind == 'measured' else 'assumed',
            source=f'{self.kind}: {self.source}' if self.value is not None else None)


class GateState(StrictModel):
    """A user-supplied gate assessment, not automatic safety certification."""

    status: Literal['unresolved', 'passed', 'failed'] = 'unresolved'
    source: str = ''

    @model_validator(mode='after')
    def sourced(self) -> GateState:
        """Require rationale/evidence when a gate is resolved."""
        if self.status != 'unresolved' and not self.source.strip():
            raise ValueError('Passed/failed gates require an evidence source or rationale')
        return self


class Gate(StrictModel):
    """Apply the same requirement to both process options."""

    category: Literal['quality', 'safety', 'space', 'budget']
    requirement: str = Field(min_length=1, max_length=4000)
    baseline: GateState = Field(default_factory=GateState)
    candidate: GateState = Field(default_factory=GateState)


class Option(StrictModel):
    """Editable observations for one complete batch, including failed work and overhead."""

    label: str = Field(min_length=1, max_length=200)
    change: str = Field(max_length=6000)
    values: dict[str, Quantity]

    @model_validator(mode='after')
    def counts_and_units(self) -> Option:
        """Keep first-pass yield distinct from eventual acceptance after rework."""
        for key, value in self.values.items():
            if key not in FIELDS or value.unit != FIELDS[key]:
                raise ValueError(f'Unsupported field or unit: {key}')
        numbers = {k: v.value for k, v in self.values.items()}
        for small, large in [('accepted_count', 'attempted_count'),
                             ('first_pass_count', 'accepted_count'),
                             ('first_pass_count', 'attempted_count'), ('rework_count', 'attempted_count')]:
            if numbers.get(small) is not None and numbers.get(large) is not None and numbers[small] > numbers[large]:
                raise ValueError(f'{small} cannot exceed {large}')
        return self


class Review(StrictModel):
    """One shared output/boundary and two editable options with retained source context."""

    title: str = Field(min_length=1, max_length=200)
    workspace: str = Field(min_length=1, max_length=3000)
    operator_goal: str = Field(min_length=1, max_length=3000)
    functional_unit: str = Field(min_length=1, max_length=3000)
    boundary: str = Field(min_length=1, max_length=6000)
    steps: list[str] = Field(max_length=100)
    steps_reviewed: bool = False
    gates: list[Gate] = Field(min_length=4, max_length=4)
    baseline: Option
    candidate: Option
    source_text: str = Field(default='', max_length=50000)
    source_note: str = Field(default='', max_length=6000)

    @model_validator(mode='after')
    def complete_gates(self) -> Review:
        """Require all four constraint classes without duplicate or empty steps."""
        if {g.category for g in self.gates} != {'quality', 'safety', 'space', 'budget'}:
            raise ValueError('Quality, safety, space and budget gates are required')
        if any(not step.strip() or len(step) > 4000 for step in self.steps):
            raise ValueError('Steps must be nonempty and at most 4000 characters')
        if self.steps_reviewed and not self.steps:
            raise ValueError('Import or enter process steps before approving them')
        return self


def example(blank: bool = False) -> tuple[Review, dict[str, Any]]:
    """Reuse the existing coil benchmark and illustrative alternatives without inference."""
    alternative_path = ROOT / 'examples/apparatus-alternatives/illustrative-input.json'
    baseline_path = ROOT / 'benchmarks/coil-winding/baseline.json'
    alternatives, baseline = read_json(alternative_path), read_json(baseline_path)
    options = []
    for item in alternatives['options'][:2]:
        values = {key: Quantity(unit=unit) for key, unit in FIELDS.items()}
        if not blank:
            for key, value in item['option']['process']['inputs'].items():
                values[key] = Quantity(value=value['value'], unit=value['unit'],
                    kind='estimated' if value['value'] is not None else 'unknown', source=value.get('source') or '')
        options.append(Option(label=item['label'], change='; '.join(item['equipment'] + item['controls']), values=values))
    if blank:
        options[0].label, options[0].change = 'Current process', 'Describe how the work happens today.'
        options[1].label, options[1].change = 'Proposed change', 'Describe the equipment, tooling, layout or procedure change.'
    process = alternatives['options'][0]['option']['process']
    data = Review(title='New process' if blank else 'Coil preparation · manual fixture vs motorized winder',
        workspace='Describe the workspace and responsible operator.' if blank else 'Small laboratory preparation bench; lab manager responsible for coil quality and operator time.',
        operator_goal='Describe the time/resource problem to resolve.' if blank else 'Reduce attended winding work without compromising released-coil quality or safe operation.',
        functional_unit='Define one accepted output.' if blank else process['functional_unit'],
        boundary='Define batch start/end, included rework and overhead.' if blank else process['boundary'],
        steps=[] if blank else [s['operation'] for s in baseline['steps']],
        gates=[Gate(category=key, requirement=text) for key, text in (
            ('quality', '; '.join(baseline['functional_unit']['criteria']) + '. Target dimensions and tolerances remain unresolved.'),
            ('safety', 'Assess pinch, entanglement, wire handling and stop/access requirements before a powered trial.'),
            ('space', 'Confirm installed footprint, access and storage fit the available bench; dimensions unknown.'),
            ('budget', 'Confirm deployment cost and recurring cost fit the approved budget; budget and quotes unknown.'))],
        baseline=options[0], candidate=options[1],
        source_note='User-entered process; no extraction performed.' if blank else 'Authored workflow hypothesis and invented planning numbers from repository examples. No source video imported or physical result verified.')
    if blank:
        for gate in data.gates:
            gate.requirement = f'Define the required {gate.category} constraint and evidence needed to pass it.'
    sources = {} if blank else {str(p.relative_to(ROOT)).replace('\\', '/'): {'sha256': sha256(p), 'content': read_json(p)}
                               for p in (alternative_path, baseline_path)}
    return data, sources


def compare(data: Review, illustrative: bool) -> dict[str, Any]:
    """Reuse accounting/investment; gate recommendations separately from arithmetic."""
    reports, gaps, processes, supporting = {}, [], {}, {}
    if not data.steps_reviewed:
        gaps.append('Review and confirm the full process steps, including failed attempts, rework, setup and cleanup.')
    for name in ('baseline', 'candidate'):
        option = getattr(data, name)
        quality = next(g for g in data.gates if g.category == 'quality')
        state = getattr(quality, name)
        process = ProcessEvaluationInput(configuration_id=name, functional_unit=data.functional_unit,
            boundary=data.boundary, acceptance_verified=not illustrative and state.status == 'passed',
            acceptance_source=state.source or None,
            inputs={key: value.accounting() for key, value in option.values.items() if key in UNITS})
        processes[name] = process
        report = evaluate_process(process).model_dump()
        first, attempts = option.values.get('first_pass_count'), option.values.get('attempted_count')
        known = first is not None and attempts is not None and first.value is not None and attempts.value is not None
        report['metrics']['first_pass_yield'] = {
            'value': first.value / attempts.value if known and attempts.value > 0 else None,
            'unit': 'fraction passing without rework', 'status': 'calculated' if known and attempts.value > 0 else 'unknown' if not known else 'undefined',
            'dependencies': ['first_pass_count', 'attempted_count'],
            'reason': 'First-pass count is separate from eventual accepted count; all initial attempts stay in the denominator.'}
        for key, metric in report['metrics'].items():
            evidence = sorted({option.values[k].kind for k in metric['dependencies'] if k in option.values})
            metric['evidence'] = 'unknown' if metric['value'] is None else ' + '.join(evidence)
            if key in PRIMARY and metric['value'] is None:
                missing = [k for k in metric['dependencies'] if k not in option.values or option.values[k].value is None]
                gaps.append(f'{option.label}: measure {", ".join(missing) or "a nonzero denominator"} for {key}.')
        reports[name] = report
        supporting[name] = {key: value.model_dump() for key, value in option.values.items()
                            if key in EXTRA_UNITS or key == 'elapsed_s'}
        accepted = option.values.get('accepted_count')
        water = option.values.get('water_l')
        supporting[name]['water_l_per_accepted'] = {
            'value': water.value / accepted.value if water and water.value is not None and accepted and accepted.value else None,
            'unit': 'L/accepted output', 'kind': 'derived',
            'source': 'water_l / accepted_count; unknown when either input is missing or accepted_count is zero'}
    gate_issues = []
    for gate in data.gates:
        for name in ('baseline', 'candidate'):
            if getattr(gate, name).status != 'passed':
                gate_issues.append(f'{name} {gate.category}: {getattr(gate, name).status} — {gate.requirement}')
    # Reuse investment contracts with explicitly unknown investment/capacity inputs.
    # Recurring batch costs stay in the headline accounting. The disjoint investment
    # model cannot treat those allocations as capital or annual fixed costs.
    template = read_json(ROOT / 'examples/apparatus-alternatives/illustrative-input.json')
    template['options'] = template['options'][:2]
    for item, name in zip(template['options'], ('baseline', 'candidate')):
        option = getattr(data, name)
        item.update(id=name, label=option.label, equipment=[option.change or 'Not described'],
                    controls=['Operator review required'], measurement_gaps=['Investment and capacity require separate sourced inputs'])
        p = processes[name].model_dump()
        p.update(acceptance_verified=False, acceptance_source=None)
        for key in ('allocated_tooling_cost', 'facility_cost', 'paid_coverage_cost', 'maintenance_cost'):
            p['inputs'].pop(key, None)
        item['option']['process'] = p
        for key, unit in [('annual_fixed_cost', 'USD/year'), ('scheduled_hours', 'h/year'),
                          ('utilization', 'fraction'), ('downtime', 'fraction'), ('useful_life', 'years')]:
            item['option'][key] = {'unit': unit, 'basis': 'unknown'}
        item['option']['upfront'] = {}
        item['option']['cost_model_source'] = 'Separate investment allocations have not been supplied; batch cost is not lifetime cost.'
        item['option']['capacity_model_source'] = 'Annual schedule, utilization and downtime remain unknown.'
    template['scenarios'] = [{'name': 'Operator review', 'annual_demand': {'unit': 'accepted outputs/year', 'basis': 'unknown'}}]
    template['horizon_years'] = {'unit': 'years', 'basis': 'unknown'}
    template['description'] = data.title
    template['limitations'] = ['Investment, annual capacity and payback remain unknown; no implicit capital allocations.']
    investment = evaluate_alternatives(AlternativeSet.model_validate(template))
    decision, reason = 'insufficient_evidence', 'Resolve the acceptance gates and missing or non-measured inputs before adopting the change.'
    failed = [g.category for g in data.gates if g.candidate.status == 'failed']
    measured = all(reports[n]['metrics'][k]['evidence'] == 'measured' for n in reports for k in PRIMARY)
    if failed:
        decision, reason = 'retain_current_process', f'Do not adopt this proposal: failed {", ".join(failed)} gate(s). This does not certify the current process as safe.'
    elif not illustrative and not gaps and not gate_issues and measured:
        directions = [1, -1, 1, -1]
        differences = [(reports['candidate']['metrics'][k]['value'] - reports['baseline']['metrics'][k]['value']) * direction
                       for k, direction in zip(PRIMARY, directions)]
        if all(d >= 0 for d in differences) and any(d > 0 for d in differences):
            decision, reason = 'supported_change', 'Candidate improves at least one headline metric without worsening the others, within the supplied evidence and passed gates. Confirm repeatability before rollout.'
        elif all(d <= 0 for d in differences):
            decision, reason = 'retain_current_process', 'The proposal shows no supported headline-metric advantage over the current process.'
        else:
            reason = 'Metrics trade off. Agree the operator priority and acceptable tradeoff before recommending adoption.'
    if illustrative:
        gaps.insert(0, 'Replace invented example numbers with a complete measured batch for each option; this is a mock walkthrough.')
    elif not measured:
        gaps.append('Replace estimates/simulation with measured evidence for the four headline metrics before a physical improvement recommendation.')
    next_action = ('Revise the proposal to satisfy the failed constraint and reassess it.' if failed else
                   'Define and verify the same quality, safety, space and budget requirements for both options.' if gate_issues else
                   gaps[0] if gaps else 'Repeat the matched batch study and review variation before an implementation decision.')
    return {'metrics': reports, 'supporting': supporting, 'investment': investment, 'decision': decision, 'reason': reason,
        'gates': [g.model_dump() for g in data.gates], 'missing_evidence': gate_issues + gaps,
        'next_action': next_action, 'illustrative': illustrative,
        'limitations': ['Values and gate assessments are supplied evidence, not independent verification.',
            'Elapsed batch time and hands-on operator time are different clocks; include failures, rework and applicable overhead once.',
            'First-pass yield is first-pass accepted units / all initially attempted units; rework is not another initial attempt.',
            'Video observations and CAD/scene animations do not establish cost, energy, forces, quality, safety or full-process labor.',
            'Single-batch arithmetic does not establish statistical reliability or general performance.',
            'Blank costs remain unknown; known cost subtotal is not total cost. Investment/payback need separate evidence.']}


def decision_markdown(record: dict[str, Any]) -> str:
    """Render a portable operator decision report with sources and limitations."""
    data, result = record['data'], record.get('result')
    lines = ['# Process improvement decision', '', data['title'], '',
             f"Evidence mode: {'MOCK / invented example' if record['illustrative'] else 'User-supplied evidence'}",
             f"Revision: {record['revision']} · Status: {record['status']}", '',
             '## Operator and process', data['workspace'], data['operator_goal'], '',
             '## Accepted output', data['functional_unit'], '', '## Shared boundary', data['boundary'], '',
             '## Reviewed steps', *[f'{i+1}. {step}' for i, step in enumerate(data['steps'])], '',
             '## Proposed change', data['candidate']['change'], '', '## Decision']
    if result:
        lines += [result['decision'], result['reason'], '', '## Four headline metrics']
        for key in PRIMARY:
            lines.append(f'### {key}')
            for name in ('baseline', 'candidate'):
                m = result['metrics'][name]['metrics'][key]
                lines.append(f"- {name}: {m['value'] if m['value'] is not None else m['status']} {m['unit']} ({m['evidence']})")
        lines += ['', '## Acceptance gates']
        for gate in data['gates']:
            lines += [f"- {gate['category']}: {gate['requirement']}"]
            for name in ('baseline', 'candidate'):
                state = gate[name]
                lines.append(f"  - {name}: {state['status']}; source: {state['source'] or 'unknown'}")
        lines += ['', '## Next action', result['next_action'], '', '## Missing evidence',
                  *['- ' + item for item in result['missing_evidence']], '', '## Limitations',
                  *['- ' + item for item in result['limitations']]]
    else:
        lines += ['Insufficient evidence: comparison has not completed.', record.get('error') or '']
    lines += ['', '## Input evidence', data['source_note']]
    for name in ('baseline', 'candidate'):
        lines.append(f'### {name}')
        for key, q in data[name]['values'].items():
            lines.append(f"- {key}: {q['value'] if q['value'] is not None else 'unknown'} {q['unit']} [{q['kind']}] — {q['source'] or 'No source'}")
    lines += ['', 'Full inputs, source captures, calculations and hashes accompany this report in the ZIP.']
    return '\n'.join(lines) + '\n'


class SaveRequest(StrictModel):
    """Optimistic revision prevents one browser from silently overwriting another."""

    revision: int = Field(ge=1)
    data: Review


class ImportRequest(StrictModel):
    """Import local SOP text or one existing video extraction without new model calls."""

    revision: int = Field(ge=1)
    text: str = Field(default='', max_length=50000)
    run_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


def router(root: Path, jobs: Any) -> APIRouter:
    """Attach local-only versioned review endpoints to the existing workbench server."""
    api = APIRouter(prefix='/api/processes')
    lock = threading.RLock()
    root.mkdir(parents=True, exist_ok=True)

    def folder(identifier: str) -> Path:
        """Validate identifiers before any file access."""
        if not re.fullmatch(r'[a-f0-9]{32}', identifier) or not (root / identifier).is_dir():
            raise HTTPException(404, 'Process review not found')
        return root / identifier

    def get(identifier: str) -> dict[str, Any]:
        """Read the last atomically published revision."""
        path = folder(identifier)
        current = read_json(path / 'current.json')
        return read_json(contained_file(path, f"v{current['revision']:06d}/review.json"))

    def persist(record: dict[str, Any]) -> dict[str, Any]:
        """Retain append-only input/result revisions using existing snapshot primitives."""
        path = folder(record['id'])
        target = allocate_snapshot(path)
        record.update(revision=int(target.name[1:]), updated_at=time.time())
        atomic_json(target / 'review.json', record)
        (target / 'decision.md').write_text(decision_markdown(record), encoding='utf-8')
        atomic_json(target / 'snapshot.json', {'kind': 'process-comparison', 'schema_version': 1,
            'revision': record['revision'], 'files': file_index(target)})
        atomic_json(path / 'current.json', {'revision': record['revision']})
        return record

    def current(identifier: str, revision: int) -> dict[str, Any]:
        """Reject stale editing and comparison requests."""
        record = get(identifier)
        if record['revision'] != revision:
            raise HTTPException(409, 'This process changed in another tab. Reopen the saved review before editing.')
        return record

    @api.get('')
    def history() -> list[dict[str, Any]]:
        """List durable reviews, including failed evaluations."""
        with lock:
            items = [get(p.parent.name) for p in root.glob('*/current.json')]
        return [{'id': r['id'], 'title': r['data']['title'], 'status': r['status'],
                 'revision': r['revision'], 'updated_at': r['updated_at']} for r in sorted(items, key=lambda r: r['updated_at'], reverse=True)]

    @api.post('')
    def create(blank: bool = False, task: int | None = None) -> dict[str, Any]:
        """Open an editable mock example or an unknown-valued blank process."""
        with lock:
            data, sources = example(blank)
            if task is not None:
                selected = next((item for item in tasks() if item['id'] == task), None)
                if selected is None:
                    raise HTTPException(404, 'Dataset task unavailable')
                data, sources = example(True)
                data.title = 'HA4M · ' + selected['description']
                data.workspace = 'Manual epicyclic gear-train assembly bench; workshop operations lead.'
                data.operator_goal = 'Assess whether tooling, a robot arm or a humanoid could reduce resource use while preserving quality and safe operation.'
                data.functional_unit = 'One correctly completed ' + selected['description'].lower() + ' operation; acceptance specification unresolved.'
                data.boundary = 'Selected annotated operation only; setup, cleanup, rework and full-process overhead remain unmeasured.'
                data.steps = [selected['description']]
                data.source_note = 'HA4M publisher action annotations. Nominal timing is a frame-count observation, not full-process labor or accepted throughput.'
                data.baseline.label = 'Current human process'
                data.candidate.label = 'Automation option — feasibility unresolved'
                data.candidate.change = 'Screen a simple fixture, task-specific robot arm and humanoid against the same task requirements. No robot capability or savings established.'
                sources = {'ha4m_task': selected}
                blank = True
            identifier = uuid.uuid4().hex
            (root / identifier).mkdir()
            return persist({'id': identifier, 'illustrative': not blank, 'sources': sources,
                'data': data.model_dump(), 'status': 'draft', 'result': None, 'error': None})

    @api.get('/tasks')
    def tasks() -> list[dict[str, Any]]:
        """Offer dataset actions without interpreting slideshow length as labor."""
        candidates = [ROOT / 'examples/ha4m-ten-previews/baseline.json', ROOT / 'runs/ha4m-ten-new/baseline.json']
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            return []
        baseline = read_json(source)
        return [{'id': row['action_id'], 'description': row['description'],
                 'nominal_seconds_per_recording': row['mean_nominal_s_per_recording'],
                 'share_of_recorded_frames': row['share_of_recorded_frames'],
                 'source_sha256': sha256(source), 'evidence': 'Publisher annotations; not accepted-output or labor measurements'}
                for row in baseline['actions_by_total_time'] if row['action_id'] != 0]

    @api.get('/{identifier}')
    def load(identifier: str) -> dict[str, Any]:
        """Reopen saved results without regeneration or inference."""
        with lock:
            return get(identifier)

    @api.post('/{identifier}/save')
    def save(identifier: str, body: SaveRequest) -> dict[str, Any]:
        """Save edits and invalidate any comparison of the previous inputs."""
        with lock:
            record = current(identifier, body.revision)
            if record['data'] == body.data.model_dump():
                return record
            old, new = record['data'], body.data
            if any(old[key] != getattr(new, key) for key in ('functional_unit', 'boundary')):
                for option in (new.baseline, new.candidate):
                    option.values = {key: Quantity(unit=unit) for key, unit in FIELDS.items()}
                for gate in new.gates:
                    gate.baseline, gate.candidate = GateState(), GateState()
                new.steps_reviewed = False
            if old['candidate']['change'] != new.candidate.change:
                for key, value in list(new.candidate.values.items()):
                    if value.model_dump() == old['candidate']['values'].get(key):
                        new.candidate.values[key] = Quantity(unit=value.unit)
                for gate in new.gates:
                    gate.candidate = GateState()
            for gate in new.gates:
                previous = next(g for g in old['gates'] if g['category'] == gate.category)
                if gate.requirement != previous['requirement']:
                    gate.baseline, gate.candidate = GateState(), GateState()
            record.update(data=body.data.model_dump(), result=None, error=None, status='draft')
            return persist(record)

    @api.post('/{identifier}/compare')
    def evaluate(identifier: str, revision: int) -> dict[str, Any]:
        """Run deterministic existing evaluators; retain an explicit failure on error."""
        with lock:
            record = current(identifier, revision)
            try:
                record.update(result=compare(Review.model_validate(record['data']), record['illustrative']), status='completed', error=None)
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                record.update(result=None, status='failed', error=f'{type(error).__name__}: {error}')
            return persist(record)

    @api.post('/{identifier}/import')
    def import_source(identifier: str, body: ImportRequest) -> dict[str, Any]:
        """Connect saved extraction to editable review, without transferring performance claims."""
        with lock:
            record = current(identifier, body.revision)
            data = Review.model_validate(record['data'])
            if body.run_id:
                job = jobs.get(body.run_id)
                if job['stage'] != 'completed':
                    raise HTTPException(409, f"Source extraction is {job['stage']}: {job.get('error') or 'no completed protocol available'}")
                path = jobs.path(body.run_id) / 'extracted/extracted-protocol.json'
                protocol = read_json(path)
                steps = [op['physical_operation'] for op in protocol['operations']]
                data.title = protocol.get('title', data.title)
                data.functional_unit = protocol.get('functional_unit', data.functional_unit)
                data.boundary = protocol.get('boundary', data.boundary)
                criteria = protocol.get('acceptance_criteria', [])
                if criteria:
                    next(g for g in data.gates if g.category == 'quality').requirement = '; '.join(c['description'] for c in criteria)
                record['sources'][f'extraction/{body.run_id}'] = {'sha256': sha256(path), 'content': protocol}
                data.source_note = f'Saved video extraction {body.run_id}; model interpretation requires review. /video#{body.run_id}'
                data.source_text = json.dumps(protocol, indent=2)
                record['linked_run'] = body.run_id
            else:
                steps = [line.strip() for line in body.text.splitlines() if line.strip()]
                data.source_text = body.text
                data.source_note = 'User-imported SOP text; each nonempty line is an editable step, not model extraction.'
                record.pop('linked_run', None)
            if not steps:
                raise HTTPException(422, 'Supply at least one procedure step')
            if len(steps) > 100 or any(len(s) > 4000 for s in steps):
                raise HTTPException(422, 'Use at most 100 steps, each at most 4000 characters')
            data.steps, data.steps_reviewed = steps, False
            data.baseline.label = 'Current process'
            data.candidate.label = 'Proposed change'
            data.candidate.change = 'Describe a change for the imported procedure; previous proposal assumptions have been cleared.'
            # A new source is not evidence for old mock numbers or old gate approvals.
            for option in (data.baseline, data.candidate):
                option.values = {key: Quantity(unit=unit) for key, unit in FIELDS.items()}
            for gate in data.gates:
                gate.baseline, gate.candidate = GateState(), GateState()
            record.update(data=Review.model_validate(data.model_dump()).model_dump(), result=None, error=None, status='draft')
            return persist(record)

    @api.get('/{identifier}/export')
    def export(identifier: str) -> FileResponse:
        """Export a checksummed decision, full input sources and calculations for one revision."""
        with lock:
            record = get(identifier)
            path = folder(identifier) / f"v{record['revision']:06d}"
            manifest = read_json(path / 'snapshot.json')
            files = []
            for item in manifest['files']:
                target = contained_file(path, item['path'])
                if target.stat().st_size != item['bytes'] or sha256(target) != item['sha256']:
                    raise HTTPException(409, 'Saved review evidence checksum mismatch')
                files.append(target)
            output = root / '.exports'
            output.mkdir(exist_ok=True)
            archive = output / f"{identifier}-v{record['revision']}.zip"
            with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
                for target in [*files, path / 'snapshot.json']:
                    bundle.write(target, target.name)
            return FileResponse(archive, filename=f"process-decision-{identifier[:8]}-v{record['revision']}.zip")

    return api
