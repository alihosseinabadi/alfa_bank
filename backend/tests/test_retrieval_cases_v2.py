"""The synthetic benchmark has a fixed split and no private profiles."""
import json
from pathlib import Path

def test_synthetic_case_inventory():
    root=Path(__file__).resolve().parents[2]
    cases=json.loads((root/'data/synthetic/retrieval_cases_v2.json').read_text(encoding='utf-8'))
    assert len(cases)==100
    assert len({c['case_id'] for c in cases})==100
    assert sum(c['split']=='dev' for c in cases)==60
    assert sum(c['split']=='test' for c in cases)==40
    assert all(c['task'] or c['behavior'] or c.get('history_topics') or c.get('selected_topics') for c in cases)
    assert all('user_id' not in c and 'user_key' not in c for c in cases)