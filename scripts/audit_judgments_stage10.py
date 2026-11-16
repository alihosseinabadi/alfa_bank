"""Audit blinded-pool judgments without treating unjudged materials as negatives."""
import argparse, hashlib, json
from collections import Counter
from pathlib import Path

def audit(pool, judgments):
    valid = {}
    for entry in pool:
        cid = entry['case']['case_id']
        if cid in valid: raise ValueError('duplicate case id')
        keys = [c['material_key'] for c in entry['cards']]
        if len(keys) != len(set(keys)): raise ValueError('duplicate material in case')
        valid[cid] = set(keys)
    seen = set(); grades = Counter()
    for label in judgments:
        key = (label['case_id'], label['material_key'])
        if key in seen: raise ValueError('duplicate judgment')
        if key[0] not in valid or key[1] not in valid[key[0]]: raise ValueError('judgment outside pool')
        if type(label['grade']) is not int or label['grade'] not in (0,1,2,3): raise ValueError('invalid grade')
        if not label.get('assessor') or not label.get('scope') or label.get('independent') not in (True,False): raise ValueError('missing assessor provenance')
        seen.add(key); grades[label['grade']] += 1
    expected = {(cid,k) for cid,keys in valid.items() for k in keys}
    complete = sum(all((cid,k) in seen for k in keys) for cid,keys in valid.items())
    return {'cases':len(valid),'pairs':len(expected),'judged_pairs':len(seen),'unjudged_pairs':len(expected-seen),
            'fully_judged_cases':complete,'grades':dict(grades),'ready_to_score':expected == seen}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--pool',required=True,type=Path); parser.add_argument('--judgments',required=True,type=Path)
    args=parser.parse_args(); pool=args.pool.read_bytes(); labels=args.judgments.read_bytes()
    result=audit(json.loads(pool),json.loads(labels))
    result.update(pool_sha256=hashlib.sha256(pool).hexdigest(),judgments_sha256=hashlib.sha256(labels).hexdigest())
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
