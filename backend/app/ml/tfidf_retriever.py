"""Deterministic public-chunk TF-IDF, material max pooling and honest fallback."""
import re
import unicodedata
from urllib.parse import urlsplit
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from .profile_contracts import CONTEXT_VERSION
from .retrieval_contracts import SearchMaterial,PublicSearchChunk,RetrievalPolicy,SearchCandidate,SearchResult,NextStep,RETRIEVAL_VERSION,TOKENIZER_VERSION

RU_STOP=frozenset("и в во на по с со для как что это или а к о об от до из за у но чтобы при ли же бы мы вы мне нам нужен нужна нужно хочу".split())

def normalize_text(text):
    text=unicodedata.normalize("NFKC",text).casefold().replace("ё","е")
    text=re.sub(r"\b1c\b","1с",text)
    return re.sub(r"\s+"," ",text).strip()

def tokenize_text(text):
    return [word for word in re.findall(r"[a-zа-я0-9]+(?:[-/][a-zа-я0-9]+)*",normalize_text(text)) if word not in RU_STOP]

def strip_passage(text):
    return re.sub(r"^passage:\s*","",text,flags=re.I).strip()

def discovery_allowed(material):
    url=urlsplit(material.url)
    return bool(material.is_discoverable and material.url_state!="unavailable" and
                material.url and url.scheme in {"http","https"} and url.netloc)

def eligible_for_context(material,context):
    if not discovery_allowed(material):return False
    if context.formats and material.item_type not in context.formats:return False
    if context.budget_preference=="free_only" and material.access_type!="Открытый":return False
    if context.available_time_minutes is not None and material.duration_minutes is not None and material.duration_minutes>context.available_time_minutes:return False
    return True

def prepare_corpus(materials,chunks):
    owners={m.material_key:m for m in materials}
    if len(owners)!=len(materials):raise ValueError("Duplicate material key")
    rows={}
    for chunk in chunks:
        if chunk.material_key not in owners:raise ValueError("Orphan public search chunk")
        if chunk.access_scope!="public":raise ValueError("Protected chunk cannot enter public index")
        material=owners[chunk.material_key]
        if material.access_type!="Открытый" and chunk.content_kind!="metadata":
            raise ValueError("Paid body cannot enter public index")
        if not discovery_allowed(material):continue
        body=strip_passage(chunk.text)
        if not tokenize_text(body):continue
        identity=(chunk.material_key,normalize_text(body))
        candidate=chunk.model_copy(update={"text":body},deep=True)
        if identity not in rows or candidate.chunk_id<rows[identity].chunk_id:
            rows[identity]=candidate
    return owners,[rows[k] for k in sorted(rows)]

def make_candidate(material,chunk,score,context,algorithm,query_tokens,*,starter=False):
    words=set(tokenize_text(chunk.text))
    matches=sorted(set(query_tokens)&words)[:5]
    if starter:
        reason="Общая стартовая подборка; персональное совпадение не установлено."
        code="general_start"
    elif algorithm=="topic_baseline":
        reason="Совпадение с темами или тегами материала: "+", ".join(matches)+"."
        code="topic_overlap"
    elif context.query_source in {"inferred_topics","material_titles"}:
        reason="По истории интересов найдено текстовое совпадение: "+", ".join(matches)+"."
        code="history_text_match"
    else:
        reason="Текстовое совпадение с вашей задачей: "+", ".join(matches)+"."
        code="task_text_match"
    if context.formats:reason+=" Формат соответствует указанному."
    fit="not_requested" if context.available_time_minutes is None else "unknown" if material.duration_minutes is None else "fits"
    flags=[]
    if material.duration_minutes is None:flags.append("duration_unknown")
    if material.listed_price is None:flags.append("listed_price_unknown")
    if material.url_state!="reachable":flags.append("live_url_not_confirmed")
    if material.access_type!="Открытый":flags.append("card_metadata_only")
    # Quote a contiguous public excerpt near a matched term.
    found=next((re.search(re.escape(term),chunk.text,re.I) for term in matches if re.search(re.escape(term),chunk.text,re.I)),None)
    start=max(0,found.start()-100) if found else 0
    excerpt=chunk.text[start:start+360]
    return SearchCandidate(material_key=material.material_key,title=material.title,item_type=material.item_type,
        url=material.url,access_badge=material.access_type,listed_price=material.listed_price,
        duration_minutes=material.duration_minutes,duration_fit=fit,price_is_unknown=material.listed_price is None,
        retrieval_score=float(min(1,max(0,score))),retrieval_version=algorithm+"-v1",reason_code=code,reason=reason,
        matched_terms=matches,evidence_chunk_id=chunk.chunk_id,evidence_source_ids=list(chunk.source_block_ids),
        evidence_text=excerpt,url_state=material.url_state,quality_flags=flags,
        next_step=NextStep(url=material.url))

class TfidfRetriever:
    def __init__(self,policy=None):
        self.policy=policy or RetrievalPolicy()
        if self.policy.version!=RETRIEVAL_VERSION or self.policy.tokenizer_version!=TOKENIZER_VERSION:
            raise ValueError("Incompatible retrieval policy")
        self.materials={}
        self.rows=[]
        self.vectorizer=None
        self.matrix=None

    def fit(self,materials,chunks):
        self.materials,self.rows=prepare_corpus(materials,chunks)
        self.vectorizer=TfidfVectorizer(tokenizer=tokenize_text,token_pattern=None,lowercase=False,
            ngram_range=(1,self.policy.ngram_max),min_df=1,sublinear_tf=True,norm="l2",dtype=np.float64)
        if self.rows:
            self.matrix=self.vectorizer.fit_transform([row.text for row in self.rows]).tocsr()
        else:
            from scipy.sparse import csr_matrix
            self.matrix=csr_matrix((0,0),dtype=np.float64)
            self.vectorizer=None
        return self

    def _eligible(self,context):
        indexed={row.material_key for row in self.rows}
        return {key for key,m in self.materials.items() if key in indexed and eligible_for_context(m,context)}

    def _metadata_row(self,key):
        rows=[r for r in self.rows if r.material_key==key]
        return min(rows,key=lambda row:(row.content_kind!="metadata",row.chunk_id))

    def _fallback(self,context,k,eligible,algorithm,reason,has_vocabulary=False):
        starters=[]
        # General starts are only used when no query exists. OOV queries get a
        # clarification rather than being replaced silently by unrelated cards.
        if not context.query_text.strip():
            for key in dict.fromkeys(self.policy.starter_keys):
                if key in eligible:
                    starters.append(make_candidate(self.materials[key],self._metadata_row(key),0,context,algorithm,[],starter=True))
                if len(starters)>=k:break
        status="starter" if starters else "no_eligible" if not eligible else "needs_clarification"
        clarification=None if starters else "Нет материалов с указанными ограничениями. Можно изменить формат или время?" if not eligible else (
            "Какую задачу бизнеса вы хотите решить?" if not context.query_text.strip() else
            "Не нашлось уверенного текстового совпадения. Уточните задачу или используйте другой термин.")
        return SearchResult(context_id=context.context_id,algorithm=algorithm,status=status,candidates=starters,
            clarification=clarification,reason_codes=[reason],eligible_materials=len(eligible),
            query_has_vocabulary=has_vocabulary,continuation_candidates=list(context.continuation_candidates))

    def query(self,context,k=50):
        if not isinstance(k,int) or isinstance(k,bool) or k<1:raise ValueError("k must be a positive integer")
        if context.schema_version!=CONTEXT_VERSION:raise ValueError("Incompatible request context")
        k=min(k,self.policy.max_candidates,50)
        eligible=self._eligible(context)
        if not eligible:return self._fallback(context,k,eligible,"tfidf","empty_eligible_pool")
        if not context.query_text.strip():return self._fallback(context,k,eligible,"tfidf","empty_query")
        if self.vectorizer is None:return self._fallback(context,k,eligible,"tfidf","empty_index")
        vector=self.vectorizer.transform([context.query_text])
        tokens=set(tokenize_text(context.query_text))
        coverage=sum(token in self.vectorizer.vocabulary_ for token in tokens)/max(1,len(tokens))
        if coverage<self.policy.min_query_coverage:
            return self._fallback(context,k,eligible,"tfidf","insufficient_query_coverage",bool(vector.nnz))
        if not vector.nnz:return self._fallback(context,k,eligible,"tfidf","query_out_of_vocabulary")
        scores=(self.matrix@vector.T).toarray().ravel()
        best={}
        for index,score in enumerate(scores):
            row=self.rows[index]
            if row.material_key not in eligible or score<self.policy.min_similarity:continue
            old=best.get(row.material_key)
            if old is None or score>old[0] or (score==old[0] and row.chunk_id<old[1].chunk_id):
                best[row.material_key]=(float(score),row)
        ordered=sorted(best,key=lambda key:(-best[key][0],key))[:k]
        if not ordered:return self._fallback(context,k,eligible,"tfidf","weak_text_match",True)
        tokens=tokenize_text(context.query_text)
        candidates=[make_candidate(self.materials[key],best[key][1],best[key][0],context,"tfidf",tokens) for key in ordered]
        return SearchResult(context_id=context.context_id,algorithm="tfidf",status="matched",candidates=candidates,
            reason_codes=["cosine_text_match","score_is_not_probability"],eligible_materials=len(eligible),
            query_has_vocabulary=True,continuation_candidates=list(context.continuation_candidates))
