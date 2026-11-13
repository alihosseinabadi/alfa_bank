"""Small manually judged retrieval metrics; unjudged top-10 is an error."""
import math

def judged_metrics(keys,judgments,k=10):
    if len(set(keys))!=len(keys):raise ValueError("Duplicate material in ranking")
    missing=[key for key in keys[:k] if key not in judgments]
    if missing:raise ValueError("Unjudged top-k; complete the blind pool first")
    def dcg(grades):return sum((2**grade-1)/math.log2(rank+2) for rank,grade in enumerate(grades))
    ideal=dcg(sorted(judgments.values(),reverse=True)[:k])
    score=dcg([judgments[key] for key in keys[:k]])
    positives={key for key,grade in judgments.items() if grade>=2}
    return {"ndcg10":score/ideal if ideal else 0.0,
        "success5":float(any(judgments.get(key,0)>=2 for key in keys[:5])),
        "pooled_recall50":len(set(keys[:50])&positives)/len(positives) if positives else 0.0}
