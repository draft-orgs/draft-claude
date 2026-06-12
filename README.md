# draft-claude

A Claude Code plugin marketplace. Made with draft.

## Structure

```
.claude-plugin/
└── marketplace.json   # lists every plugin
plugins/
└── shopify/           # work with Shopify from Claude Code
```

## Setup

```bash
# 1. add this marketplace
claude plugin marketplace add draft-orgs/draft-claude

# 2. install a plugin from it (current project only)
claude plugin install shopify@draft-claude --scope project
```
