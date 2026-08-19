from app.ai.provider import OpenAICompatibleProvider
from app.processors.common import chunk_text


class TextProcessor:
    def __init__(self, ai: OpenAICompatibleProvider):
        self.ai = ai

    async def process(self, text: str, kind: str = 'текст', *, deep: bool = False):
        chunks = chunk_text(text)
        if len(chunks) > 1:
            return await self.ai.summarize_chunks(chunks)

        # Most Telegram inputs do not need the expensive smart model. Use the
        # fast model for ordinary-sized material, and escalate only on demand.
        model = self.ai.settings.smart if deep or len(text) > self.ai.settings.fast_text_chars else self.ai.settings.fast
        return await self.ai.analyze_text(text, kind, model=model)
