"""Анализ противоречий через LLM на основе unsat core."""

import json
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from llm.prompts import ANALYSIS_SYSTEM_PROMPT
from prover.z3_checker import CheckResult


def _build_analysis_message(
    core_labels: set[str],
    claims: list[dict],
    domain_rules: list[tuple[str, str]],
) -> str:
    """Формирует сообщение для LLM из unsat core, утверждений и правил."""
    involved_claims = [c for c in claims if c["label"] in core_labels]
    involved_rules = [(l, f) for l, f in domain_rules if l in core_labels]

    claims_text = "\n".join(
        f'  {c["label"]}: {c["formula"]}  (из: "{c["original_text"]}")'
        for c in involved_claims
    )
    rules_text = "\n".join(
        f"  {label}: {formula}" for label, formula in involved_rules
    )
    all_core = ", ".join(sorted(core_labels))

    return (
        f"Метки unsat core: {all_core}\n\n"
        f"Утверждения из резюме:\n{claims_text}\n\n"
        f"Доменные правила:\n{rules_text}\n\n"
        f"Объясни противоречия."
    )


def _call_llm(user_message: str) -> dict:
    """Отправляет запрос к LLM и возвращает распарсенный JSON-ответ."""
    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    return json.loads(response.choices[0].message.content)


def analyze_contradictions(
    check_result: CheckResult,
    claims: list[dict],
    domain_rules: list[tuple[str, str]],
) -> dict:
    """Анализирует противоречия, найденные Z3, через LLM.

    Args:
        check_result: CheckResult из Z3 с метками unsat core.
        claims: Список утверждений из экстрактора (label, original_text, formula).
        domain_rules: Список кортежей (метка, строка_формулы) доменных правил.

    Returns:
        Dict с ключами 'contradictions' и 'overall_assessment'.
    """
    if check_result.is_consistent:
        return {
            "contradictions": [],
            "overall_assessment": "Противоречий не найдено. Все утверждения логически согласованы с доменными правилами.",
        }

    core_labels = set(check_result.unsat_core_labels)
    message = _build_analysis_message(core_labels, claims, domain_rules)
    return _call_llm(message)
