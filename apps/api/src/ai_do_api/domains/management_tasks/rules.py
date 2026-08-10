from __future__ import annotations

from dataclasses import dataclass
from datetime import date


AGE_CALC_KOREAN = "korean"
AGE_CALC_INTERNATIONAL = "international"
EXCLUDED_OCCUPATIONS = frozenset({"파견직"})

REASON_SENIOR = "senior"
REASON_ADULT_OR_SERVICE = "adult_or_service"
REASON_DEFERRED = "deferred"
REASON_NOT_ELIGIBLE = "not_eligible"
REASON_DISPATCH = "dispatch"


def base_date_for(target_year: int) -> date:
    return date(target_year, 1, 1)


def _full_years_between(start: date, reference: date) -> int:
    years = reference.year - start.year
    if (reference.month, reference.day) < (start.month, start.day):
        years -= 1
    return max(years, 0)


def calc_age(birth_date: date, target_year: int, method: str) -> int:
    if method == AGE_CALC_KOREAN:
        return target_year - birth_date.year + 1
    if method == AGE_CALC_INTERNATIONAL:
        return _full_years_between(birth_date, base_date_for(target_year))
    raise ValueError("unsupported age calculation method")


def calc_service_years(hire_date: date, target_year: int) -> int:
    return _full_years_between(hire_date, base_date_for(target_year))


@dataclass(frozen=True)
class DeterminationSettings:
    age_calc_method: str = AGE_CALC_KOREAN
    senior_age: int = 57
    adult_age: int = 40
    service_years_threshold: int = 10


@dataclass(frozen=True)
class DeterminationResult:
    age: int
    service_years: int
    is_senior: bool
    is_adult: bool
    is_long_service: bool
    prior_year_examined: bool
    is_target: bool
    reason: str


def determine(
    *,
    birth_date: date,
    hire_date: date,
    occupation: str,
    prior_year_examined: bool,
    settings: DeterminationSettings,
    target_year: int,
) -> DeterminationResult:
    age = calc_age(birth_date, target_year, settings.age_calc_method)
    service_years = calc_service_years(hire_date, target_year)
    is_senior = age >= settings.senior_age
    is_adult = age >= settings.adult_age
    is_long_service = service_years >= settings.service_years_threshold

    if occupation.strip() in EXCLUDED_OCCUPATIONS:
        is_target, reason = False, REASON_DISPATCH
    elif is_senior:
        is_target, reason = True, REASON_SENIOR
    elif is_adult or is_long_service:
        if prior_year_examined:
            is_target, reason = False, REASON_DEFERRED
        else:
            is_target, reason = True, REASON_ADULT_OR_SERVICE
    else:
        is_target, reason = False, REASON_NOT_ELIGIBLE

    return DeterminationResult(
        age=age,
        service_years=service_years,
        is_senior=is_senior,
        is_adult=is_adult,
        is_long_service=is_long_service,
        prior_year_examined=prior_year_examined,
        is_target=is_target,
        reason=reason,
    )
