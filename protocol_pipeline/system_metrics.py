# SPDX-License-Identifier: MPL-2.0
"""Useful artifact facts and explicitly scoped planning economics; never invented measurements."""
import json
import math
from pathlib import Path


def processing_costs(fields: dict, full_metrics: dict) -> dict:
    def value(key):return fields[key]['value']
    def product(*values):return None if any(v is None for v in values) else math.prod(values)
    def metric(number,unit,reason='Calculated from saved planning assumptions; materials excluded'):
        return {'value':number,'unit':unit,'status':'unknown' if number is None else 'calculated','basis':'planning_assumptions','reason':reason}
    costs={};breakdown={}
    for mode in ('manual','autonomous'):
        labor=product(value(mode+'.labor_seconds_per_output'),value('labor_rate_usd_per_hour'),1/3600)
        energy=product(value(mode+'.energy_wh_per_output'),value('electricity_rate_usd_per_kwh'),1/1000)
        consumables=value(mode+'.consumables_usd_per_output')
        breakdown[mode]={'labor_usd':labor,'electricity_usd':energy,'consumables_usd':consumables}
        costs[mode]=None if any(v is None for v in breakdown[mode].values()) else sum(breakdown[mode].values())
    delta=None if any(v is None for v in costs.values()) else costs['manual']-costs['autonomous']
    fixed=None if any(value(k) is None for k in ('manual.annual_fixed_usd','autonomous.annual_fixed_usd')) else value('autonomous.annual_fixed_usd')-value('manual.annual_fixed_usd')
    upfront=full_metrics['incremental_upfront']['value']
    volume=value('annual_volume');horizon=value('horizon_years')
    def annual(n):return None if delta is None or fixed is None or n is None else delta*n-fixed
    saving=annual(volume)
    payback=upfront/saving if upfront is not None and saving is not None and saving>0 else None
    breakeven=(upfront/horizon+fixed)/delta if upfront is not None and horizon and fixed is not None and delta and delta>0 else None
    metrics={**full_metrics,
        'baseline.variable_unit_cost':metric(costs['manual'],'USD/output'),
        'candidate.variable_unit_cost':metric(costs['autonomous'],'USD/output'),
        'annual_operating_saving':metric(saving,'USD/year'),
        'simple_payback_years':metric(payback,'years','Conditional process-only payback; no positive savings means no payback'),
        'horizon_break_even_annual_volume':metric(breakeven,'outputs/year')}
    if saving is not None and saving<=0:
        metrics['simple_payback_years'].update(status='undefined',reason='No positive annual processing saving under these assumptions')
    capacities=[full_metrics[k]['value'] for k in ('baseline.annual_capacity','candidate.annual_capacity')]
    capacity=min(capacities) if all(v is not None for v in capacities) else None
    volumes=sorted({v for v in [volume/2 if volume else None,volume,volume*2 if volume else None,capacity] if v is not None and v>0})
    sensitivity=[]
    for n in volumes:
        s=annual(n)
        sensitivity.append({'annual_outputs':n,'annual_saving_usd':s,'payback_years':upfront/s if upfront is not None and s is not None and s>0 else None,
                            'within_modeled_capacity':None if capacity is None else n<=capacity})
    warnings=['Process-only scenario: material purchase costs and material-loss differences are excluded, not assumed to be zero.',
              'Cycle time, labor, energy, utilization and capital are planning assumptions, not measured machine performance.']
    if payback is not None and value('useful_life_years') is not None and payback>value('useful_life_years'):
        warnings.append(f"Conditional payback ({payback:.1f} years) exceeds the assumed {value('useful_life_years'):g}-year equipment life.")
    if breakeven is not None and capacity is not None and breakeven>capacity:
        warnings.append(f"{horizon:g}-year payback needs about {breakeven:,.0f} outputs/year, above the {capacity:,.0f} shared modeled capacity.")
    missing=[{'key':key,'label':field['label'],'rationale':field['rationale']} for key,field in fields.items() if field['value'] is None]
    return {'metrics':metrics,'breakdown':breakdown,'sensitivity':sensitivity,'warnings':warnings,'missing_inputs':missing,
            'scope':'Labor + electricity + consumables per output; annual savings also subtract the difference in fixed overhead. Conditional on equivalent accepted outputs and no material-loss difference.'}


def artifact_metrics(run: Path, proposal: dict) -> dict:
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    cards=[];boundary_changed=False
    def add(label,value,unit,basis,detail):cards.append({'label':label,'value':value,'unit':unit,'basis':basis,'detail':detail})
    add('Integrated machines',len(proposal['equipment']),'machine(s)','Saved design','Equipment groups in the current design, not physical installations.')
    add('Machine requirements',len(proposal.get('machine_requirements',[])),'requirements','Saved design','Coverage requirements; not verified acceptance results.')
    frames=run/'ingested/manifest.json'
    if frames.is_file():add('Source evidence',len(read(frames)['frames']),'sampled frames','Recorded run','Actual retained video samples used by the vision model.')
    scene_job=run/'scene/job.json'
    if scene_job.is_file():
        job=read(scene_job)
        if job['stage']=='completed':
            folder=run/'scene'/job['attempt_id'];manifest=read(folder/'scene.oi.json');preview=read(folder/'preview.json')
            boundary_changed='user-requested' in manifest.get('storyboard',{}).get('basis','').lower()
            machine_ids={i['id'] for i in preview['instances']}
            asset_ids={i['assetId'] for i in manifest['instances'] if i['id'] in machine_ids}
            assets=[a for a in manifest.get('bundledAssets',[]) if a['id'] in asset_ids]
            add('Native CAD bodies',sum(len(a['parts']) for a in assets),'bodies','CAD-derived','Named geometry bodies within the machine; source workpieces are excluded.')
            if len(assets)==1:
                w,h,d=assets[0]['dimensions']
                add('Static CAD envelope',f'{w:.3f} × {d:.3f} × {h:.3f}','m · W × D × H','CAD-derived','Unscaled assembly bounds; excludes operating/service clearances.')
                add('Machine footprint',round(w*d,3),'m²','CAD-derived','Static width × depth; not the required lab or safety envelope.')
            add('Demo timeline',manifest['animation']['duration'],'seconds','Authored animation','Presentation timing only; do not use as measured production cycle time.')
    return {'cards':cards,'note':'Artifact-derived facts and authored demo values are separate from operating-cost assumptions.'+(' The requested stacking demo changes the task boundary; re-baseline costs before an investment decision.' if boundary_changed else '')}
