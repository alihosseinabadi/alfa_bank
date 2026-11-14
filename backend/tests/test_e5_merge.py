import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from merge_e5_segments import verify_segment_identity, verify_vectors

def test_merge_rejects_mismatched_sources():
    first={"index_bundle_id":"a","model":"m","revision":"r","model_files_sha256":{},"dimensions":768,"pooling":"p","batch_size":8,"rows":12}
    second={**first,"start":8,"end":12}
    verify_segment_identity(first,second,12)
    second["index_bundle_id"]="different"
    with pytest.raises(ValueError,match="identity mismatch"):
        verify_segment_identity(first,second,12)

def test_merge_rejects_unwritten_or_invalid_vectors():
    valid=np.zeros((1,768),dtype=np.float32);valid[0,0]=1
    verify_vectors(valid)
    with pytest.raises(ValueError,match="norm"):
        verify_vectors(np.zeros((1,768),dtype=np.float32))
    valid[0,0]=np.nan
    with pytest.raises(ValueError,match="values"):
        verify_vectors(valid)
def test_merge_writes_complete_checked_matrix(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import merge_e5_segments as merge
    from app.data_preparation.history_io import file_hash
    first_dir=tmp_path/"artifacts/e5-vectors"; second_dir=tmp_path/"artifacts/e5-segment2"
    first_dir.mkdir(parents=True);second_dir.mkdir(parents=True)
    common={"index_bundle_id":"a","model":"m","revision":"r","model_files_sha256":{},"dimensions":768,"pooling":"p","batch_size":8}
    first={**common,"rows":16};second={**common,"start":8,"end":16,"runtime_versions":{},"encoder_code_sha256":"x"}
    arr=np.zeros((16,768),dtype=np.float32);arr[:,0]=1
    np.save(first_dir/"vectors.partial.npy",arr,allow_pickle=False)
    np.save(second_dir/"vectors.npy",arr[8:],allow_pickle=False)
    checkpoint=first_dir/"checkpoint.json";checkpoint.write_text(json.dumps({"identity":first,"completed_rows":8}))
    (first_dir/"prefix_validation_v2.json").write_text(json.dumps({"checkpoint_sha256":file_hash(checkpoint),"index_bundle_id":"a","rows_verified":list(range(8)),"matrix_sha256":file_hash(first_dir/"vectors.partial.npy"),"max_abs_difference":0}))
    (second_dir/"manifest.json").write_text(json.dumps({"identity":second,"vectors_sha256":file_hash(second_dir/"vectors.npy")}))
    monkeypatch.setattr(merge,"ROOT",tmp_path)
    monkeypatch.setattr(merge,"load_index",lambda _: (SimpleNamespace(rows=[None]*16),{"bundle_id":"a"}))
    monkeypatch.setattr(sys,"argv",["merge_e5_segments.py","--first-pid","99999999"])
    merge.main()
    np.testing.assert_array_equal(np.load(first_dir/"vectors.npy",allow_pickle=False),arr)
    assert (first_dir/"manifest.json").exists()
    with pytest.raises(FileExistsError):merge.main()