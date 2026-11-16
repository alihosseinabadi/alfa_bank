import pytest
from scripts.audit_judgments_stage10 import audit

def test_audit_never_treats_missing_as_negative():
    pool=[{'case':{'case_id':'q'},'cards':[{'material_key':'a'},{'material_key':'b'}]}]
    row={'case_id':'q','material_key':'a','grade':0,'assessor':'agent','scope':'public excerpt','independent':False}
    out=audit(pool,[row])
    assert out['unjudged_pairs']==1 and out['grades']=={0:1} and not out['ready_to_score']
    with pytest.raises(ValueError,match='duplicate judgment'): audit(pool,[row,row])
    with pytest.raises(ValueError,match='outside pool'): audit(pool,[dict(row,material_key='outside')])
    with pytest.raises(ValueError,match='provenance'): audit(pool,[dict(row,assessor='')])
