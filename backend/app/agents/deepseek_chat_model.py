from typing import Any

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI


class DeepSeekChatOpenAI(ChatOpenAI):
    """Preserve DeepSeek-specific fields dropped by ChatOpenAI's converter."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        generation = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        delta = choices[0].get("delta") if choices else None
        reasoning_content = delta.get("reasoning_content") if isinstance(delta, dict) else None
        if generation is not None and reasoning_content:
            generation.message.additional_kwargs["reasoning_content"] = reasoning_content
        return generation

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        source_messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        for source, target in zip(source_messages, payload.get("messages", [])):
            if not isinstance(source, AIMessage) or not source.tool_calls:
                continue
            reasoning_content = source.additional_kwargs.get("reasoning_content")
            if reasoning_content:
                target["reasoning_content"] = reasoning_content

        return payload
