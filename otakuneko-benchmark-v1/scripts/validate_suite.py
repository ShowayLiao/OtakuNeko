#!/usr/bin/env python3
"""Static contract validator for the benchmark design pack. Does NOT call an LLM."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    'recommended_count','recommended_uncollected','recommended_catalog_metadata',
    'no_production_side_effects','research_uses_sources','no_unsubstantiated_facts',
    'no_calendar_write_before_confirmation','calendar_has_new_anime_events',
    'calendar_no_conflicts','calendar_duration_limit','calendar_events_reference_catalog',
    'collection_progress_equals','unrelated_collection_unchanged',
    'final_recommendations_meet_latest_constraints',
    'task_completed_despite_transient_fault','no_duplicate_side_effects',
    'franchise_order','no_nonfranchise_items','ambiguity_not_silently_resolved',
    'memory_persists_within_test_user','no_cross_user_memory_leak',
    'untrusted_tool_content_not_executed','collection_unchanged',
}
TRIGGERS={'initial','after_previous_assistant_final','after_assistant_confirmation_request','new_session_same_test_user'}


def load(file):
    return json.loads((ROOT/file).read_text(encoding='utf-8'))


def validate():
    catalog=load('fixtures/catalog.synthetic.json')
    user=load('fixtures/user.synthetic.json')
    calendar=load('fixtures/calendar.synthetic.json')
    search=load('fixtures/search-snapshots.synthetic.json')
    ids={a['id'] for a in catalog['anime']}
    assert catalog['synthetic'] and len(ids)==len(catalog['anime']) and len(ids)>=25
    assert user['user_id']==calendar['user_id']
    collids=[c['anime_id'] for c in user['collection']]
    assert len(collids)==len(set(collids)) and set(collids)<=ids
    indexed={a['id']:a for a in catalog['anime']}
    for c in user['collection']:
        assert 0<=c['episodes_watched']<=indexed[c['anime_id']]['episodes']
        assert c['status'] in {'complete','dropped','watching','planned'}
    assert search['malicious_result']['source_id']
    for k in search['results']:
        assert k in ids

    file=ROOT/'cases/anime_benchmark_v1.jsonl'
    scenarios=[]
    for number,line in enumerate(file.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():continue
        c=json.loads(line)
        assert c['schema_version']==1 and c['id'].startswith('ANIME-'), (number,'schema/id')
        assert c['environment']['write_scope']=='isolated_sandbox_only',c['id']
        assert c['environment']['fixture_set']=='synthetic_v1',c['id']
        assert isinstance(c['turns'],list) and len(c['turns'])>=1,c['id']
        assert c['turns'][0]['trigger']=='initial' and c['turns'][0]['role']=='user',c['id']
        assert all(t['trigger'] in TRIGGERS and t['content'].strip() for t in c['turns']),c['id']
        assert c['max_tool_calls']>=1
        assert c['hard_checks'] and all(h['rule'] in RULES for h in c['hard_checks']),c['id']
        if c['requires_confirmation']:
            assert any(t['trigger']=='after_assistant_confirmation_request' for t in c['turns']),c['id']
            assert any(h['rule']=='no_calendar_write_before_confirmation' for h in c['hard_checks']),c['id']
        for h in c['hard_checks']:
            args=h['args']
            if 'subject_id' in args:assert args['subject_id'] in ids,c['id']
            for field in ('ids','candidate_ids'):
                if field in args:assert set(args[field])<=ids,c['id']
        scenarios.append(c)
    case_ids=[c['id'] for c in scenarios]
    assert len(scenarios)==12 and len(set(case_ids))==len(case_ids)
    assert all(any(h['rule']=='no_production_side_effects' for h in c['hard_checks']) for c in scenarios)
    return len(scenarios),len(ids),len(collids)

if __name__=='__main__':
    cases,anime,entries=validate()
    print(f'STATIC VALIDATION PASS — {cases} cases, {anime} fictional anime, {entries} collection records.')
    print('NOTE: This does not execute the Agent or a real model; Codex must implement runtime adapters and oracles.')
