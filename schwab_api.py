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

import argparse, base64, csv, http.server, json, os, ssl, subprocess, sys, tempfile
import urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
CHAINS_URL = "https://api.schwabapi.com/marketdata/v1/chains"
# The token is a secret and must NOT land in the repo. Keep it in the home directory
# (~/.schwab/), outside the working tree.
TOKEN_PATH = os.path.expanduser(
    os.environ.get("SCHWAB_TOKEN_PATH", "~/.schwab/calendar_skew_token.json"))
DEFAULT_CB = "https://127.0.0.1:8182"
BUCKETS = (0.30, 0.35, 0.40, 0.50)


def cfg():
    k, s = os.environ.get("SCHWAB_APP_KEY"), os.environ.get("SCHWAB_APP_SECRET")
    cb = os.environ.get("SCHWAB_CALLBACK_URL", DEFAULT_CB)
    if not k or not s:
        sys.exit("set SCHWAB_APP_KEY and SCHWAB_APP_SECRET")
    return k, s, cb


def post_token(key, secret, data):
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
        print(f"token request failed: {e.code} {e.reason}", file=sys.stderr)
        print(f"response body: {body}", file=sys.stderr)
        print(f"redirect_uri sent: {data.get('redirect_uri')}", file=sys.stderr)
        print(f"app key length: {len(key)}", file=sys.stderr)
        print(f"app secret length: {len(secret)}", file=sys.stderr)
        sys.exit(1)
    tok["obtained_at"] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(tok, f, indent=2)
    os.chmod(TOKEN_PATH, 0o600)
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
    sys.exit("no ?code= found in that URL")


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
                       "code": extract_code(pasted), "redirect_uri": cb})


def flow_listen(key, secret, cb):
    parts = urllib.parse.urlparse(cb)
    port = parts.port or 443
    if port < 1024:
        sys.exit(f"port {port} needs root. Register a callback with a port "
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
                       "code": extract_code(box["url"]), "redirect_uri": cb})


def flow_schwabpy(key, secret, cb):
    try:
        from schwab import auth as sauth
    except ImportError:
        sys.exit("pip install schwab-py")
    sauth.easy_client(key, secret, cb, TOKEN_PATH)
    print(f"schwab-py wrote its token to {TOKEN_PATH}. Use schwab-py's client "
          f"to read chains; this script's token format differs.")
    return None


def access_token():
    if not os.path.exists(TOKEN_PATH):
        sys.exit("no token. run: schwab_api.py auth")
    tok = json.load(open(TOKEN_PATH))
    key, secret, _ = cfg()
    age = (datetime.now(timezone.utc)
           - datetime.fromisoformat(tok["obtained_at"])).total_seconds()
    if age > 6.5 * 86400:
        sys.exit(f"refresh token is {age/86400:.1f} days old. Schwab kills it at "
                 f"7 days - run: schwab_api.py auth")
    if age < 25 * 60:
        return tok["access_token"]
    return post_token(key, secret, {"grant_type": "refresh_token",
                                    "refresh_token": tok["refresh_token"]})["access_token"]


# ----------------------------------------------------------------- chain

def get_chain(symbol, dte_max):
    """fromDate/toDate cap the expiration window and range=OTM caps the strike
    window. Without both, Schwab's gateway returns the entire chain and 502s
    with a "Body buffer overflow" once it exceeds the gateway's body limit.

    range=OTM was chosen empirically: range=NTM is too narrow and drops the
    50-delta (ATM) row; range=SBK/ALL return it but with a
    ~30% larger payload for no extra coverage. See README.md."""
    today = date.today()
    url = CHAINS_URL + "?" + urllib.parse.urlencode({
        "symbol": symbol, "contractType": "PUT", "strategy": "SINGLE",
        "includeUnderlyingQuote": "true", "range": "OTM",
        "fromDate": today.isoformat(),
        "toDate": (today + timedelta(days=dte_max)).isoformat()})
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {access_token()}",
                      "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"chain request failed: {e.code} {e.reason}", file=sys.stderr)
        print(f"response body: {body}", file=sys.stderr)
        sys.exit(1)


def parse(chain, dte_max=60):
    """putExpDateMap: {'2026-08-21:8': {'775.0': [contract, ...]}}"""
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
    c.add_argument("--demo", action="store_true", help="parse a fixture, no network")
    args = p.parse_args()

    if args.cmd == "auth":
        key, secret, cb = cfg()
        tok = {"manual": flow_manual, "listen": flow_listen,
               "schwabpy": flow_schwabpy}[args.flow](key, secret, cb)
        if tok:
            print(f"\ntoken written to {TOKEN_PATH} (mode 600). "
                  f"Re-run within 7 days.")
    else:
        chain = DEMO if args.demo else get_chain(args.symbol, args.dte_max)
        rows = parse(chain, args.dte_max)
        if not rows:
            sys.exit("no contracts parsed - check the symbol and field names")
        n1 = write_atm(rows, args.out)
        n2 = write_smile(rows, args.smile)
        print(f"{len(rows)} contracts -> {args.out} ({n1} expirations), "
              f"{args.smile} ({n2} rows)")
        print(f"  next: calendar_math.py screen {args.out} --capital 10000")


if __name__ == "__main__":
    main()
