# flowers

A bouquet for Aria, live at **https://flowers.hemm.ing**.

Red roses, dok rak (ดอกรัก, the Thai "love flower") and orchids, rendered entirely as coloured ASCII. The bouquet blooms on load, sways in the wind, and when tapped the flowers physically rearrange themselves to spell "Aria".

## How it works

Everything is in `index.html`, with no dependencies and no build step.

1. Each frame, the bouquet is drawn as shaded vector shapes onto a hidden canvas.
2. That image is sampled cell by cell into a monospace grid. Brightness picks a glyph from a density ramp, and strong edges get directional glyphs (`| / - \`).
3. Temporal smoothing and per-cell hysteresis keep glyphs from flickering as things move.

## Debug URLs

| URL | What it shows |
|---|---|
| `/?bt=3` | Freezes the bloom at 3 seconds |
| `/?m=0.5` | Freezes the Aria morph halfway (0 = bouquet, 1 = name) |
| `/?cols=200` | Forces the grid density |

## Deploy

```bash
scp index.html og.jpg apple-touch-icon.png root@74.207.243.33:/var/www/flowers/
```

The nginx server block for `flowers.hemm.ing` is in `/etc/nginx/nginx.conf` on the server. Cloudflare proxies the domain and uses the `*.hemm.ing` origin certificate.
