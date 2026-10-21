from schemas.premarket import GiftNiftySnapshot, MarketSentiment


class GiftNiftyProvider:
    """GIFT Nifty is not available on free Yahoo or Angel One master today."""

    async def collect(self) -> GiftNiftySnapshot:
        return GiftNiftySnapshot(
            available=False,
            sentiment=MarketSentiment.INSUFFICIENT_DATA,
            warning=(
                "No licensed free GIFT Nifty feed is configured. "
                "Indicator excluded from the score until a provider is added."
            ),
        )
