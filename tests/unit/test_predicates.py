"""Operator semantics.

The most important cases here are the `None` ones. A predicate that succeeds
against missing data turns "Zence could not see" into "Zence checked and it was
fine", which is the exact failure this project exists to prevent.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    NORTHSTAR_DOMAIN,
    PII_TAG,
    make_action,
    make_evidence,
    make_workspace,
)
from zence_core.policy.fields import EvalContext, UnknownFieldError, resolve
from zence_core.policy.predicates import evaluate_predicate
from zence_core.schemas import Predicate

LISTS = {
    "allowed_domains": [NORTHSTAR_DOMAIN],
    "sensitive_tags": [PII_TAG],
    "allowed_environments": ["DEV", "QA"],
}


def resolve_list(name: str) -> list[str]:
    return LISTS[name]


def context(**evidence_kwargs: object) -> EvalContext:
    return EvalContext(
        action=make_action(),
        workspace=make_workspace(),
        evidence=make_evidence(**evidence_kwargs),  # type: ignore[arg-type]
    )


def check(path: str, raw: dict[str, object], ctx: EvalContext) -> bool:
    return evaluate_predicate(path, Predicate.model_validate(raw), ctx, resolve_list)


# --- equals / not_equals -----------------------------------------------------


def test_equals_matches_scalar() -> None:
    assert check("asset.environment", {"equals": "DEV"}, context(environment="DEV"))


def test_equals_rejects_different_scalar() -> None:
    assert not check("asset.environment", {"equals": "PROD"}, context(environment="DEV"))


def test_equals_on_bool_field() -> None:
    ctx = context(domain=NORTHSTAR_DOMAIN)
    assert check("asset.in_domain", {"equals": True}, ctx)
    assert not check("asset.in_domain", {"equals": False}, ctx)


def test_not_equals_is_false_when_field_is_none() -> None:
    """`not_equals` against nothing is not a match.

    Otherwise every rule of the form "environment is not PROD" would fire for
    assets whose environment Zence never managed to read.
    """
    ctx = context(environment=None)
    assert resolve("asset.environment", ctx) is None
    assert not check("asset.environment", {"not_equals": "PROD"}, ctx)


# --- in / not_in -------------------------------------------------------------


def test_in_matches_against_reference_list() -> None:
    ctx = context(environment="DEV")
    assert check("asset.environment", {"in": "$allowed_environments"}, ctx)


def test_in_rejects_value_outside_list() -> None:
    ctx = context(environment="PROD")
    assert not check("asset.environment", {"in": "$allowed_environments"}, ctx)


def test_not_in_is_false_when_field_is_none() -> None:
    """The single most dangerous predicate to get wrong.

    A missing domain must not satisfy "domain is not in allowed_domains" — that
    would produce a confident cross-client denial built on no evidence at all.
    """
    ctx = context(domain=None)
    assert not check("asset.domain_urn", {"not_in": "$allowed_domains"}, ctx)


def test_not_in_matches_a_real_foreign_domain() -> None:
    ctx = context(domain=BLUEPEAK_DOMAIN)
    assert check("asset.domain_urn", {"not_in": "$allowed_domains"}, ctx)


# --- intersects --------------------------------------------------------------


def test_intersects_finds_dataset_tag() -> None:
    ctx = context(tags={PII_TAG})
    assert check("asset.all_tags", {"intersects": "$sensitive_tags"}, ctx)


def test_intersects_finds_column_level_tag_only() -> None:
    """Column-level PII is the realistic case: the dataset is clean, one field is not."""
    from zence_core.schemas import ColumnTags

    ctx = context(
        tags=set(),
        column_tags=(ColumnTags(field_path="email", tags=frozenset({PII_TAG})),),
    )
    assert not check("asset.tags", {"intersects": "$sensitive_tags"}, ctx)
    assert check("asset.all_tags", {"intersects": "$sensitive_tags"}, ctx)


def test_intersects_is_false_on_empty_set() -> None:
    assert not check("asset.all_tags", {"intersects": "$sensitive_tags"}, context(tags=set()))


def test_not_intersects_is_false_when_field_is_none() -> None:
    ctx = EvalContext(action=make_action(), workspace=make_workspace(), evidence=None)
    assert not check("asset.all_tags", {"not_intersects": "$sensitive_tags"}, ctx)


def test_not_intersects_matches_a_clean_asset() -> None:
    assert check("asset.all_tags", {"not_intersects": "$sensitive_tags"}, context(tags=set()))


# --- matches -----------------------------------------------------------------


def test_matches_is_fullmatch_not_search() -> None:
    """Anchored on purpose: an unanchored `prod` would match `reproduction`."""
    ctx = context(name="northstar.marketing_leads")
    assert check("asset.name", {"matches": r"northstar\..*"}, ctx)
    assert not check("asset.name", {"matches": r"marketing"}, ctx)


def test_matches_is_false_when_field_is_none() -> None:
    assert not check("asset.domain_urn", {"matches": r".*"}, context(domain=None))


def test_matches_bounds_the_subject_length() -> None:
    """The subject is truncated before matching, so a huge value cannot be used
    to make an innocuous pattern do unbounded work."""
    from zence_core.schemas import MAX_SUBJECT_CHARS

    oversized = MAX_SUBJECT_CHARS + 500
    ctx = context(name="x" * oversized)

    # Exactly the bound matches, because that is all the matcher ever sees.
    assert check("asset.name", {"matches": f"x{{{MAX_SUBJECT_CHARS}}}"}, ctx)
    # The true length does not, because those characters were dropped.
    assert not check("asset.name", {"matches": f"x{{{oversized}}}"}, ctx)


# --- gte / lte ---------------------------------------------------------------


def test_gte_on_downstream_count() -> None:
    ctx = context(downstream_critical=("urn:li:dashboard:(looker,x)",))
    assert check("asset.downstream_critical_count", {"gte": 1}, ctx)
    assert not check("asset.downstream_critical_count", {"gte": 2}, ctx)


def test_gte_is_false_when_field_is_none() -> None:
    ctx = EvalContext(action=make_action(), workspace=make_workspace(), evidence=None)
    assert not check("asset.downstream_critical_count", {"gte": 1}, ctx)


def test_lte_on_downstream_count() -> None:
    assert check("asset.downstream_critical_count", {"lte": 0}, context())


# --- exists ------------------------------------------------------------------


def test_exists_false_matches_empty_owner_set() -> None:
    assert check("asset.owners", {"exists": False}, context(owners=set()))


def test_exists_true_matches_populated_owner_set() -> None:
    assert check("asset.owners", {"exists": True}, context(owners={"urn:li:corpuser:dana"}))


def test_exists_is_the_only_operator_that_reads_none_as_information() -> None:
    ctx = context(domain=None)
    assert check("asset.domain_urn", {"exists": False}, ctx)
    assert not check("asset.domain_urn", {"exists": True}, ctx)


# --- field allowlist ---------------------------------------------------------


def test_unknown_field_raises_with_a_suggestion() -> None:
    with pytest.raises(UnknownFieldError) as excinfo:
        resolve("asset.doamin_urn", context())
    assert "asset.domain_urn" in str(excinfo.value)


def test_unknown_field_is_not_silently_none() -> None:
    with pytest.raises(UnknownFieldError):
        resolve("asset.__class__", context())


def test_asset_fields_are_none_without_evidence() -> None:
    ctx = EvalContext(action=make_action(), workspace=make_workspace(), evidence=None)
    assert resolve("asset.domain_urn", ctx) is None
    assert resolve("asset.in_domain", ctx) is None


# --- predicate parsing -------------------------------------------------------


def test_predicate_rejects_multiple_operators() -> None:
    with pytest.raises(ValueError, match="single-key mapping"):
        Predicate.model_validate({"equals": "a", "in": ["b"]})


def test_predicate_rejects_unknown_operator() -> None:
    with pytest.raises(ValueError, match="unknown operator"):
        Predicate.model_validate({"approximately": "a"})


def test_predicate_rejects_invalid_regex() -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        Predicate.model_validate({"matches": "([unclosed"})


def test_predicate_rejects_overlong_regex() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        Predicate.model_validate({"matches": "a" * 500})


def test_predicate_exists_requires_boolean() -> None:
    with pytest.raises(ValueError, match="takes a boolean"):
        Predicate.model_validate({"exists": "yes"})
