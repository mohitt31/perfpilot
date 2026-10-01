"""Blinded PerfBench contracts, validation, and denominator-safe scoring."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from perfpilot.evidence.schema import CommitSha, StrictModel


class CaseReadiness(StrEnum):
    CURATED_UNRUN = "curated_unrun"
    RECIPE_VALIDATED = "recipe_validated"


class PerfBenchCase(StrictModel):
    case_id: str = Field(pattern=r"^pb-[0-9]{3}$")
    repository_url: str = Field(pattern=r"^https://github\.com/.+/.+$")
    baseline_commit: CommitSha
    language: Literal["cpp"] = "cpp"
    build_system: Literal["cmake"] = "cmake"
    category: str = Field(min_length=1)
    readiness: CaseReadiness
    job_path: str | None = None
    predeclared_at: datetime
    limitations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ready_case_has_job(self) -> PerfBenchCase:
        if self.readiness is CaseReadiness.RECIPE_VALIDATED and self.job_path is None:
            raise ValueError("a recipe-validated case requires job_path")
        if self.readiness is CaseReadiness.CURATED_UNRUN and self.job_path is not None:
            raise ValueError("a curated-unrun case cannot imply a validated job recipe")
        return self


class PerfBenchCatalog(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    suite_id: str = Field(min_length=1)
    selection_rule: str = Field(min_length=1)
    cases: tuple[PerfBenchCase, ...] = Field(min_length=6, max_length=8)

    @model_validator(mode="after")
    def unique_cases(self) -> PerfBenchCatalog:
        values = [case.case_id for case in self.cases]
        if len(values) != len(set(values)):
            raise ValueError("PerfBench case IDs must be unique")
        return self


class PerfBenchAnswer(StrictModel):
    case_id: str = Field(pattern=r"^pb-[0-9]{3}$")
    fix_commit: CommitSha
    reference_url: str = Field(pattern=r"^https://github\.com/.+/.+/pull/[0-9]+$")
    title: str = Field(min_length=1)
    changed_paths: tuple[str, ...] = Field(min_length=1)
    reference_claim: str = Field(min_length=1)


class PerfBenchAnswerKey(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    suite_id: str = Field(min_length=1)
    public_catalog_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    answers: tuple[PerfBenchAnswer, ...] = Field(min_length=6, max_length=8)


class ObservationState(StrEnum):
    NOT_RUN = "not_run"
    SETUP_FAILED = "setup_failed"
    NO_HOTSPOT = "no_hotspot"
    NO_VALID_CANDIDATE = "no_valid_candidate"
    CANDIDATE_UNVERIFIED = "candidate_unverified"
    CANDIDATE_VERIFIED = "candidate_verified"


class PerfBenchObservation(StrictModel):
    case_id: str = Field(pattern=r"^pb-[0-9]{3}$")
    state: ObservationState
    hotspot_identified: bool = False
    valid_candidate: bool = False
    equivalent_fix: bool | None = None
    verified_speedup: bool = False
    review_ready: bool = False
    evidence_bundle: str | None = None
    notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def stages_are_monotone(self) -> PerfBenchObservation:
        if self.valid_candidate and not self.hotspot_identified:
            raise ValueError("a valid candidate requires an identified hotspot")
        if self.equivalent_fix is not None and not self.valid_candidate:
            raise ValueError("equivalent-fix classification requires a valid candidate")
        if self.verified_speedup and not self.valid_candidate:
            raise ValueError("a verified speedup requires a valid candidate")
        if self.review_ready and not self.verified_speedup:
            raise ValueError("review readiness requires a verified speedup")
        if self.state is ObservationState.NOT_RUN and any(
            (
                self.hotspot_identified,
                self.valid_candidate,
                self.verified_speedup,
                self.review_ready,
            )
        ):
            raise ValueError("an unrun case cannot have positive stage outcomes")
        return self


class PerfBenchObservations(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    suite_id: str = Field(min_length=1)
    observations: tuple[PerfBenchObservation, ...] = Field(min_length=6, max_length=8)


class Rate(StrictModel):
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    fraction: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def fraction_matches_counts(self) -> Rate:
        expected = None if self.denominator == 0 else self.numerator / self.denominator
        if self.fraction != expected:
            raise ValueError("rate fraction must exactly match its numerator and denominator")
        return self


class PerfBenchScore(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    suite_id: str
    total_cases: int
    attempted_cases: int
    setup_failures: int
    hotspot_identification: Rate
    valid_candidate: Rate
    equivalent_fix_recovery: Rate
    verified_speedup: Rate
    review_readiness: Rate
    warning: str


def canonical_sha256(path: Path) -> str:
    """Hash the exact public catalog bytes used to lock a hidden answer key."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_suite(
    catalog_path: Path, answer_path: Path, observations_path: Path | None = None
) -> tuple[PerfBenchCatalog, PerfBenchAnswerKey, PerfBenchObservations | None]:
    catalog = PerfBenchCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    answers = PerfBenchAnswerKey.model_validate_json(answer_path.read_text(encoding="utf-8"))
    observations = (
        None
        if observations_path is None
        else PerfBenchObservations.model_validate_json(
            observations_path.read_text(encoding="utf-8")
        )
    )
    if answers.suite_id != catalog.suite_id:
        raise ValueError("answer key suite_id does not match public catalog")
    if answers.public_catalog_sha256 != canonical_sha256(catalog_path):
        raise ValueError("answer key is not locked to these exact public catalog bytes")
    catalog_ids = {case.case_id for case in catalog.cases}
    answer_ids = [answer.case_id for answer in answers.answers]
    if set(answer_ids) != catalog_ids or len(answer_ids) != len(set(answer_ids)):
        raise ValueError("answer key must contain exactly one answer for every public case")
    if observations is not None:
        if observations.suite_id != catalog.suite_id:
            raise ValueError("observations suite_id does not match public catalog")
        observation_ids = [item.case_id for item in observations.observations]
        if set(observation_ids) != catalog_ids or len(observation_ids) != len(
            set(observation_ids)
        ):
            raise ValueError("observations must contain exactly one outcome for every public case")
    return catalog, answers, observations


def _rate(numerator: int, denominator: int) -> Rate:
    return Rate(
        numerator=numerator,
        denominator=denominator,
        fraction=None if denominator == 0 else numerator / denominator,
    )


def score_suite(catalog: PerfBenchCatalog, observations: PerfBenchObservations) -> PerfBenchScore:
    attempted = [
        item
        for item in observations.observations
        if item.state is not ObservationState.NOT_RUN
    ]
    setup_succeeded = [
        item for item in attempted if item.state is not ObservationState.SETUP_FAILED
    ]
    valid = [item for item in setup_succeeded if item.valid_candidate]
    equivalent_classified = [item for item in valid if item.equivalent_fix is not None]
    return PerfBenchScore(
        suite_id=catalog.suite_id,
        total_cases=len(catalog.cases),
        attempted_cases=len(attempted),
        setup_failures=sum(item.state is ObservationState.SETUP_FAILED for item in attempted),
        hotspot_identification=_rate(
            sum(item.hotspot_identified for item in setup_succeeded), len(setup_succeeded)
        ),
        valid_candidate=_rate(
            sum(item.valid_candidate for item in setup_succeeded), len(setup_succeeded)
        ),
        equivalent_fix_recovery=_rate(
            sum(item.equivalent_fix is True for item in equivalent_classified),
            len(equivalent_classified),
        ),
        verified_speedup=_rate(
            sum(item.verified_speedup for item in setup_succeeded), len(setup_succeeded)
        ),
        review_readiness=_rate(
            sum(item.review_ready for item in setup_succeeded), len(setup_succeeded)
        ),
        warning=(
            "Historical public fixes may have appeared in model training data; equivalent-fix "
            "classification requires blinded human review. A zero denominator is undefined."
        ),
    )


def write_score(path: Path, score: PerfBenchScore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(score.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
