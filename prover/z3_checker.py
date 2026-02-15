"""Проверка непротиворечивости на Z3 с извлечением unsat core."""

from dataclasses import dataclass, field
from typing import Optional
import z3

from parser.ast_nodes import (
    Formula, Const, Var, Pred, Not, And, Or, Implies, Bicond,
)


@dataclass
class CheckResult:
    """Результат проверки непротиворечивости Z3."""
    is_consistent: bool
    unsat_core_labels: list[str] = field(default_factory=list)
    label_to_formula: dict[str, str] = field(default_factory=dict)
    model: Optional[str] = None


class Z3Checker:
    """Конвертирует AST-формулы в Z3 и проверяет выполнимость."""

    def __init__(self):
        self._vars: dict[str, z3.BoolRef] = {}

    def _get_var(self, name: str) -> z3.BoolRef:
        if name not in self._vars:
            self._vars[name] = z3.Bool(name)
        return self._vars[name]

    def to_z3(self, formula: Formula) -> z3.BoolRef:
        """Рекурсивно конвертирует AST-формулу в Z3 BoolRef."""
        match formula:
            case Const(value=True):
                return z3.BoolVal(True)
            case Const(value=False):
                return z3.BoolVal(False)
            case Var(name=name):
                return self._get_var(name)
            case Pred(name=name, args=args):
                # Разворачиваем предикат в пропозициональную переменную
                flat = f"{name}_{'_'.join(args)}"
                return self._get_var(flat)
            case Not(operand=op):
                return z3.Not(self.to_z3(op))
            case And(left=l, right=r):
                return z3.And(self.to_z3(l), self.to_z3(r))
            case Or(left=l, right=r):
                return z3.Or(self.to_z3(l), self.to_z3(r))
            case Implies(left=l, right=r):
                return z3.Implies(self.to_z3(l), self.to_z3(r))
            case Bicond(left=l, right=r):
                lz = self.to_z3(l)
                rz = self.to_z3(r)
                return lz == rz
            case _:
                raise ValueError(f"Неизвестный тип формулы: {type(formula)}")

    def check(self, labeled_formulas: list[tuple[str, Formula]]) -> CheckResult:
        """Проверяет непротиворечивость набора маркированных формул.

        Args:
            labeled_formulas: Список пар (метка, формула).

        Returns:
            CheckResult со статусом и unsat core при противоречии.
        """
        self._vars.clear()
        solver = z3.Solver()

        label_to_formula_str: dict[str, str] = {}

        for label, formula in labeled_formulas:
            z3_formula = self.to_z3(formula)
            p = z3.Bool(f"label_{label}")
            solver.assert_and_track(z3_formula, p)
            label_to_formula_str[label] = str(formula)

        result = solver.check()

        if result == z3.sat:
            model_str = str(solver.model())
            return CheckResult(
                is_consistent=True,
                model=model_str,
                label_to_formula=label_to_formula_str,
            )
        else:
            core = solver.unsat_core()
            # Убираем префикс "label_" из меток ядра
            core_labels = []
            for c in core:
                name = str(c)
                if name.startswith("label_"):
                    core_labels.append(name[len("label_"):])
                else:
                    core_labels.append(name)
            return CheckResult(
                is_consistent=False,
                unsat_core_labels=core_labels,
                label_to_formula=label_to_formula_str,
            )
