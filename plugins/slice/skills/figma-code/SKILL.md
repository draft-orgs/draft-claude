---
name: figma-code
description: use when turning a figma node or an html into a design document with an optional skeleton html
---

## Scripts

- [extract.py](./scripts/extract.py) -- use when extracting a figma node or an html into a design document with an optional skeleton html

  Usage: `python3 extract.py [--figma STRING] [--figma-token STRING] [--html STRING] --out STRING [--emit-skeleton]`

  | Arg | Description |
  | --- | --- |
  | figma | The figma design url |
  | figma-token | The figma personal access token |
  | html | The path to the html file |
  | out | The output folder for the design document |
  | emit-skeleton | Also write a skeleton html and css rendered from the design document tree |

  Examples:
  ```bash
  python3 extract.py --figma-token your-figma-token --figma https://www.figma.com/design/your-file-key/Name?node-id=1-2 --out /path/to/dist --emit-skeleton
  python3 extract.py --html /path/to/page.html --out /path/to/dist
  ```

- [validate.py](./scripts/validate.py) -- use when comparing two design documents for fidelity

  Usage: `python3 validate.py --a STRING --b STRING`

  | Arg | Description |
  | --- | --- |
  | a | The path to the first design document |
  | b | The path to the second design document |

  Examples:
  ```bash
  python3 validate.py --a /path/to/fig/1-2.json --b /path/to/cln/1-2.json
  ```

## References

- [Element schema](./references/element.schema.json) -- read when you want to understand the element json schema

- [Skeleton class scheme](./references/class-scheme.md) -- read when you want to understand the skeleton class scheme

- [Wrapper marker](./references/wrapper.md) -- read when you add a structural wrapper while coding

## Gotchas

- **Don't:** Use the box x y width and height for coding.
  **Instead:** Read it to reason about the layout structure.
  **Why:** Html always needs to be responsive.

- **Don't:** Continue or work around a script error.
  **Instead:** Stop at once and report the error to the user.
  **Why:** A hidden failure produces a wrong design document.

- **Don't:** Reshape the skeleton tree or add an unmarked node.
  **Instead:** Style nodes in place and mark any wrapper you add.
  **Why:** Validate matches the two trees node by node.
