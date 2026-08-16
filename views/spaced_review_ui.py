SPACED_REVIEW_STAGE_COUNT = 3


def get_spaced_review_label(task: dict) -> str | None:
    """자동 복습 과제의 간격 반복 단계 라벨을 반환합니다."""

    if task.get("source_type") != "weakness_review":
        return None

    review_stage = task.get("review_stage")
    review_interval_days = task.get(
        "review_interval_days"
    )

    if (
        isinstance(review_stage, bool)
        or not isinstance(review_stage, int)
        or review_stage not in range(
            1,
            SPACED_REVIEW_STAGE_COUNT + 1,
        )
        or isinstance(review_interval_days, bool)
        or not isinstance(review_interval_days, int)
        or review_interval_days not in {1, 3, 7}
    ):
        return None

    return (
        f"간격 반복 {review_stage}/"
        f"{SPACED_REVIEW_STAGE_COUNT} · "
        f"목표 간격 {review_interval_days}일"
    )
