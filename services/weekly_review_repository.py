from supabase import Client

from models.weekly_review import (
    WeeklyReviewAnalysis,
    WeeklyStatisticsSnapshot,
)


def get_weekly_review_by_plan(
    supabase: Client,
    user_id: str,
    plan_id: str,
) -> dict | None:
    """사용자 본인의 계획에 저장된 주간 회고를 조회합니다."""

    response = (
        supabase.table("weekly_learning_reviews")
        .select(
            "id, user_id, plan_id, week_start, week_end, "
            "statistics_snapshot, reflection_answers, ai_review_data, "
            "ai_review_markdown, created_at, updated_at"
        )
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0]


def create_weekly_review(
    supabase: Client,
    user_id: str,
    plan_id: str,
    statistics: WeeklyStatisticsSnapshot,
    reflection_answers: dict[str, str],
    analysis: WeeklyReviewAnalysis,
    markdown: str,
) -> dict:
    """계획에 첫 주간 회고를 저장합니다."""

    payload = _build_review_payload(
        user_id=user_id,
        plan_id=plan_id,
        statistics=statistics,
        reflection_answers=reflection_answers,
        analysis=analysis,
        markdown=markdown,
    )
    response = (
        supabase.table("weekly_learning_reviews")
        .insert(payload)
        .execute()
    )
    if not response.data:
        raise RuntimeError("주간 학습 회고 저장 결과가 비어 있습니다.")
    return response.data[0]


def update_weekly_review(
    supabase: Client,
    user_id: str,
    plan_id: str,
    review_id: str,
    statistics: WeeklyStatisticsSnapshot,
    reflection_answers: dict[str, str],
    analysis: WeeklyReviewAnalysis,
    markdown: str,
) -> dict:
    """명시적으로 다시 만든 기존 회고와 스냅샷을 갱신합니다."""

    payload = _build_review_payload(
        user_id=user_id,
        plan_id=plan_id,
        statistics=statistics,
        reflection_answers=reflection_answers,
        analysis=analysis,
        markdown=markdown,
    )
    payload.pop("user_id")
    payload.pop("plan_id")
    response = (
        supabase.table("weekly_learning_reviews")
        .update(payload)
        .eq("id", review_id)
        .eq("user_id", user_id)
        .eq("plan_id", plan_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError("갱신할 주간 학습 회고를 찾을 수 없습니다.")
    return response.data[0]


def _build_review_payload(
    user_id: str,
    plan_id: str,
    statistics: WeeklyStatisticsSnapshot,
    reflection_answers: dict[str, str],
    analysis: WeeklyReviewAnalysis,
    markdown: str,
) -> dict:
    """Supabase 저장용 JSON 안전 payload를 만듭니다."""

    cleaned_markdown = markdown.strip()
    if not cleaned_markdown:
        raise ValueError("저장할 주간 회고 Markdown이 비어 있습니다.")
    return {
        "user_id": user_id,
        "plan_id": plan_id,
        "week_start": statistics.plan_start_date.isoformat(),
        "week_end": statistics.plan_target_date.isoformat(),
        "statistics_snapshot": statistics.model_dump(mode="json"),
        "reflection_answers": dict(reflection_answers),
        "ai_review_data": analysis.model_dump(mode="json"),
        "ai_review_markdown": cleaned_markdown,
    }
