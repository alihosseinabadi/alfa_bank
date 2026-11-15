"""Onboarding must never invent preferences the user did not state."""
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.ml.onboarding import (
    GOAL_TOPICS_VERSION,
    ONBOARDING_VERSION,
    OnboardingAnswers,
    OnboardingPolicy,
    apply_onboarding,
    load_goal_topics,
    starter_candidates,
)
from app.ml.profile_contracts import ExplicitPreferences

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "data" / "synthetic" / "light_benchmark_v1" / "catalog.json"


@dataclass
class Material:
    material_key: str
    title: str
    topics: list[str]
    access_type: str = "Открытый"
    duration_minutes: int | None = 15


GOAL_TOPICS = {
    "find_customers": ["Маркетинг", "Продажи"],
    "increase_profit": ["Юнит-экономика", "Финансы"],
}

MATERIALS = [
    Material("m-paid", "Платный маркетинг", ["Маркетинг"], access_type="По подписке", duration_minutes=90),
    Material("m-long", "Длинный курс по продажам", ["Продажи"], duration_minutes=120),
    Material("m-short", "Короткий курс по продажам", ["Продажи"], duration_minutes=15),
    Material("m-unknown", "Продажи без указанной длительности", ["Продажи"], duration_minutes=None),
    Material("m-other", "Налоги для новичка", ["Налоги"], duration_minutes=5),
]


def test_skipped_answers_never_become_preferences():
    result = apply_onboarding(OnboardingAnswers(), goal_topics=GOAL_TOPICS)
    prefs = result.preferences
    assert prefs.budget_preference is None
    assert prefs.available_time_minutes is None
    assert prefs.business_stage is None
    assert prefs.experience is None
    assert prefs.industry is None
    assert prefs.selected_topics == []
    assert result.topics_in_effect is False
    assert result.answered == []
    assert result.skipped == [
        "business_area",
        "stage",
        "goal",
        "experience",
        "available_time",
        "budget",
    ]
    assert "no_answers" in result.reason_codes


def test_partial_answers_leave_the_rest_null():
    answers = OnboardingAnswers(budget="free_only", available_time="15m")
    result = apply_onboarding(answers, goal_topics=GOAL_TOPICS)
    assert result.preferences.budget_preference == "free_only"
    assert result.preferences.available_time_minutes == 15
    assert result.preferences.business_stage is None
    assert result.preferences.experience is None
    assert result.preferences.selected_topics == []
    assert "skipped_answers_stay_null" in result.reason_codes


def test_goal_selects_catalog_topics():
    result = apply_onboarding(OnboardingAnswers(goal="find_customers"), goal_topics=GOAL_TOPICS)
    assert result.onboarding_topics == ["Маркетинг", "Продажи"]
    assert result.preferences.selected_topics == ["Маркетинг", "Продажи"]
    assert result.topics_in_effect is True


def test_goal_topic_limit_is_respected():
    policy = OnboardingPolicy(goal_topic_limit=1)
    result = apply_onboarding(OnboardingAnswers(goal="find_customers"), policy=policy, goal_topics=GOAL_TOPICS)
    assert result.preferences.selected_topics == ["Маркетинг"]


def test_unknown_goal_does_not_select_topics():
    answers = OnboardingAnswers(goal="find_customers")
    result = apply_onboarding(answers, goal_topics={"increase_profit": ["Финансы"]})
    assert result.onboarding_topics == []
    assert result.topics_in_effect is False
    assert result.reason_codes == ["goal_has_no_catalog_topic", "skipped_answers_stay_null"]


def test_history_outweighs_onboarding_after_three_interactions():
    answers = OnboardingAnswers(goal="find_customers")
    before = apply_onboarding(answers, interaction_count=2, goal_topics=GOAL_TOPICS)
    after = apply_onboarding(answers, interaction_count=3, goal_topics=GOAL_TOPICS)
    assert before.topics_in_effect is True
    assert before.preferences.selected_topics == ["Маркетинг", "Продажи"]
    assert after.topics_in_effect is False
    assert after.onboarding_topics == ["Маркетинг", "Продажи"]
    assert after.preferences.selected_topics == []
    assert "history_outweighs_onboarding" in after.reason_codes


def test_existing_preferences_are_never_overwritten():
    base = ExplicitPreferences(
        industry="IT",
        business_stage="growing",
        experience="some",
        budget_preference="paid_allowed",
        available_time_minutes=60,
        selected_topics=["Налоги"],
    )
    answers = OnboardingAnswers(
        business_area="trade",
        stage="idea",
        goal="find_customers",
        experience="beginner",
        available_time="15m",
        budget="free_only",
    )
    result = apply_onboarding(answers, base=base, goal_topics=GOAL_TOPICS)
    prefs = result.preferences
    assert prefs.industry == "IT"
    assert prefs.business_stage == "growing"
    assert prefs.experience == "some"
    assert prefs.budget_preference == "paid_allowed"
    assert prefs.available_time_minutes == 60
    assert prefs.selected_topics == ["Налоги", "Маркетинг", "Продажи"]


def test_answers_map_onto_existing_profile_fields():
    answers = OnboardingAnswers(
        business_area="trade",
        stage="first_sales",
        experience="beginner",
        available_time="1h",
        budget="paid_ok",
    )
    result = apply_onboarding(answers, goal_topics=GOAL_TOPICS)
    prefs = result.preferences
    assert prefs.industry == "торговля"
    assert prefs.business_stage == "first_sales"
    assert prefs.experience == "beginner"
    assert prefs.available_time_minutes == 60
    assert prefs.budget_preference == "paid_allowed"


def test_long_time_answer_means_no_limit_rather_than_a_big_number():
    result = apply_onboarding(OnboardingAnswers(available_time="long"), goal_topics=GOAL_TOPICS)
    assert result.preferences.available_time_minutes is None


@pytest.mark.parametrize("count", [-1, 1.5, True, "3"])
def test_invalid_interaction_count_is_rejected(count):
    with pytest.raises(ValueError):
        apply_onboarding(OnboardingAnswers(), interaction_count=count, goal_topics=GOAL_TOPICS)


def test_incompatible_onboarding_version_is_rejected():
    answers = OnboardingAnswers(schema_version="onboarding-v0")
    with pytest.raises(ValueError):
        apply_onboarding(answers, goal_topics=GOAL_TOPICS)


def test_incompatible_goal_map_version_is_rejected(tmp_path):
    path = tmp_path / "goal_topics.json"
    path.write_text(json.dumps({"version": "v0", "goals": {"find_customers": ["Маркетинг"]}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_goal_topics(path)


def test_missing_goal_map_is_empty_not_invented(tmp_path):
    assert load_goal_topics(tmp_path / "absent.json") == {}


def test_shipped_goal_map_names_only_catalog_topics():
    goals = load_goal_topics()
    assert goals, "shipped goal/topic map must not be empty"
    assert set(goals) <= {
        "find_customers",
        "increase_profit",
        "retain_customers",
        "build_team",
        "formalize_business",
        "launch_product",
        "raise_money",
        "grow_business",
    }
    if not CATALOG_PATH.exists():
        pytest.skip("frozen benchmark catalog is not present")
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog_topics = {topic for material in catalog["materials"] for topic in material.get("topics", [])}
    for goal, topics in goals.items():
        missing = set(topics) - catalog_topics
        assert not missing, f"{goal} names topics absent from the catalog: {missing}"


def test_shipped_goal_map_version_matches_the_constant():
    raw = json.loads((REPO_ROOT / "data" / "onboarding_goal_topics.json").read_text(encoding="utf-8"))
    assert raw["version"] == GOAL_TOPICS_VERSION == "onboarding-goal-topics-v1"
    assert ONBOARDING_VERSION == "onboarding-v1"


def test_starter_picks_respect_goal_and_explain_their_answer():
    answers = OnboardingAnswers(goal="find_customers", available_time="1h")
    picks = starter_candidates(answers, MATERIALS, goal_topics=GOAL_TOPICS)
    assert [pick.material_key for pick in picks] == ["m-short"]
    pick = picks[0]
    assert pick.matched_question == "goal"
    assert "найти клиентов" in pick.reason
    assert "Продажи" in pick.reason


def test_starter_picks_respect_free_only():
    answers = OnboardingAnswers(goal="find_customers", budget="free_only", available_time="long")
    picks = starter_candidates(answers, MATERIALS, goal_topics=GOAL_TOPICS)
    keys = [pick.material_key for pick in picks]
    assert "m-paid" not in keys
    assert keys[0] == "m-short"
    assert all("бесплатн" in pick.reason for pick in picks)


def test_starter_time_limit_excludes_slow_and_unknown_durations():
    answers = OnboardingAnswers(goal="find_customers", available_time="15m")
    picks = starter_candidates(answers, MATERIALS, goal_topics=GOAL_TOPICS)
    keys = [pick.material_key for pick in picks]
    assert "m-long" not in keys
    assert "m-unknown" not in keys
    assert keys == ["m-short"]
    assert all(pick.matched_question in {"goal", "available_time"} for pick in picks)
    assert "до 15 мин" in picks[0].reason


def test_starter_picks_are_deterministic_and_limited():
    answers = OnboardingAnswers()
    policy = OnboardingPolicy(starter_limit=2)
    first = starter_candidates(answers, MATERIALS, policy=policy, goal_topics=GOAL_TOPICS)
    second = starter_candidates(answers, MATERIALS, policy=policy, goal_topics=GOAL_TOPICS)
    assert first == second
    assert len(first) == 2
    assert [pick.material_key for pick in first] == ["m-other", "m-short"]
    assert all(pick.matched_question == "goal" for pick in first)
    assert "ответы не указаны" in first[0].reason


def test_starter_budget_only_answer_is_attributed_to_budget():
    answers = OnboardingAnswers(budget="free_only")
    picks = starter_candidates(answers, MATERIALS, goal_topics=GOAL_TOPICS)
    assert picks
    assert all(pick.matched_question == "budget" for pick in picks)
    assert all("только бесплатное" in pick.reason for pick in picks)


def test_empty_starter_set_is_preferred_over_a_wrong_promise():
    answers = OnboardingAnswers(goal="find_customers", available_time="15m", budget="free_only")
    picks = starter_candidates(answers, [MATERIALS[0]], goal_topics=GOAL_TOPICS)
    assert picks == []
