"""Operator evaluation.

Ten operators, each a small pure function. No expression parsing, no `eval`, no
dynamic dispatch on user-supplied strings beyond a dictionary lookup.

**The None rule.** When a field resolves to `None` — the asset has no domain, the
lookup failed, there is no evidence at all — every operator except `exists`
returns `False`, meaning *this rule does not fire*.

That is deliberate and it matters. The tempting alternative, letting `not_in`
succeed against `None`, would make a rule like "domain not in allowed_domains"
fire for every asset Zence failed to resolve, producing confident denials built
on no evidence. Missing information is handled once, explicitly, by the
fail-safe matrix in `defaults.py` — never by accident inside a predicate.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from zence_core.policy.fields import EvalContext, FieldValue, resolve
from zence_core.schemas import MAX_SUBJECT_CHARS, Predicate

#: Resolves a `$name` reference to its declared list.
ListResolver = Callable[[str], list[str]]


def _as_set(value: Any) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, frozenset):
        return value
    if isinstance(value, set | list | tuple):
        return frozenset(str(item) for item in value)
    return frozenset({str(value)})


def _resolve_operand(predicate: Predicate, resolve_list: ListResolver) -> Any:
    """Dereference `$name`, otherwise return the literal."""
    name = predicate.reference_name
    if name is None:
        return predicate.value
    return resolve_list(name)


def _op_equals(field: FieldValue, operand: Any) -> bool:
    if field is None:
        return False
    if isinstance(field, frozenset):
        return field == _as_set(operand)
    return bool(field == operand)


def _op_in(field: FieldValue, operand: Any) -> bool:
    if field is None:
        return False
    candidates = _as_set(operand) or frozenset()
    if isinstance(field, frozenset):
        # Every member must appear in the operand set.
        return bool(field) and field <= candidates
    return str(field) in candidates


def _op_intersects(field: FieldValue, operand: Any) -> bool:
    if field is None:
        return False
    left = _as_set(field) or frozenset()
    right = _as_set(operand) or frozenset()
    return bool(left & right)


def _op_matches(field: FieldValue, operand: Any) -> bool:
    if field is None or not isinstance(operand, str):
        return False
    subjects: Iterable[str]
    subjects = field if isinstance(field, frozenset) else [str(field)]
    # Anchored and length-bounded. See MAX_SUBJECT_CHARS in schemas.policy for why.
    pattern = re.compile(operand)
    return any(pattern.fullmatch(subject[:MAX_SUBJECT_CHARS]) is not None for subject in subjects)


def _op_gte(field: FieldValue, operand: Any) -> bool:
    if field is None or isinstance(field, frozenset | bool):
        return False
    try:
        return float(field) >= float(operand)
    except (TypeError, ValueError):
        return False


def _op_lte(field: FieldValue, operand: Any) -> bool:
    if field is None or isinstance(field, frozenset | bool):
        return False
    try:
        return float(field) <= float(operand)
    except (TypeError, ValueError):
        return False


def _op_exists(field: FieldValue, operand: Any) -> bool:
    """The only operator that treats `None` as information rather than absence."""
    present = field is not None
    if isinstance(field, frozenset):
        present = bool(field)
    return present is bool(operand)


def evaluate_predicate(
    path: str,
    predicate: Predicate,
    context: EvalContext,
    resolve_list: ListResolver,
) -> bool:
    """Evaluate one field/predicate pair."""
    field = resolve(path, context)
    operand = _resolve_operand(predicate, resolve_list)

    match predicate.operator:
        case "equals":
            return _op_equals(field, operand)
        case "not_equals":
            return not _op_equals(field, operand) if field is not None else False
        case "in":
            return _op_in(field, operand)
        case "not_in":
            return not _op_in(field, operand) if field is not None else False
        case "intersects":
            return _op_intersects(field, operand)
        case "not_intersects":
            return not _op_intersects(field, operand) if field is not None else False
        case "matches":
            return _op_matches(field, operand)
        case "gte":
            return _op_gte(field, operand)
        case "lte":
            return _op_lte(field, operand)
        case "exists":
            return _op_exists(field, operand)

    raise AssertionError(f"unreachable operator {predicate.operator!r}")
