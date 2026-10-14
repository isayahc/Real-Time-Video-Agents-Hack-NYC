"""Single-command, evidence-labeled accounting loop and coil scene demonstration."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, cast

from .design import SceneRequest, build_design, write_json
from .iteration import (
    OBJECTIVES, OutcomeRecord, OutcomeRequest, PredictionRecord, PredictionRequest,
    RevisionRequest, observe, predict, revise,
)

LABELS = {
    'cost_usd_per_accepted': 'Cost per accepted output (USD)',
    'labor_s_per_accepted': 'Attended labor per accepted output (operator-s)',
    'electricity_wh_per_accepted': 'Electricity per accepted output (Wh)',
    'stock_g_per_accepted': 'Consumed stock per accepted output (g)',
    'unrecovered_waste_g_per_accepted': 'Unrecovered waste per accepted output (g)',
    'accepted_outputs_per_hour': 'Accepted outputs per hour',
}


def value_text(value: float | None, status: str = 'unknown') -> str:
    """Format zero as a real value and preserve unknown/undefined distinctions."""
    return f'{value:,.4f}'.rstrip('0').rstrip('.') if value is not None else status.replace('_', ' ').capitalize()


def report_markdown(summary: dict[str, Any]) -> str:
    """Render evaluator results with prominent provenance and unresolved gates."""
    rows = []
    for key, values in summary['illustrative_loop']['metrics'].items():
        rows.append('| ' + LABELS[key] + ' | ' + ' | '.join(
            value_text(values[stage]['value'], values[stage]['status'])
            for stage in ('prediction', 'illustrative_outcome', 'revision')) + ' |')
    loop = summary['illustrative_loop']
    investment = loop['investment']
    design = summary['coil_scene']
    lines = [
        '# Resource-efficiency loop demo', '',
        '**Evidence: illustrative arithmetic plus an existing coil concept. No physical experiment, live model inference or demonstrated coil savings.**', '',
        '## Illustrative accounting loop', '',
        'The financial fixture exercises predict → attach outcome → compare → revise → reevaluate. Its numbers are fabricated examples and do not describe CW-02.', '',
        '| Metric | Prediction v1 | Illustrative outcome | Revision v2 prediction |',
        '| --- | ---: | ---: | ---: |', *rows, '',
        f"Revision assessment: **{loop['revision_conclusion'].replace('_', ' ')}**.", '',
        'Flagged deviations: ' + (', '.join(loop['flagged_metrics']) or 'None calculable outside tolerance') + '.', '',
        'Predicted improvements versus illustrative outcome: ' + (', '.join(loop['predicted_improvements']) or 'None calculated') + '.', '',
        'Predicted regressions versus illustrative outcome: ' + (', '.join(loop['predicted_regressions']) or 'None calculated') + '.', '',
        'The revised result remains a prediction. Lower labor and cost can coexist with higher electricity use.', '',
        '### Illustrative investment results', '',
        '| Metric | Prediction v1 | Illustrative outcome update | Revision v2 |', '| --- | ---: | ---: | ---: |',
    ]
    for key, label in [('annual_operating_saving', 'Annual operating saving (USD/year)'),
                       ('simple_payback_years', 'Simple payback (years)'),
                       ('horizon_net_saving', 'Undiscounted horizon saving (USD)')]:
        lines.append('| ' + label + ' | ' + ' | '.join(value_text(investment[stage]['metrics'][key]['value'], investment[stage]['metrics'][key]['status'])
            for stage in ('prediction', 'illustrative_outcome', 'revision')) + ' |')
    lines += ['', 'These figures are conditional synthetic calculations. The outcome update retains the prediction’s fixed costs, demand, baseline and capacity factors.', '',
              '## CW-02 coil concept and scene', '',
              '**This is a separate evidence lane. The illustrative cost/savings figures above are not assigned to the coil apparatus.**', '',
              f"Actual coil investment decision: **{summary['coil_investment_decision']}**.", '',
              f"Actual coil unit cost: **{value_text(summary['coil_unit_cost'])}**. Output equivalence and full-process measurements remain unresolved.", '']
    if design['status'] == 'artifacts_created':
        lines += [f"Mode: **{design['mode']}** (existing concept replay; no generation call).", '',
                  f"Native OpenIndustries scene roundtrip: **{design['portable_roundtrip']}**; {design['parts']} mesh parts and {design['retained_bom_lines']} retained BOM lines.", '',
                  f"Forma schema valid: **{design['schema_valid']}**. Deterministic design validation passed: **{design['deterministic_is_valid']}**.", '',
                  'The meshes are schematic concept geometry. Electrical/mechanical completion, requirement coverage, collision/clearance and physical equivalence are unverified.', '',
                  'OpenIndustries MCP created/read a local empty planning room; native import/export populated the portable scene. No cloud scene was published.', '',
                  '[Portable scene](coil-design/apparatus.oi.json) · [Design manifest](coil-design/design-manifest.json)', '']
    else:
        lines += ['Scene handoff: **explicitly skipped in accounting-only mode**. No scene import/MCP execution is claimed.', '']
    lines += ['## Record lineage and artifacts', '',
              '| Record | Meaning | SHA-256 |', '| --- | --- | --- |']
    for item in summary['records']:
        lines.append(f"| [{item['id']}](records/{item['id']}.json) | {item['description']} | `{item['sha256']}` |")
    lines += ['', '[Machine-readable summary](demo-summary.json)', '',
              '## Remaining evidence', '',
              '- Review the actual video and source protocol, including off-camera preparation.',
              '- Verify released-coil acceptance criteria and downstream functional equivalence.',
              '- Measure the full manual/apparatus workflow: labor, elapsed time, energy, input material and waste.',
              '- Source deployment, maintenance, facility and labor prices and verify production demand/capacity.',
              '- Configure a live generation provider for actual synthesis; record another measured run to test revisions.', '',
              'No fabricated observation is promoted to physical evidence. Original predictions remain unchanged.', '']
    return '\n'.join(lines)


def report_html(summary: dict[str, Any]) -> str:
    """Build a self-contained, escaped HTML report without scripts or external assets."""
    loop = summary['illustrative_loop']
    rows = []
    for key, values in loop['metrics'].items():
        cells = ''.join('<td>' + html.escape(value_text(values[stage]['value'], values[stage]['status'])) + '</td>'
                        for stage in ('prediction', 'illustrative_outcome', 'revision'))
        rows.append('<tr><th scope="row">' + html.escape(LABELS[key]) + '</th>' + cells + '</tr>')
    escaped_markdown = html.escape(report_markdown(summary))
    investment_rows = []
    for key, label in [('annual_operating_saving', 'Annual operating saving (USD/year)'),
                       ('simple_payback_years', 'Simple payback (years)'),
                       ('horizon_net_saving', 'Undiscounted horizon saving (USD)')]:
        cells = ''.join('<td>' + html.escape(value_text(loop['investment'][stage]['metrics'][key]['value'],
                                                       loop['investment'][stage]['metrics'][key]['status'])) + '</td>'
                        for stage in ('prediction', 'illustrative_outcome', 'revision'))
        investment_rows.append('<tr><th scope="row">' + html.escape(label) + '</th>' + cells + '</tr>')
    scene = summary['coil_scene']
    coil_status = ('Scene replay verified: ' + str(scene['parts']) + ' schematic mesh parts; '
                   + str(scene['retained_bom_lines']) + ' BOM lines. Deterministic design validation passed: '
                   + str(scene['deterministic_is_valid']) + '.' if scene['status'] == 'artifacts_created'
                   else 'Scene/MCP handoff explicitly skipped in accounting-only mode.')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resource-efficiency loop demo</title><style>
body{font:16px/1.6 system-ui,sans-serif;color:#15283b;background:#f5f7fa;margin:0}main{max-width:1080px;margin:auto;padding:32px 20px}
h1{font-size:2.2rem;line-height:1.2}.notice{background:#fff1cb;border-left:5px solid #af7000;padding:16px;border-radius:4px}
.card{background:white;border:1px solid #dbe3eb;border-radius:12px;padding:20px;margin:24px 0}.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:650px}th,td{padding:12px;text-align:left;border-bottom:1px solid #dbe3eb}td{text-align:right}thead{background:#ecf2f7}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.65 ui-monospace,monospace}a{color:#145d92}
</style><main><h1>Resource-efficiency loop</h1><p class="notice"><strong>Illustrative evidence only.</strong> The arithmetic fixture and coil concept are separate. No physical run, live inference or demonstrated coil savings.</p>
<section class="card"><h2>Predict → compare → revise</h2><div class="scroll"><table><thead><tr><th>Metric</th><th>Prediction v1</th><th>Illustrative outcome</th><th>Revision v2 prediction</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div></section>
<section class="card"><h2>Illustrative investment comparison</h2><p>Fabricated arithmetic fixture; these savings do not describe the coil apparatus.</p><div class="scroll"><table><thead><tr><th>Metric</th><th>Prediction v1</th><th>Illustrative outcome update</th><th>Revision v2</th></tr></thead><tbody>''' + ''.join(investment_rows) + '''</tbody></table></div></section>
<section class="card"><h2>CW-02: measurement pending</h2><p>Actual coil cost: <strong>''' + html.escape(value_text(summary['coil_unit_cost'])) + '''</strong>. Investment decision: <strong>''' + html.escape(summary['coil_investment_decision']) + '''</strong>.</p><p>''' + html.escape(coil_status) + '''</p><p>Output equivalence, full-process measurements and design completion remain unresolved.</p></section>
<section class="card"><h2>Complete evidence report</h2><p><a href="report.md">Markdown report</a> · <a href="demo-summary.json">Structured summary</a></p><details><summary>Read provenance, tradeoffs and remaining evidence</summary><pre>''' + escaped_markdown + '</pre></details></section></main></html>\n'


def run_demo(output: Path, examples_root: Path, forma_root: Path | None = None,
             oi_root: Path | None = None, coil_project: Path | None = None,
             accounting_only: bool = False) -> dict[str, Any]:
    """Run two clearly separated evidence lanes and exclusively create their report."""
    examples_root = examples_root.resolve()
    paths = {
        'prediction': examples_root / 'iteration-loop/prediction.json',
        'outcome': examples_root / 'iteration-loop/outcome.json',
        'revision': examples_root / 'iteration-loop/revision.json',
        'coil_prediction': examples_root / 'iteration-loop/coil-prediction-unknown.json',
        'coil_requirements': examples_root / 'design-handoff/coil-requirements.json',
    }
    for path in paths.values():
        if not path.is_file():
            raise ValueError(f'Missing demo fixture: {path.name}; run from the repo or supply --examples-root')
    prediction_request = PredictionRequest.model_validate_json(paths['prediction'].read_text())
    outcome_request = OutcomeRequest.model_validate_json(paths['outcome'].read_text())
    revision_request = RevisionRequest.model_validate_json(paths['revision'].read_text())
    coil_request = PredictionRequest.model_validate_json(paths['coil_prediction'].read_text())
    if outcome_request.evidence_kind != 'illustrative':
        raise ValueError('The demo outcome must be explicitly illustrative')
    if not accounting_only and (oi_root is None or coil_project is None or not coil_project.is_file()):
        raise ValueError('Full demo requires --oi-root and a coil project; use --accounting-only to explicitly skip scene handoff')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stage = 'accounting_loop'
    try:
        store = output / 'records'
        p1 = predict(store, 'p1', prediction_request)
        o1 = observe(store, 'o1', 'p1', outcome_request)
        p2 = revise(store, 'p2', 'p1', 'o1', revision_request)
        coil = predict(store, 'coil-p1', coil_request)
        original = cast(PredictionRecord, p1.record)
        observed = cast(OutcomeRecord, o1.record)
        revised = cast(PredictionRecord, p2.record)
        coil_record = cast(PredictionRecord, coil.record)
        scene: dict[str, Any] = {'status': 'skipped_accounting_only'}
        if not accounting_only:
            stage = 'coil_scene'
            design = build_design(paths['coil_requirements'], output / 'coil-design', forma_root,
                oi_root, 'replay', 'Replay the existing CW-02 concept; scene import evidence only',
                SceneRequest(name='CW-02 concept / unmeasured'), replay_project=coil_project,
                store=store, prediction_id='coil-p1')
            scene = {'status': design['status'], 'mode': design['mode'],
                **{key: design['openindustries'][key] for key in ('parts', 'retained_bom_lines', 'portable_roundtrip')},
                **{key: design['forma'][key] for key in ('schema_valid', 'deterministic_is_valid')}}
        metric_rows = {key: {label: record.process_report.metrics[key].model_dump()
            for label, record in [('prediction', original), ('illustrative_outcome', observed), ('revision', revised)]}
            for key in OBJECTIVES}
        investment_rows = {label: record.investment_report.base.model_dump()
            for label, record in [('prediction', original), ('illustrative_outcome', observed), ('revision', revised)]
            if record.investment_report is not None}
        if len(investment_rows) != 3 or revised.revision is None or coil_record.investment_report is None:
            raise ValueError('Demo fixtures must include both evaluator stages')
        summary: dict[str, Any] = {
            'schema_version': 1, 'status': 'accounting_only' if accounting_only else 'demo_completed',
            'physical_validation': False, 'live_inference': False,
            'evidence_statement': 'Fabricated illustrative accounting fixture and separately replayed CW-02 concept; no demonstrated coil savings',
            'source_fixture_sha256': {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
            'illustrative_loop': {'metrics': metric_rows, 'investment': investment_rows,
                'revision_conclusion': revised.revision.conclusion,
                'flagged_metrics': [key for key, value in observed.deviation.metrics.items() if value.outside_tolerance],
                'predicted_improvements': revised.revision.predicted_improvements,
                'predicted_regressions': revised.revision.predicted_regressions},
            'coil_scene': scene, 'coil_investment_decision': coil_record.investment_report.base.decision,
            'coil_unit_cost': coil_record.process_report.metrics['cost_usd_per_accepted'].value,
            'records': [{'id': envelope.record.id, 'sha256': envelope.sha256, 'description': description}
                for envelope, description in [(p1, 'Illustrative prediction v1'), (o1, 'Fabricated illustrative outcome'),
                                             (p2, 'Illustrative revision v2'), (coil, 'Actual coil concept: unknown operating inputs')]],
        }
        stage = 'report'
        write_json(output / 'demo-summary.json', summary)
        with (output / 'report.md').open('x') as destination:
            destination.write(report_markdown(summary))
        with (output / 'report.html').open('x') as destination:
            destination.write(report_html(summary))
        return summary
    except (OSError, ValueError, RuntimeError) as error:
        write_json(output / 'demo-failure.json', {'status': 'failed', 'stage': stage,
            'error_type': type(error).__name__, 'physical_validation': False})
        raise
