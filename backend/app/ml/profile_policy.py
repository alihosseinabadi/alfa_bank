"""Reviewed MVP hypotheses; strengths are not probabilities or learned utility."""
import hashlib
import json
from pydantic import Field,model_validator
from .profile_contracts import ProfileRecord

def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

class RatingRule(ProfileRecord):
    reviewed_group_question: str | None = None
    reviewed_value_questions: dict[int,str] = Field(default_factory=dict)
    scale_values: list[int] = Field(default_factory=lambda:[1,2,3,4,5])
    positive_values: list[int] = Field(default_factory=lambda:[4,5])
    negative_values: list[int] = Field(default_factory=lambda:[1,2,3])

    @model_validator(mode="after")
    def valid_partition(self):
        values=set(self.scale_values)
        if not values or set(self.positive_values)&set(self.negative_values) or not (
            set(self.positive_values)|set(self.negative_values))<=values:
            raise ValueError("Invalid rating polarity definition")
        return self

class ProfilePolicy(ProfileRecord):
    version: str = "mvp-profile-policy-v1"
    enrollment_strength: float = Field(default=0.2,ge=0,le=1)
    completion_strength: float = Field(default=0.6,ge=0,le=1)
    positive_rating_strength: float = Field(default=1.0,ge=0,le=1)
    negative_rating_strength: float = Field(default=1.0,ge=0,le=1)
    confidence_prior_materials: float = Field(default=2.0,gt=0)
    max_title_fallbacks: int = Field(default=3,ge=0,le=10)
    max_context_topics: int = Field(default=3,ge=1,le=10)
    rating_rules: dict[str,RatingRule] = Field(default_factory=dict)

    def identity(self):
        return fingerprint(self.model_dump())

def default_policy() -> ProfilePolicy:
    # Only four active dictionaries were reviewed. The deleted NDFl-2 group
    # 574f... is deliberately not enabled. Lower-score questions ask what failed;
    # 4/5 questions ask what was useful. This is a transparent MVP interpretation.
    groups=("6a58f491-1f1a-460d-a8a0-d4a04cae51bc",
            "96ee8fd2-fdb4-4a9a-bc10-3b2e7291c0d7",
            "9823650f-6cde-4509-b6cc-e77b4c05f6c7",
            "9ffc36a8-504e-4279-8e59-72a45572edad")
    rules={}
    for key in groups:
        lesson=key=="96ee8fd2-fdb4-4a9a-bc10-3b2e7291c0d7"
        negative="Чего в уроке не хватило?" if lesson else "Что именно не понравилось?"
        rules[key]=RatingRule(reviewed_group_question="Как вам урок?" if lesson else "Насколько калькулятор помог решить вашу задачу?",
            reviewed_value_questions={v:negative if v<=3 else "Что понравилось больше всего?" for v in range(1,6)})
    return ProfilePolicy(rating_rules=rules)

def rating_polarity(observation,policy:ProfilePolicy) -> str | None:
    rule=policy.rating_rules.get(observation.rating_group_id)
    if observation.rating_scale_status!="resolved" or not rule or sorted(set(
        observation.rating_scale_values))!=sorted(set(rule.scale_values)):
        return None
    if observation.rating_value in rule.positive_values:return "positive"
    if observation.rating_value in rule.negative_values:return "negative"
    return None
