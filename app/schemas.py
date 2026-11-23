"""API request and response models. Core output models (FinderResult, Spot, ...) live in app/core/models.py."""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core import config
from app.core.models import FinderResult, Spot


class FinderFilters(BaseModel):
    """The Finder filter bar. Bad input becomes a 422, never a stack trace."""
    dte_min: int = config.SHORT_DTE_DEFAULT[0]
    dte_max: int = config.SHORT_DTE_DEFAULT[1]
    widths: list[int] = Field(default_factory=lambda: list(config.WIDTHS_DEFAULT))
    strike_sets: list[str] = Field(default_factory=lambda: list(config.STRIKE_SETS))
    size_mode: Literal["margin", "contracts"] = "margin"
    size_value: float = config.MARGIN

    @model_validator(mode="after")
    def _check_range(self):
        lo, hi = config.SHORT_DTE_LIMITS
        if not (lo <= self.dte_min <= self.dte_max <= hi):
            raise ValueError(f"short DTE range must satisfy {lo} <= min <= max <= {hi}")
        if self.size_mode == "contracts" and self.size_value != int(self.size_value):
            raise ValueError("contracts must be a whole number")
        return self

    @field_validator("widths")
    @classmethod
    def _widths(cls, v):
        bad = [w for w in v if w not in config.WIDTHS]
        if not v or bad:
            raise ValueError(f"widths must be a non-empty subset of {list(config.WIDTHS)}")
        return sorted(set(v))

    @field_validator("strike_sets")
    @classmethod
    def _strike_sets(cls, v):
        bad = [s for s in v if s not in config.STRIKE_SETS]
        if not v or bad:
            raise ValueError(f"strike_sets must be a non-empty subset of {list(config.STRIKE_SETS)}")
        return [s for s in config.STRIKE_SETS if s in v]

    @field_validator("size_value")
    @classmethod
    def _size(cls, v):
        if v <= 0:
            raise ValueError("size_value must be positive")
        return v

    @property
    def dte_range(self) -> tuple[int, int]:
        return (self.dte_min, self.dte_max)


class HealthResponse(BaseModel):
    status: str
    version: str


class SettingValue(BaseModel):
    value: Any = None


class FinderSnapshot(BaseModel):
    """One Refresh: what the table, strike rows and panel all read, so they always agree."""
    snapshot_id: str
    spot: Spot | None = None
    result: FinderResult


class QuoteSpreadRequest(BaseModel):
    short_symbol: str
    long_symbol: str
    size_mode: Literal["margin", "contracts"] = "margin"
    size_value: float = Field(default=config.MARGIN, gt=0)
    fill_price: float | None = None
    keep_waiting: bool = False


class OpenTradeRequest(BaseModel):
    """What the Open Trade dialog sends: which calendar (from a Finder snapshot) and what was confirmed."""
    snapshot_id: str
    short_expiry: str
    long_expiry: str
    strike: float
    size_mode: Literal["margin", "contracts"] = "margin"
    size_value: float = Field(default=config.MARGIN, gt=0)
    contracts: int = Field(ge=1)
    fill_price: float = Field(gt=0)
    price_source: Literal["auto", "manual", "pasted"] | None = None
    account: str = "Paper"


class TosOrderRequest(BaseModel):
    """The calendar and price in the dialog, to be written as a thinkorswim line."""
    short_expiry: str
    long_expiry: str
    strike: float = Field(gt=0)
    contracts: int = Field(ge=1)
    price: float = Field(gt=0)
    side: Literal["BUY", "SELL"] = "BUY"


class TosOrderLine(BaseModel):
    line: str
