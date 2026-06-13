---
name: shopify-store
description: use when querying or mutating a shopify store
---

## Scripts

- [execute.py](./scripts/execute.py) -- use when running a graphql query against a store

  Usage: `python3 execute.py --query STRING --store STRING [--variables STRING]`

  | Arg | Description |
  | --- | --- |
  | query | The graphql query or mutation to run |
  | store | The store domain or short name to target |
  | variables | The graphql variables as a json object string |

  Examples:
  ```bash
  python3 execute.py --store your-store --query '{ shop { name } }'
  python3 execute.py --store your-store --query 'query($n: Int!){ products(first: $n){ nodes { id } } }' --variables '{"n": 5}'
  ```

- [auth.py](./scripts/auth.py) -- use when logging in to a store or importing a saved session

  Usage: `python3 auth.py [--store STRING] [--exclude STRING] [--import STRING]`

  | Arg | Description |
  | --- | --- |
  | store | The store domain or short name to log in to |
  | exclude | The comma separated scopes to drop from the default set |
  | import | The session blob to import |

  Examples:
  ```bash
  python3 auth.py --store your-store
  python3 auth.py --store your-store --exclude write_orders,write_payment_terms
  python3 auth.py --import <blob>
  ```

## References

- [Authentication guide](./references/authentication.md) -- read when a store needs auth

## Gotchas

- **Don't:** Run the auth login yourself.
  **Instead:** Read the authentication guide in references then guide the human.
  **Why:** The guide has the exact steps and the human owns the login.

- **Don't:** Retry auth with the same scopes when one is refused.
  **Instead:** Ask for the error then reissue the login with that scope excluded.
  **Why:** Auth is all or nothing so one refused scope blocks the login.
