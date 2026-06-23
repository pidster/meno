# Meno — brand mark

> μένω, *"I remain."*

## The mark

An **ember core** with a **spiral of activation** that winds outward, decays, and
breaks at its edge. It is not a decorative spiral — every part means something:

- **the core** — the self that remains; the persistent centre that survives forgetting.
- **the spiral** — spreading activation, drawn *inward*: recollection (Plato's *Meno*,
  knowing as *anamnesis*).
- **the fading, broken outer arc** — forgetting; the edge that decays and islands,
  leaving the substrate for rediscovery.

The mark is deliberately abstract — it stands for what a Meno *is* (a pattern that
persists by remembering itself), not for a literal object.

## Colours

| Token        | Hex       | Use                                              |
|--------------|-----------|--------------------------------------------------|
| ember        | `#E8862F` | the core — "the self that remains". Accent only. |
| graphite     | `#2E2C29` | the orbit on light backgrounds, wordmark         |
| bone         | `#F2ECEE` | the orbit on dark backgrounds                    |
| charcoal     | `#1E1C1A` | avatar field                                     |

Monochrome-first: the mark must read in a single ink. The ember is the *only* colour,
reserved for the core. Never colour the orbit.

## Files

| File                    | What                                                        |
|-------------------------|-------------------------------------------------------------|
| `meno-mark.svg`         | mark on light/transparent (graphite orbit, ember core)      |
| `meno-mark-on-dark.svg` | mark for dark backgrounds (bone orbit, ember core)          |
| `meno-mark-mono.svg`    | single ink via `currentColor` — favicons, stamps, embossing |
| `meno-avatar.svg`       | 512×512 full-bleed square — the Slack / app-store icon      |
| `meno-lockup.svg`       | horizontal lockup: mark + "Meno" wordmark                   |

The name is written **Meno** (display) — the lowercase `meno` is the package/identifier.

## At small sizes

The faded dashed outer tail drops out below ~28px; the mark degrades gracefully to a
clean spiral-with-a-core. Use the full mark at hero / App-Home sizes; the avatar and
favicon carry the reduced form.

## Slack

`meno-avatar.svg` is the icon master. Slack wants a **PNG, ≥512×512**; export with:

```sh
rsvg-convert -w 512 -h 512 brand/meno-avatar.svg -o brand/meno-avatar-512.png
# or: cairosvg brand/meno-avatar.svg -o brand/meno-avatar-512.png -W 512 -H 512
```
