#!/usr/bin/env python3
"""The flowers API (hemm.ing/flowers/api/*): saves bouquets behind a 99-cent Stripe payment
or a single-use redeem code, and serves them back for short links (hemm.ing/flowers/<id>).

Standard library only. Keys come from the environment (/etc/flowers.env), never the repo:
  STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET
  MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET, MAIL_FROM   (confirmation email via Office 365 / Microsoft Graph)

  python3 server.py                 run the API on 127.0.0.1:8790
  python3 server.py codes 5         print 5 new redeem codes
  python3 server.py selftest        quick checks, no network
"""
import base64, hashlib, hmac, html, json, threading, os, re, secrets, sqlite3, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get('FLOWERS_DB', '/var/lib/flowers/flowers.db')
PRICE = 99                                    # cents, USD
KEYS = {'rose', 'tulip', 'sunflower', 'orchid', 'peony', 'hydrangea', 'lily', 'carnation', 'gerbera', 'ranunculus',
        'calla', 'mum', 'dahlia', 'anemone', 'iris', 'lavender', 'dokrak', 'daisy', 'babys', 'eucalyptus'}
ID_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789'  # no 0/o, 1/l/i: easy to read out loud
ID_RE = re.compile(r'^[a-hjkmnp-z2-9]{6}$')
ICONS = os.path.join(os.path.dirname(DB), 'icons')
DEFAULT_ICON = os.environ.get('FLOWERS_DEFAULT_ICON', '/var/www/flowers-app/apple-touch-icon.png')
icon_path = lambda i: os.path.join(ICONS, i + '.png')


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10, isolation_level=None)
    c.execute('create table if not exists bouquets (id text primary key, data text, status text, pi text, via text, created int)')
    c.execute('create table if not exists codes (code text primary key, used_by text, created int, used int)')
    for col in ('email text', 'mailed int'):   # added later; harmless if already there
        try:
            c.execute('alter table bouquets add column ' + col)
        except sqlite3.OperationalError:
            pass
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


EMAIL_RE = re.compile(r'^[^@\s<>"]{1,64}@[^@\s<>"]{1,180}\.[A-Za-z]{2,24}$')


def paid(c, i):
    """Mark a bouquet paid and send the buyer their link, exactly once."""
    c.execute("update bouquets set status='paid' where id=?", (i,))
    if c.execute("update bouquets set mailed=1 where id=? and status='paid' and mailed is null and email is not null", (i,)).rowcount:
        email, data = c.execute('select email, data from bouquets where id=?', (i,)).fetchone()
        threading.Thread(target=mail_link, args=(i, email, json.loads(data)), daemon=True).start()


def email_html(i, d):
    url = f'https://hemm.ing/flowers/{i}'
    name, frm = html.escape(d['name'].lower()), html.escape(d.get('from', '').lower())
    mono = "font-family:'JetBrains Mono',Menlo,Consolas,'Courier New',monospace"
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#0b0a0d">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0b0a0d"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:440px;{mono};color:#e7dde1;font-size:14px;line-height:1.55">
<tr><td style="border:1px dashed #5a4a50;border-radius:3px;padding:22px 20px;background:#0b0a0d">
<div style="color:#ffd6dc;font-weight:bold;font-size:15px">&gt; flowers for {name}{f', from {frm}' if frm else ''} <span style="color:#ffd6dc">&lt;3</span></div>
<p style="color:#9d9096;margin:6px 0 18px">your bouquet is ready. it blooms, sways in the wind, and spells their name when they tap it.</p>
<img src="{url.replace('/flowers/', '/flowers/api/icon/')}" width="96" height="96" alt="" style="display:block;border:1px dashed #5a4a50;border-radius:3px;margin:0 0 18px">
<a href="{url}" style="color:#ffd6dc;font-size:16px;text-decoration:none;{mono}">hemm.ing/flowers/{i}</a>
<table role="presentation" cellpadding="0" cellspacing="0" style="margin:16px 0 4px"><tr><td style="border:1px solid #ffd6dc;border-radius:3px">
<a href="{url}" style="display:inline-block;padding:10px 18px;color:#ffd6dc;text-decoration:none;{mono};font-size:13px">[ open the bouquet ]</a></td></tr></table>
<p style="color:#9d9096;font-size:12px;margin:18px 0 0">send that link to {name}. keep this email: it's your copy if you ever lose it.</p>
</td></tr>
<tr><td style="color:#5a5258;font-size:11px;padding:12px 4px;text-align:center;{mono}">made with <a href="https://hemm.ing/flowers/" style="color:#9d9096;text-decoration:none">hemm.ing/flowers</a></td></tr>
</table></td></tr></table></body></html>"""


def mail_link(i, to, d):
    """Send through Office 365 (Microsoft Graph, app-only). On failure, leave it unsent so a later check retries."""
    env = os.environ
    try:
        if not all(env.get(k) for k in ('MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'MAIL_FROM')):
            raise RuntimeError('email not configured')
        tok = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://login.microsoftonline.com/{env['MS_TENANT_ID']}/oauth2/v2.0/token",
            data=urllib.parse.urlencode({'client_id': env['MS_CLIENT_ID'], 'client_secret': env['MS_CLIENT_SECRET'],
                                         'scope': 'https://graph.microsoft.com/.default', 'grant_type': 'client_credentials'}).encode()), timeout=20))['access_token']
        msg = {'message': {'subject': f"your flowers for {d['name']} <3", 'body': {'contentType': 'HTML', 'content': email_html(i, d)},
                           'toRecipients': [{'emailAddress': {'address': to}}]}, 'saveToSentItems': True}
        urllib.request.urlopen(urllib.request.Request(f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(env['MAIL_FROM'])}/sendMail",
                                                      data=json.dumps(msg).encode(), method='POST',
                                                      headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}), timeout=20)
        sys.stderr.write(f'mailed {i}\n')
    except Exception as e:   # never take the API down over an email
        sys.stderr.write(f'mail {i} failed: {e}\n')
        db().execute('update bouquets set mailed=null where id=?', (i,))


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
        return self.rfile.read(min(n, 400001 if self.path.startswith('/icon/') else 20000))

    def do_GET(self):
        path = self.path.split('?')[0]
        m = re.match(r'^/icon/([a-z0-9]{6})$', path)
        if m:   # the bouquet's home-screen icon, or the plain rose until it has one
            f = icon_path(m.group(1)) if ID_RE.match(m.group(1)) and os.path.exists(icon_path(m.group(1))) else DEFAULT_ICON
            body = open(f, 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'public, max-age=86400' if f != DEFAULT_ICON else 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
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
                    paid(c, m.group(1))
                    status = 'paid'
            except (urllib.error.URLError, KeyError):
                pass
        if status == 'paid':
            paid(c, m.group(1))   # retries an email that failed earlier (no-op once sent)
        return self.send(200, {'status': status, 'icon': os.path.exists(icon_path(m.group(1))), **(json.loads(data) if status == 'paid' else {})})

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/webhook':
            payload = self.read()
            secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
            if not secret or not verify_webhook(payload, self.headers.get('Stripe-Signature', ''), secret):
                return self.send(400, {'error': 'bad signature'})
            ev = json.loads(payload)
            if ev.get('type') == 'payment_intent.succeeded':
                c = db()
                row = c.execute('select id from bouquets where pi=?', (ev['data']['object']['id'],)).fetchone()
                if row:
                    paid(c, row[0])
            return self.send(200, {'ok': True})
        m = re.match(r'^/icon/([a-z0-9]{6})$', path)
        if m:   # set once, by the first browser to show the bouquet: a paid bouquet, a PNG, small
            i, png = m.group(1), self.read()
            row = ID_RE.match(i) and db().execute('select status from bouquets where id=?', (i,)).fetchone()
            if not row or row[0] != 'paid' or os.path.exists(icon_path(i)) or not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) > 400000:
                return self.send(400, {'error': 'no'})
            os.makedirs(ICONS, exist_ok=True)
            with open(icon_path(i), 'xb') as fh:
                fh.write(png)
            return self.send(200, {'ok': True})
        m = re.match(r'^/email/([a-z0-9]{6})$', path)
        if m:
            try:
                email = str(json.loads(self.read() or b'{}').get('email', '')).strip()
            except json.JSONDecodeError:
                email = ''
            c = db()
            if not EMAIL_RE.match(email) or not ID_RE.match(m.group(1)) or not c.execute(
                    'update bouquets set email=? where id=? and mailed is null', (email, m.group(1))).rowcount:
                return self.send(400, {'error': "that email doesn't look right"})
            if c.execute('select status from bouquets where id=?', (m.group(1),)).fetchone()[0] == 'paid':
                paid(c, m.group(1))
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
        email = str(body.get('email', '')).strip()
        email = email if EMAIL_RE.match(email) else ''
        if code:   # a friend's free bouquet: each code works exactly once
            c.execute('begin immediate')
            used = c.execute('update codes set used_by=?, used=? where code=? and used_by is null', (i, int(time.time()), code)).rowcount
            if used:
                c.execute('insert into bouquets (id, data, status, pi, via, created, email) values (?,?,?,?,?,?,?)',
                          (i, json.dumps(data), 'pending', None, 'code:' + code, int(time.time()), email or None))
            c.execute('commit')
            if used:
                paid(c, i)
            return self.send(200, {'id': i}) if used else self.send(400, {'error': "that code doesn't work (or it's been used)"})
        if not os.environ.get('STRIPE_SECRET_KEY'):
            return self.send(503, {'error': "payments aren't switched on yet"})
        # ponytail: no per-IP rate limit on unpaid intents; add one if someone spams this
        try:
            pi = stripe('POST', 'payment_intents', {'amount': PRICE, 'currency': 'usd', 'automatic_payment_methods[enabled]': 'true',
                                                    'description': f'Flowers for {data["name"]}', 'metadata[bouquet]': i})
        except urllib.error.URLError:
            return self.send(502, {'error': "couldn't reach the payment provider, try again"})
        c.execute('insert into bouquets (id, data, status, pi, via, created) values (?,?,?,?,?,?)', (i, json.dumps(data), 'pending', pi['id'], 'stripe', int(time.time())))
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
    assert EMAIL_RE.match('a.b+c@hemm.ing') and not EMAIL_RE.match('a@b') and not EMAIL_RE.match('a <x>@b.co')
    page = email_html('k7x2p9', {'name': 'Sam', 'from': 'Al <b>', 'f': 'rose', 'msgs': []})
    assert 'flowers for sam, from al &lt;b&gt;' in page and 'hemm.ing/flowers/api/icon/k7x2p9' in page
    print('ok')


if __name__ == '__main__':
    if sys.argv[1:2] == ['selftest']:
        selftest()
    elif sys.argv[1:2] == ['codes']:
        print('\n'.join(make_codes(int(sys.argv[2]) if len(sys.argv) > 2 else 1)))
    else:
        ThreadingHTTPServer(('127.0.0.1', 8790), API).serve_forever()
