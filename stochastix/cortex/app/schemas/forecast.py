import os

from pydantic import BaseModel, field_validator

# Every currency the ECB publishes a daily reference rate for.
ALL_CURRENCIES = {
    "GBP", "CHF", "USD", "INR", "JPY", "CZK", "DKK", "HUF", "PLN", "RON",
    "SEK", "ISK", "NOK", "TRY", "AUD", "BRL", "CAD", "CNY", "HKD", "IDR",
    "ILS", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR", "EUR",
}


def _configured_currencies() -> set:
    """
    The active currency set, from the CURRENCIES environment variable.

    Set CURRENCIES=GBP,INR,USD to run a small local deployment; leave it
    unset for the full list. One variable drives both the API and the
    trainer, so the two can no longer drift apart. EUR is always included
    because every model is quoted against it and it needs none of its own.
    """
    raw = os.getenv("CURRENCIES", "").strip()
    if not raw:
        chosen = set(ALL_CURRENCIES)
    else:
        chosen = {code.strip().upper() for code in raw.split(",") if code.strip()}
        unknown = chosen - ALL_CURRENCIES
        if unknown:
            raise ValueError(f"CURRENCIES contains codes the ECB does not publish: {sorted(unknown)}")

    # EUR is structural, whichever branch produced the set. Every rate is
    # quoted against it and every cross pair triangulates through it, so a
    # deployment without EUR cannot price anything. This also covers a
    # hand-trimmed ALL_CURRENCIES, which previously slipped through with
    # no safety net and broke the whole site with NaN figures.
    chosen.add("EUR")
    if len(chosen) < 2:
        raise ValueError("The currency set needs at least one currency besides EUR.")
    return chosen


SUPPORTED_CURRENCIES = _configured_currencies()

# Currencies that need a trained model. EUR is excluded: its series against
# itself is a constant 1.0, so there is nothing to learn.
TRAINABLE_CURRENCIES = sorted(SUPPORTED_CURRENCIES - {"EUR"})


class PredictionRequest(BaseModel):
    from_currency: str
    to_currency: str
    days: int = 30

    @field_validator("days")
    @classmethod
    def validate_days(cls, v: int):
        if v < 1 or v > 90:
            raise ValueError("Forecast horizon must be between 1 and 90 days")
        return v

    @field_validator("from_currency", "to_currency")
    @classmethod
    def validate_currency(cls, v: str):
        v = v.upper()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Currency '{v}' is not supported.")
        return v