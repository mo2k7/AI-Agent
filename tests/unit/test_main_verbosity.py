"""Unit coverage for prompt verbosity parsing."""

import pytest

from agent_host import main as main_module
from agent_host.tools import _helpers as helpers_module


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("low", 0),
        ("LOW", 0),
        (" medium ", 1),
        ("high", 2),
        ("extra_high", 3),
        (" EXTRA_HIGH ", 3),
    ],
)
def test_parse_verbosity_level_strict_valid(raw_value: str, expected: int) -> None:
    assert main_module._parse_verbosity_level_strict(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["", "extra high", "detailed", "v2", 2, None, object()])
def test_parse_verbosity_level_strict_invalid(raw_value: object) -> None:
    assert main_module._parse_verbosity_level_strict(raw_value) is None


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("direct", main_module.ExecutionMode.DIRECT),
        (" DIRECT ", main_module.ExecutionMode.DIRECT),
        ("plan", main_module.ExecutionMode.PLAN),
        ("PLAN", main_module.ExecutionMode.PLAN),
        ("teacher", main_module.ExecutionMode.TEACHER),
        (" TEACHER ", main_module.ExecutionMode.TEACHER),
    ],
)
def test_parse_execution_mode_strict_valid(raw_value: object, expected: object) -> None:
    assert main_module._parse_execution_mode_strict(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["", "guided", "planner", None, 3, object()])
def test_parse_execution_mode_strict_invalid(raw_value: object) -> None:
    assert main_module._parse_execution_mode_strict(raw_value) is None


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("readable_pro", "readable_pro"),
        (" GLASS_EDITORIAL ", "glass_editorial"),
        ("dense_technical", "dense_technical"),
    ],
)
def test_parse_presentation_style_strict_valid(raw_value: object, expected: str) -> None:
    assert main_module._parse_presentation_style_strict(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["", "readable-pro", "editorial", None, 5, object()])
def test_parse_presentation_style_strict_invalid(raw_value: object) -> None:
    assert main_module._parse_presentation_style_strict(raw_value) is None


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("wave_reveal", "wave_reveal"),
        (" TYPEWRITER_LUXE ", "typewriter_luxe"),
        ("minimal_motion", "minimal_motion"),
    ],
)
def test_parse_stream_animation_style_strict_valid(raw_value: object, expected: str) -> None:
    assert main_module._parse_stream_animation_style_strict(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["", "wave", "luxe", None, 7, object()])
def test_parse_stream_animation_style_strict_invalid(raw_value: object) -> None:
    assert main_module._parse_stream_animation_style_strict(raw_value) is None


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (False, False),
    ],
)
def test_parse_deep_think_flag_strict_valid(raw_value: object, expected: bool) -> None:
    assert main_module._parse_deep_think_flag_strict(raw_value) is expected


@pytest.mark.parametrize("raw_value", ["true", "false", 1, 0, None, object()])
def test_parse_deep_think_flag_strict_invalid(raw_value: object) -> None:
    assert main_module._parse_deep_think_flag_strict(raw_value) is None


@pytest.mark.parametrize(
    ("model_name", "expected"),
    [
        ("gemini-3-pro-preview", True),
        ("gemini-3-flash-preview", True),
        ("gemini-2.5-pro", True),
        ("gemini-2.5-flash", True),
        ("gemini-2.0-flash-exp", False),
        ("gemini-1.5-pro", False),
    ],
)
def test_model_supports_native_deep_think(model_name: str, expected: bool) -> None:
    assert main_module._model_supports_native_deep_think(model_name) is expected


def test_resolve_model_timeout_seconds_scales_for_deep_teacher_continuation() -> None:
    resolved = main_module._resolve_model_timeout_seconds(
        base_timeout_seconds=180.0,
        deep_think=True,
        execution_mode=main_module.ExecutionMode.TEACHER,
        is_continuation=True,
        deep_think_multiplier=1.25,
        teacher_multiplier=1.10,
        continuation_multiplier=1.15,
        max_timeout_seconds=300.0,
    )
    assert resolved == pytest.approx(284.625)


def test_resolve_model_timeout_seconds_honors_cap() -> None:
    resolved = main_module._resolve_model_timeout_seconds(
        base_timeout_seconds=180.0,
        deep_think=True,
        execution_mode=main_module.ExecutionMode.TEACHER,
        is_continuation=True,
        deep_think_multiplier=2.0,
        teacher_multiplier=2.0,
        continuation_multiplier=2.0,
        max_timeout_seconds=240.0,
    )
    assert resolved == 240.0


def test_resolve_prompt_timeout_seconds_extends_teacher_deep_think_window() -> None:
    resolved = main_module._resolve_prompt_timeout_seconds(
        base_timeout_seconds=300.0,
        model_timeout_seconds=284.625,
        tool_timeout_seconds=120.0,
        deep_think=True,
        execution_mode=main_module.ExecutionMode.TEACHER,
        max_timeout_seconds=900.0,
    )
    assert resolved == pytest.approx(449.625)


def test_compact_ocr_text_for_model_prioritizes_relevant_lines_when_truncated() -> None:
    ocr_text = "\n".join(
        [
            "Header line",
            "App toolbar",
            "Random content",
            "Another random line",
            "Yet another line",
            "Classification is grouping items by shared features.",
            "This line mentions classes and categories.",
            "Footer line",
        ]
    )
    compact, truncated, included, total = helpers_module._compact_ocr_text_for_model(
        ocr_text,
        purpose="Explain classification with examples",
        prompt="Help me understand classification from this screen",
        max_chars=180,
        max_lines=4,
    )
    assert truncated is True
    assert included <= 4
    assert total == 8
    assert "classification" in compact.lower()


def test_normalize_note_tags_deduplicates_and_sanitizes() -> None:
    tags = helpers_module._normalize_note_tags(
        [" Exam Prep ", "exam,prep", "physics", "", 8],
        extra_tags=("Teacher-Mode",),
    )
    assert tags == ["exam-prep", "physics", "teacher-mode"]


def test_extract_teacher_highlights_reads_distinct_lines() -> None:
    highlights = helpers_module._extract_teacher_highlights(
        """
        ## Lesson Summary
        - Newton's second law links force, mass, and acceleration.
        - Momentum is conserved in isolated systems.
        - Momentum is conserved in isolated systems.
        """
    )
    assert highlights == [
        "Newton's second law links force, mass, and acceleration.",
        "Momentum is conserved in isolated systems.",
    ]


def test_build_teacher_note_body_includes_required_sections() -> None:
    note = helpers_module._build_teacher_note_body(
        prompt="Explain photosynthesis",
        response_text="Photosynthesis converts light energy into chemical energy in glucose.",
    )
    assert "## Student Question" in note
    assert "## Teacher Explanation" in note
    assert "## Key Highlights" in note
    assert "## Review Prompts" in note


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("0", 0),
        ("1", 1),
        ("8", 8),
        ("9", 8),
        ("-2", 0),
        (" 4 ", 4),
    ],
)
def test_parse_plan_mode_discovery_budget_clamps_to_safe_range(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: int,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER", raw_value)
    assert main_module._parse_plan_mode_discovery_budget() == expected


def test_parse_plan_mode_discovery_budget_invalid_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER", "not-a-number")
    assert (
        main_module._parse_plan_mode_discovery_budget()
        == main_module._PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT
    )


def test_parse_plan_mode_discovery_budget_missing_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_AGENT_PLAN_MODE_DISCOVERY_BEFORE_PLANNER", raising=False)
    assert (
        main_module._parse_plan_mode_discovery_budget()
        == main_module._PLAN_MODE_DISCOVERY_BEFORE_PLANNER_DEFAULT
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "organize this file",
        "Move these files into folders",
        "please copy file to archive",
        "rename them now",
        "delete it from desktop",
        "create a folder now",
        "apply operations immediately",
    ],
)
def test_prompt_has_actionable_file_operation_intent_positive(prompt: str) -> None:
    assert main_module._prompt_has_actionable_file_operation_intent(prompt) is True


@pytest.mark.parametrize(
    "prompt",
    [
        "",
        "What is plan mode?",
        "Explain how file search works",
        "summarize this report",
    ],
)
def test_prompt_has_actionable_file_operation_intent_negative(prompt: str) -> None:
    assert main_module._prompt_has_actionable_file_operation_intent(prompt) is False


def test_looks_like_plan_clarification_reply_accepts_q2_prefixed_freeform() -> None:
    state = main_module.PlanClarificationState(
        root_prompt="Create a study plan for machine learning.",
        domain="study",
        pending_dimension="timeframe",
        pending_question_number=2,
        asked_rounds=1,
    )
    assert main_module._looks_like_plan_clarification_reply("Q2: 6 weeks", state) is True


def test_looks_like_plan_clarification_reply_rejects_short_new_task_prompt() -> None:
    state = main_module.PlanClarificationState(
        root_prompt="Create a study plan for machine learning.",
        domain="study",
        pending_dimension="baseline",
        pending_question_number=1,
        asked_rounds=1,
    )
    assert main_module._looks_like_plan_clarification_reply("write me a poem", state) is False


def test_looks_like_plan_clarification_reply_allows_constraints_signal() -> None:
    state = main_module.PlanClarificationState(
        root_prompt="Create a study plan for machine learning.",
        domain="study",
        pending_dimension="constraints",
        pending_question_number=1,
        asked_rounds=1,
    )
    assert main_module._looks_like_plan_clarification_reply("weekends only", state) is True


def test_plan_mode_text_requests_structured_clarification_detects_freeform_question_list() -> None:
    text = (
        "To ensure the plan is tailored, please answer the following clarification questions:\n"
        "- Timeline priority: Which duration fits your schedule better?\n"
        "- Storage baseline: Do you have a staging area ready?\n"
        "- Data volume: Roughly how much data are we organizing?\n"
    )
    assert main_module._plan_mode_text_requests_structured_clarification(text) is True


def test_plan_mode_text_requests_structured_clarification_ignores_structured_q_and_options() -> None:
    text = (
        "PLAN MODE (Quick Clarification)\n"
        "Q1. What outcome should this plan target?\n"
        "A) Beginner-friendly structured path\n"
        "B) Practical intermediate path\n"
        "C) Advanced/accelerated path\n"
        "D) Concise high-level roadmap\n"
    )
    assert main_module._plan_mode_text_requests_structured_clarification(text) is False


def test_prepare_plan_mode_followup_clarification_state_rebuilds_unanswered_dimensions() -> None:
    state = main_module.PlanClarificationState(
        root_prompt="Create a 6-week file organization plan.",
        domain="files",
        question_dimensions=["goal", "constraints", "timeframe", "baseline"],
        pending_dimension="goal",
        pending_question_number=1,
        asked_rounds=1,
        answered_dimensions={
            "goal": "Safe step-by-step dry run",
            "timeframe": "Standard (1-2 months)",
        },
        option_answers={"goal": "B", "timeframe": "B"},
    )
    prepared = main_module._prepare_plan_mode_followup_clarification_state(
        root_prompt="Create a 6-week file organization plan.",
        state=state,
    )
    assert prepared.question_dimensions == ["constraints", "baseline"]
    assert prepared.pending_dimension == "constraints"
    assert prepared.pending_question_number == 1
    assert prepared.asked_rounds == 2


def test_prepare_plan_mode_followup_clarification_state_stops_when_all_dimensions_answered() -> None:
    state = main_module.PlanClarificationState(
        root_prompt="Create a 6-week file organization plan.",
        domain="files",
        question_dimensions=["goal", "constraints", "timeframe", "baseline"],
        pending_dimension="goal",
        pending_question_number=1,
        asked_rounds=2,
        answered_dimensions={
            "goal": "High-level strategy only (no execution)",
            "constraints": "Minimal daily time",
            "timeframe": "Fast track (1-2 weeks)",
            "baseline": "Basic familiarity",
        },
        option_answers={"goal": "A", "constraints": "A", "timeframe": "A", "baseline": "B"},
    )
    prepared = main_module._prepare_plan_mode_followup_clarification_state(
        root_prompt="Create a 6-week file organization plan.",
        state=state,
    )
    assert prepared.question_dimensions == []
    assert prepared.pending_dimension is None
    assert prepared.pending_question_number == 1
    assert prepared.asked_rounds == 2


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_parse_plan_mode_clarification_required(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: bool,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", raw_value)
    assert main_module._parse_plan_mode_clarification_required() is expected


def test_parse_plan_mode_clarification_required_invalid_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_REQUIRED", "maybe")
    assert (
        main_module._parse_plan_mode_clarification_required()
        is main_module._PLAN_MODE_CLARIFICATION_REQUIRED_DEFAULT
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", 1),
        ("3", 3),
        ("4", 4),
        ("9", 4),
        ("0", 1),
        ("-2", 1),
    ],
)
def test_parse_plan_mode_clarification_min_missing_clamps(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: int,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_MIN_MISSING", raw_value)
    assert main_module._parse_plan_mode_clarification_min_missing() == expected


def test_parse_plan_mode_clarification_min_missing_invalid_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_AGENT_PLAN_MODE_CLARIFICATION_MIN_MISSING", "maybe")
    assert (
        main_module._parse_plan_mode_clarification_min_missing()
        == main_module._PLAN_MODE_CLARIFICATION_MIN_MISSING_DEFAULT
    )


def test_should_run_plan_mode_clarification_runs_for_non_actionable_prompt() -> None:
    assert (
        main_module._should_run_plan_mode_clarification(
            prompt="Create a study plan for machine learning.",
            clarification_required=True,
            requires_unified_planning=False,
        )
        is True
    )


def test_should_run_plan_mode_clarification_runs_for_actionable_prompt_without_explicit_request() -> None:
    # File operations now also benefit from clarification (goal + constraints).
    assert (
        main_module._should_run_plan_mode_clarification(
            prompt="Organize these files into folders.",
            clarification_required=True,
            requires_unified_planning=True,
        )
        is True
    )


def test_should_run_plan_mode_clarification_stays_enabled_when_explicitly_requested() -> None:
    assert (
        main_module._should_run_plan_mode_clarification(
            prompt="Before writing the plan, ask clarifying questions first while organizing files.",
            clarification_required=True,
            requires_unified_planning=True,
        )
        is True
    )


def test_prompt_requires_plan_mode_clarification_when_dimensions_missing() -> None:
    assert (
        main_module._prompt_requires_plan_mode_clarification(
            "Create a study plan for machine learning."
        )
        is True
    )


def test_prompt_requires_plan_mode_clarification_false_when_detailed() -> None:
    assert (
        main_module._prompt_requires_plan_mode_clarification(
            "Create a 10-week beginner study plan for AWS ML with 1 hour per day."
        )
        is False
    )


def test_prompt_requires_plan_mode_clarification_false_for_rich_file_prompt() -> None:
    assert (
        main_module._prompt_requires_plan_mode_clarification(
            "I need a complete, real-world plan to safely reorganize my digital life "
            "over the next 12 weeks. I'm talking about everything: ~2.5 TB of documents, "
            "photos, videos, and downloads spread across my Mac, iCloud Drive, and "
            "external drives. I want this plan to be retention/compliance-aware "
            "(tax documents, legal files), privacy-first, with no permanent deletion "
            "initially — rollback checkpoints at every phase."
        )
        is False
    )


def test_plan_mode_missing_dimensions_detects_goal_via_plan_to_verb() -> None:
    missing = main_module._plan_mode_missing_clarification_dimensions(
        "plan to reorganize my photos over 4 weeks"
    )
    assert "goal" not in missing
    assert "timeframe" not in missing


def test_plan_mode_missing_dimensions_detects_constraints_via_profile_signals() -> None:
    missing = main_module._plan_mode_missing_clarification_dimensions(
        "create a privacy-first file backup plan with rollback checkpoints"
    )
    assert "constraints" not in missing


def test_plan_mode_missing_dimensions_detects_baseline_via_volume_hint() -> None:
    missing = main_module._plan_mode_missing_clarification_dimensions(
        "organize 2.5 TB of documents and photos"
    )
    assert "baseline" not in missing


def test_prompt_requires_plan_mode_clarification_when_user_explicitly_requests_questions() -> None:
    assert (
        main_module._prompt_requires_plan_mode_clarification(
            "Create a practical 6-week plan. Before writing the plan, ask clarifying questions."
        )
        is True
    )


def test_extract_plan_prompt_profile_detects_high_signal_file_constraints() -> None:
    profile = main_module._extract_plan_prompt_profile(
        (
            "Create a privacy-first 12 weeks file plan for 2.5 TB of documents and photos. "
            "No permanent deletion initially, include rollback checkpoints, and account for "
            "weekday limits plus weekend batches with non-technical helpers."
        )
    )
    assert profile.timeline_hint == "12 weeks"
    assert profile.volume_hint == "2.5 TB"
    assert profile.has_privacy_signal is True
    assert profile.has_no_delete_signal is True
    assert profile.has_rollback_signal is True
    assert profile.has_helper_signal is True
    assert profile.prefers_weekend_batches is True
    assert profile.has_weekday_time_limit is True


def test_build_plan_mode_choice_question_uses_timeline_hint_for_timeframe_dimension() -> None:
    _, options, _ = main_module._build_plan_mode_choice_question(
        dimension="timeframe",
        prompt="Build a 10 week plan for organizing files safely.",
        session_learning=None,
        global_learning=None,
    )
    option_texts = [text for _, text in options]
    assert any("10 week" in text.lower() for text in option_texts)


def test_plan_mode_clarification_dimensions_use_all_core_dimensions_when_explicitly_requested() -> None:
    dims = main_module._plan_mode_clarification_dimensions_for_prompt(
        "I need a 6-week plan. Before writing the plan, ask all clarification questions first.",
        "project",
    )
    assert dims == ["goal", "constraints", "timeframe", "baseline"]


def test_normalize_plan_mode_banner_removes_trailing_ellipsis() -> None:
    text = (
        "PLAN MODE (Planning Only)...\n"
        "No destructive tools were executed in this response.\n"
        "Draft follows."
    )
    normalized = main_module._normalize_plan_mode_banner(text)
    assert normalized.splitlines()[0] == "PLAN MODE (Planning Only)"


def test_compute_plan_mode_alignment_score_rewards_query_aligned_response() -> None:
    score = main_module._compute_plan_mode_alignment_score(
        root_prompt="Create a practical 6-week file organization plan with rollback checkpoints.",
        response_text=(
            "Phase 1 (week 1-2): define taxonomy and constraints.\n"
            "Phase 2 (week 3-4): execute safe moves with verification checkpoints.\n"
            "Phase 3 (week 5-6): rollback validation and final review."
        ),
        clarification_context_block=(
            "[PLAN_CLARIFICATION_CONTEXT]\n"
            "Use these user-confirmed clarifications while planning:\n"
            "- Goal: Safe step-by-step dry run\n"
            "- Timeline: 6 weeks\n"
            "- Constraints: Minimal daily time\n"
        ),
    )
    assert score >= 0.45


def test_compute_plan_mode_alignment_score_penalizes_off_topic_response() -> None:
    score = main_module._compute_plan_mode_alignment_score(
        root_prompt="Create a practical 6-week file organization plan with rollback checkpoints.",
        response_text="Here is a random poem about summer weather and mountains.",
        clarification_context_block="",
    )
    assert score < 0.38
