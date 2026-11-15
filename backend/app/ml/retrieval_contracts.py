"""Public search contracts for the TF-IDF MVP."""
from typing import Literal
from pydantic import Field
from .profile_contracts import ProfileRecord,MaterialFormat,ContinuationCandidate

RETRIEVAL_VERSION="tfidf-search-v1"
TOKENIZER_VERSION="ru-lexical-v1"

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
    algorithm:Literal["tfidf","topic_baseline"]
    status:Literal["matched","starter","needs_clarification","no_eligible"]
    candidates:list[SearchCandidate]
    clarification:str|None=None
    reason_codes:list[str]
    eligible_materials:int=Field(ge=0)
    query_has_vocabulary:bool
    continuation_candidates:list[ContinuationCandidate]=Field(default_factory=list)
