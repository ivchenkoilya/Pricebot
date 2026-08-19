from app.ai.provider import OpenAICompatibleProvider
from app.processors.common import chunk_text


class TextProcessor:
    def __init__(self, ai: OpenAICompatibleProvider):
        self.ai = ai

    async def process(self, text: str, kind: str = 'текст'):
        chunks = chunk_text(text)
        if len(chunks) > 1:
            return await self.ai.summarize_chunks(chunks)
        return await self.ai.analyze_text(text, kind)
