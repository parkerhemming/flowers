# flowers

Bouquets made of text characters. They bloom, sway in the wind, and spell the recipient's name when tapped.

This repo runs two sites:

| Branch | Site | What it is |
|---|---|---|
| `main` | **https://hemm.ing/flowers** | The generator: anyone can make a bouquet for someone for 99¢ |
| `aria` | **https://flowers.hemm.ing** | The original bouquet made for Aria. Kept as it was; only changed on purpose |

## Making a bouquet

1. **Who it's for.** `> to:` takes the recipient's name: letters only, up to 9. `> from:` is optional.
2. **Step 1 · focal flowers.** Up to 3 main flowers, picked from live ASCII cards. A pink `<3` marks one as their favorite.
3. **Step 2 · filler & greenery.** Up to 2 accents, such as baby's breath or eucalyptus.
4. **Step 3 · little notes.** Up to 6 short messages, typed one by one under the flowers after "to: …, from: …".
5. **Checkout.** 99¢: Apple Pay first, Google Pay where Apple Pay isn't available, then card. A redeem code makes it free.
6. **The link.** The buyer gets a short link like `hemm.ing/flowers/k7x2p9`, plus a confirmation email with the same link.

A live preview of the bouquet sits at the bottom of the screen on phones, and in a side column on desktop.

## What the recipient sees

- The bouquet grows out of the dark and sways in the wind. A note types itself at the bottom: "to: sam, from: alex", then each extra message in turn.
- Tapping the flowers rearranges them to spell the name. The letters grow in as a thin vine, so even long names stay readable.
- `[i]` lists every flower and what it means. Their favorite gets a pink `<3` and "Sam's favorite."
- `[↺]` replays it from the start.
- **Link previews:** shared in Messages, the link shows "For Sam" and a picture of that bouquet.
- **Add to Home Screen:** the bouquet becomes its own app, "For Sam", with that picture as its icon.

## Files

| File | What it does |
|---|---|
| `index.html` | The create page and checkout |
| `bouquet.html` | Shows a bouquet, from a short link or from `?name=&f=&msg=` |
| `flowers.js` | Shared code: all 20 flower drawings, their meanings, and the ASCII card renderer |
| `catalog.html` | Every flower on one page, for reviewing new ones |
| `api/server.py` | The backend: saved bouquets, payments, codes, icons and email. Python standard library only |
| `api/flowers-api.service` | Keeps the backend running on the server (systemd) |

There's no build step and no libraries, apart from Stripe's own `js.stripe.com` script on the checkout.

## How the flowers are drawn

1. Each flower is painted as shaded vector shapes onto a hidden canvas: petals, stems, leaves.
2. That image is sampled cell by cell into a monospace grid. Brightness picks a character from a density ramp (`` .`',:;~-=+*<>!?ox%&#@``), strong edges become `| / - \`, and the colour comes from the flower underneath.
3. Light smoothing between frames keeps characters from flickering, so the motion reads smoothly even though it's made of text.

A bouquet is built from its flower list (`?f=rose.calla*.babys`, where `*` marks their favorite):
- The focal flowers spread through a dome on a sunflower-seed spiral.
- Filler goes into the gaps.
- Smaller flowers are added if there are too few to spell a name.

## Server

Everything runs on the hemm.ing server (74.207.243.33), behind Cloudflare.

| What | Where |
|---|---|
| Pages | `/var/www/flowers-app/`, served at `hemm.ing/flowers/` by nginx |
| Backend | `/opt/flowers/server.py`, systemd service `flowers-api`, on `127.0.0.1:8790`. nginx sends `hemm.ing/flowers/api/*` to it |
| Short links | nginx rewrites `hemm.ing/flowers/<6 letters>` to the backend, which serves `bouquet.html` with that bouquet's title and image filled in |
| Data | `/var/lib/flowers/flowers.db` (SQLite: bouquets and codes); home-screen icons in `/var/lib/flowers/icons/` |
| Secrets | `/etc/flowers.env`: Stripe keys and webhook secret, plus the Office 365 mail app (tenant ID, client ID, secret, `MAIL_FROM`). Never in this repo |

**Payments:**
- The backend creates a 99¢ Stripe payment when checkout opens.
- A bouquet unlocks when Stripe's signed webhook (`payment_intent.succeeded`, sent to `https://hemm.ing/flowers/api/webhook`) confirms the payment, or when the backend checks with Stripe directly.

**Email:**
- The confirmation email goes out once per paid bouquet, from `flowers@hemm.ing`, through Microsoft Graph.
- The mail app is locked to that mailbox by an Exchange application access policy.

**Limits:** each visitor can start 12 checkouts and make 10 wrong code guesses per hour.

### Admin commands

Run these on the server:

```bash
ssh root@74.207.243.33 sudo -u flowers python3 /opt/flowers/server.py codes 5
```
Makes 5 new single-use redeem codes, like `FLWR-HA7TWM`. Give one to a friend and they get a free bouquet.

```bash
ssh root@74.207.243.33 sudo -u flowers python3 /opt/flowers/server.py codes
```
Lists every code: when it was made, whether it's been used, and which bouquet it made.

```bash
ssh root@74.207.243.33 sudo -u flowers python3 /opt/flowers/server.py list
```
Shows the latest 30 bouquets: id, date, paid or pending, how it was paid, names, flowers, buyer email. Add a number for more, e.g. `list 200`.

```bash
ssh root@74.207.243.33 sudo -u flowers python3 /opt/flowers/server.py delete 59jg3v 9kzptm
```
Deletes bouquets and their icons for good. Their links stop working.

### Publishing a change

Upload the pages:
```bash
scp index.html bouquet.html flowers.js catalog.html root@74.207.243.33:/var/www/flowers-app/
```

Upload the backend and restart it:
```bash
scp api/server.py root@74.207.243.33:/opt/flowers/server.py && ssh root@74.207.243.33 systemctl restart flowers-api
```

- HTML is served with `Cache-Control: no-store`.
- After changing `flowers.js`, bump `?v=` in the three pages that load it.
- `python3 api/server.py selftest` checks the backend's input cleaning, the webhook signature check, the rate limits and the email template, with no network needed.

The Aria page (`aria` branch) deploys separately, to `/var/www/flowers/`.
