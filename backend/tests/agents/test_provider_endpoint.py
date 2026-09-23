from types import SimpleNamespace

import pytest

from app.agents import provider_endpoint
from app.agents.provider_endpoint import (
    ProviderEndpointPolicy,
    create_provider_http_client,
    validate_provider_configuration,
    validate_provider_endpoint,
    validate_provider_redirect,
)


def test_provider_endpoint_accepts_public_https_url():
    assert validate_provider_endpoint("https://api.example.com/v1") == (
        "https://api.example.com/v1"
    )


def test_provider_endpoint_rejects_private_and_loopback_hosts_in_production():
    for url in (
        "http://127.0.0.1:11434",
        "http://10.0.0.5:8080",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]:8080",
    ):
        with pytest.raises(ValueError):
            validate_provider_endpoint(url, allow_local=False)


def test_provider_endpoint_rejects_ipv4_mapped_ipv6_private_address():
    with pytest.raises(ValueError):
        validate_provider_endpoint("https://[::ffff:127.0.0.1]/v1")


def test_provider_endpoint_rejects_any_private_address_in_mixed_dns_answer(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        assert host == "provider.example"
        return [
            (SimpleNamespace(name="AF_INET"), type, 6, "", ("93.184.216.34", port)),
            (SimpleNamespace(name="AF_INET"), type, 6, "", ("10.0.0.5", port)),
        ]

    monkeypatch.setattr(provider_endpoint.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="resolved address"):
        validate_provider_endpoint(
            "https://provider.example/v1",
            resolve_dns=True,
        )


def test_provider_redirect_uses_the_same_canonical_allowlist(monkeypatch):
    def fake_getaddrinfo(host, port, type=None):
        assert host == "provider.example"
        return [(SimpleNamespace(name="AF_INET"), type, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(provider_endpoint.socket, "getaddrinfo", fake_getaddrinfo)

    assert validate_provider_redirect(
        "HTTPS://provider.example:443/v1",
        allowed_hosts={"PROVIDER.EXAMPLE."},
        allowed_ports={443},
    ) == "HTTPS://provider.example:443/v1"

    with pytest.raises(ValueError, match="allowlisted"):
        validate_provider_redirect(
            "https://other.example/v1",
            allowed_hosts={"provider.example"},
            allowed_ports={443},
        )

    with pytest.raises(ValueError, match="scheme"):
        validate_provider_redirect(
            "http://provider.example/v1",
            allowed_hosts={"provider.example"},
            allowed_ports={80, 443},
            allowed_schemes={"https"},
        )


@pytest.mark.asyncio
async def test_shared_provider_client_rejects_private_redirect(monkeypatch):
    client = create_provider_http_client(
        ProviderEndpointPolicy(
            resolve_dns=True,
            allowed_hosts=frozenset({"provider.example"}),
            allowed_ports=frozenset({443}),
        ),
        timeout=1,
    )
    hook = client.event_hooks["response"][0]
    response = provider_endpoint.httpx.Response(
        302,
        headers={"location": "http://169.254.169.254/latest/meta-data"},
        request=provider_endpoint.httpx.Request("GET", "https://provider.example/v1"),
    )

    with pytest.raises(ValueError):
        await hook(response)
    await client.aclose()


def test_cloud_provider_configuration_fails_closed_without_dns_and_egress_policy():
    with pytest.raises(ValueError, match="DNS"):
        validate_provider_configuration(
            deploy_mode="cloud",
            resolve_dns=False,
            allowed_hosts=set(),
            allowed_ports={80, 443},
        )

    with pytest.raises(ValueError, match="allowlist"):
        validate_provider_configuration(
            deploy_mode="cloud",
            resolve_dns=True,
            allowed_hosts=set(),
            allowed_ports={80, 443},
        )


def test_local_provider_configuration_keeps_explicit_local_exception():
    validate_provider_configuration(
        deploy_mode="local",
        resolve_dns=False,
        allowed_hosts=set(),
        allowed_ports={80, 443},
    )


def test_provider_endpoint_allows_localhost_only_when_explicitly_enabled():
    assert validate_provider_endpoint("http://localhost:11434", allow_local=True)

    with pytest.raises(ValueError):
        validate_provider_endpoint("http://localhost:11434", allow_local=False)


def test_provider_endpoint_rejects_credentials_and_unsupported_schemes():
    with pytest.raises(ValueError):
        validate_provider_endpoint("https://user:password@example.com/v1")

    with pytest.raises(ValueError):
        validate_provider_endpoint("file:///etc/passwd")
