"""Tests for local NLP clarification intent classifier."""

from agent_host.nlp.intent_classifier import PlanClarificationIntentClassifier


def test_sanitize_text_redacts_paths_and_sensitive_tokens() -> None:
    raw = (
        "Move /Users/alex/Documents/todo.txt to ../archive/todo.txt and "
        "check C:\\Users\\alex\\Desktop\\notes.md with token "
        "1234567890abcdef1234567890abcdef and https://example.com"
    )
    sanitized = PlanClarificationIntentClassifier.sanitize_text(raw)
    lowered = sanitized.lower()
    assert "/users/" not in lowered
    assert "../archive" not in lowered
    assert "c:\\users" not in lowered
    assert "https://example.com" not in lowered
    assert "[path]" in lowered
    assert "[hex]" in lowered or "[token]" in lowered
    assert "[url]" in lowered


def test_classify_accepts_structured_clarification_reply() -> None:
    classifier = PlanClarificationIntentClassifier()
    result = classifier.classify(
        reply_prompt="6 weeks, beginner baseline, weekends only",
        root_prompt="Create a study plan for machine learning",
        pending_dimension="timeframe",
        question_count=2,
    )
    assert result.source == "builtin"
    assert result.model_name == "builtin"
    assert result.is_clarification_reply is True
    assert result.confidence >= 0.36


def test_classify_rejects_unrelated_task() -> None:
    classifier = PlanClarificationIntentClassifier()
    result = classifier.classify(
        reply_prompt="Write a short poem about winter clouds.",
        root_prompt="Create a study plan for machine learning",
        pending_dimension="constraints",
        question_count=2,
    )
    assert result.source == "builtin"
    assert result.is_clarification_reply is False
    assert result.confidence < 0.36
