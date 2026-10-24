"""Provider gateway coverage independent of the removed graph workflow."""

from app.harness.model_gateway import OpenAIModelGateway


def test_deepseek_endpoint_selects_provider_without_compiling_a_graph():
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )

    assert gateway.provider == "deepseek"
    assert gateway.model == "deepseek-chat"
