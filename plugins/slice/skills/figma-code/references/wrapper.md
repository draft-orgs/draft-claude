# Wrapper marker

When you code responsive HTML from a skeleton and feed it back through `extract.py`,
any structural element you ADD (an overflow clip for a carousel, a flex/grid
container, a positioning shell) becomes an extra node in the extracted tree and
misaligns it with the design document — every path below it shifts, so `validate`
floods with false differences.

To add such scaffolding safely, mark it with the boolean attribute `data-wrapper`:

```html
<div data-wrapper class="carousel-viewport">
  ... real design nodes ...
</div>
```

`extract.py` treats a `data-wrapper` element as **transparent**: it emits no node for
the wrapper, lifts the wrapper's children into its parent in place, and discards the
wrapper's own tag, box, and style. Nested wrappers collapse away the same way.

## Rules

- A wrapper carries **layout only** — `display`, `flex`/`grid`, `overflow`,
  `position`, sizing. Never put **fidelity style** (background, border,
  border-radius, font, color) on a wrapper; it would be discarded. Fidelity style
  belongs on a real design node.
- Never mark a real design node `data-wrapper` — it would vanish from the tree and
  from `validate`.
- The figma side never has wrappers, so a marked wrapper keeps the coded tree
  aligned with the figma tree.
