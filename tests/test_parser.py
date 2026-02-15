"""Юнит-тесты для парсера логических формул."""

import pytest
from parser.logic_parser import parse_formula
from parser.ast_nodes import Var, Pred, Not, And, Or, Implies, Bicond, Const


def test_parse_variable():
    """Парсинг переменной."""
    result = parse_formula("fastChanges")
    assert result == Var("fastChanges")


def test_parse_const_true():
    """Парсинг константы true."""
    result = parse_formula("true")
    assert result == Const(True)


def test_parse_const_false():
    """Парсинг константы false."""
    result = parse_formula("false")
    assert result == Const(False)


def test_parse_predicate_with_string_args():
    """Парсинг предиката со строковыми аргументами."""
    result = parse_formula('reducedCycle("5d", "1h")')
    assert result == Pred("reducedCycle", ("5d", "1h"))


def test_parse_predicate_with_name_arg():
    """Парсинг предиката с именным аргументом."""
    result = parse_formula("crashFreeRate(high)")
    assert result == Pred("crashFreeRate", ("high",))


def test_parse_negation():
    """Парсинг отрицания."""
    result = parse_formula("~fastChanges")
    assert result == Not(Var("fastChanges"))


def test_parse_conjunction():
    """Парсинг конъюнкции."""
    result = parse_formula("a & b")
    assert result == And(Var("a"), Var("b"))


def test_parse_disjunction():
    """Парсинг дизъюнкции."""
    result = parse_formula("a | b")
    assert result == Or(Var("a"), Var("b"))


def test_parse_implication():
    """Парсинг импликации."""
    result = parse_formula("a -> b")
    assert result == Implies(Var("a"), Var("b"))


def test_parse_biconditional():
    """Парсинг бикондиционала."""
    result = parse_formula("a <-> b")
    assert result == Bicond(Var("a"), Var("b"))


def test_parse_negation_of_conjunction():
    """Парсинг отрицания конъюнкции."""
    result = parse_formula("~(a & b)")
    assert result == Not(And(Var("a"), Var("b")))


def test_parse_implication_chain_right_assoc():
    """Правоассоциативность импликации: a -> b -> c = a -> (b -> c)."""
    result = parse_formula("a -> b -> c")
    assert result == Implies(Var("a"), Implies(Var("b"), Var("c")))


def test_precedence_and_over_or():
    """Приоритет: a | b & c = a | (b & c)."""
    result = parse_formula("a | b & c")
    assert result == Or(Var("a"), And(Var("b"), Var("c")))


def test_precedence_or_over_implies():
    """Приоритет: a -> b | c = a -> (b | c)."""
    result = parse_formula("a -> b | c")
    assert result == Implies(Var("a"), Or(Var("b"), Var("c")))


def test_complex_formula():
    """Составная формула с несколькими связками."""
    result = parse_formula("fastChanges -> moreBugs & ~qualityArch")
    expected = Implies(
        Var("fastChanges"),
        And(Var("moreBugs"), Not(Var("qualityArch")))
    )
    assert result == expected


def test_domain_rule_sdui():
    """Парсинг доменного правила SDUI."""
    result = parse_formula("sdui -> compatibility & rollback & monitoring")
    expected = Implies(
        Var("sdui"),
        And(And(Var("compatibility"), Var("rollback")), Var("monitoring"))
    )
    assert result == expected


def test_invalid_formula():
    """Невалидная формула вызывает исключение."""
    with pytest.raises(Exception):
        parse_formula("-> ->")
