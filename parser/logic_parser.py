"""Парсер формул пропозициональной логики на основе Lark."""

import os
from lark import Lark, Transformer, v_args
from parser.ast_nodes import (
    Formula, Const, Var, Pred, Not, And, Or, Implies, Bicond,
)

_GRAMMAR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "grammar", "logic.lark"
)

_parser = Lark.open(_GRAMMAR_PATH, parser="earley", start="start")


@v_args(inline=True)
class LogicTransformer(Transformer):
    """Преобразует дерево разбора Lark в типизированные AST-узлы."""

    def const_true(self, _=None):
        return Const(True)

    def const_false(self, _=None):
        return Const(False)

    def variable(self, name):
        return Var(str(name))

    def predicate(self, name, args):
        return Pred(str(name), args)

    def arguments(self, *args):
        return tuple(args)

    def argument(self, value):
        s = str(value)
        # Убрать кавычки у экранированных строк
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s

    def logic_not(self, operand):
        return Not(operand)

    def logic_and(self, left, right):
        return And(left, right)

    def logic_or(self, left, right):
        return Or(left, right)

    def logic_implies(self, left, right):
        return Implies(left, right)

    def logic_bicond(self, left, right):
        return Bicond(left, right)


_transformer = LogicTransformer()


def parse_formula(text: str) -> Formula:
    """Парсит строку в AST логической формулы.

    Выбрасывает lark.exceptions.LarkError при невалидном синтаксисе.
    """
    tree = _parser.parse(text)
    return _transformer.transform(tree)
