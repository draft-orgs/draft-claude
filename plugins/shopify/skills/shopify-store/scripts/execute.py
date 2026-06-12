#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys

# The scope set the Shopify CLI can grant for a normal custom app. Auth is
# all-or-nothing, so this excludes privileged payment, subscription,
# marketplace, and Plus-only scopes that would make the whole reauth refuse.
DEFAULT_SCOPES = "read_all_orders,write_app_proxy,read_assigned_fulfillment_orders,write_assigned_fulfillment_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders,read_third_party_fulfillment_orders,write_third_party_fulfillment_orders,read_cart_transforms,write_cart_transforms,read_checkout_branding_settings,write_checkout_branding_settings,read_checkout_and_accounts_configurations,write_checkout_and_accounts_configurations,read_content,write_content,read_online_store_pages,read_customer_events,write_pixels,read_customer_merge,write_customer_merge,read_customers,write_customers,read_delivery_customizations,write_delivery_customizations,read_discounts,write_discounts,read_draft_orders,write_draft_orders,read_files,write_files,read_fulfillments,write_fulfillments,read_gift_cards,write_gift_cards,read_inventory,write_inventory,read_legal_policies,write_legal_policies,read_locales,write_locales,read_locations,write_locations,read_markets,write_markets,read_marketing_events,write_marketing_events,read_metaobject_definitions,write_metaobject_definitions,read_metaobjects,write_metaobjects,read_online_store_navigation,write_online_store_navigation,read_order_edits,write_order_edits,read_orders,write_orders,read_payment_customizations,write_payment_customizations,read_payment_terms,write_payment_terms,read_price_rules,write_price_rules,write_privacy_settings,read_privacy_settings,read_products,write_products,read_reports,read_returns,write_returns,read_script_tags,write_script_tags,read_shipping,write_shipping,read_shopify_payments_disputes,read_shopify_payments_payouts,read_store_credit_accounts,read_store_credit_account_transactions,write_store_credit_account_transactions,read_themes,write_themes,read_translations,write_translations,read_validations,write_validations,read_publications,write_publications,read_product_listings,write_product_listings,read_inventory_shipments,read_inventory_transfers,read_cash_tracking"


def main():
    parser = argparse.ArgumentParser(
        prog="execute.py",
        description="Run a graphql query against a store",
        epilog="Examples:\n  python3 execute.py --store your-store --query '{ shop { name } }'\n  python3 execute.py --store your-store --query '{ shop { name } }' --scopes read_products,read_orders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", type=str, required=True, help="The graphql query or mutation to run")
    parser.add_argument("--store", type=str, required=True, help="The store domain or short name to target")
    parser.add_argument("--variables", type=str, help="The graphql variables as a json object string")
    parser.add_argument("--scopes", type=str, help="The comma separated scopes to request on reauth")
    args = parser.parse_args()

    # Resolve store to a domain by appending .myshopify.com unless it already ends with that suffix.
    domain = args.store if args.store.endswith(".myshopify.com") else args.store + ".myshopify.com"

    # Build the cli base as npx -y @shopify/cli@latest store, using npx.cmd on win32.
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    cli = [npx, "-y", "@shopify/cli@latest", "store"]

    # Run execute with -s domain -j -q query, appending --variables only when variables is given.
    execute_cmd = cli + ["execute", "-s", domain, "-j", "-q", args.query]
    if args.variables is not None:
        execute_cmd += ["--variables", args.variables]

    def run_query():
        return subprocess.run(execute_cmd, capture_output=True, text=True)

    def is_auth_error(result):
        # Treat it as an auth error when the json body has an errors entry whose extensions.code is ACCESS_DENIED.
        try:
            body = json.loads(result.stdout)
        except (ValueError, TypeError):
            body = None
        if isinstance(body, dict):
            for error in body.get("errors", []) or []:
                if isinstance(error, dict) and error.get("extensions", {}).get("code") == "ACCESS_DENIED":
                    return True
        # Also treat a nonzero exit whose stdout or stderr mentions auth as an auth error.
        if result.returncode != 0 and ("auth" in result.stdout.lower() or "auth" in result.stderr.lower()):
            return True
        return False

    result = run_query()

    if is_auth_error(result):
        # On an auth error run store auth -s domain --scopes, defaulting to the
        # cli-grantable scope set when scopes is omitted.
        scopes = args.scopes if args.scopes is not None else DEFAULT_SCOPES
        # Send reauth output to stderr so stdout carries only the response json.
        subprocess.run(
            cli + ["auth", "-s", domain, "--scopes", scopes],
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        # Rerun the query once after reauth and never reauth more than once.
        result = run_query()

    # Exit loud with stderr or stdout when the final run is nonzero, otherwise print the stripped stdout.
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        sys.exit(result.returncode)
    print(result.stdout.strip())



if __name__ == "__main__":
    main()
