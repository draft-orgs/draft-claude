---
name: shopify-store
description: use when querying or mutating a shopify store
---

## Scripts

- [execute.py](./scripts/execute.py) -- use when running a graphql query against a store

  Usage: `python3 execute.py --query STRING --store STRING [--variables STRING] [--scopes STRING]`

  | Arg | Description |
  | --- | --- |
  | query | The graphql query or mutation to run |
  | store | The store domain or short name to target |
  | variables | The graphql variables as a json object string |
  | scopes | The comma separated scopes to request on reauth |

  Examples:
  ```bash
  python3 execute.py --store your-store --query '{ shop { name } }'
  python3 execute.py --store your-store --query '{ shop { name } }' --scopes read_products,read_orders
  ```

## Gotchas

- **Don't:** Add a privileged scope the cli cannot grant.
  **Instead:** Keep to the default scopes the cli can grant.
  **Why:** Auth fails for the whole set when one scope is refused.
