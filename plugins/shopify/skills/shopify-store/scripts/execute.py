#!/usr/bin/env python3
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="execute.py",
        description="Run a graphql query against a store",
        epilog="Examples:\n  python3 execute.py --store your-store --query '{ shop { name } }'\n  python3 execute.py --store your-store --query 'query($n: Int!){ products(first: $n){ nodes { id } } }' --variables '{\"n\": 5}'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", type=str, required=True, help="The graphql query or mutation to run")
    parser.add_argument("--store", type=str, required=True, help="The store domain or short name to target")
    parser.add_argument("--variables", type=str, help="The graphql variables as a json object string")
    args = parser.parse_args()

    # Resolve store to a domain by appending .myshopify.com unless it already ends with that suffix.
    store = args.store
    if not store.endswith(".myshopify.com"):
        store = store + ".myshopify.com"

    # Build the cli base as npx -y @shopify/cli@latest store, using npx.cmd on win32.
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    cli_base = [npx, "-y", "@shopify/cli@latest", "store"]

    # Run execute with -s domain -j -q query, appending --variables only when variables is given.
    cmd = cli_base + ["execute", "-s", store, "-j", "-q", args.query]
    if args.variables:
        cmd = cmd + ["--variables", args.variables]

    # Exit loud with stderr or stdout when the run is nonzero, otherwise print the stripped stdout.
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        output = result.stderr or result.stdout
        sys.stderr.write(output)
        sys.exit(result.returncode)
    else:
        print(result.stdout.strip())



if __name__ == "__main__":
    main()
