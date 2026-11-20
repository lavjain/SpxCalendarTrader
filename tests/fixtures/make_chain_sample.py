"""Builds chain_sample.json: a synthetic Schwab-shaped $SPX chain (no real account data).

Run: python tests/fixtures/make_chain_sample.py
Expiries: Fri Dec 18 2026 (third Friday: both SPX AM and SPXW PM rows), Thu Dec 24, Thu Dec 31.
"""
import json
import math
from datetime import date
from pathlib import Path

from scipy.stats import norm

TODAY, SPX, R = date(2026, 11, 24), 6800.0, 0.04
EXPIRIES = ["2026-12-18", "2026-12-24", "2026-12-31"]


def bs(right, S, K, T, iv):
    F = S
    sd = iv * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    disc = math.exp(-R * T)
    if right == "P":
        price = disc * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
        delta = disc * (norm.cdf(d1) - 1)
    else:
        price = disc * (F * norm.cdf(d1) - K * norm.cdf(d2))
        delta = disc * norm.cdf(d1)
    vega = disc * F * norm.pdf(d1) * math.sqrt(T) / 100
    gamma = disc * norm.pdf(d1) / (F * sd)
    theta = -(F * norm.pdf(d1) * iv / (2 * math.sqrt(T))) / 365
    return price, delta, gamma, theta, vega


def contract(exp, K, right, root, bump=0.0):
    dte = (date.fromisoformat(exp) - TODAY).days
    T = dte / 365
    iv = 0.14 + 0.00004 * max(SPX - K, 0) + 0.002 * (30 - dte) / 30 + bump   # a put skew + term slope
    price, delta, gamma, theta, vega = bs(right, SPX, K, T, iv)
    spread = max(0.1, price * 0.01)
    return {"putCall": "PUT" if right == "P" else "CALL", "symbol": f"{root:<6}{exp[2:4]}{exp[5:7]}{exp[8:]}{right}{int(K*1000):08d}",
            "optionRoot": root, "strikePrice": K, "bid": round(price - spread / 2, 2),
            "ask": round(price + spread / 2, 2), "mark": round(price, 2), "delta": round(delta, 4),
            "gamma": round(gamma, 5), "theta": round(theta, 4), "vega": round(vega, 4),
            "volatility": round(iv * 100, 3), "daysToExpiration": dte}


put_map, call_map = {}, {}
for exp in EXPIRIES:
    dte = (date.fromisoformat(exp) - TODAY).days
    pm, cm = {}, {}
    for K in [x * 1.0 for x in range(6200, 6805, 5)]:               # range=OTM: puts below spot
        cs = [contract(exp, K, "P", "SPXW")]
        if exp == "2026-12-18":                                      # third Friday: SPX (AM) twin
            cs.append(contract(exp, K, "P", "SPX", bump=0.01))
        pm[f"{K}"] = cs
    for K in [6785.0, 6790.0, 6795.0, 6800.0, 6805.0, 6810.0]:       # a few calls near the money
        cs = [contract(exp, K, "C", "SPXW")]
        if exp == "2026-12-18":
            cs.append(contract(exp, K, "C", "SPX", bump=0.01))
        cm[f"{K}"] = cs
    put_map[f"{exp}:{dte}"], call_map[f"{exp}:{dte}"] = pm, cm

# a few bad rows the parser must skip
bad = put_map["2026-12-24:30"]["6600.0"][0]
bad["delta"] = "NaN"
bad2 = put_map["2026-12-31:37"]["6600.0"][0]
bad2["bid"] = None

out = {"symbol": "$SPX", "underlyingPrice": SPX, "putExpDateMap": put_map, "callExpDateMap": call_map}
Path(__file__).with_name("chain_sample.json").write_text(json.dumps(out, indent=1))
print("wrote", sum(len(c) for m in put_map.values() for c in m.values()), "puts")
