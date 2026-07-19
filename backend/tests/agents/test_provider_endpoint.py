import pytest

from app.agents.provider_endpoint import validate_provider_endpoint


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


def test_provider_endpoint_allows_localhost_only_when_explicitly_enabled():
    assert validate_provider_endpoint("http://localhost:11434", allow_local=True)

    with pytest.raises(ValueError):
        validate_provider_endpoint("http://localhost:11434", allow_local=False)


def test_provider_endpoint_rejects_credentials_and_unsupported_schemes():
    with pytest.raises(ValueError):
        validate_provider_endpoint("https://user:password@example.com/v1")

    with pytest.raises(ValueError):
        validate_provider_endpoint("file:///etc/passwd")
