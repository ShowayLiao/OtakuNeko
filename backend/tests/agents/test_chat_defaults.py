from app.core.config import Settings


def test_multi_agent_routing_is_enabled_for_personalized_chat_by_default():
    assert Settings().ENABLE_MULTI_AGENT_ROUTING is True
