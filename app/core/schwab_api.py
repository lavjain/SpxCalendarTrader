#!/usr/bin/env python3
"""
schwab_api.py - Schwab OAuth + SPX option chain pull for SPX Calendar Trader.

THE CALLBACK QUESTION
    Schwab's OAuth redirects your browser to your registered callback URL carrying
    a one-time ?code=. Something has to read that code. Three ways:

    manual   (default here)  No server. The browser fails to connect and shows an
                             error page - but the address bar holds the code. You
                             paste the whole URL in. Since Schwab's refresh token
                             dies every 7 days, this is a once-a-week, 30-second
                             ritual. Simplest thing that works.

    listen   (--flow listen) This script opens a throwaway HTTPS server on the
                             callback port, catches the redirect, shuts down. Needs
                             a self-signed cert; your browser will warn. Click through.

    schwabpy (--flow schwabpy)  Hand it to schwab-py, which does the same thing but
                             is maintained and battle-tested. Recommended if you
                             don't want to own OAuth code.

    Do not write your own long-running OAuth web service. There is nothing to serve.

USAGE
    export SCHWAB_APP_KEY=... SCHWAB_APP_SECRET=...
    schwab_api.py auth                          # once a week
    schwab_api.py chain --symbol '$SPX' --out spx_chain.csv --smile spx_smile.csv
    schwab_api.py chain --demo                  # parse a fixture, no network

Verified against a live $SPX pull on 2026-08-17: symbol format, field names,
and per-share greek scaling all confirmed as assumed below. See the "Verified
against the live API" section of README.md for details, including two
non-obvious findings (theoreticalVolatility is a useless flat constant;
volatility can blow up on worthless contracts) that parse() does not yet
guard against beyond the existing None/NaN/-999 filter.
"""

import argparse, base64, collections, csv, http.server, json, logging, os, ssl, subprocess
import sys, tempfile, threading, time
import urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

from app.core import config
from app.core.expiries import market_today
from app.core.models import ExpiryPair, OptionQuote

log = logging.getLogger(__name__)

AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
CHAINS_URL = "https://api.schwabapi.com/marketdata/v1/chains"
QUOTES_URL = "https://api.schwabapi.com/marketdata/v1/quotes"
# The token is a secret and must NOT land in the repo. Keep it in the home directory
# (~/.schwab/), outside the working tree.
TOKEN_PATH = os.path.expanduser(
    os.environ.get("SCHWAB_TOKEN_PATH", "~/.schwab/calendar_skew_token.json"))
# schwab-py writes a different token format; keep it away from the file access_token() reads.
SCHWABPY_TOKEN_PATH = TOKEN_PATH + ".schwabpy"
DEFAULT_CB = "https://127.0.0.1:8182"
BUCKETS = (0.30, 0.35, 0.40, 0.50)
REFRESH_TOKEN_LIFE_DAYS = 7.0
LOGIN_WARN_DAYS = 6.5
ACCESS_TOKEN_LIFE_S = 25 * 60


# ----------------------------------------------------------------- errors

class SchwabError(Exception):
    """Base class. The command line prints the message and exits 1; the web app maps it to 502/503."""


class SchwabAuthError(SchwabError):
    """Missing keys, no token, expired login, or a bad pasted URL."""


class SchwabHTTPError(SchwabError):
    def __init__(self, message, status=None, body=""):
        super().__init__(message)
        self.status, self.body = status, body


# ----------------------------------------------------------------- config + token

def cfg():
    k, s = os.environ.get("SCHWAB_APP_KEY"), os.environ.get("SCHWAB_APP_SECRET")
    cb = os.environ.get("SCHWAB_CALLBACK_URL", DEFAULT_CB)
    if not k or not s:
        raise SchwabAuthError("set SCHWAB_APP_KEY and SCHWAB_APP_SECRET")
    return k, s, cb


_token_lock = threading.Lock()   # one refresh at a time, so requests don't rewrite the file together


def _now():
    return datetime.now(timezone.utc)


def _read_token():
    with open(TOKEN_PATH) as f:
        tok = json.load(f)
    # tokens written before login_at/access_at existed carry one timestamp, obtained_at
    tok.setdefault("login_at", tok.get("obtained_at"))
    tok.setdefault("access_at", tok.get("obtained_at"))
    return tok


def _write_token(tok):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    tmp = TOKEN_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tok, f, indent=2)
    os.replace(tmp, TOKEN_PATH)          # atomic: readers never see half a file


def post_token(key, secret, data, login=False):
    """Exchange a code (login=True starts a new 7-day clock) or a refresh token.

    login_at is set by the login only; access_at changes on every refresh, so the 7-day check
    keeps counting from the login."""
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(data).encode(),
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SchwabHTTPError(
            f"token request failed: {e.code} {e.reason}\n"
            f"response body: {body}\n"
            f"redirect_uri sent: {data.get('redirect_uri')}\n"
            f"app key length: {len(key)}\n"
            f"app secret length: {len(secret)}", status=e.code, body=body) from None
    except urllib.error.URLError as e:
        raise SchwabHTTPError(f"token request failed: {e.reason}") from None
    now = _now().isoformat()
    if login:
        tok["login_at"] = now
    else:
        try:
            old = _read_token()
        except (OSError, ValueError):
            old = {}
        tok["login_at"] = old.get("login_at") or now
        if not tok.get("refresh_token"):
            tok["refresh_token"] = old.get("refresh_token")
    tok["access_at"] = now
    _write_token(tok)
    return tok


# ----------------------------------------------------------------- auth flows

def login_url(key, cb):
    return (f"{AUTH_URL}?client_id={urllib.parse.quote(key)}"
            f"&redirect_uri={urllib.parse.quote(cb, safe='')}&response_type=code")


def extract_code(pasted):
    """The code is URL-encoded in the address bar and usually ends in %40.
    Failing to decode it is the #1 cause of 'invalid_grant'."""
    q = urllib.parse.urlparse(pasted.strip()).query
    for part in q.split("&"):
        if part.startswith("code="):
            return urllib.parse.unquote(part[5:])
    raise SchwabAuthError("no ?code= found in that URL")


def flow_manual(key, secret, cb):
    print("\n1. Open this URL in your browser and log in with your BROKERAGE "
          "credentials (not the developer portal login):\n")
    print("   " + login_url(key, cb))
    print("\n2. After you click Allow, the browser will fail to load the page.")
    print("   That is expected - nothing is listening. Copy the ENTIRE URL from")
    print("   the address bar (it contains ?code=...).\n")
    pasted = input("3. Paste it here: ").strip()
    return post_token(key, secret,
                      {"grant_type": "authorization_code",
                       "code": extract_code(pasted), "redirect_uri": cb},
                      login=True)


def flow_listen(key, secret, cb):
    parts = urllib.parse.urlparse(cb)
    port = parts.port or 443
    if port < 1024:
        raise SchwabAuthError(f"port {port} needs root. Register a callback with a port "
                              f">1024, e.g. {DEFAULT_CB}")
    box = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            box["url"] = f"{parts.scheme}://{parts.netloc}{self.path}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h3>Code captured. Close this tab.</h3>")

        def log_message(self, *a):
            pass

    tmp = tempfile.mkdtemp()
    cert, kf = os.path.join(tmp, "c.pem"), os.path.join(tmp, "k.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", kf, "-out", cert, "-days", "1",
                    "-subj", "/CN=127.0.0.1"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, kf)
    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"\nlistening on {cb} - open this and log in:\n\n   "
          f"{login_url(key, cb)}\n")
    print("Your browser will warn about the self-signed certificate. "
          "Proceed anyway.\n")
    srv.handle_request()
    srv.server_close()
    return post_token(key, secret,
                      {"grant_type": "authorization_code",
                       "code": extract_code(box["url"]), "redirect_uri": cb},
                      login=True)


def flow_schwabpy(key, secret, cb):
    try:
        from schwab import auth as sauth
    except ImportError:
        raise SchwabAuthError("pip install schwab-py")
    sauth.easy_client(key, secret, cb, SCHWABPY_TOKEN_PATH)
    print(f"schwab-py wrote its token to {SCHWABPY_TOKEN_PATH}. Use schwab-py's client "
          f"to read chains; this script's token format differs, so the app does not use it.")
    return None


def login_age_days(tok=None):
    tok = tok or _read_token()
    return (_now() - datetime.fromisoformat(tok["login_at"])).total_seconds() / 86400


def access_token():
    """A valid access token, refreshing if needed. Raises SchwabAuthError when the weekly login is
    missing or has run out (Schwab kills the refresh token 7 days after login)."""
    with _token_lock:
        if not os.path.exists(TOKEN_PATH):
            raise SchwabAuthError("no token. run: python -m app.core.schwab_api auth")
        tok = _read_token()
        age = login_age_days(tok)
        if age >= REFRESH_TOKEN_LIFE_DAYS:
            raise SchwabAuthError(f"refresh token is {age:.1f} days old. Schwab kills it at "
                                  f"7 days - run: python -m app.core.schwab_api auth")
        if age > LOGIN_WARN_DAYS:
            log.warning("Schwab login is %.1f days old; it expires at 7 - run the weekly auth", age)
        access_age = (_now() - datetime.fromisoformat(tok["access_at"])).total_seconds()
        if access_age < ACCESS_TOKEN_LIFE_S:
            return tok["access_token"]
        key, secret, _ = cfg()
        return post_token(key, secret, {"grant_type": "refresh_token",
                                        "refresh_token": tok["refresh_token"]})["access_token"]


# ----------------------------------------------------------------- request layer
# TTL cache, at most SCHWAB_MAX_CONCURRENT requests in flight, a per-minute limiter, backoff on 429.

_cache, _cache_lock = {}, threading.Lock()
_inflight = threading.BoundedSemaphore(config.SCHWAB_MAX_CONCURRENT)
_calls, _calls_lock = collections.deque(), threading.Lock()
_sleep = time.sleep           # tests replace these
_clock = time.monotonic


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _rate_limit():
    """Block until fewer than SCHWAB_REQUESTS_PER_MIN requests started in the last 60 s."""
    while True:
        with _calls_lock:
            now = _clock()
            while _calls and now - _calls[0] >= 60:
                _calls.popleft()
            if len(_calls) < config.SCHWAB_REQUESTS_PER_MIN:
                _calls.append(now)
                return
            wait = 60 - (now - _calls[0])
        _sleep(max(wait, 0.01))


def _get_json(url, use_cache=True, retries=4):
    if use_cache:
        with _cache_lock:
            hit = _cache.get(url)
            if hit and _clock() - hit[0] < config.CACHE_TTL_S:
                return hit[1]
    delay = 1.0
    for attempt in range(retries + 1):
        _rate_limit()
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {access_token()}",
                          "Accept": "application/json"})
        try:
            with _inflight:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < retries:
                try:
                    delay = float(e.headers.get("Retry-After") or delay)
                except (TypeError, ValueError):
                    pass
                log.warning("Schwab 429; backing off %.1f s", delay)
                _sleep(delay)
                delay *= 2
                continue
            raise SchwabHTTPError(f"request failed: {e.code} {e.reason}\nresponse body: {body}",
                                  status=e.code, body=body) from None
        except urllib.error.URLError as e:
            raise SchwabHTTPError(f"request failed: {e.reason}") from None
    if use_cache:
        with _cache_lock:
            _cache[url] = (_clock(), data)
    return data


# ----------------------------------------------------------------- chain
def _window(pairs):
    """fromDate/toDate covering every short expiry through the last long expiry."""
    return (min(p.short for p in pairs), max(p.long for p in pairs))


def get_chain(symbol, pairs, dte_max=config.MAX_DTE, today=None):
    """Puts (range=OTM) for the window spanned by `pairs`.

    fromDate/toDate cap the expiration window and range=OTM caps the strike window; without
    both, Schwab's gateway returns the whole chain and 502s ("Body buffer overflow"). range=NTM is
    too narrow and drops the 50-delta row. See README.md. Nothing past `dte_max` (63 = 56 + 7)."""
    today = today or market_today()
    last = today + timedelta(days=dte_max)
    if not pairs:
        raise ValueError("no expiry pairs to pull")
    lo, hi = _window(pairs)
    if date.fromisoformat(hi) > last:
        raise ValueError(f"expiry {hi} is more than {dte_max} days out")
    return _get_json(CHAINS_URL + "?" + urllib.parse.urlencode({
        "symbol": symbol, "contractType": "PUT", "strategy": "SINGLE",
        "includeUnderlyingQuote": "true", "range": "OTM",
        "fromDate": lo, "toDate": hi}))


def get_call_chain(symbol, pairs, strike_count=config.CALL_STRIKE_COUNT):
    """A few calls around the money on each expiry, for the put-call-parity forward.
    contractType=CALL with strikeCount keeps the payload small (unverified live: check once)."""
    lo, hi = _window(pairs)
    return _get_json(CHAINS_URL + "?" + urllib.parse.urlencode({
        "symbol": symbol, "contractType": "CALL", "strategy": "SINGLE",
        "strikeCount": strike_count, "fromDate": lo, "toDate": hi}))


def _num(x):
    """Schwab uses None, "NaN" and -999 for "no value"."""
    if x is None or x == "NaN" or x == -999 or x == -999.0:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _is_spxw(c):
    root = c.get("optionRoot")
    if root is not None:
        return root == "SPXW"
    return str(c.get("symbol", "")).startswith("SPXW")   # fallback if the field is absent


def _quote(expiry, c, right):
    return OptionQuote(
        expiry=expiry, strike=float(c["strikePrice"]), right=right,
        bid=_num(c.get("bid")), ask=_num(c.get("ask")), mark=_num(c.get("mark")),
        delta=_num(c.get("delta")), gamma=_num(c.get("gamma")), theta=_num(c.get("theta")),
        vega=_num(c.get("vega")), iv=_num(c.get("volatility")))


def _contracts(chain, key, right):
    """(expiry_iso, OptionQuote) for each SPXW contract; SPX (AM-settled) rows are dropped."""
    for exp, strikes in (chain.get(key) or {}).items():
        expiry = exp.split(":")[0]
        for contracts in strikes.values():
            for c in contracts:
                if _is_spxw(c):
                    yield expiry, _quote(expiry, c, right)


def strike_ok(strike, strike_sets=config.STRIKE_SETS):
    return any(strike % int(s) == 0 for s in strike_sets)


def parse(chain, pairs, strike_sets=config.STRIKE_SETS, delta_band=config.DELTA_BAND,
          dte_max=config.MAX_DTE):
    """Puts for the chosen expiry pairs only.

    Short expiry: |delta| inside `delta_band`, on a strike in `strike_sets`.
    Long expiry:  the put at each of those strikes, whatever its delta.
    Rows missing a mark, delta or IV are skipped. Returns a list of OptionQuote."""
    short_exp = {p.short for p in pairs if p.short_dte <= dte_max}
    long_exp = {p.long for p in pairs if p.long_dte <= dte_max}
    puts = [q for e, q in _contracts(chain, "putExpDateMap", "P") if e in short_exp | long_exp]
    puts = [q for q in puts if None not in (q.mark, q.delta, q.iv)]
    lo, hi = delta_band
    short_strikes = {}
    for q in puts:
        if q.expiry in short_exp and strike_ok(q.strike, strike_sets) and lo <= abs(q.delta) <= hi:
            short_strikes.setdefault(q.expiry, set()).add(q.strike)
    out = []
    for q in puts:
        for p in pairs:
            if (q.expiry == p.short and q.strike in short_strikes.get(p.short, ())) or \
               (q.expiry == p.long and q.strike in short_strikes.get(p.short, ())):
                out.append(q)
                break
    return sorted(set_unique(out), key=lambda q: (q.expiry, q.strike))


def set_unique(quotes):
    seen, out = set(), []
    for q in quotes:
        k = (q.expiry, q.strike, q.right)
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def parse_calls(chain, pairs):
    """The calls the chain pull returned on the Finder's expiries (a few nearest the money)."""
    exps = {p.short for p in pairs} | {p.long for p in pairs}
    calls = [q for e, q in _contracts(chain, "callExpDateMap", "C") if e in exps]
    return sorted((q for q in calls if None not in (q.mark, q.iv)),
                  key=lambda q: (q.expiry, q.strike))


def calendar_legs(rows, short_exp, long_exp, strike):
    """The short and long put at the SAME strike, or None if either is missing."""
    def pick(exp):
        return next((q for q in rows if q.right == "P" and q.expiry == exp and q.strike == strike),
                    None)
    s, l = pick(short_exp), pick(long_exp)
    return (s, l) if s and l else None


def get_quotes(symbols, use_cache=True):
    """Many symbols in one call ($SPX, $VIX, $VIX9D, option legs).
    Returns {symbol: {"bid","ask","mark","last"}} with None for anything missing."""
    syms = list(dict.fromkeys(symbols))
    data = _get_json(QUOTES_URL + "?" + urllib.parse.urlencode(
        {"symbols": ",".join(syms), "fields": "quote"}), use_cache=use_cache)
    out = {}
    for sym, v in data.items():
        q = (v or {}).get("quote") or {}
        out[sym] = {"bid": _num(q.get("bidPrice")), "ask": _num(q.get("askPrice")),
                    "mark": _num(q.get("mark")), "last": _num(q.get("lastPrice"))}
    return out


def parse_atm_rows(chain, dte_max=60):
    """Old flat parse: one dict per put (dte, strike, mark, greeks, iv). Feeds write_atm/write_smile
    for the --demo CSV path only; the app uses parse() below."""
    rows = []
    for exp, strikes in (chain.get("putExpDateMap") or {}).items():
        try:
            dte = int(exp.split(":")[1])
        except (IndexError, ValueError):
            continue
        if dte > dte_max or dte < 1:
            continue
        for _, contracts in strikes.items():
            for c in contracts:
                iv = c.get("volatility")
                d = c.get("delta")
                if iv in (None, "NaN", -999) or d in (None, "NaN", -999):
                    continue
                rows.append(dict(
                    dte=dte, strike=float(c["strikePrice"]),
                    mark=float(c.get("mark") or 0),
                    bid=float(c.get("bid") or 0), ask=float(c.get("ask") or 0),
                    delta=float(d), gamma=float(c.get("gamma") or 0),
                    theta=float(c.get("theta") or 0),
                    vega=float(c.get("vega") or 0), iv=float(iv)))
    return rows


def nearest(rows, dte, target):
    cands = [r for r in rows if r["dte"] == dte]
    return min(cands, key=lambda r: abs(abs(r["delta"]) - target)) if cands else None


def write_atm(rows, path):
    """One row per expiration at the ~50 delta strike -> calendar_math.py input.
    Greeks come per-share from Schwab, which is what calendar_math expects."""
    out = []
    for dte in sorted({r["dte"] for r in rows}):
        r = nearest(rows, dte, 0.50)
        if r:
            out.append({k: round(r[k], 5) for k in
                        ("dte", "mark", "delta", "gamma", "theta", "vega", "iv")})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dte", "mark", "delta", "gamma",
                                          "theta", "vega", "iv"])
        w.writeheader()
        w.writerows(out)
    return len(out)


def write_smile(rows, path):
    """dte,delta,iv at each delta bucket (the put skew smile)."""
    out = []
    for dte in sorted({r["dte"] for r in rows}):
        for D in BUCKETS:
            r = nearest(rows, dte, D)
            if r and abs(abs(r["delta"]) - D) < 0.05:
                out.append(dict(dte=dte, delta=D, iv=round(r["iv"], 3),
                                strike=r["strike"],
                                actual_delta=round(abs(r["delta"]), 4)))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dte", "delta", "iv", "strike",
                                          "actual_delta"])
        w.writeheader()
        w.writerows(out)
    return len(out)


DEMO = {"putExpDateMap": {
    f"2026-0{9 if d>18 else 8}-{d:02d}:{d}": {
        f"{k}.0": [{"strikePrice": k, "mark": 5.0 + d*0.1 + (780-k)*0.05,
                    "bid": 4.9, "ask": 5.1,
                    "delta": -(0.50 - (780-k)*0.004*(30/d)**0.5),
                    "gamma": 0.016, "theta": -0.20, "vega": 0.74,
                    "volatility": 11.0 + (780-k)*0.16*(30/d)**0.5 + d*0.03}]
        for k in (740, 750, 760, 770, 780)}
    for d in (8, 15, 22, 29, 36)}}


def main():
    try:
        _main()
    except SchwabError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _main():
    p = argparse.ArgumentParser(description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth")
    a.add_argument("--flow", choices=["manual", "listen", "schwabpy"],
                   default="manual")
    c = sub.add_parser("chain")
    c.add_argument("--symbol", default="$SPX")
    c.add_argument("--out", default="chain.csv")
    c.add_argument("--smile", default="smile.csv")
    c.add_argument("--dte-max", type=int, default=60)
    c.add_argument("--demo", action="store_true",
                   help="parse a fixture, no network (writes the --out/--smile CSVs); "
                        "without it: a live pull with the default Finder filters")
    args = p.parse_args()

    if args.cmd == "auth":
        key, secret, cb = cfg()
        tok = {"manual": flow_manual, "listen": flow_listen,
               "schwabpy": flow_schwabpy}[args.flow](key, secret, cb)
        if tok:
            print(f"\ntoken written to {TOKEN_PATH} (mode 600). "
                  f"Re-run within 7 days.")
    elif args.demo:
        rows = parse_atm_rows(DEMO, args.dte_max)
        if not rows:
            raise SchwabError("no contracts parsed - check the symbol and field names")
        n1 = write_atm(rows, args.out)
        n2 = write_smile(rows, args.smile)
        print(f"{len(rows)} contracts -> {args.out} ({n1} expirations), "
              f"{args.smile} ({n2} rows)")
        print(f"  next: calendar_math.py screen {args.out} --capital 10000")
    else:
        from app.core.expiries import pick_expiries
        today = market_today()
        pairs = pick_expiries(today)
        if not pairs:
            raise SchwabError("no expiry pairs for today's default filters")
        chain = get_chain(args.symbol, pairs, today=today)
        puts = parse(chain, pairs)
        calls = parse_calls(get_call_chain(args.symbol, pairs), pairs)
        print(f"{len(puts)} puts, {len(calls)} calls for "
              f"{', '.join(f'{p.short}->{p.long}' for p in pairs)}")
        for q in puts:
            print(f"  {q.expiry} P {q.strike:>7.0f}  mark {q.mark:>7.2f}  delta {q.delta:>7.3f}  iv {q.iv:>6.2f}")

if __name__ == "__main__":
    main()
