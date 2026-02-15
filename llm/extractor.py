"""Извлечение предикатов из текста резюме через LLM."""

import json
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from llm.prompts import build_extraction_prompt
from domain.rules import DOMAIN_RULES, DOMAIN_VOCABULARY


def extract_predicates(resume_text: str) -> dict:
    """Извлекает логические утверждения из текста резюме через LLM.

    Возвращает dict с ключами 'claims' и 'predicates_used'.
    """
    system_prompt = build_extraction_prompt(DOMAIN_VOCABULARY, DOMAIN_RULES)

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    response = client.chat.completions.create(
        model=LLM_MODEL,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Текст резюме:\n\n{resume_text}"},
        ],
    )

    content = response.choices[0].message.content
    return json.loads(content)
