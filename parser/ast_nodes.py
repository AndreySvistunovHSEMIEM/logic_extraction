"""Датаклассы AST-узлов для формул пропозициональной логики."""

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Const:
    """Булева константа: true или false."""
    value: bool

    def __str__(self):
        return "true" if self.value else "false"


@dataclass(frozen=True)
class Var:
    """Пропозициональная переменная (напр. fastChanges)."""
    name: str

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class Pred:
    """Граундовый предикат с аргументами (напр. reducedCycle("5d", "1h"))."""
    name: str
    args: tuple[str, ...]

    def __str__(self):
        args_str = ", ".join(f'"{a}"' for a in self.args)
        return f"{self.name}({args_str})"


@dataclass(frozen=True)
class Not:
    """Логическое отрицание."""
    operand: "Formula"

    def __str__(self):
        return f"~{self.operand}"


@dataclass(frozen=True)
class And:
    """Логическая конъюнкция."""
    left: "Formula"
    right: "Formula"

    def __str__(self):
        return f"({self.left} & {self.right})"


@dataclass(frozen=True)
class Or:
    """Логическая дизъюнкция."""
    left: "Formula"
    right: "Formula"

    def __str__(self):
        return f"({self.left} | {self.right})"


@dataclass(frozen=True)
class Implies:
    """Логическая импликация (правоассоциативная)."""
    left: "Formula"
    right: "Formula"

    def __str__(self):
        return f"({self.left} -> {self.right})"


@dataclass(frozen=True)
class Bicond:
    """Логический бикондиционал."""
    left: "Formula"
    right: "Formula"

    def __str__(self):
        return f"({self.left} <-> {self.right})"


# Объединённый тип для всех узлов формул
Formula = Union[Const, Var, Pred, Not, And, Or, Implies, Bicond]
