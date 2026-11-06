#!/usr/bin/env python3
"""The flowers API (hemm.ing/flowers/api/*): saves bouquets behind a 99-cent Stripe payment
or a single-use redeem code, and serves them back for short links (hemm.ing/flowers/<id>).

Standard library only. Keys come from the environment (/etc/flowers.env), never the repo:
  STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET

  python3 server.py                 run the API on 127.0.0.1:8790
  python3 server.py codes 5         print 5 new redeem codes
  python3 server.py selftest        quick checks, no network
"""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get('FLOWERS_DB', '/var/lib/flowers/flowers.db')
PRICE = 99                                    # cents, USD
KEYS = {'rose', 'tulip', 'sunflower', 'orchid', 'peony', 'hydrangea', 'lily', 'carnation', 'gerbera', 'ranunculus',
        'calla', 'mum', 'dahlia', 'anemone', 'iris', 'lavender', 'dokrak', 'daisy', 'babys', 'eucalyptus'}
ID_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789'  # no 0/o, 1/l/i: easy to read out loud
ID_RE = re.compile(r'^[a-hjkmnp-z2-9]{6}$')


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10, isolation_level=None)
    c.execute('create table if not exists bouquets (id text primary key, data text, status text, pi text, via text, created int)')
    c.execute('create table if not exists codes (code text primary key, used_by text, created int, used int)')
    return c


# ---- the same rules the pages use, enforced again here ----
def clean(body):
    name = unicodedata.normalize('NFD', str(body.get('name', '')))
    name = re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z ]', '', name)).strip()[:9].strip()
    if not name:
        raise ValueError('name')
    frm = re.sub(r'[<>&"]', '', unicodedata.normalize('NFC', str(body.get('from', '')))).strip()[:20]
    picks, seen, fav = [], set(), False
    for k in str(body.get('f', '')).split('.'):
        key = k.rstrip('*')
        if key in KEYS and key not in seen and len(picks) < 5:
            star = k.endswith('*') and not fav
            fav = fav or star
            picks.append(key + ('*' if star else ''))
            seen.add(key)
    if not picks:
        raise ValueError('flowers')
    msgs = [m.strip()[:40] for m in body.get('msgs', []) if isinstance(m, str) and m.strip()][:6]
    return {'name': name, 'from': frm, 'f': '.'.join(picks), 'msgs': msgs}


def new_id(c):
    while True:
        i = ''.join(secrets.choice(ID_CHARS) for _ in range(6))
        if not c.execute('select 1 from bouquets where id=?', (i,)).fetchone():
            return i


# ---- Stripe over plain HTTPS ----
def stripe(method, path, params=None):
    req = urllib.request.Request('https://api.stripe.com/v1/' + path, method=method,
                                 data=urllib.parse.urlencode(params).encode() if params else None,
                                 headers={'Authorization': 'Bearer ' + os.environ['STRIPE_SECRET_KEY']})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def verify_webhook(payload, header, secret, now=None, tolerance=300):
    """Stripe-Signature: t=<ts>,v1=<hmac sha256 of "<ts>.<payload>">"""
    parts = dict(p.split('=', 1) for p in header.split(',') if '=' in p)
    sigs = [p.split('=', 1)[1] for p in header.split(',') if p.startswith('v1=')]
    t = parts.get('t', '')
    if not t.isdigit() or abs((now or time.time()) - int(t)) > tolerance:
        return False
    want = hmac.new(secret.encode(), f'{t}.'.encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


class API(BaseHTTPRequestHandler):
    def send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(min(n, 20000))

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/config':
            return self.send(200, {'publishableKey': os.environ.get('STRIPE_PUBLISHABLE_KEY', ''), 'price': PRICE})
        m = re.match(r'^/b/([a-z0-9]{6})$', path)
        if not m or not ID_RE.match(m.group(1)):
            return self.send(404, {'error': 'not found'})
        c = db()
        row = c.execute('select data, status, pi from bouquets where id=?', (m.group(1),)).fetchone()
        if not row:
            return self.send(404, {'error': 'not found'})
        data, status, pi = row
        if status != 'paid' and pi and os.environ.get('STRIPE_SECRET_KEY'):
            # the webhook can lag a second or two behind the buyer; ask Stripe directly
            try:
                if stripe('GET', 'payment_intents/' + pi).get('status') == 'succeeded':
                    c.execute("update bouquets set status='paid' where id=?", (m.group(1),))
                    status = 'paid'
            except (urllib.error.URLError, KeyError):
                pass
        return self.send(200, {'status': status, **(json.loads(data) if status == 'paid' else {})})

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/webhook':
            payload = self.read()
            secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
            if not secret or not verify_webhook(payload, self.headers.get('Stripe-Signature', ''), secret):
                return self.send(400, {'error': 'bad signature'})
            ev = json.loads(payload)
            if ev.get('type') == 'payment_intent.succeeded':
                db().execute("update bouquets set status='paid' where pi=?", (ev['data']['object']['id'],))
            return self.send(200, {'ok': True})
        if path != '/create':
            return self.send(404, {'error': 'not found'})
        try:
            body = json.loads(self.read() or b'{}')
            data = clean(body)
        except (ValueError, json.JSONDecodeError) as e:
            return self.send(400, {'error': f'missing {e}' if str(e) in ('name', 'flowers') else 'bad request'})
        c = db()
        i = new_id(c)
        code = re.sub(r'[^A-Z0-9]', '', str(body.get('code', '')).upper())
        if code:   # a friend's free bouquet: each code works exactly once
            c.execute('begin immediate')
            used = c.execute('update codes set used_by=?, used=? where code=? and used_by is null', (i, int(time.time()), code)).rowcount
            if used:
                c.execute('insert into bouquets values (?,?,?,?,?,?)', (i, json.dumps(data), 'paid', None, 'code:' + code, int(time.time())))
            c.execute('commit')
            return self.send(200, {'id': i}) if used else self.send(400, {'error': "that code doesn't work (or it's been used)"})
        if not os.environ.get('STRIPE_SECRET_KEY'):
            return self.send(503, {'error': "payments aren't switched on yet"})
        # ponytail: no per-IP rate limit on unpaid intents; add one if someone spams this
        try:
            pi = stripe('POST', 'payment_intents', {'amount': PRICE, 'currency': 'usd', 'automatic_payment_methods[enabled]': 'true',
                                                    'description': f'Flowers for {data["name"]}', 'metadata[bouquet]': i})
        except urllib.error.URLError:
            return self.send(502, {'error': "couldn't reach the payment provider, try again"})
        c.execute('insert into bouquets values (?,?,?,?,?,?)', (i, json.dumps(data), 'pending', pi['id'], 'stripe', int(time.time())))
        return self.send(200, {'id': i, 'clientSecret': pi['client_secret']})

    def log_message(self, fmt, *args):   # one line per request, no bodies
        sys.stderr.write('%s %s\n' % (self.command, self.path.split('?')[0]))


def make_codes(n):
    c = db()
    out = []
    for _ in range(n):
        code = 'FLWR-' + ''.join(secrets.choice('ABCDEFGHJKMNPQRSTUVWXYZ23456789') for _ in range(6))
        c.execute('insert into codes values (?,?,?,?)', (code.replace('-', ''), None, int(time.time()), None))
        out.append(code)
    return out


def selftest():
    d = clean({'name': ' Zoë <b>!! ', 'from': 'Al <x>', 'f': 'rose*.nope.calla*.rose.babys', 'msgs': ['hi', '', 'x' * 99, 3]})
    assert d == {'name': 'Zoe b', 'from': 'Al x', 'f': 'rose*.calla.babys', 'msgs': ['hi', 'x' * 40]}, d
    for bad in ({'name': '123', 'f': 'rose'}, {'name': 'Sam', 'f': 'nope'}):
        try:
            clean(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    t = int(time.time()); sig = hmac.new(b'whsec', f'{t}.'.encode() + b'{}', hashlib.sha256).hexdigest()
    assert verify_webhook(b'{}', f't={t},v1={sig}', 'whsec')
    assert not verify_webhook(b'{"x":1}', f't={t},v1={sig}', 'whsec')
    assert not verify_webhook(b'{}', f't={t - 999},v1={sig}', 'whsec')
    assert ID_RE.match('k7x2p9') and not ID_RE.match('k7x2p0')
    print('ok')


if __name__ == '__main__':
    if sys.argv[1:2] == ['selftest']:
        selftest()
    elif sys.argv[1:2] == ['codes']:
        print('\n'.join(make_codes(int(sys.argv[2]) if len(sys.argv) > 2 else 1)))
    else:
        ThreadingHTTPServer(('127.0.0.1', 8790), API).serve_forever()
