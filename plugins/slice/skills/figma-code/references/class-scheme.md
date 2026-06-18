# Skeleton class scheme

How `--emit-skeleton` turns each field of an element `style` into atomic utility
classes (Tailwind-like, but hand-generated — there is no Tailwind dependency). Each
distinct property/value becomes one class, defined once and deduplicated in the
`<name>.css` stylesheet that `<name>.html` links, then listed in the element's
`class` attribute.

Scope: only the `style` object fields below become classes. `box`, `content`,
`screenshot`, and the tree structure are not styled here.

## One class per atomic value

Split every style field down to the smallest reusable unit so classes are shared
across the whole document.

| Field | Class(es) | CSS declaration(s) |
| --- | --- | --- |
| font-family | `ff-<primary-slug>` | `font-family:<full original string>` |
| font-weight | `fw-<n>` | `font-weight:<n>` |
| font-size | `fs-<n>` | `font-size:<n>px` |
| text-align | `ta-<value>` | `text-align:<value>` |
| letter-spacing | `ls-<token>` | `letter-spacing:<n>px` |
| line-height | `lh-<n>` | `line-height:<n>px` |
| color | `c-<hex>` | `color:<original color string>` |
| border-top | `bt-<w>` `bt-<style>` `bt-<hex>` | `border-top-width` / `border-top-style` / `border-top-color` |
| border-right | `br-<w>` `br-<style>` `br-<hex>` | `border-right-width` / `border-right-style` / `border-right-color` |
| border-bottom | `bb-<w>` `bb-<style>` `bb-<hex>` | `border-bottom-width` / `border-bottom-style` / `border-bottom-color` |
| border-left | `bl-<w>` `bl-<style>` `bl-<hex>` | `border-left-width` / `border-left-style` / `border-left-color` |
| border-radius | `rtl-<n>` `rtr-<n>` `rbr-<n>` `rbl-<n>` | `border-top-left-radius` / `border-top-right-radius` / `border-bottom-right-radius` / `border-bottom-left-radius` |
| background (solid color) | `bg-<hex>` | `background:<original color string>` |
| background (complex) | — none, inline instead — | see below |
| background-blend-mode | — none, inline instead — | emitted with the complex background |

## Token rules

- **Number** — drop the `px` unit. `24px` → `24`, e.g. `fs-24`.
- **Negative** — prefix `n`. `-1px` → `ls-n1`; the CSS body keeps `-1px`.
- **Decimal** — keep the dot in the class name and escape it in the selector, like
  Tailwind. `1.5px` → class attribute `bt-1.5`, rule `.bt-1\.5{border-top-width:1.5px}`.
- **Color** — opaque → 6-digit hex, e.g. `bg-2563eb`. Alpha below 1 → 8-digit hex
  `rrggbbaa` where the alpha byte is `round(a*255)`, e.g. `rgba(0, 0, 0, 0.5)` →
  `bg-00000080`. The CSS body always keeps the original color string.
- **font-family** — the class name slugs the **primary** family only (lowercase,
  non-alphanumeric runs collapsed to `-`, trimmed): `"Helvetica Neue", Arial` →
  `ff-helvetica-neue`. The CSS body keeps the **full** original string so the
  fallbacks survive.
- **border side** — three longhand classes: width (`bt-1`), style (`bt-solid`),
  color (`bt-e5e7eb`).
- **border-radius** — always four per-corner classes, even when the radii are equal.

## Complex background → inline

A `background` that is not a single solid color (a gradient, a `url(...)` image, or
multiple layers) cannot be tokenized cleanly, so it is written as an inline
`style="background:…"` on the element instead of a class. When
`background-blend-mode` is present it is emitted in the same inline `style` next to
the background. A solid-color background never carries a blend mode.
