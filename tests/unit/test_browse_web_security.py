"""Security regression coverage for browse_web hardening."""

from __future__ import annotations

import urllib.error
import urllib.request

from agent_host.tools import browse_web


def test_fetch_url_blocks_unsafe_redirect_before_second_request(monkeypatch) -> None:
    """Redirect targets must be validated before any follow-up request is sent."""
    open_calls: list[str] = []

    def _fake_resolve(hostname: str, port: int | None = None) -> list[str]:
        if hostname == "example.com":
            return ["93.184.216.34"]
        if hostname == "127.0.0.1":
            raise browse_web.URLSecurityViolation("private IP blocked")
        return ["93.184.216.34"]

    class _FakeOpener:
        def open(self, req: urllib.request.Request, timeout: int = 0):
            open_calls.append(req.full_url)
            raise urllib.error.HTTPError(
                req.full_url,
                302,
                "Found",
                {"Location": "http://127.0.0.1/internal"},
                None,
            )

    monkeypatch.setattr(browse_web, "_resolve_and_validate_hostname", _fake_resolve)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args, **kwargs: _FakeOpener())

    result = browse_web._fetch_url(
        "https://example.com/start",
        follow_redirects=True,
        max_redirects=5,
        verify_ssl=True,
    )

    assert result["ok"] is False
    assert result["error_class"] == "redirect_security_violation"
    assert len(open_calls) == 1


def test_robots_txt_uses_secure_fetch_pipeline(monkeypatch) -> None:
    """robots.txt retrieval should flow through the hardened fetch helper."""
    requested_urls: list[str] = []

    def _fake_fetch_url(
        url: str,
        timeout_seconds: int = 15,
        max_redirects: int = 5,
        follow_redirects: bool = True,
        custom_headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
    ) -> dict[str, object]:
        requested_urls.append(url)
        return {
            "ok": True,
            "_raw_body": "User-agent: *\nDisallow: /private\n",
        }

    monkeypatch.setattr(browse_web, "_fetch_url", _fake_fetch_url)

    cache = browse_web.RobotsTxtCache(ttl_seconds=60.0)
    allowed, _info = cache.is_allowed(
        url="https://example.com/private/page",
        scheme="https",
        hostname="example.com",
    )

    assert allowed is False
    assert requested_urls == ["https://example.com/robots.txt"]
