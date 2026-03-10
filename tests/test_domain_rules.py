"""Тесты парсинга всех доменных правил из domain/rules.py."""

import pytest
from domain.rules import DOMAIN_RULES
from parser.logic_parser import parse_formula


@pytest.mark.parametrize(
    "label,formula",
    DOMAIN_RULES,
    ids=[label for label, _ in DOMAIN_RULES],
)
def test_domain_rule_parses(label: str, formula: str):
    """Каждое доменное правило должно успешно парситься."""
    ast = parse_formula(formula)
    assert ast is not None, f"Rule {label} parsed to None"
