"""
TokenTracker — a LangChain callback handler that accumulates input/output
token counts across all LLM calls in a pipeline run.

Usage:
    tracker = TokenTracker()
    await graph.ainvoke(state, config={"callbacks": [tracker]})
    print(tracker.input_tokens, tracker.output_tokens)
"""
from langchain_core.callbacks import AsyncCallbackHandler


class TokenTracker(AsyncCallbackHandler):
    """Accumulates token usage reported by LLM responses."""

    def __init__(self):
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    async def on_chat_model_start(self, serialized, messages, **kwargs) -> None:  # type: ignore[override]
        pass

    async def on_llm_end(self, response, **kwargs) -> None:  # type: ignore[override]
        """Called after every LLM call — extract usage_metadata if present."""
        for generation_list in response.generations:
            for generation in generation_list:
                usage = getattr(generation.message, "usage_metadata", None)
                if usage:
                    self.input_tokens += usage.get("input_tokens", 0)
                    self.output_tokens += usage.get("output_tokens", 0)