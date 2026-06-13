# Session import guide

The `execute` tool runs a query against an **already stored** session. In a headless
environment with no browser it cannot log in, so the Shopify CLI reports
**No stored app authentication found** for the store and `execute` fails.

To recover, log in on a machine that has a browser, then carry that session over as a
single base64 line and import it here.

## 1. On your local machine (has a browser)

Run the `auth` tool, pointing it at your store:

    curl -s https://raw.githubusercontent.com/draft-orgs/draft-claude/main/plugins/shopify/skills/shopify-store/scripts/auth.py | python3 - --store your-store

This opens the browser login. After you finish logging in it prints a single base64
line — the gzipped Shopify CLI config holding the store session.

If the login fails because one scope is refused (auth is all or nothing), paste the
error back here. The assistant will reissue the command with that scope dropped:

    curl -s https://raw.githubusercontent.com/draft-orgs/draft-claude/main/plugins/shopify/skills/shopify-store/scripts/auth.py | python3 - --store your-store --exclude write_payment_terms

## 2. Paste that base64 line back into the chat.

## 3. The assistant imports it

The assistant runs the local script with the pasted blob:

    python3 auth.py --import <blob>

This decodes and writes the config to the per-platform path with owner only
permissions, so `execute` works again without a browser reauth.
