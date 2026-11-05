# flowers

A bouquet for Aria, live at **https://flowers.hemm.ing**.

Aria is in Thailand, so the bouquet is made from flowers that carry romantic meaning there. Everything on the page, every petal, leaf and stem, is a coloured text character.

## The flowers

| Flower | Thai | Why it's here |
|---|---|---|
| Red roses | กุหลาบแดง | Thailand's favourite way to say "I love you" |
| Dok rak (crown flower) | ดอกรัก | Its name means "love flower"; Thai couples wear it in wedding garlands |
| Orchids | กล้วยไม้ | Thailand's signature flower, for grace and beauty |
| Baby's breath | ยิปโซ | Aria's favourite, tucked into every gap |

## What happens on the page

1. **The bloom.** The bunch grows out of the dark: stems rise from the twine, leaves and ferns unfurl, then each flower opens on its own timing.
2. **The wind.** Once open, the bouquet sways in slow gusts. Taller flowers swing further and lag behind, heads nod, and leaves flutter.
3. **The hint.** If she hasn't tapped yet, the scene dims and a small prompt invites her to tap the flowers.
4. **Her name.** Tapping the flowers physically rearranges them to spell "Aria". The heads travel to the letters while their stems bend to stay attached. Tapping again sends them home. Tapping mid-way turns the motion around with a little momentum.
5. **The note.** A line types itself out at the bottom: "to: aria, from: parker". Every so often it backspaces and types one of a few other messages.

The `[i]` button explains the flowers. `[↺]` replays everything from the start. On an iPhone, the info panel also shows how to add the page to the home screen, where it gets its own rose icon and opens full screen.

## How it's made

Everything lives in a single `index.html`, with no libraries and no build step.

1. **Vector scene.** Each frame, the bouquet is painted as shaded vector shapes onto a hidden canvas: layered rose petals, five-lobed dok rak florets, orchid sprays, and stems that curve back to the tie.
2. **ASCII conversion.** That image is sampled cell by cell into a monospace grid. Each cell's brightness picks a character from a density ramp, strong edges get directional strokes (`| / - \`), and the colour comes from the flower underneath.
3. **Smoothness.** Small per-cell easing and hysteresis keep characters from flickering as things move, so motion reads as smooth even though it's made of text.

Everything is driven by one clock, so the bloom, wind, morph and note always stay in sync, and replay simply rewinds it.

## Hosting

The site is a static page served by nginx on the hemm.ing server, behind Cloudflare. To publish a change:

```bash
scp index.html apple-touch-icon.png root@74.207.243.33:/var/www/flowers/
```

The page is served with `Cache-Control: no-store`, so visitors always get the latest version.
