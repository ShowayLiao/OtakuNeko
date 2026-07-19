from app.schemas.agent import ChatRequest


def test_message_id_is_preserved_for_checkpoint_deduplication():
    request = ChatRequest(
        model="test",
        messages=[{"id": "message-1", "role": "user", "content": "hello"}],
    )

    assert request.messages[0].model_dump(exclude_none=True) == {
        "id": "message-1",
        "role": "user",
        "content": "hello",
    }
