# SPDX-License-Identifier: MPL-2.0
"""Separate machine proposals and conditional, editable investment economics."""
import copy
import json
from pathlib import Path

import pytest

from protocol_pipeline.autonomy import AutonomyProposal, evaluate_proposal, validate_coverage, integrate_workcell
from protocol_pipeline.compiler import ProtocolSpecification

ROOT = Path(__file__).resolve().parents[1]


def proposal_fixture(protocol: ProtocolSpecification) -> dict:
    """Explicit synthetic hardware/cost scenario, not a live design or a quotation."""
    def value(amount):
        return {'value': amount, 'rationale': 'Synthetic arithmetic fixture; not measured or quoted'}

    return {
        'title': 'Synthetic robotic transfer workstation',
        'overview': 'Fixture illustrating a separate actuator and tooling proposal.',
        'equipment': [{'id': 'robot', 'name': 'Motorized positioning stage', 'category': 'actuator',
                       'role': 'Move the tool between fixtures under controller command', 'quantity': 2,
                       'unit_cost_usd': value(1000)}],
        'operation_designs': [{'source_operation_id': op.id, 'implementation': 'Use the positioning stage with dedicated tooling',
                              'equipment_ids': ['robot'], 'autonomy': 'proposed_automated',
                              'verification_needed': 'Check alignment and acceptance against the original output'} for op in protocol.operations],
        'remaining_human_tasks': [{'task': 'Replenish supplies', 'frequency': 'per_batch', 'within_process_boundary': True}],
        'assumptions': ['Tooling and fixtures require engineering design'],
        'limitations': ['Synthetic fixture, not a feasible or physically tested machine'],
        'costs': {
            'annual_volume': value(1000), 'labor_rate_usd_per_hour': value(36),
            'electricity_rate_usd_per_kwh': value(.2), 'scheduled_hours_per_year': value(100),
            'utilization': value(.8), 'useful_life_years': value(5), 'horizon_years': value(3),
            'installation_usd': value(100), 'integration_usd': value(200), 'training_usd': value(50),
            'manual': {'labor_seconds_per_output': value(120), 'cycle_seconds_per_output': value(120),
                       'energy_wh_per_output': value(1), 'materials_usd_per_output': value(2),
                       'consumables_usd_per_output': value(1), 'annual_fixed_usd': value(100)},
            'autonomous': {'labor_seconds_per_output': value(10), 'cycle_seconds_per_output': value(60),
                           'energy_wh_per_output': value(10), 'materials_usd_per_output': value(2),
                           'consumables_usd_per_output': value(1), 'annual_fixed_usd': value(200)},
        },
    }


@pytest.fixture
def protocol():
    raw = json.loads((ROOT / 'examples/extraction/recorded-response.json').read_text())['responses'][0]['response']
    return ProtocolSpecification.model_validate(raw)


def test_design_coverage_and_human_activity_rejected(protocol):
    proposal = AutonomyProposal.model_validate(proposal_fixture(protocol))
    validate_coverage(proposal, protocol)
    for mutation in ('human-equipment', 'missing-operation', 'unknown-equipment'):
        raw = proposal_fixture(protocol)
        if mutation == 'human-equipment':
            raw['equipment'][0]['name'] = 'manual_handling'
        elif mutation == 'missing-operation':
            raw['operation_designs'].pop()
        else:
            raw['operation_designs'][0]['equipment_ids'] = ['invented']
        with pytest.raises(ValueError):
            validate_coverage(AutonomyProposal.model_validate(raw), protocol)


def test_attributes_become_requirements_for_one_machine(protocol):
    original=AutonomyProposal.model_validate(proposal_fixture(protocol))
    result=integrate_workcell(original,protocol)
    assert result.design_scope=='integrated_workcell'
    assert len(result.equipment)==1 and result.equipment[0].quantity==1
    assert result.equipment[0].id=='workcell'
    assert result.component_bill_of_materials==original.equipment
    assert all(op.equipment_ids==['workcell'] for op in result.operation_designs)
    assert {r.id for r in result.machine_requirements}>={f'task-{op.id}' for op in protocol.operations}
    assert result.machine_requirements[0].source_refs==protocol.operations[0].source_refs
    assert evaluate_proposal(result,protocol)['equipment_total_usd']==evaluate_proposal(original,protocol)['equipment_total_usd']
    validate_coverage(result,protocol)
    assert integrate_workcell(result,protocol)==result
    assert original.design_scope=='equipment_list'


def test_cost_arithmetic_overrides_and_no_verified_decision(protocol):
    proposal = AutonomyProposal.model_validate(proposal_fixture(protocol))
    original = copy.deepcopy(proposal.model_dump())
    result = evaluate_proposal(proposal, protocol)
    metrics = result['comparison']['base']['metrics']
    assert result['equipment_total_usd'] == 2000
    assert metrics['candidate.upfront_total']['value'] == 2350
    assert metrics['baseline.variable_unit_cost']['value'] == pytest.approx(4.2002)
    assert metrics['candidate.variable_unit_cost']['value'] == pytest.approx(3.102)
    assert metrics['annual_operating_saving']['value'] == pytest.approx(998.2)
    assert metrics['simple_payback_years']['value'] == pytest.approx(2350 / 998.2)
    assert result['comparison']['base']['decision'] == 'undetermined'
    assert result['comparison']['base']['assumptions_present'] is True
    changed = evaluate_proposal(proposal, protocol, {'equipment.robot.unit_cost_usd': 2000})
    assert changed['comparison']['base']['metrics']['candidate.upfront_total']['value'] == 4350
    assert changed['fields']['equipment.robot.unit_cost_usd']['basis'] == 'user_assumption'
    assert proposal.model_dump() == original


def test_unknown_zero_invalid_and_capacity_are_distinct(protocol):
    proposal = AutonomyProposal.model_validate(proposal_fixture(protocol))
    result = evaluate_proposal(proposal, protocol, {'autonomous.labor_seconds_per_output': 0})
    assert result['comparison']['base']['metrics']['candidate.variable_unit_cost']['value'] == pytest.approx(3.002)
    result = evaluate_proposal(proposal, protocol, {'equipment.robot.unit_cost_usd': None})
    assert result['comparison']['base']['metrics']['candidate.upfront_total']['value'] is None
    assert result['comparison']['base']['metrics']['simple_payback_years']['value'] is None
    for edits in ({'made_up': 1}, {'annual_volume': -1}, {'utilization': 2}, {'annual_volume': float('nan')}):
        with pytest.raises(ValueError):
            evaluate_proposal(proposal, protocol, edits)
    result = evaluate_proposal(proposal, protocol, {'annual_volume': 100000})
    assert result['comparison']['base']['status'] == 'infeasible_capacity'
