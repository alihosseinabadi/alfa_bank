"""Checked public catalog adapter and atomic, pickle-free search snapshots."""
import json
import os
import tempfile
from pathlib import Path
import numpy as np
import scipy
from scipy.sparse import save_npz,load_npz
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from .history_io import resolve_bundle,load_catalog,read_jsonl,write_json,write_jsonl,verify_files,file_hash
from app.ml.profile_contracts import CONTEXT_VERSION,PROFILE_SCHEMA_VERSION
from app.ml.profile_policy import fingerprint
from app.ml.retrieval_contracts import SearchMaterial,PublicSearchChunk,RetrievalPolicy,RETRIEVAL_VERSION,TOKENIZER_VERSION
from app.ml.tfidf_retriever import TfidfRetriever,tokenize_text

PAYLOAD_FILES={"materials.jsonl","rows.jsonl","vocabulary.json","idf.npy","matrix.npz"}

def catalog_search_inputs(catalog_dir):
    path=resolve_bundle(Path(catalog_dir))
    materials,_,_,manifest=load_catalog(Path(catalog_dir))
    converted=[SearchMaterial(**{key:getattr(m,key) for key in SearchMaterial.model_fields}) for m in materials]
    blocks={b["block_id"]:b for b in read_jsonl(path/"content_blocks.jsonl")}
    chunks=[]
    for row in read_jsonl(path/"public_chunks.jsonl"):
        sources=[blocks[key] for key in row["source_block_ids"]]
        if not sources or row["access_scope"]!="public" or row.get("entitlement_key") is not None:
            raise ValueError("Invalid public chunk provenance")
        if any(b["material_key"]!=row["material_key"] or b["access_scope"]!="public" or b.get("entitlement_key") is not None for b in sources):
            raise ValueError("Protected or cross-material source block")
        kind="metadata" if all(b["content_kind"]=="metadata" for b in sources) else "body"
        chunks.append(PublicSearchChunk(**{key:row[key] for key in ("chunk_id","material_key","text","source_block_ids","access_scope")},content_kind=kind))
    return converted,chunks,manifest

def save_index(index,output_dir,metadata):
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".search-building-",dir=output) as directory:
        stage=Path(directory)
        write_jsonl(stage/"materials.jsonl",[index.materials[k] for k in sorted(index.materials)])
        write_jsonl(stage/"rows.jsonl",index.rows)
        write_json(stage/"vocabulary.json",index.vectorizer.vocabulary_ if index.vectorizer else {})
        np.save(stage/"idf.npy",index.vectorizer.idf_ if index.vectorizer else np.array([],dtype=np.float64),allow_pickle=False)
        save_npz(stage/"matrix.npz",index.matrix)
        hashes={p.name:file_hash(p) for p in sorted(stage.iterdir())}
        payload={"retrieval_version":RETRIEVAL_VERSION,"tokenizer_version":TOKENIZER_VERSION,
            "context_version":CONTEXT_VERSION,"profile_version":PROFILE_SCHEMA_VERSION,
            "sklearn_version":sklearn.__version__,"numpy_version":np.__version__,"scipy_version":scipy.__version__,
            "policy":index.policy.model_dump(),"files":hashes,**metadata}
        identity=fingerprint(payload)
        write_json(stage/"manifest.json",dict(payload,bundle_id=identity))
        final=output/identity
        if final.exists():
            existing=json.loads((final/"manifest.json").read_text())
            verify_files(final,existing)
            if existing!=dict(payload,bundle_id=identity):raise ValueError("Immutable retrieval snapshot collision")
        else:os.replace(stage,final)
        (output/"CURRENT.tmp").write_text(identity+"\n")
        os.replace(output/"CURRENT.tmp",output/"CURRENT")
    return final

def load_index(index_dir,*,catalog_bundle_id=None,profiles_catalog_bundle_id=None):
    path=resolve_bundle(Path(index_dir))
    manifest=json.loads((path/"manifest.json").read_text())
    payload={key:value for key,value in manifest.items() if key!="bundle_id"}
    if fingerprint(payload)!=manifest["bundle_id"]:raise ValueError("Retrieval manifest identity mismatch")
    expected={"retrieval_version":RETRIEVAL_VERSION,"tokenizer_version":TOKENIZER_VERSION,
        "context_version":CONTEXT_VERSION,"profile_version":PROFILE_SCHEMA_VERSION,
        "sklearn_version":sklearn.__version__,"numpy_version":np.__version__,"scipy_version":scipy.__version__}
    if any(manifest.get(key)!=value for key,value in expected.items()):raise ValueError("Incompatible retrieval/runtime version")
    if set(manifest["files"])!=PAYLOAD_FILES:raise ValueError("Incomplete retrieval payload")
    for identity in (catalog_bundle_id,profiles_catalog_bundle_id):
        if identity is not None and manifest["catalog_bundle_id"]!=identity:raise ValueError("Incompatible retrieval/catalog/profile snapshot")
    verify_files(path,manifest)
    index=TfidfRetriever(RetrievalPolicy.model_validate(manifest["policy"]))
    materials=read_jsonl(path/"materials.jsonl",SearchMaterial)
    index.materials={m.material_key:m for m in materials}
    if len(index.materials)!=len(materials):raise ValueError("Duplicate saved material")
    index.rows=read_jsonl(path/"rows.jsonl",PublicSearchChunk)
    vocabulary=json.loads((path/"vocabulary.json").read_text())
    idf=np.load(path/"idf.npy",allow_pickle=False)
    index.matrix=load_npz(path/"matrix.npz").tocsr()
    if index.matrix.shape!=(len(index.rows),len(vocabulary)) or len(idf)!=len(vocabulary):
        raise ValueError("Retrieval matrix shape mismatch")
    if sorted(vocabulary.values())!=list(range(len(vocabulary))) or not np.isfinite(index.matrix.data).all() or not np.isfinite(idf).all():
        raise ValueError("Invalid retrieval numeric payload")
    owners,rows=__import__("app.ml.tfidf_retriever",fromlist=["prepare_corpus"]).prepare_corpus(materials,index.rows)
    if rows!=index.rows:raise ValueError("Noncanonical saved search rows")
    if vocabulary:
        index.vectorizer=TfidfVectorizer(tokenizer=tokenize_text,token_pattern=None,lowercase=False,
            ngram_range=(1,index.policy.ngram_max),min_df=1,sublinear_tf=True,norm="l2",dtype=np.float64,vocabulary=vocabulary)
        index.vectorizer.idf_=idf
    return index,manifest

def build_index(catalog_dir,output_dir,root,policy=None):
    materials,chunks,catalog=catalog_search_inputs(catalog_dir)
    index=TfidfRetriever(policy).fit(materials,chunks)
    paths=[root/"backend/app/ml"/name for name in ("retrieval_contracts.py","tfidf_retriever.py","retrieval_baselines.py")]
    paths += [Path(__file__),root/"scripts/build_retrieval_index.py",root/"scripts/search_materials.py"]
    metadata={"catalog_bundle_id":catalog["bundle_id"],
        "catalog_files":catalog["files"],"code_sha256":{str(p.relative_to(root)):file_hash(p) for p in sorted(paths)},
        "audit":{"materials":len(index.materials),"indexed_materials":len({r.material_key for r in index.rows}),
                 "source_public_chunks":len(chunks),"deduplicated_public_chunks":len(index.rows),
                 "protected_chunks":0,"paid_body_chunks":0,"vocabulary_size":index.matrix.shape[1],"matrix_nnz":index.matrix.nnz}}
    return save_index(index,output_dir,metadata),metadata["audit"]

def verify_index(index_dir,catalog_dir):
    materials,chunks,catalog=catalog_search_inputs(catalog_dir)
    loaded,manifest=load_index(index_dir,catalog_bundle_id=catalog["bundle_id"])
    if manifest["catalog_files"]!=catalog["files"]:raise ValueError("Catalog provenance mismatch")
    rebuilt=TfidfRetriever(loaded.policy).fit(materials,chunks)
    if loaded.rows!=rebuilt.rows or loaded.materials!=rebuilt.materials:
        raise ValueError("Search/catalog reconstruction mismatch")
    if (loaded.vectorizer.vocabulary_ if loaded.vectorizer else {})!=(rebuilt.vectorizer.vocabulary_ if rebuilt.vectorizer else {}):
        raise ValueError("Search vocabulary reconstruction mismatch")
    if loaded.matrix.shape!=rebuilt.matrix.shape or (loaded.matrix-rebuilt.matrix).nnz:
        raise ValueError("Search matrix reconstruction mismatch")
    if loaded.vectorizer is not None and not np.array_equal(loaded.vectorizer.idf_,rebuilt.vectorizer.idf_):
        raise ValueError("Search IDF reconstruction mismatch")
    return manifest,manifest["audit"]
