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
