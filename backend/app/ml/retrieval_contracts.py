"""Public search contracts for the TF-IDF MVP."""
from typing import Literal
from pydantic import Field
from .profile_contracts import ProfileRecord,MaterialFormat,ContinuationCandidate

RETRIEVAL_VERSION="tfidf-search-v1"
TOKENIZER_VERSION="ru-lexical-v1"

# Light (stemmed) retrieval path. Versioned separately so the legacy index and
# policy stay byte-identical until the new path is validated.
LIGHT_RETRIEVAL_VERSION="light-hybrid-search-v1"
LIGHT_TOKENIZER_VERSION="ru-stem-v1"

class SearchMaterial(ProfileRecord):
    material_key:str
    title:str
    item_type:MaterialFormat
    url:str
    topics:list[str]=Field(default_factory=list)
    tags:list[str]=Field(default_factory=list)
    access_type:str
    listed_price:float|None=Field(default=None,ge=0)
    duration_minutes:float|None=Field(default=None,gt=0)
    is_discoverable:bool
    url_state:str
    content_hash:str=""

class PublicSearchChunk(ProfileRecord):
    chunk_id:str
    material_key:str
    text:str
    source_block_ids:list[str]
    access_scope:Literal["public"]="public"
    content_kind:Literal["metadata","body"]="metadata"

class RetrievalPolicy(ProfileRecord):
    version:str=RETRIEVAL_VERSION
    tokenizer_version:str=TOKENIZER_VERSION
    min_similarity:float=Field(default=0.04,gt=0,le=1)
    min_query_coverage:float=Field(default=0.3,ge=0,le=1)
    max_candidates:int=Field(default=50,ge=1,le=50)
    ngram_max:int=Field(default=2,ge=1,le=2)
    starter_keys:list[str]=Field(default_factory=list)

class LightRetrievalPolicy(ProfileRecord):
    """Policy for the stemmed light hybrid. Every parameter is explicit and frozen."""
    version:str=LIGHT_RETRIEVAL_VERSION
    tokenizer_version:str=LIGHT_TOKENIZER_VERSION
    min_query_coverage:float=Field(default=0.3,ge=0,le=1)
    max_candidates:int=Field(default=50,ge=1,le=50)
    rank_constant:int=Field(default=60,ge=1)
    channel_weights:dict[str,float]=Field(
        default_factory=lambda:{"bm25_stem":1.0,"char_ngram":0.8,"lsa":0.6})
    char_ngram_range:tuple[int,int]=Field(default=(3,5))
    char_min_similarity:float=Field(default=0.15,gt=0,le=1)
    lsa_components:int=Field(default=120,ge=2,le=512)
    lsa_random_state:int=0
    lsa_min_similarity:float=Field(default=0.15,gt=0,le=1)
    synonym_weight:float=Field(default=0.25,ge=0,le=1)
    starter_keys:list[str]=Field(default_factory=list)

class NextStep(ProfileRecord):
    action:Literal["open_material"]="open_material"
    label:str="Открыть материал"
    url:str

class SearchCandidate(ProfileRecord):
    material_key:str
    title:str
    item_type:MaterialFormat
    url:str
    access_badge:str
    listed_price:float|None
    duration_minutes:float|None
    duration_fit:Literal["fits","unknown","not_requested"]
    price_is_unknown:bool
    retrieval_score:float=Field(ge=0,le=1)
    retrieval_version:str
    reason_code:str
    reason:str
    matched_terms:list[str]
    evidence_chunk_id:str
    evidence_source_ids:list[str]
    evidence_text:str
    url_state:str
    quality_flags:list[str]
    next_step:NextStep

class SearchResult(ProfileRecord):
    version:str=RETRIEVAL_VERSION
    context_id:str
    algorithm:Literal["tfidf","topic_baseline","light_hybrid"]
    status:Literal["matched","starter","needs_clarification","no_eligible"]
    candidates:list[SearchCandidate]
    clarification:str|None=None
    reason_codes:list[str]
    eligible_materials:int=Field(ge=0)
    query_has_vocabulary:bool
    continuation_candidates:list[ContinuationCandidate]=Field(default_factory=list)
