"""Versioned onboarding questions mapped onto the existing profile/context fields.

Design rules, all enforced by tests:

1. **Six questions, each independently skippable.** A skipped answer is ``None``, and
   ``None`` never becomes a negative preference. Concretely: skipping the budget
   question does not mean "free only", skipping the time question does not mean
   "no time", and skipping the goal question produces no topic selection at all.
2. **No new profile schema.** Answers are translated into the fields that already
   exist: ``ExplicitPreferences.selected_topics`` / ``business_stage`` /
   ``experience`` / ``budget_preference`` / ``available_time_minutes``, which
   ``build_request_context`` already reads. Nothing downstream needs to change.
3. **Onboarding is a cold-start aid, not a permanent claim.** After
   ``history_outweighs_after`` real interactions the topic selection is dropped and
   history drives the context. The existing ``history_weight`` mechanism in
   ``request_context.py`` then does the rest. This module only decides *whether* the
   onboarding topics are still allowed to act as an explicit selection.
4. **Starter picks explain themselves.** Every starter reason names the answer it
   came from, so a user can see why the card is there.

The module is pure: no IO beyond the goal/topic map, no database, no retrievers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Protocol, Sequence

from pydantic import Field

from .profile_contracts import ExplicitPreferences, ProfileRecord

ONBOARDING_VERSION = "onboarding-v1"
GOAL_TOPICS_VERSION = "onboarding-goal-topics-v1"

DEFAULT_GOAL_TOPICS_PATH = Path(__file__).resolve().parents[3] / "data" / "onboarding_goal_topics.json"

BusinessArea = Literal["trade", "services", "production", "it", "food", "other"]
Stage = Literal["idea", "first_sales", "growing", "scaling"]
Goal = Literal[
    "find_customers",
    "increase_profit",
    "retain_customers",
    "build_team",
    "formalize_business",
    "launch_product",
    "raise_money",
    "grow_business",
]
Experience = Literal["beginner", "some", "experienced"]
AvailableTime = Literal["15m", "1h", "long"]
Budget = Literal["free_only", "paid_ok"]

QUESTION_IDS = (
    "business_area",
    "stage",
    "goal",
    "experience",
    "available_time",
    "budget",
)

# Minutes the time answer translates into. "long" means "no upper bound", which is
# None, not a large number: a large number would silently exclude long materials.
TIME_MINUTES: dict[str, int | None] = {"15m": 15, "1h": 60, "long": None}

BUDGET_BY_ANSWER: dict[str, str] = {"free_only": "free_only", "paid_ok": "paid_allowed"}

GOAL_LABELS: dict[str, str] = {
    "find_customers": "найти клиентов",
    "increase_profit": "увеличить прибыль",
    "retain_customers": "удержать клиентов",
    "build_team": "собрать команду",
    "formalize_business": "оформить бизнес",
    "launch_product": "запустить продукт",
    "raise_money": "привлечь деньги",
    "grow_business": "масштабировать бизнес",
}

STAGE_LABELS: dict[str, str] = {
    "idea": "идея",
    "first_sales": "первые продажи",
    "growing": "рост",
    "scaling": "масштабирование",
}

EXPERIENCE_LABELS: dict[str, str] = {
    "beginner": "новичок",
    "some": "есть небольшой опыт",
    "experienced": "опытный предприниматель",
}

# `business_area` is a coarse onboarding question; the profile only has free-text
# `industry`. The catalogue does not carry an industry vocabulary, so the answer is
# stored as a human-readable label rather than as an English enum key: a label is at
# worst display-only, while "trade" in `industry` would silently never match anything.
BUSINESS_AREA_LABELS: dict[str, str] = {
    "trade": "торговля",
    "services": "услуги",
    "production": "производство",
    "it": "IT",
    "food": "общепит",
    "other": "другое",
}


class OnboardingAnswers(ProfileRecord):
    """The six questions. Every field is optional; ``None`` means skipped."""

    schema_version: str = ONBOARDING_VERSION
    business_area: BusinessArea | None = None
    stage: Stage | None = None
    goal: Goal | None = None
    experience: Experience | None = None
    available_time: AvailableTime | None = None
    budget: Budget | None = None

    def answered(self) -> tuple[str, ...]:
        return tuple(name for name in QUESTION_IDS if getattr(self, name) is not None)

    def skipped(self) -> tuple[str, ...]:
        return tuple(name for name in QUESTION_IDS if getattr(self, name) is None)


class OnboardingPolicy(ProfileRecord):
    version: str = ONBOARDING_VERSION
    history_outweighs_after: int = Field(default=3, ge=1, le=50)
    goal_topic_limit: int = Field(default=3, ge=1, le=10)
    starter_limit: int = Field(default=6, ge=1, le=20)


class OnboardingResult(ProfileRecord):
    """What the onboarding answers are allowed to change right now."""

    schema_version: str = ONBOARDING_VERSION
    preferences: ExplicitPreferences
    onboarding_topics: list[str]
    topics_in_effect: bool
    answered: list[str]
    skipped: list[str]
    reason_codes: list[str]


class StarterCandidate(ProfileRecord):
    material_key: str
    title: str
    topics: list[str]
    reason: str
    matched_question: Literal["goal", "stage", "experience", "budget", "available_time"]


class MaterialLike(Protocol):
    material_key: str
    title: str
    topics: Sequence[str]
    access_type: str
    duration_minutes: int | None


def load_goal_topics(path: Path | str | None = None) -> dict[str, list[str]]:
    """Load the goal -> topics map; a missing file yields an empty map."""
    source = Path(path) if path is not None else DEFAULT_GOAL_TOPICS_PATH
    if not source.exists():
        return {}
    raw = json.loads(source.read_text(encoding="utf-8"))
    version = raw.get("version")
    if version != GOAL_TOPICS_VERSION:
        raise ValueError(f"Unsupported goal/topic map version: {version!r}")
    goals: dict[str, list[str]] = {}
    for goal, topics in raw.get("goals", {}).items():
        cleaned = list(dict.fromkeys(str(topic).strip() for topic in topics if str(topic).strip()))
        if cleaned:
            goals[goal] = cleaned
    return goals


def apply_onboarding(
    answers: OnboardingAnswers,
    *,
    interaction_count: int = 0,
    policy: OnboardingPolicy | None = None,
    goal_topics: dict[str, list[str]] | None = None,
    base: ExplicitPreferences | None = None,
) -> OnboardingResult:
    """Translate answers into preferences, honouring the history-over-onboarding rule.

    ``base`` lets a caller merge onboarding on top of preferences that came from
    elsewhere (for example a settings page). Onboarding never overwrites a value the
    user set explicitly elsewhere: it only fills fields that are still ``None``.
    """
    policy = policy or OnboardingPolicy()
    if answers.schema_version != ONBOARDING_VERSION:
        raise ValueError("Incompatible onboarding schema version")
    if not isinstance(interaction_count, int) or isinstance(interaction_count, bool) or interaction_count < 0:
        raise ValueError("interaction_count must be a non-negative integer")

    base = base or ExplicitPreferences()
    topics_map = load_goal_topics() if goal_topics is None else goal_topics
    reasons: list[str] = []

    onboarding_topics: list[str] = []
    if answers.goal is not None:
        onboarding_topics = topics_map.get(answers.goal, [])[: policy.goal_topic_limit]
        if not onboarding_topics:
            reasons.append("goal_has_no_catalog_topic")
    topics_in_effect = bool(onboarding_topics) and interaction_count < policy.history_outweighs_after
    if onboarding_topics and not topics_in_effect:
        reasons.append("history_outweighs_onboarding")

    selected_topics = list(base.selected_topics)
    if topics_in_effect:
        selected_topics += [topic for topic in onboarding_topics if topic not in selected_topics]

    # Skipped answers must never become a negative preference: each branch below is
    # entered only when the answer exists, and each value we write is the user's
    # stated one.
    budget = base.budget_preference
    if budget is None and answers.budget is not None:
        budget = BUDGET_BY_ANSWER[answers.budget]

    minutes = base.available_time_minutes
    if minutes is None and answers.available_time is not None:
        minutes = TIME_MINUTES[answers.available_time]

    business_stage = base.business_stage if base.business_stage is not None else answers.stage
    experience = base.experience if base.experience is not None else answers.experience
    industry = base.industry
    if industry is None and answers.business_area is not None:
        industry = BUSINESS_AREA_LABELS[answers.business_area]

    preferences = base.model_copy(
        update={
            "selected_topics": list(dict.fromkeys(selected_topics)),
            "budget_preference": budget,
            "available_time_minutes": minutes,
            "business_stage": business_stage,
            "experience": experience,
            "industry": industry,
        }
    )
    if answers.skipped():
        reasons.append("skipped_answers_stay_null")
    if not answers.answered():
        reasons.append("no_answers")

    return OnboardingResult(
        preferences=preferences,
        onboarding_topics=list(onboarding_topics),
        topics_in_effect=topics_in_effect,
        answered=list(answers.answered()),
        skipped=list(answers.skipped()),
        reason_codes=reasons,
    )


def starter_candidates(
    answers: OnboardingAnswers,
    materials: Sequence[MaterialLike],
    *,
    policy: OnboardingPolicy | None = None,
    goal_topics: dict[str, list[str]] | None = None,
) -> list[StarterCandidate]:
    """Deterministic starter picks that respect the answers and explain themselves.

    Ordering: goal-topic overlap first (more overlap first), then shorter duration
    first (a starter should be cheap to try), then ``material_key`` for stability.

    When the user states a time budget, a material with an unknown duration is
    excluded: the card would otherwise promise something the data cannot back. If
    that leaves nothing, the caller shows no starter set rather than a wrong one.
    """
    policy = policy or OnboardingPolicy()
    topics_map = load_goal_topics() if goal_topics is None else goal_topics
    goal_set = set(topics_map.get(answers.goal, []) if answers.goal else [])
    free_only = answers.budget == "free_only"
    minutes = TIME_MINUTES[answers.available_time] if answers.available_time else None

    rows: list[tuple[int, int, str, StarterCandidate]] = []
    for material in materials:
        topics = list(material.topics)
        overlap = len(goal_set & set(topics))
        if goal_set and overlap == 0:
            continue
        if free_only and material.access_type != "Открытый":
            continue
        if minutes is not None:
            if material.duration_minutes is None or material.duration_minutes > minutes:
                continue
        reason, question = _starter_reason(answers, topics, overlap)
        rows.append((
            -overlap,
            material.duration_minutes if material.duration_minutes is not None else 10**6,
            material.material_key,
            StarterCandidate(
                material_key=material.material_key,
                title=material.title,
                topics=list(topics),
                reason=reason,
                matched_question=question,
            ),
        ))
    rows.sort(key=lambda row: row[:3])
    return [row[3] for row in rows[: policy.starter_limit]]


def _starter_reason(
    answers: OnboardingAnswers, topics: Sequence[str], overlap: int
) -> tuple[str, Literal["goal", "stage", "experience", "budget", "available_time"]]:
    """Name the answers that produced this card; the first one names the card.

    The ``matched_question`` is the answer that actually drove the pick, not the last
    answer mentioned, so a budget note never takes credit for a goal-based card.
    """
    parts: list[str] = []
    question: Literal["goal", "stage", "experience", "budget", "available_time"]
    if answers.goal is not None and overlap:
        parts.append(f"по вашей цели «{GOAL_LABELS[answers.goal]}» (тема: {', '.join(topics)})")
        question = "goal"
    elif answers.stage is not None:
        parts.append(f"как стартовый материал для этапа «{STAGE_LABELS[answers.stage]}»")
        question = "stage"
    elif answers.experience is not None:
        parts.append(f"с учётом опыта: {EXPERIENCE_LABELS[answers.experience]}")
        question = "experience"
    elif answers.budget == "free_only":
        parts.append("из бесплатных материалов, потому что вы выбрали только бесплатное")
        question = "budget"
    elif answers.available_time is not None:
        limit = TIME_MINUTES[answers.available_time]
        parts.append(
            "из коротких материалов под ваш ответ о времени"
            if limit is not None
            else "из материалов без ограничения по времени"
        )
        question = "available_time"
    else:
        parts.append("из общей стартовой подборки: ответы не указаны")
        question = "goal"
    if answers.budget == "free_only" and question != "budget":
        parts.append("только бесплатные материалы — по ответу о бюджете")
    if answers.available_time is not None and question != "available_time":
        limit = TIME_MINUTES[answers.available_time]
        label = "без ограничения по времени" if limit is None else f"до {limit} мин"
        parts.append(f"формат по времени: {label}")
    return "Стартовый материал: " + "; ".join(parts) + ".", question

