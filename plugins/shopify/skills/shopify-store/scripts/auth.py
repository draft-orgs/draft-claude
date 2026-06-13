#!/usr/bin/env python3
import argparse
import base64
import gzip
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="auth.py",
        description="Log in to a store and print its session or import a saved one",
        epilog="Examples:\n  python3 auth.py --store your-store\n  python3 auth.py --store your-store --exclude write_orders,write_payment_terms\n  python3 auth.py --import <blob>",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--store", type=str, help="The store domain or short name to log in to")
    parser.add_argument("--exclude", type=str, help="The comma separated scopes to drop from the default set")
    parser.add_argument("--import", type=str, help="The session blob to import")
    args = parser.parse_args()

    # Resolve store to a domain by appending .myshopify.com unless it already ends with that suffix.
    if args.store:
        if args.store.endswith(".myshopify.com"):
            domain = args.store
        else:
            domain = args.store + ".myshopify.com"

    # Build the cli base as npx -y @shopify/cli@latest store, using npx.cmd on win32.
    if sys.platform == "win32":
        npx = "npx.cmd"
    else:
        npx = "npx"
    cli_base = [npx, "-y", "@shopify/cli@latest", "store"]

    # Resolve the config path per platform matching the shopify cli env-paths layout.
    # Use the Library/Preferences dir on macOS, the APPDATA shopify-cli-store-nodejs/Config dir on windows, and XDG_CONFIG_HOME else the default user config dir on linux.
    if sys.platform == "darwin":
        config_path = os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Preferences",
            "shopify-cli-store-nodejs",
            "config.json",
        )
    elif sys.platform == "win32":
        config_path = os.path.join(
            os.environ["APPDATA"],
            "shopify-cli-store-nodejs",
            "Config",
            "config.json",
        )
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            base_dir = xdg
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".config")
        config_path = os.path.join(base_dir, "shopify-cli-store-nodejs", "config.json")

    # Run login when store is given otherwise import when import is given.
    if args.store:
        # Default to the baked scope set then drop any scope listed in exclude.
        # The baked scope set is read_all_orders,write_app_proxy,read_assigned_fulfillment_orders,write_assigned_fulfillment_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders,read_third_party_fulfillment_orders,write_third_party_fulfillment_orders,read_cart_transforms,write_cart_transforms,read_checkout_branding_settings,write_checkout_branding_settings,read_checkout_and_accounts_configurations,write_checkout_and_accounts_configurations,read_content,write_content,read_online_store_pages,read_customer_events,write_pixels,read_customer_merge,write_customer_merge,read_customers,write_customers,read_delivery_customizations,write_delivery_customizations,read_discounts,write_discounts,read_draft_orders,write_draft_orders,read_files,write_files,read_fulfillments,write_fulfillments,read_gift_cards,write_gift_cards,read_inventory,write_inventory,read_legal_policies,write_legal_policies,read_locales,write_locales,read_locations,write_locations,read_markets,write_markets,read_marketing_events,write_marketing_events,read_metaobject_definitions,write_metaobject_definitions,read_metaobjects,write_metaobjects,read_online_store_navigation,write_online_store_navigation,read_order_edits,write_order_edits,read_orders,write_orders,read_payment_customizations,write_payment_customizations,read_payment_terms,write_payment_terms,read_price_rules,write_price_rules,write_privacy_settings,read_privacy_settings,read_products,write_products,read_reports,read_returns,write_returns,read_script_tags,write_script_tags,read_shipping,write_shipping,read_shopify_payments_disputes,read_shopify_payments_payouts,read_store_credit_accounts,read_store_credit_account_transactions,write_store_credit_account_transactions,read_themes,write_themes,read_translations,write_translations,read_validations,write_validations,read_publications,write_publications,read_product_listings,write_product_listings,read_inventory_shipments,read_inventory_transfers,read_cash_tracking.
        baked_scopes = "read_all_orders,write_app_proxy,read_assigned_fulfillment_orders,write_assigned_fulfillment_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders,read_third_party_fulfillment_orders,write_third_party_fulfillment_orders,read_cart_transforms,write_cart_transforms,read_checkout_branding_settings,write_checkout_branding_settings,read_checkout_and_accounts_configurations,write_checkout_and_accounts_configurations,read_content,write_content,read_online_store_pages,read_customer_events,write_pixels,read_customer_merge,write_customer_merge,read_customers,write_customers,read_delivery_customizations,write_delivery_customizations,read_discounts,write_discounts,read_draft_orders,write_draft_orders,read_files,write_files,read_fulfillments,write_fulfillments,read_gift_cards,write_gift_cards,read_inventory,write_inventory,read_legal_policies,write_legal_policies,read_locales,write_locales,read_locations,write_locations,read_markets,write_markets,read_marketing_events,write_marketing_events,read_metaobject_definitions,write_metaobject_definitions,read_metaobjects,write_metaobjects,read_online_store_navigation,write_online_store_navigation,read_order_edits,write_order_edits,read_orders,write_orders,read_payment_customizations,write_payment_customizations,read_payment_terms,write_payment_terms,read_price_rules,write_price_rules,write_privacy_settings,read_privacy_settings,read_products,write_products,read_reports,read_returns,write_returns,read_script_tags,write_script_tags,read_shipping,write_shipping,read_shopify_payments_disputes,read_shopify_payments_payouts,read_store_credit_accounts,read_store_credit_account_transactions,write_store_credit_account_transactions,read_themes,write_themes,read_translations,write_translations,read_validations,write_validations,read_publications,write_publications,read_product_listings,write_product_listings,read_inventory_shipments,read_inventory_transfers,read_cash_tracking"
        scope_list = baked_scopes.split(",")
        if args.exclude:
            excluded = args.exclude.split(",")
            kept_scopes = []
            for scope in scope_list:
                if scope not in excluded:
                    kept_scopes.append(scope)
            scope_list = kept_scopes
        resolved_scopes = ",".join(scope_list)

        # Auth is all or nothing so one refused scope fails the whole login.
        # On login run store auth -s domain --scopes with the resolved set to open the browser.
        cmd = cli_base + ["auth", "-s", domain, "--scopes", resolved_scopes]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.exit(result.returncode)

        # After a successful login read config.json then gzip -9 and base64 encode it as a single line and print that string.
        with open(config_path, "rb") as f:
            raw_bytes = f.read()
        compressed = gzip.compress(raw_bytes, compresslevel=9)
        encoded = base64.b64encode(compressed).decode("ascii")
        print(encoded)

    elif getattr(args, "import"):
        # On import base64 decode and gunzip the value then write config.json with owner only permissions.
        blob = getattr(args, "import")
        compressed = base64.b64decode(blob)
        raw_bytes = gzip.decompress(compressed)
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)
        fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, raw_bytes)
        finally:
            os.close(fd)
        os.chmod(config_path, 0o600)


if __name__ == "__main__":
    main()
