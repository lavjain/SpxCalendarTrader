"""The words behind every ⓘ: one place to edit them. Templates call info('key'); an unknown key raises, and
tests/test_info_text.py also checks that every key used in a template exists and that every key is used."""
from markupsafe import Markup, escape

# key: (title, text). One or two sentences: what the number means and how it is worked out.
INFO: dict[str, tuple[str, str]] = {
    # filters
    "short_dte": ("Short DTE", "Days to expiry of the short leg. The Finder lists pairs whose short expiry falls between the two sliders; the Friday nearest 30 days is the default trade."),
    "width": ("Days Between Short and Long", "How many days later the long leg expires than the short leg. A day that is not an expiry (a holiday) is greyed out, and its note appears underneath."),
    "strikes": ("Strikes", "Which strikes are listed: multiples of 10 and/or multiples of 25. SPX lists these reliably a month out."),
    "size_by": ("Size By", "Margin $ buys as many contracts as that much margin allows; Contracts uses exactly that many. The setting is saved in the app database."),
    # calendar panel tiles
    "cost": ("Cost", "What you pay to open: contracts x (mid price + the fill offset) x 100. This is also the most the calendar can lose."),
    "break_evens": ("Break-Evens", "SPX levels where the calendar breaks even when the short leg expires. Each leg keeps its current implied volatility, repriced with Black-Scholes."),
    "delta": ("Delta", "Dollars the position gains per 1-point rise in SPX, for all contracts. Near zero means the calendar is balanced either way."),
    "gamma": ("Gamma", "How fast delta changes per 1-point move in SPX, for all contracts. Negative gamma means delta works against you as SPX moves away from the strike."),
    "theta": ("Theta / Day", "Dollars the position earns per calendar day from time decay, all else equal. The short leg decays faster than the long leg, which is the point of the trade."),
    "vega": ("Vega / Pt", "Dollars the position gains if implied volatility rises one point on both legs. A calendar is long vega: it likes volatility rising."),
    "margin": ("Margin", "Buying power the broker holds for the position. For a long calendar this is its debit."),
    "max_profit": ("Max Profit", "The best P/L at the short expiry across SPX levels, from the repriced curve. It is a model figure, not a promise."),
    "max_loss": ("Max Loss", "The debit paid. A long calendar cannot lose more than it cost."),
    "pl_now": ("P/L If Closed Now", "P/L if you closed at today's mid prices: about minus the fill offset, because a fair price gives nothing back yet."),
    # risk profile controls
    "risk_range": ("Range", "How far each side of today's SPX the chart reaches. Scroll on the chart to zoom, drag to pan, double-click to reset."),
    "risk_today": ("Today", "P/L if SPX jumped to each level right now and nothing else changed. Each leg keeps its implied volatility."),
    "risk_expiry": ("At Short Expiry", "P/L at each SPX level on the day the short leg expires, with the long leg still alive and priced by Black-Scholes."),
    "risk_sd": ("±1 SD", "The shaded band is one standard deviation of SPX to the short expiry, from the short leg's implied volatility. About two thirds of outcomes land inside it."),
    # weekly comparison
    "weekly_comparison": ("Weekly Comparison", "The same 7-day calendar at one strike, the starred row's, for the Friday nearest 7, 14, 21, 28, 35 and 42 days out. It shows how price, greeks and skew change as the short expiry moves out, for one contract."),
}


def info(key: str) -> Markup:
    """The ⓘ button for `key`. Raises KeyError for an unknown key, so a typo in a template fails loudly."""
    title, text = INFO[key]
    return Markup(
        '<button type="button" class="info-btn" aria-expanded="false" aria-label="About {t}" '
        'data-info-title="{t}" data-info="{x}">ⓘ</button>').format(t=escape(title), x=escape(text))
