# SPDX-License-Identifier: MPL-2.0
import copy
import json

import pytest

from protocol_pipeline.system_metrics import processing_costs, artifact_metrics


def test_processing_only_costs_do_not_fill_unknown_material_prices():
    values={'labor_rate_usd_per_hour':30,'electricity_rate_usd_per_kwh':.15,'annual_volume':10000,'horizon_years':5,'useful_life_years':7,
            'manual.labor_seconds_per_output':40,'autonomous.labor_seconds_per_output':3,
            'manual.energy_wh_per_output':.5,'autonomous.energy_wh_per_output':2.5,
            'manual.consumables_usd_per_output':.02,'autonomous.consumables_usd_per_output':.03,
            'manual.annual_fixed_usd':500,'autonomous.annual_fixed_usd':2500,
            'manual.materials_usd_per_output':None,'autonomous.materials_usd_per_output':None}
    fields={k:{'value':v,'label':k,'rationale':'Fixture'} for k,v in values.items()}
    metrics={'incremental_upfront':{'value':44000},'baseline.annual_capacity':{'value':16000},'candidate.annual_capacity':{'value':24000}}
    original=copy.deepcopy(fields)
    result=processing_costs(fields,metrics)
    assert result['metrics']['baseline.variable_unit_cost']['value']==pytest.approx(.3534083333)
    assert result['metrics']['candidate.variable_unit_cost']['value']==pytest.approx(.055375)
    assert result['metrics']['annual_operating_saving']['value']==pytest.approx(980.3333333)
    assert result['metrics']['simple_payback_years']['value']==pytest.approx(44.882693)
    assert len(result['missing_inputs'])==2
    assert fields==original
    assert any('exceeds' in warning for warning in result['warnings'])
    fields['annual_volume']['value']=1000
    assert processing_costs(fields,metrics)['metrics']['simple_payback_years']['status']=='undefined'
    fields['manual.labor_seconds_per_output']['value']=None
    assert processing_costs(fields,metrics)['metrics']['baseline.variable_unit_cost']['value'] is None


def test_artifact_metrics_exclude_workpieces_and_label_animation(tmp_path):
    folder=tmp_path/'scene'/'attempt';folder.mkdir(parents=True)
    (tmp_path/'scene/job.json').write_text(json.dumps({'stage':'completed','attempt_id':'attempt'}))
    (folder/'preview.json').write_text(json.dumps({'instances':[{'id':'cell','equipment_id':'workcell'}]}))
    (folder/'scene.oi.json').write_text(json.dumps({'instances':[{'id':'cell','assetId':'machine'},{'id':'paper','assetId':'paper'}],
        'bundledAssets':[{'id':'machine','dimensions':[1.1,.445,.7],'parts':[{},{}]},{'id':'paper','parts':[{}]}],
        'animation':{'duration':24},'storyboard':{'basis':'User-requested stacking'}}))
    report=artifact_metrics(tmp_path,{'equipment':[{}],'machine_requirements':[{}]})
    cards={row['label']:row for row in report['cards']}
    assert cards['Native CAD bodies']['value']==2
    assert cards['Machine footprint']['value']==.77
    assert cards['Demo timeline']['basis']=='Authored animation'
    assert 're-baseline' in report['note']
