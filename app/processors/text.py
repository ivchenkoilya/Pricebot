from app.ai.provider import OpenAICompatibleProvider
from app.processors.common import chunk_text


class TextProcessor:
    def __init__(self, ai: OpenAICompatibleProvider):
        self.ai = ai

    async def process(self, text: str, kind: str = 'текст', *, deep: bool = False):
        # A 10–20 minute transcript is normally still small enough for one fast
        # model request. The old generic path split it into multiple AI calls and
        # then ran a smart reduce, adding a large delay after Whisper had already
        # finished. Voice/audio prioritises latency and does one structured pass.
        if kind.lower() in {'голосовое', 'аудио', 'транскрипт видео'} and len(text) <= 50_000 and not deep:
            return await self.ai.analyze_text(
                text,
                kind,
                model=self.ai.settings.fast,
                max_tokens=min(1000, self.ai.settings.openai_max_output_tokens),
            )

        chunks = chunk_text(text)
        if len(chunks) > 1:
            return await self.ai.summarize_chunks(chunks)

        # Most Telegram inputs do not need the expensive smart model. Use the
        # fast model for ordinary-sized material, and escalate only on demand.
        model = self.ai.settings.smart if deep or len(text) > self.ai.settings.fast_text_chars else self.ai.settings.fast
        return await self.ai.analyze_text(text, kind, model=model)
