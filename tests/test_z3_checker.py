"""Юнит-тесты для Z3 проверки непротиворечивости."""

import pytest
from parser.logic_parser import parse_formula
from prover.z3_checker import Z3Checker


def test_consistent_set():
    """Простое непротиворечивое множество должно быть SAT."""
    checker = Z3Checker()
    formulas = [
        ("f1", parse_formula("a -> b")),
        ("f2", parse_formula("a")),
        ("f3", parse_formula("b")),
    ]
    result = checker.check(formulas)
    assert result.is_consistent is True
    assert result.unsat_core_labels == []
    assert result.model is not None


def test_contradictory_set():
    """p и ~p должны быть UNSAT."""
    checker = Z3Checker()
    formulas = [
        ("f1", parse_formula("p")),
        ("f2", parse_formula("~p")),
    ]
    result = checker.check(formulas)
    assert result.is_consistent is False
    assert len(result.unsat_core_labels) > 0
    # Обе метки должны быть в unsat core
    assert set(result.unsat_core_labels) == {"f1", "f2"}


def test_unsat_core_with_rules():
    """Извлечение unsat core с доменными правилами."""
    checker = Z3Checker()
    formulas = [
        ("rule1", parse_formula("a -> b")),       # a влечёт b
        ("rule2", parse_formula("b -> c")),       # b влечёт c
        ("rule3", parse_formula("~c")),           # не c
        ("claim1", parse_formula("a")),           # a истинно
        ("unrelated", parse_formula("x | y")),    # не связано, НЕ должно быть в core
    ]
    result = checker.check(formulas)
    assert result.is_consistent is False
    # unrelated не должно быть в ядре
    assert "unrelated" not in result.unsat_core_labels
    # Ядро должно содержать цепочку: a, a->b, b->c, ~c
    core = set(result.unsat_core_labels)
    assert "claim1" in core
    assert "rule3" in core


def test_resume_contradiction_scenario():
    """Сценарий противоречия резюме: быстрые изменения + стабильность."""
    checker = Z3Checker()
    formulas = [
        # Доменные правила
        ("rule_fast_bugs", parse_formula("fastChanges -> moreBugs")),
        ("rule_stability_less", parse_formula("improvedStability -> lessChanges")),
        ("rule_conflict", parse_formula("~(moreBugs & lessChanges)")),
        # Утверждения из резюме
        ("claim_fast", parse_formula("fastChanges")),
        ("claim_stable", parse_formula("improvedStability")),
    ]
    result = checker.check(formulas)
    assert result.is_consistent is False
    core = set(result.unsat_core_labels)
    # Утверждения должны быть в ядре
    assert "claim_fast" in core
    assert "claim_stable" in core


def test_predicate_flattening():
    """Предикаты с аргументами сворачиваются в уникальные переменные."""
    checker = Z3Checker()
    formulas = [
        ("f1", parse_formula('reducedCycle("5d", "1h")')),
        ("f2", parse_formula('~reducedCycle("5d", "1h")')),
    ]
    result = checker.check(formulas)
    assert result.is_consistent is False


def test_empty_formulas():
    """Пустое множество тривиально непротиворечиво."""
    checker = Z3Checker()
    result = checker.check([])
    assert result.is_consistent is True
