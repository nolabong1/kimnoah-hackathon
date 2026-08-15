import hashlib
import re
import unicodedata

from models.quiz import QuizDraft


def normalize_course_key(course_name: str) -> str:
    """과목명을 사용자별 개념 사전에서 사용할 안정적인 키로 바꿉니다."""

    if not isinstance(course_name, str):
        raise ValueError("과목명은 문자열이어야 합니다.")

    normalized_name = " ".join(
        unicodedata.normalize(
            "NFKC",
            course_name,
        ).casefold().split()
    )
    course_slug = re.sub(
        r"[^\w]+",
        "_",
        normalized_name,
        flags=re.UNICODE,
    ).strip("_")
    course_hash = hashlib.sha256(
        normalized_name.encode("utf-8")
    ).hexdigest()[:12]

    if not course_slug:
        course_slug = "course"

    return f"{course_slug[:107].rstrip('_')}_{course_hash}"


def normalize_concept_alias(concept_name: str) -> str:
    """공백·문장부호·대소문자 차이를 제거한 개념 별칭을 만듭니다."""

    if not isinstance(concept_name, str):
        raise ValueError("개념 이름은 문자열이어야 합니다.")

    normalized_name = unicodedata.normalize(
        "NFKC",
        concept_name,
    ).casefold()
    normalized_alias = "".join(
        character
        for character in normalized_name
        if character.isalnum()
    )[:120]

    if not normalized_alias:
        raise ValueError("정규화할 수 있는 개념 이름이 필요합니다.")

    return normalized_alias


def canonicalize_quiz_concepts(
    quiz: QuizDraft,
    concept_catalog: list[dict],
) -> QuizDraft:
    """기존 키나 별칭과 일치하는 문항 개념을 정규 개념으로 통일합니다."""

    concepts_by_key: dict[str, dict] = {}
    concepts_by_alias: dict[str, dict] = {}

    for concept in concept_catalog:
        concept_key = concept.get("concept_key")
        concept_name = concept.get("concept_name")

        if (
            not isinstance(concept_key, str)
            or not isinstance(concept_name, str)
        ):
            continue

        concepts_by_key.setdefault(
            concept_key,
            concept,
        )

        aliases = concept.get("aliases", [])

        if not isinstance(aliases, list):
            aliases = []

        alias_names = [concept_name, *aliases]

        for alias_name in alias_names:
            if not isinstance(alias_name, str):
                continue

            try:
                normalized_alias = normalize_concept_alias(
                    alias_name
                )
            except ValueError:
                continue

            concepts_by_alias.setdefault(
                normalized_alias,
                concept,
            )

    canonical_questions = []

    for question in quiz.questions:
        matched_concept = concepts_by_key.get(
            question.concept_key
        )

        if matched_concept is None:
            normalized_alias = normalize_concept_alias(
                question.concept_name
            )
            matched_concept = concepts_by_alias.get(
                normalized_alias
            )

        if matched_concept is None:
            canonical_questions.append(question)
            continue

        canonical_questions.append(
            question.model_copy(
                update={
                    "concept_key": matched_concept[
                        "concept_key"
                    ],
                    "concept_name": matched_concept[
                        "concept_name"
                    ],
                }
            )
        )

    return quiz.model_copy(
        update={
            "questions": canonical_questions,
        }
    )


def build_quiz_concept_payload(
    quiz: QuizDraft,
) -> list[dict]:
    """퀴즈 문항에서 RPC가 저장할 중복 없는 개념 목록을 만듭니다."""

    concepts_by_key: dict[str, dict] = {}
    concept_keys_by_alias: dict[str, str] = {}

    for question in quiz.questions:
        concept = {
            "concept_key": question.concept_key,
            "concept_name": question.concept_name,
            "normalized_alias": normalize_concept_alias(
                question.concept_name
            ),
        }
        existing_concept = concepts_by_key.get(
            question.concept_key
        )
        existing_concept_key = concept_keys_by_alias.get(
            concept["normalized_alias"]
        )

        if (
            existing_concept is not None
            and existing_concept != concept
        ):
            raise ValueError(
                "같은 개념 키에 서로 다른 개념 이름이 생성되었습니다."
            )

        if (
            existing_concept_key is not None
            and existing_concept_key
            != question.concept_key
        ):
            raise ValueError(
                "같은 개념 이름에 서로 다른 개념 키가 생성되었습니다."
            )

        concepts_by_key[question.concept_key] = concept
        concept_keys_by_alias[
            concept["normalized_alias"]
        ] = question.concept_key

    return list(concepts_by_key.values())
