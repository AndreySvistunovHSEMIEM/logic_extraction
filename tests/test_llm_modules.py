"""Тесты LLM-модулей (extractor и analyzer) с mock OpenAI."""

import json
from unittest.mock import patch, MagicMock

import pytest

from prover.z3_checker import CheckResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_openai_response(content: str | None):
    """Создаёт mock-объект ответа OpenAI."""
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# extractor tests
# ---------------------------------------------------------------------------
class TestExtractor:
    @patch("llm.extractor.OpenAI")
    def test_extract_success(self, mock_openai_cls):
        from llm.extractor import extract_predicates

        result_data = {
            "claims": [
                {"label": "claim_1", "formula": "fastChanges", "original_text": "test"}
            ],
            "predicates_used": {"fastChanges": "desc"},
        }
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps(result_data)
        )
        mock_openai_cls.return_value = client

        result = extract_predicates("some resume")
        assert result["claims"] == result_data["claims"]

    @patch("llm.extractor.OpenAI")
    def test_extract_none_content(self, mock_openai_cls):
        from llm.extractor import extract_predicates

        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(None)
        mock_openai_cls.return_value = client

        with pytest.raises(ValueError, match="empty content"):
            extract_predicates("some resume")

    @patch("llm.extractor.OpenAI")
    def test_extract_invalid_json(self, mock_openai_cls):
        from llm.extractor import extract_predicates

        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(
            "not json at all"
        )
        mock_openai_cls.return_value = client

        with pytest.raises(json.JSONDecodeError):
            extract_predicates("some resume")

    @patch("llm.extractor.OpenAI")
    def test_extract_missing_claims_key(self, mock_openai_cls):
        from llm.extractor import extract_predicates

        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({"predicates_used": {}})
        )
        mock_openai_cls.return_value = client

        with pytest.raises(ValueError, match="claims"):
            extract_predicates("some resume")


# ---------------------------------------------------------------------------
# analyzer tests
# ---------------------------------------------------------------------------
class TestAnalyzer:
    def test_consistent_no_llm_call(self):
        from llm.analyzer import analyze_contradictions

        result = CheckResult(is_consistent=True, unsat_core_labels=[], model={"a": True})
        analysis = analyze_contradictions(result, [], [])
        assert analysis["contradictions"] == []
        assert "Противоречий не найдено" in analysis["overall_assessment"]

    @patch("llm.analyzer.OpenAI")
    def test_analyze_success(self, mock_openai_cls):
        from llm.analyzer import analyze_contradictions

        analysis_data = {
            "contradictions": [{"explanation": "test"}],
            "overall_assessment": "Found issues",
        }
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps(analysis_data)
        )
        mock_openai_cls.return_value = client

        check_result = CheckResult(
            is_consistent=False, unsat_core_labels=["claim_1"], model=None
        )
        claims = [{"label": "claim_1", "formula": "a", "original_text": "text"}]
        result = analyze_contradictions(check_result, claims, [])
        assert result["contradictions"] == analysis_data["contradictions"]

    @patch("llm.analyzer.OpenAI")
    def test_analyze_none_content(self, mock_openai_cls):
        from llm.analyzer import analyze_contradictions

        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(None)
        mock_openai_cls.return_value = client

        check_result = CheckResult(
            is_consistent=False, unsat_core_labels=["claim_1"], model=None
        )
        with pytest.raises(ValueError, match="empty content"):
            analyze_contradictions(check_result, [], [])

    @patch("llm.analyzer.OpenAI")
    def test_analyze_missing_keys(self, mock_openai_cls):
        from llm.analyzer import analyze_contradictions

        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(
            json.dumps({"contradictions": []})
        )
        mock_openai_cls.return_value = client

        check_result = CheckResult(
            is_consistent=False, unsat_core_labels=["claim_1"], model=None
        )
        with pytest.raises(ValueError, match="overall_assessment"):
            analyze_contradictions(check_result, [], [])
