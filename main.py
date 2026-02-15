"""Главный пайплайн: Резюме -> Извлечение LLM -> Парсинг Lark -> Проверка Z3 -> Анализ LLM."""

import argparse
import json
import sys

from parser.logic_parser import parse_formula
from prover.z3_checker import Z3Checker, CheckResult
from domain.rules import DOMAIN_RULES
from llm.extractor import extract_predicates
from llm.analyzer import analyze_contradictions


def read_resume(path: str) -> str:
    """Читает текст резюме из файла (txt или PDF)."""
    if path.lower().endswith(".pdf"):
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    else:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


def _print_header(title: str):
    """Печатает заголовок стадии."""
    print("=" * 60)
    print(title)
    print("=" * 60)


# ---------------------------------------------------------------------------
# Стадии пайплайна
# ---------------------------------------------------------------------------

def stage_extract(resume_text: str, verbose: bool) -> tuple[list[dict], dict]:
    """Стадия 2: извлечение утверждений через LLM.

    Возвращает (claims, predicates_used).
    """
    if verbose:
        _print_header("СТАДИЯ 2: Извлечение LLM (утверждения -> формулы)")

    extraction = extract_predicates(resume_text)
    claims = extraction.get("claims", [])
    predicates_used = extraction.get("predicates_used", {})

    if verbose:
        print(f"  Извлечено {len(claims)} утверждений:")
        for c in claims:
            print(f"    [{c['label']}] {c['formula']}")
            print(f"      из: \"{c['original_text']}\"")
        print()

    return claims, predicates_used


def _parse_formulas_list(
    items: list[tuple[str, str]], tag: str, verbose: bool
) -> tuple[list[tuple[str, object]], list[dict]]:
    """Парсит список (метка, строка_формулы) в AST.

    Возвращает (успешно_распарсенные, ошибки).
    """
    parsed = []
    errors = []
    for label, formula_str in items:
        try:
            ast = parse_formula(formula_str)
            parsed.append((label, ast))
            if verbose:
                print(f"  [{tag}] {label}: {formula_str}")
        except Exception as e:
            errors.append({"label": label, "formula": formula_str, "error": str(e)})
            if verbose:
                print(f"  [{tag}] {label}: {formula_str} ОШИБКА ({e})")
    return parsed, errors


def stage_parse_and_check(
    claims: list[dict], verbose: bool
) -> tuple[CheckResult, list[dict]]:
    """Стадия 3: парсинг формул и проверка непротиворечивости через Z3.

    Возвращает (check_result, parse_errors).
    """
    if verbose:
        _print_header("СТАДИЯ 3: Парсинг и проверка непротиворечивости (Z3)")

    # Парсинг доменных правил
    rule_items = [(label, formula) for label, formula in DOMAIN_RULES]
    parsed_rules, rule_errors = _parse_formulas_list(rule_items, "правило", verbose)

    # Парсинг формул утверждений из резюме
    claim_items = [(c["label"], c["formula"]) for c in claims]
    parsed_claims, claim_errors = _parse_formulas_list(claim_items, "утверждение", verbose)

    labeled_formulas = parsed_rules + parsed_claims
    parse_errors = rule_errors + claim_errors

    if verbose:
        print(f"\n  Распарсено {len(labeled_formulas)} формул, {len(parse_errors)} ошибок")

    # Проверка Z3
    checker = Z3Checker()
    check_result = checker.check(labeled_formulas)

    if verbose:
        status = "SAT (непротиворечиво)" if check_result.is_consistent else "UNSAT (есть противоречия)"
        print(f"\n  Результат Z3: {status}")
        if not check_result.is_consistent:
            print(f"  Ядро противоречия (unsat core): {check_result.unsat_core_labels}")
        if check_result.model:
            print(f"  Модель: {check_result.model}")
        print()

    return check_result, parse_errors


def stage_analyze(
    check_result: CheckResult, claims: list[dict], verbose: bool
) -> dict:
    """Стадия 4: анализ противоречий через LLM.

    Возвращает dict с 'contradictions' и 'overall_assessment'.
    """
    if verbose:
        _print_header("СТАДИЯ 4: Анализ противоречий (LLM)")

    analysis = analyze_contradictions(check_result, claims, DOMAIN_RULES)

    if verbose:
        for i, c in enumerate(analysis.get("contradictions", []), 1):
            print(f"\n  Противоречие {i} (серьёзность: {c.get('severity', 'неизвестно')}):")
            print(f"    Участвуют: {c.get('involved_labels', [])}")
            print(f"    Объяснение: {c.get('explanation', '')}")
            print(f"    Рекомендация: {c.get('suggestion', '')}")
        print(f"\n  Общая оценка: {analysis.get('overall_assessment', '')}")
        print()

    return analysis


# ---------------------------------------------------------------------------
# Оркестрация
# ---------------------------------------------------------------------------

def run_pipeline(resume_path: str, verbose: bool = False) -> dict:
    """Запускает полный пайплайн фактчекинга.

    Возвращает dict-отчёт с результатами всех стадий.
    """
    # Стадия 1: чтение
    if verbose:
        _print_header("СТАДИЯ 1: Чтение резюме")
    resume_text = read_resume(resume_path)
    if verbose:
        print(f"  Прочитано {len(resume_text)} символов из {resume_path}\n")

    # Стадия 2: извлечение
    claims, predicates_used = stage_extract(resume_text, verbose)

    # Стадия 3: парсинг + Z3
    check_result, parse_errors = stage_parse_and_check(claims, verbose)

    # Стадия 4: анализ
    analysis = stage_analyze(check_result, claims, verbose)

    return {
        "stages": {
            "extraction": {
                "claims_count": len(claims),
                "claims": claims,
                "predicates_used": predicates_used,
            },
            "z3_check": {
                "is_consistent": check_result.is_consistent,
                "unsat_core_labels": check_result.unsat_core_labels,
                "parse_errors": parse_errors,
                "total_formulas": len(DOMAIN_RULES) + len(claims) - len(parse_errors),
            },
            "analysis": analysis,
        },
        "summary": {
            "resume_path": resume_path,
            "total_claims": len(claims),
            "total_rules": len(DOMAIN_RULES),
            "is_consistent": check_result.is_consistent,
            "contradictions_found": len(analysis.get("contradictions", [])),
        },
    }


def main():
    arg_parser = argparse.ArgumentParser(
        description="Фактчекер резюме: LLM + Z3"
    )
    arg_parser.add_argument(
        "--resume", required=True, help="Путь к файлу резюме (txt или pdf)"
    )
    arg_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Подробный вывод"
    )
    arg_parser.add_argument(
        "--output", "-o", help="Сохранить JSON-отчёт в файл"
    )

    args = arg_parser.parse_args()

    try:
        report = run_pipeline(args.resume, verbose=args.verbose)
    except Exception as e:
        print(f"Ошибка пайплайна: {e}", file=sys.stderr)
        sys.exit(1)

    report_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_json)
        print(f"Отчёт сохранён в {args.output}")
    else:
        print("\n" + "=" * 60)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("=" * 60)
        print(report_json)


if __name__ == "__main__":
    main()
