# Authentication guide

The assistant must never run the auth login itself. The human runs it, because
the human owns the login and its responsibility. The assistant only imports the
session the human hands back.

A store needs auth when it has no stored session — for example `execute` reports
**No stored app authentication found**. Recover like this.

## 1. The human logs in (local machine with a browser)

Run the `auth` tool against the store:

    curl -s https://raw.githubusercontent.com/draft-orgs/draft-claude/main/plugins/shopify/skills/shopify-store/scripts/auth.py | python3 - --store your-store

This opens the browser login. After login it prints a single base64 line — the
gzipped Shopify CLI config holding the store session.

If the login fails because one scope is refused (auth is all or nothing), paste
the error back. The assistant will hand you the command again with that scope
dropped:

    curl -s https://raw.githubusercontent.com/draft-orgs/draft-claude/main/plugins/shopify/skills/shopify-store/scripts/auth.py | python3 - --store your-store --exclude write_payment_terms

## 2. Paste the base64 line back into the chat.

## 3. The assistant imports it

The assistant runs the local script with the pasted blob:

    python3 auth.py --import <blob>

This writes the config to the per-platform path with owner only permissions, so
`execute` works — without the assistant ever running the login.
