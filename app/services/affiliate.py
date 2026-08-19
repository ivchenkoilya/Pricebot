class AffiliateService:
    """Transparent no-op placeholder for future contracted affiliate programs."""

    async def link_for(self, original_url: str, source: str | None = None) -> str:
        return original_url
