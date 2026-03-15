"""Compliance and governance tests for browse_web."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from agent_host.observability import reset_request_context, set_request_context
from agent_host.tools import browse_web


def _executor() -> SimpleNamespace:
    return SimpleNamespace(
        _browse_rate_limiter=browse_web.DomainRateLimiter(max_requests=1000, window_seconds=60.0),
        _browse_response_cache=browse_web.ResponseCache(max_entries=32, ttl_seconds=60.0),
        _browse_robots_cache=browse_web.RobotsTxtCache(ttl_seconds=60.0),
        _browse_circuit_breaker=browse_web.DomainCircuitBreaker(),
        _browse_incident_monitor=browse_web.BrowseIncidentMonitor(
            threshold=5,
            window_seconds=300,
            cooldown_seconds=600,
            incident_log_path="/tmp/browse_incidents_test.jsonl",
        ),
    )


@contextmanager
def _browse_profile(profile: str):
    tokens = set_request_context(
        correlation_id="test-correlation",
        request_id="test-request",
        method="prompt",
        browse_profile=profile,
    )
    try:
        yield
    finally:
        reset_request_context(tokens)


def test_process_single_url_blocks_egress_policy(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    policy["egress"]["deny_domain_suffixes"] = [".example.com"]
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)

    result = browse_web._process_single_url(
        executor=ex,
        url="https://api.example.com/data",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is False
    assert result["error_class"] == "egress_policy_blocked"


def test_process_single_url_blocks_jurisdiction_policy(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    policy["allowed_jurisdictions"] = ["US"]
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)

    with _browse_profile("strict"):
        result = browse_web._process_single_url(
            executor=ex,
            url="https://example.de/news",
            timeout_seconds=10,
            follow_redirects=True,
            max_redirects=5,
            include_raw_html=False,
            respect_robots_txt=False,
            use_cache=False,
            custom_headers=None,
            verify_ssl=True,
        )

    assert result["ok"] is False
    assert result["error_class"] == "jurisdiction_policy_blocked"


def test_process_single_url_allows_jurisdiction_in_standard_profile(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    policy["allowed_jurisdictions"] = ["US"]
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/plain",
            "response_size_bytes": 128,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 7.0,
            "_raw_body": "Public news article.",
        },
    )

    with _browse_profile("standard"):
        result = browse_web._process_single_url(
            executor=ex,
            url="https://example.de/news",
            timeout_seconds=10,
            follow_redirects=True,
            max_redirects=5,
            include_raw_html=False,
            respect_robots_txt=False,
            use_cache=False,
            custom_headers=None,
            verify_ssl=True,
        )

    assert result["ok"] is True
    assert result["effective_browse_profile"] == "standard"


def test_process_single_url_warns_when_robots_unavailable_in_standard_profile(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        ex._browse_robots_cache,
        "is_allowed",
        lambda **kwargs: (False, "Could not confirm robots.txt policy at https://example.com/robots.txt."),
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/plain",
            "response_size_bytes": 64,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 6.0,
            "_raw_body": "Public page.",
        },
    )

    with _browse_profile("standard"):
        result = browse_web._process_single_url(
            executor=ex,
            url="https://example.com/public",
            timeout_seconds=10,
            follow_redirects=True,
            max_redirects=5,
            include_raw_html=False,
            respect_robots_txt=True,
            use_cache=False,
            custom_headers=None,
            verify_ssl=True,
        )

    assert result["ok"] is True
    assert result["security_checks"]["robots_txt"] == "WARNING_UNAVAILABLE"
    assert any("Robots policy could not be verified" in warning for warning in result["policy_warnings"])


def test_process_single_url_blocks_auth_wall(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/html",
            "response_size_bytes": 100,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 10.0,
            "_raw_body": "<html><body>Members only. Please log in.</body></html>",
        },
    )

    result = browse_web._process_single_url(
        executor=ex,
        url="https://example.com/article",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is False
    assert result["error_class"] == "access_restricted"


def test_process_single_url_warns_on_auth_wall_in_flexible_profile(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/html",
            "response_size_bytes": 100,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 10.0,
            "_raw_body": "<html><body>Members only. Please log in.</body></html>",
        },
    )

    with _browse_profile("flexible"):
        result = browse_web._process_single_url(
            executor=ex,
            url="https://example.com/article",
            timeout_seconds=10,
            follow_redirects=True,
            max_redirects=5,
            include_raw_html=False,
            respect_robots_txt=False,
            use_cache=False,
            custom_headers=None,
            verify_ssl=True,
        )

    assert result["ok"] is True
    assert result["effective_browse_profile"] == "flexible"
    assert any("Access restriction warning" in warning for warning in result["policy_warnings"])


def test_process_single_url_applies_pii_and_copyright_controls(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    policy["privacy"]["block_on_pii_detection"] = False
    policy["copyright"]["max_excerpt_chars"] = 40
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/plain",
            "response_size_bytes": 500,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 11.0,
            "_raw_body": (
                "Contact alice@example.com or call 555-444-3333 for details. "
                "This is longer than the excerpt limit."
            ),
        },
    )

    result = browse_web._process_single_url(
        executor=ex,
        url="https://example.com/public",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is True
    assert "[REDACTED_EMAIL]" in result["content"]
    assert result["copyright_policy"]["truncated_for_copyright"] is True
    assert result["source_attribution"]["final_url"] == "https://example.com/public"


def test_process_single_url_blocks_when_pii_detected(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    policy["privacy"]["block_on_pii_detection"] = True
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/plain",
            "response_size_bytes": 500,
            "size_truncated": False,
            "redirect_chain": [],
                "redirect_count": 0,
                "resolved_ips": ["93.184.216.34"],
                "fetch_time_ms": 11.0,
                "_raw_body": (
                    "Customer SSN 123-45-6789 appears in the page body. "
                    "This should be blocked."
                ),
            },
        )

    result = browse_web._process_single_url(
        executor=ex,
        url="https://example.com/public",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is False
    assert result["error_class"] == "pii_detected_blocked"
    assert "content" not in result
    assert "title" not in result


def test_process_single_url_redacts_incidental_raw_html_pii_without_blocking(monkeypatch) -> None:
    ex = _executor()
    policy = browse_web._default_browse_compliance_policy()
    policy["security_attestation"]["require_recent_attestation"] = False
    monkeypatch.setattr(browse_web, "_load_browse_compliance_policy", lambda: policy)
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/html",
            "response_size_bytes": 500,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 11.0,
            "_raw_body": (
                "<html><head><script>"
                "window.__tracker__={ip:\"203.0.113.42\", email:\"ops@example.com\"};"
                "</script></head><body><main><p>Latest model ranking update.</p></main></body></html>"
            ),
        },
    )

    result = browse_web._process_single_url(
        executor=ex,
        url="https://example.com/public",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is True
    assert "Latest model ranking update." in result["content"]
    assert result["pii_redaction_counts"]["email"] >= 1


def test_compliance_action_purge_cache_domain() -> None:
    ex = _executor()
    ex._browse_response_cache.put(
        "https://example.com/a",
        {"url": "https://example.com/a", "final_url": "https://example.com/a", "ok": True},
    )
    ex._browse_response_cache.put(
        "https://other.com/b",
        {"url": "https://other.com/b", "final_url": "https://other.com/b", "ok": True},
    )

    result = browse_web.handle(
        ex,
        {
            "compliance_action": "purge_cache_domain",
            "target_domain": "example.com",
        },
    )

    assert result["ok"] is True
    assert result["removed_entries"] == 1


def test_security_attestation_gate_blocks_when_invalid(monkeypatch) -> None:
    ex = _executor()
    monkeypatch.setattr(
        browse_web,
        "_check_security_attestation",
        lambda policy: (False, "stale", {"status": "stale"}),
    )

    result = browse_web._process_single_url(
        executor=ex,
        url="https://example.com",
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        include_raw_html=False,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
    )

    assert result["ok"] is False
    assert result["error_class"] == "security_attestation_expired"


def test_security_attestation_warns_in_flexible_profile(monkeypatch) -> None:
    ex = _executor()
    monkeypatch.setattr(
        browse_web,
        "_check_security_attestation",
        lambda policy: (False, "stale", {"status": "stale"}),
    )
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/plain",
            "response_size_bytes": 64,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 5.0,
            "_raw_body": "Public page.",
        },
    )

    with _browse_profile("flexible"):
        result = browse_web._process_single_url(
            executor=ex,
            url="https://example.com",
            timeout_seconds=10,
            follow_redirects=True,
            max_redirects=5,
            include_raw_html=False,
            respect_robots_txt=False,
            use_cache=False,
            custom_headers=None,
            verify_ssl=True,
        )

    assert result["ok"] is True
    assert any("Security attestation warning" in warning for warning in result["policy_warnings"])


def test_handle_blocks_before_processing_when_attestation_invalid(monkeypatch) -> None:
    ex = _executor()
    monkeypatch.setattr(
        browse_web,
        "_check_security_attestation",
        lambda policy: (False, "missing attestation", {"status": "missing"}),
    )
    called = {"process_urls_parallel": False}

    def _should_not_run(**kwargs):
        called["process_urls_parallel"] = True
        raise AssertionError("_process_urls_parallel should not run when attestation is invalid")

    monkeypatch.setattr(browse_web, "_process_urls_parallel", _should_not_run)

    result = browse_web.handle(
        ex,
        {
            "url": "https://example.com",
            "respect_robots_txt": False,
        },
    )

    assert result["ok"] is False
    assert result["error_class"] == "security_attestation_expired"
    assert result["request_blocked_before_fetch"] is True
    assert called["process_urls_parallel"] is False


def test_build_search_urls_defaults_to_multiple_discovery_engines() -> None:
    urls = browse_web._build_search_urls("openai latest announcements")

    assert urls == [
        (
            "duckduckgo",
            "https://html.duckduckgo.com/html/?q=openai+latest+announcements",
        ),
        (
            "brave",
            "https://search.brave.com/search?q=openai+latest+announcements",
        ),
        (
            "google",
            "https://www.google.com/search?q=openai+latest+announcements",
        ),
    ]


def test_execute_search_query_falls_back_to_generic_result_harvest(monkeypatch) -> None:
    ex = _executor()

    monkeypatch.setattr(
        browse_web,
        "_fetch_url",
        lambda **kwargs: {
            "ok": True,
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "status_code": 200,
            "content_type": "text/html",
            "response_size_bytes": 512,
            "size_truncated": False,
            "redirect_chain": [],
            "redirect_count": 0,
            "resolved_ips": ["93.184.216.34"],
            "fetch_time_ms": 4.0,
            "_raw_body": (
                '<html><body><a href="https://example.com/releases/new-model">'
                "New model release notes</a></body></html>"
            ),
        },
    )
    monkeypatch.setattr(browse_web, "_parse_search_results", lambda engine, html, search_url: [])
    monkeypatch.setattr(
        browse_web,
        "_process_urls_parallel",
        lambda **kwargs: [{"ok": True, "url": "https://example.com/releases/new-model"}],
    )
    monkeypatch.setattr(
        browse_web,
        "_resolve_and_validate_hostname",
        lambda hostname, port=None: ["93.184.216.34"],
    )

    result = browse_web._execute_search_query(
        executor=ex,
        query="new model release",
        engines=["duckduckgo"],
        timeout_seconds=10,
        follow_redirects=True,
        max_redirects=5,
        respect_robots_txt=False,
        use_cache=False,
        custom_headers=None,
        verify_ssl=True,
        browse_profile="standard",
    )

    assert result["ok"] is True
    assert result["search_results"][0]["url"] == "https://example.com/releases/new-model"
    assert "duckduckgo:generic_harvest" in result["discovery_sources_used"]


def test_effective_policy_relaxes_anti_bot_enforcement_by_profile() -> None:
    base = browse_web._default_browse_compliance_policy()

    strict = browse_web._build_effective_browse_policy(base, "strict")
    standard = browse_web._build_effective_browse_policy(base, "standard")
    flexible = browse_web._build_effective_browse_policy(base, "flexible")

    assert strict["anti_bot"]["enforcement"] == "strict"
    assert standard["anti_bot"]["enforcement"] == "balanced"
    assert flexible["anti_bot"]["enforcement"] == "warn_only"


def test_incident_monitor_spike_triggers_cooldown(tmp_path) -> None:
    monitor = browse_web.BrowseIncidentMonitor(
        threshold=2,
        window_seconds=300,
        cooldown_seconds=120,
        incident_log_path=str(tmp_path / "incidents.jsonl"),
    )
    monitor.record_event("example.com", event_type="anti_bot_challenge", details={"k": "v"})
    allowed, _ = monitor.check_domain("example.com")
    assert allowed is True
    monitor.record_event("example.com", event_type="anti_bot_challenge", details={"k": "v"})
    allowed_after, message = monitor.check_domain("example.com")
    assert allowed_after is False
    assert "Incident response active" in message


def test_signature_change_management_validation() -> None:
    signatures = browse_web._load_anti_bot_signatures()
    assert browse_web._validate_signature_change_management(signatures) is True

    broken = {"version": "x", "providers": signatures["providers"]}
    assert browse_web._validate_signature_change_management(broken) is False
