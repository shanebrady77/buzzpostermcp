"""
Ecommerce platform integrations for BuzzPoster
Supports: Shopify, WooCommerce, Etsy with universal product schema
"""
import os
import base64
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
from sqlalchemy import select

from ..auth.middleware import UserContext, check_rate_limit, check_feature_access, log_usage
from ..db.models import ConnectedStore


# =============================================================================
# Universal Product Schema
# =============================================================================

@dataclass
class Product:
    """Universal product schema that all platforms normalize to"""
    id: str
    platform: str  # "shopify" | "woocommerce" | "etsy"
    title: str
    description: str
    price: float
    currency: str
    compare_at_price: Optional[float] = None  # original price if on sale
    images: List[str] = None  # URLs
    url: str = ""
    variants: List[Dict] = None
    tags: List[str] = None
    category: str = ""
    inventory_quantity: Optional[int] = None
    created_at: str = ""
    updated_at: str = ""
    rating: Optional[float] = None
    review_count: Optional[int] = None

    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.variants is None:
            self.variants = []
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# Helper Functions
# =============================================================================

async def get_store(user_ctx: UserContext, platform: str, store_identifier: str) -> Optional[ConnectedStore]:
    """Get user's connected store for a specific platform"""
    if platform == "etsy":
        stmt = select(ConnectedStore).where(
            ConnectedStore.user_id == user_ctx.user.id,
            ConnectedStore.platform == platform,
            ConnectedStore.shop_id == store_identifier
        )
    else:
        stmt = select(ConnectedStore).where(
            ConnectedStore.user_id == user_ctx.user.id,
            ConnectedStore.platform == platform,
            ConnectedStore.store_domain == store_identifier
        )
    result = await user_ctx.db.execute(stmt)
    return result.scalar_one_or_none()


# =============================================================================
# Shopify Integration (GraphQL API)
# =============================================================================

async def buzzposter_connect_shopify(
    user_ctx: UserContext,
    store_domain: str,
    storefront_token: str
) -> Dict[str, Any]:
    """
    Connect a Shopify store

    Args:
        user_ctx: User context
        store_domain: Shopify store domain (e.g., mystore.myshopify.com)
        storefront_token: Storefront API access token

    Returns:
        Dict with success status or error
    """
    await check_rate_limit(user_ctx, "buzzposter_connect_shopify")
    await check_feature_access(user_ctx, "ecommerce")

    try:
        # Test connection
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://{store_domain}/api/2025-01/graphql.json",
                headers={"X-Shopify-Storefront-Access-Token": storefront_token},
                json={"query": "{ shop { name } }"}
            )
            response.raise_for_status()

        # Check if store already exists
        existing = await get_store(user_ctx, "shopify", store_domain)

        if existing:
            existing.credentials = {"storefront_token": storefront_token}
            existing.updated_at = datetime.utcnow()
        else:
            store = ConnectedStore(
                user_id=user_ctx.user.id,
                platform="shopify",
                store_domain=store_domain,
                credentials={"storefront_token": storefront_token}
            )
            user_ctx.db.add(store)

        await user_ctx.db.commit()
        await log_usage(user_ctx, "buzzposter_connect_shopify")

        return {
            "success": True,
            "platform": "shopify",
            "store_domain": store_domain,
            "message": "Shopify store connected successfully"
        }

    except Exception as e:
        return {"error": f"Failed to connect Shopify store: {str(e)}"}


async def buzzposter_shopify_products(
    user_ctx: UserContext,
    store_domain: str,
    limit: int = 20,
    collection: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get products from Shopify store

    Args:
        user_ctx: User context
        store_domain: Shopify store domain
        limit: Number of products to return
        collection: Optional collection handle to filter by

    Returns:
        Dict with normalized products or error
    """
    await check_rate_limit(user_ctx, "buzzposter_shopify_products")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "shopify", store_domain)
    if not store:
        return {"error": "Shopify store not connected. Use buzzposter_connect_shopify first."}

    query = f"""
    {{
      products(first: {min(limit, 250)}) {{
        edges {{
          node {{
            id
            title
            description
            handle
            productType
            tags
            createdAt
            updatedAt
            priceRange {{
              minVariantPrice {{ amount currencyCode }}
              maxVariantPrice {{ amount currencyCode }}
            }}
            compareAtPriceRange {{
              minVariantPrice {{ amount currencyCode }}
            }}
            images(first: 5) {{
              edges {{ node {{ url altText }} }}
            }}
            variants(first: 10) {{
              edges {{ node {{ id title price availableForSale quantityAvailable }} }}
            }}
          }}
        }}
      }}
    }}
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://{store_domain}/api/2025-01/graphql.json",
                headers={"X-Shopify-Storefront-Access-Token": store.credentials["storefront_token"]},
                json={"query": query}
            )
            response.raise_for_status()
            data = response.json()

        # Normalize to universal schema
        products = []
        for edge in data.get("data", {}).get("products", {}).get("edges", []):
            node = edge["node"]
            price_range = node["priceRange"]["minVariantPrice"]

            product = Product(
                id=node["id"],
                platform="shopify",
                title=node["title"],
                description=node.get("description", ""),
                price=float(price_range["amount"]),
                currency=price_range["currencyCode"],
                compare_at_price=float(node["compareAtPriceRange"]["minVariantPrice"]["amount"]) if node.get("compareAtPriceRange") else None,
                images=[img["node"]["url"] for img in node.get("images", {}).get("edges", [])],
                url=f"https://{store_domain}/products/{node['handle']}",
                variants=[{"id": v["node"]["id"], "title": v["node"]["title"], "price": v["node"]["price"]} for v in node.get("variants", {}).get("edges", [])],
                tags=node.get("tags", []),
                category=node.get("productType", ""),
                created_at=node.get("createdAt", ""),
                updated_at=node.get("updatedAt", "")
            )
            products.append(product.to_dict())

        await log_usage(user_ctx, "buzzposter_shopify_products")

        return {
            "platform": "shopify",
            "store_domain": store_domain,
            "products": products,
            "count": len(products)
        }

    except Exception as e:
        return {"error": f"Shopify API error: {str(e)}"}


async def buzzposter_shopify_collections(
    user_ctx: UserContext,
    store_domain: str
) -> Dict[str, Any]:
    """
    List Shopify collections

    Args:
        user_ctx: User context
        store_domain: Shopify store domain

    Returns:
        Dict with collections or error
    """
    await check_rate_limit(user_ctx, "buzzposter_shopify_collections")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "shopify", store_domain)
    if not store:
        return {"error": "Shopify store not connected. Use buzzposter_connect_shopify first."}

    query = """
    {
      collections(first: 50) {
        edges {
          node {
            id
            title
            handle
            description
            productsCount
          }
        }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://{store_domain}/api/2025-01/graphql.json",
                headers={"X-Shopify-Storefront-Access-Token": store.credentials["storefront_token"]},
                json={"query": query}
            )
            response.raise_for_status()
            data = response.json()

        collections = [
            {
                "id": edge["node"]["id"],
                "title": edge["node"]["title"],
                "handle": edge["node"]["handle"],
                "description": edge["node"].get("description", ""),
                "product_count": edge["node"].get("productsCount", 0)
            }
            for edge in data.get("data", {}).get("collections", {}).get("edges", [])
        ]

        await log_usage(user_ctx, "buzzposter_shopify_collections")

        return {
            "platform": "shopify",
            "store_domain": store_domain,
            "collections": collections,
            "count": len(collections)
        }

    except Exception as e:
        return {"error": f"Shopify API error: {str(e)}"}


async def buzzposter_shopify_bestsellers(
    user_ctx: UserContext,
    store_domain: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get bestselling products from Shopify

    Args:
        user_ctx: User context
        store_domain: Shopify store domain
        limit: Number of products to return

    Returns:
        Dict with normalized products or error
    """
    await check_rate_limit(user_ctx, "buzzposter_shopify_bestsellers")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "shopify", store_domain)
    if not store:
        return {"error": "Shopify store not connected. Use buzzposter_connect_shopify first."}

    query = f"""
    {{
      products(first: {min(limit, 250)}, sortKey: BEST_SELLING) {{
        edges {{
          node {{
            id
            title
            description
            handle
            productType
            tags
            priceRange {{
              minVariantPrice {{ amount currencyCode }}
            }}
            images(first: 3) {{
              edges {{ node {{ url }} }}
            }}
          }}
        }}
      }}
    }}
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://{store_domain}/api/2025-01/graphql.json",
                headers={"X-Shopify-Storefront-Access-Token": store.credentials["storefront_token"]},
                json={"query": query}
            )
            response.raise_for_status()
            data = response.json()

        products = []
        for edge in data.get("data", {}).get("products", {}).get("edges", []):
            node = edge["node"]
            price_range = node["priceRange"]["minVariantPrice"]

            product = Product(
                id=node["id"],
                platform="shopify",
                title=node["title"],
                description=node.get("description", ""),
                price=float(price_range["amount"]),
                currency=price_range["currencyCode"],
                images=[img["node"]["url"] for img in node.get("images", {}).get("edges", [])],
                url=f"https://{store_domain}/products/{node['handle']}",
                tags=node.get("tags", []),
                category=node.get("productType", "")
            )
            products.append(product.to_dict())

        await log_usage(user_ctx, "buzzposter_shopify_bestsellers")

        return {
            "platform": "shopify",
            "store_domain": store_domain,
            "products": products,
            "count": len(products)
        }

    except Exception as e:
        return {"error": f"Shopify API error: {str(e)}"}


# =============================================================================
# WooCommerce Integration (REST API v3)
# =============================================================================

async def buzzposter_connect_woocommerce(
    user_ctx: UserContext,
    site_url: str,
    consumer_key: str,
    consumer_secret: str
) -> Dict[str, Any]:
    """
    Connect a WooCommerce store

    Args:
        user_ctx: User context
        site_url: WooCommerce site URL
        consumer_key: WooCommerce API consumer key
        consumer_secret: WooCommerce API consumer secret

    Returns:
        Dict with success status or error
    """
    await check_rate_limit(user_ctx, "buzzposter_connect_woocommerce")
    await check_feature_access(user_ctx, "ecommerce")

    try:
        # Test connection
        auth_header = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{site_url.rstrip('/')}/wp-json/wc/v3/system_status",
                headers={"Authorization": f"Basic {auth_header}"}
            )
            response.raise_for_status()

        # Check if store already exists
        existing = await get_store(user_ctx, "woocommerce", site_url)

        if existing:
            existing.credentials = {"consumer_key": consumer_key, "consumer_secret": consumer_secret}
            existing.updated_at = datetime.utcnow()
        else:
            store = ConnectedStore(
                user_id=user_ctx.user.id,
                platform="woocommerce",
                store_domain=site_url,
                credentials={"consumer_key": consumer_key, "consumer_secret": consumer_secret}
            )
            user_ctx.db.add(store)

        await user_ctx.db.commit()
        await log_usage(user_ctx, "buzzposter_connect_woocommerce")

        return {
            "success": True,
            "platform": "woocommerce",
            "site_url": site_url,
            "message": "WooCommerce store connected successfully"
        }

    except Exception as e:
        return {"error": f"Failed to connect WooCommerce store: {str(e)}"}


async def buzzposter_woo_products(
    user_ctx: UserContext,
    site_url: str,
    limit: int = 20,
    category: Optional[int] = None,
    on_sale: bool = False,
    orderby: str = "date"
) -> Dict[str, Any]:
    """
    Get products from WooCommerce store

    Args:
        user_ctx: User context
        site_url: WooCommerce site URL
        limit: Number of products to return
        category: Optional category ID to filter by
        on_sale: Filter by on-sale products
        orderby: Sort order (date, popularity, rating, price)

    Returns:
        Dict with normalized products or error
    """
    await check_rate_limit(user_ctx, "buzzposter_woo_products")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "woocommerce", site_url)
    if not store:
        return {"error": "WooCommerce store not connected. Use buzzposter_connect_woocommerce first."}

    try:
        creds = store.credentials
        auth_header = base64.b64encode(f"{creds['consumer_key']}:{creds['consumer_secret']}".encode()).decode()

        params = {
            "per_page": min(limit, 100),
            "orderby": orderby,
            "order": "desc"
        }
        if category:
            params["category"] = category
        if on_sale:
            params["on_sale"] = "true"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{site_url.rstrip('/')}/wp-json/wc/v3/products",
                headers={"Authorization": f"Basic {auth_header}"},
                params=params
            )
            response.raise_for_status()
            data = response.json()

        # Normalize to universal schema
        products = []
        for item in data:
            product = Product(
                id=str(item["id"]),
                platform="woocommerce",
                title=item["name"],
                description=item.get("description", ""),
                price=float(item.get("price", 0)),
                currency="USD",  # WooCommerce doesn't return currency in product list
                compare_at_price=float(item["regular_price"]) if item.get("on_sale") and item.get("regular_price") else None,
                images=[img["src"] for img in item.get("images", [])],
                url=item["permalink"],
                variants=[],
                tags=[tag["name"] for tag in item.get("tags", [])],
                category=item["categories"][0]["name"] if item.get("categories") else "",
                inventory_quantity=item.get("stock_quantity"),
                rating=float(item.get("average_rating", 0)) if item.get("average_rating") else None,
                review_count=item.get("rating_count", 0)
            )
            products.append(product.to_dict())

        await log_usage(user_ctx, "buzzposter_woo_products")

        return {
            "platform": "woocommerce",
            "site_url": site_url,
            "products": products,
            "count": len(products)
        }

    except Exception as e:
        return {"error": f"WooCommerce API error: {str(e)}"}


async def buzzposter_woo_categories(
    user_ctx: UserContext,
    site_url: str
) -> Dict[str, Any]:
    """
    List WooCommerce product categories

    Args:
        user_ctx: User context
        site_url: WooCommerce site URL

    Returns:
        Dict with categories or error
    """
    await check_rate_limit(user_ctx, "buzzposter_woo_categories")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "woocommerce", site_url)
    if not store:
        return {"error": "WooCommerce store not connected. Use buzzposter_connect_woocommerce first."}

    try:
        creds = store.credentials
        auth_header = base64.b64encode(f"{creds['consumer_key']}:{creds['consumer_secret']}".encode()).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{site_url.rstrip('/')}/wp-json/wc/v3/products/categories",
                headers={"Authorization": f"Basic {auth_header}"},
                params={"per_page": 100}
            )
            response.raise_for_status()
            data = response.json()

        categories = [
            {
                "id": cat["id"],
                "name": cat["name"],
                "slug": cat["slug"],
                "description": cat.get("description", ""),
                "product_count": cat.get("count", 0)
            }
            for cat in data
        ]

        await log_usage(user_ctx, "buzzposter_woo_categories")

        return {
            "platform": "woocommerce",
            "site_url": site_url,
            "categories": categories,
            "count": len(categories)
        }

    except Exception as e:
        return {"error": f"WooCommerce API error: {str(e)}"}


async def buzzposter_woo_reviews(
    user_ctx: UserContext,
    site_url: str,
    product_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get product reviews from WooCommerce

    Args:
        user_ctx: User context
        site_url: WooCommerce site URL
        product_id: Optional specific product ID to get reviews for

    Returns:
        Dict with reviews or error
    """
    await check_rate_limit(user_ctx, "buzzposter_woo_reviews")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "woocommerce", site_url)
    if not store:
        return {"error": "WooCommerce store not connected. Use buzzposter_connect_woocommerce first."}

    try:
        creds = store.credentials
        auth_header = base64.b64encode(f"{creds['consumer_key']}:{creds['consumer_secret']}".encode()).decode()

        params = {"per_page": 50}
        if product_id:
            params["product"] = product_id

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{site_url.rstrip('/')}/wp-json/wc/v3/products/reviews",
                headers={"Authorization": f"Basic {auth_header}"},
                params=params
            )
            response.raise_for_status()
            data = response.json()

        reviews = [
            {
                "id": review["id"],
                "product_id": review["product_id"],
                "reviewer": review["reviewer"],
                "review": review["review"],
                "rating": review["rating"],
                "verified": review.get("verified", False),
                "date": review["date_created"]
            }
            for review in data
        ]

        await log_usage(user_ctx, "buzzposter_woo_reviews")

        return {
            "platform": "woocommerce",
            "site_url": site_url,
            "reviews": reviews,
            "count": len(reviews)
        }

    except Exception as e:
        return {"error": f"WooCommerce API error: {str(e)}"}


async def buzzposter_woo_bestsellers(
    user_ctx: UserContext,
    site_url: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Get bestselling products from WooCommerce

    Args:
        user_ctx: User context
        site_url: WooCommerce site URL
        limit: Number of products to return

    Returns:
        Dict with normalized products or error
    """
    # Reuse buzzposter_woo_products with orderby=popularity
    return await buzzposter_woo_products(user_ctx, site_url, limit=limit, orderby="popularity")


# =============================================================================
# Etsy Integration (OAuth 2.0)
# =============================================================================

async def _refresh_etsy_token(store: ConnectedStore) -> Dict[str, str]:
    """Refresh Etsy access token using refresh token"""
    creds = store.credentials
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.etsy.com/v3/public/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": creds["keystring"],
                "refresh_token": creds["refresh_token"]
            }
        )
        response.raise_for_status()
        data = response.json()

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"]
    }


async def buzzposter_connect_etsy(
    user_ctx: UserContext,
    api_keystring: str,
    access_token: str,
    refresh_token: str,
    shop_id: str
) -> Dict[str, Any]:
    """
    Connect an Etsy shop

    Args:
        user_ctx: User context
        api_keystring: Etsy API keystring
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        shop_id: Etsy shop ID

    Returns:
        Dict with success status or error
    """
    await check_rate_limit(user_ctx, "buzzposter_connect_etsy")
    await check_feature_access(user_ctx, "ecommerce")

    try:
        # Test connection
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.etsy.com/v3/application/shops/{shop_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "x-api-key": api_keystring
                }
            )
            response.raise_for_status()

        # Check if shop already exists
        existing = await get_store(user_ctx, "etsy", shop_id)

        if existing:
            existing.credentials = {
                "keystring": api_keystring,
                "access_token": access_token,
                "refresh_token": refresh_token
            }
            existing.updated_at = datetime.utcnow()
        else:
            store = ConnectedStore(
                user_id=user_ctx.user.id,
                platform="etsy",
                shop_id=shop_id,
                credentials={
                    "keystring": api_keystring,
                    "access_token": access_token,
                    "refresh_token": refresh_token
                }
            )
            user_ctx.db.add(store)

        await user_ctx.db.commit()
        await log_usage(user_ctx, "buzzposter_connect_etsy")

        return {
            "success": True,
            "platform": "etsy",
            "shop_id": shop_id,
            "message": "Etsy shop connected successfully"
        }

    except Exception as e:
        return {"error": f"Failed to connect Etsy shop: {str(e)}"}


async def buzzposter_etsy_listings(
    user_ctx: UserContext,
    shop_id: str,
    limit: int = 25,
    sort_on: str = "created",
    state: str = "active"
) -> Dict[str, Any]:
    """
    Get listings from Etsy shop

    Args:
        user_ctx: User context
        shop_id: Etsy shop ID
        limit: Number of listings to return
        sort_on: Sort field (created, price, score)
        state: Listing state (active, inactive, sold_out, draft)

    Returns:
        Dict with normalized products or error
    """
    await check_rate_limit(user_ctx, "buzzposter_etsy_listings")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "etsy", shop_id)
    if not store:
        return {"error": "Etsy shop not connected. Use buzzposter_connect_etsy first."}

    try:
        creds = store.credentials

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.etsy.com/v3/application/shops/{shop_id}/listings/{state}",
                headers={
                    "Authorization": f"Bearer {creds['access_token']}",
                    "x-api-key": creds["keystring"]
                },
                params={
                    "limit": min(limit, 100),
                    "sort_on": sort_on
                }
            )

            # Handle token expiry
            if response.status_code == 401:
                new_tokens = await _refresh_etsy_token(store)
                store.credentials.update(new_tokens)
                await user_ctx.db.commit()

                # Retry request
                response = await client.get(
                    f"https://api.etsy.com/v3/application/shops/{shop_id}/listings/{state}",
                    headers={
                        "Authorization": f"Bearer {new_tokens['access_token']}",
                        "x-api-key": creds["keystring"]
                    },
                    params={"limit": min(limit, 100), "sort_on": sort_on}
                )

            response.raise_for_status()
            data = response.json()

        # Normalize to universal schema
        products = []
        for item in data.get("results", []):
            price = item["price"]
            price_amount = float(price["amount"]) / float(price["divisor"])

            product = Product(
                id=str(item["listing_id"]),
                platform="etsy",
                title=item["title"],
                description=item.get("description", ""),
                price=price_amount,
                currency=price["currency_code"],
                images=[],  # Images require separate API call
                url=item["url"],
                tags=item.get("tags", []),
                inventory_quantity=item.get("quantity"),
                created_at=str(item.get("creation_timestamp", "")),
                updated_at=str(item.get("last_modified_timestamp", ""))
            )
            products.append(product.to_dict())

        await log_usage(user_ctx, "buzzposter_etsy_listings")

        return {
            "platform": "etsy",
            "shop_id": shop_id,
            "products": products,
            "count": len(products)
        }

    except Exception as e:
        return {"error": f"Etsy API error: {str(e)}"}


async def buzzposter_etsy_listing_images(
    user_ctx: UserContext,
    listing_id: str
) -> Dict[str, Any]:
    """
    Get images for an Etsy listing

    Args:
        user_ctx: User context
        listing_id: Etsy listing ID

    Returns:
        Dict with image URLs or error
    """
    await check_rate_limit(user_ctx, "buzzposter_etsy_listing_images")
    await check_feature_access(user_ctx, "ecommerce")

    # Need to find the store for this listing
    stmt = select(ConnectedStore).where(
        ConnectedStore.user_id == user_ctx.user.id,
        ConnectedStore.platform == "etsy"
    )
    result = await user_ctx.db.execute(stmt)
    store = result.scalar_one_or_none()

    if not store:
        return {"error": "No Etsy shop connected. Use buzzposter_connect_etsy first."}

    try:
        creds = store.credentials

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.etsy.com/v3/application/listings/{listing_id}/images",
                headers={
                    "Authorization": f"Bearer {creds['access_token']}",
                    "x-api-key": creds["keystring"]
                }
            )
            response.raise_for_status()
            data = response.json()

        images = [
            {
                "url_570xN": img["url_570xN"],
                "url_fullxfull": img["url_fullxfull"]
            }
            for img in data.get("results", [])
        ]

        await log_usage(user_ctx, "buzzposter_etsy_listing_images")

        return {
            "platform": "etsy",
            "listing_id": listing_id,
            "images": images,
            "count": len(images)
        }

    except Exception as e:
        return {"error": f"Etsy API error: {str(e)}"}


async def buzzposter_etsy_shop_reviews(
    user_ctx: UserContext,
    shop_id: str,
    limit: int = 25
) -> Dict[str, Any]:
    """
    Get reviews for an Etsy shop

    Args:
        user_ctx: User context
        shop_id: Etsy shop ID
        limit: Number of reviews to return

    Returns:
        Dict with reviews or error
    """
    await check_rate_limit(user_ctx, "buzzposter_etsy_shop_reviews")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "etsy", shop_id)
    if not store:
        return {"error": "Etsy shop not connected. Use buzzposter_connect_etsy first."}

    try:
        creds = store.credentials

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.etsy.com/v3/application/shops/{shop_id}/reviews",
                headers={
                    "Authorization": f"Bearer {creds['access_token']}",
                    "x-api-key": creds["keystring"]
                },
                params={"limit": min(limit, 100)}
            )
            response.raise_for_status()
            data = response.json()

        reviews = [
            {
                "id": review["shop_id"],
                "rating": review["rating"],
                "review": review.get("review", ""),
                "buyer": review.get("buyer_display_name", ""),
                "date": str(review.get("create_timestamp", ""))
            }
            for review in data.get("results", [])
        ]

        await log_usage(user_ctx, "buzzposter_etsy_shop_reviews")

        return {
            "platform": "etsy",
            "shop_id": shop_id,
            "reviews": reviews,
            "count": len(reviews)
        }

    except Exception as e:
        return {"error": f"Etsy API error: {str(e)}"}


async def buzzposter_etsy_shop_sections(
    user_ctx: UserContext,
    shop_id: str
) -> Dict[str, Any]:
    """
    Get sections (categories) for an Etsy shop

    Args:
        user_ctx: User context
        shop_id: Etsy shop ID

    Returns:
        Dict with sections or error
    """
    await check_rate_limit(user_ctx, "buzzposter_etsy_shop_sections")
    await check_feature_access(user_ctx, "ecommerce")

    store = await get_store(user_ctx, "etsy", shop_id)
    if not store:
        return {"error": "Etsy shop not connected. Use buzzposter_connect_etsy first."}

    try:
        creds = store.credentials

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.etsy.com/v3/application/shops/{shop_id}/sections",
                headers={
                    "Authorization": f"Bearer {creds['access_token']}",
                    "x-api-key": creds["keystring"]
                }
            )
            response.raise_for_status()
            data = response.json()

        sections = [
            {
                "id": section["shop_section_id"],
                "title": section["title"],
                "listing_count": section.get("active_listing_count", 0)
            }
            for section in data.get("results", [])
        ]

        await log_usage(user_ctx, "buzzposter_etsy_shop_sections")

        return {
            "platform": "etsy",
            "shop_id": shop_id,
            "sections": sections,
            "count": len(sections)
        }

    except Exception as e:
        return {"error": f"Etsy API error: {str(e)}"}


# =============================================================================
# Universal Wrapper Tools
# =============================================================================

async def buzzposter_get_products(
    user_ctx: UserContext,
    platform: str,
    store_id: str,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Universal product getter - routes to correct platform

    Args:
        user_ctx: User context
        platform: Platform name (shopify, woocommerce, etsy)
        store_id: Store domain or shop ID
        limit: Number of products to return

    Returns:
        Dict with normalized products or error
    """
    if platform == "shopify":
        return await buzzposter_shopify_products(user_ctx, store_id, limit)
    elif platform == "woocommerce":
        return await buzzposter_woo_products(user_ctx, store_id, limit)
    elif platform == "etsy":
        return await buzzposter_etsy_listings(user_ctx, store_id, limit)
    else:
        return {"error": f"Unsupported platform: {platform}. Use shopify, woocommerce, or etsy."}


async def buzzposter_get_bestsellers(
    user_ctx: UserContext,
    platform: str,
    store_id: str,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Universal bestsellers getter - routes to correct platform

    Args:
        user_ctx: User context
        platform: Platform name (shopify, woocommerce, etsy)
        store_id: Store domain or shop ID
        limit: Number of products to return

    Returns:
        Dict with normalized products or error
    """
    if platform == "shopify":
        return await buzzposter_shopify_bestsellers(user_ctx, store_id, limit)
    elif platform == "woocommerce":
        return await buzzposter_woo_bestsellers(user_ctx, store_id, limit)
    elif platform == "etsy":
        return await buzzposter_etsy_listings(user_ctx, store_id, limit, sort_on="score")
    else:
        return {"error": f"Unsupported platform: {platform}. Use shopify, woocommerce, or etsy."}


async def buzzposter_get_reviews(
    user_ctx: UserContext,
    platform: str,
    store_id: str,
    product_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Universal reviews getter - routes to correct platform
    Note: Shopify doesn't expose review text via Storefront API

    Args:
        user_ctx: User context
        platform: Platform name (woocommerce, etsy)
        store_id: Store domain or shop ID
        product_id: Optional specific product ID

    Returns:
        Dict with reviews or error
    """
    if platform == "shopify":
        return {"error": "Shopify Storefront API doesn't expose review text. Use WooCommerce or Etsy."}
    elif platform == "woocommerce":
        return await buzzposter_woo_reviews(user_ctx, store_id, int(product_id) if product_id else None)
    elif platform == "etsy":
        return await buzzposter_etsy_shop_reviews(user_ctx, store_id)
    else:
        return {"error": f"Unsupported platform: {platform}. Use woocommerce or etsy."}


async def buzzposter_get_on_sale(
    user_ctx: UserContext,
    platform: str,
    store_id: str
) -> Dict[str, Any]:
    """
    Universal sale items getter - routes to correct platform

    Args:
        user_ctx: User context
        platform: Platform name (shopify, woocommerce, etsy)
        store_id: Store domain or shop ID

    Returns:
        Dict with normalized products or error
    """
    if platform == "shopify":
        # Shopify doesn't have a direct on_sale filter, would need to check compareAtPrice in results
        return {"error": "Shopify on-sale filtering not directly supported. Use woocommerce or filter products client-side."}
    elif platform == "woocommerce":
        return await buzzposter_woo_products(user_ctx, store_id, limit=20, on_sale=True)
    elif platform == "etsy":
        return {"error": "Etsy doesn't expose on-sale status via API. Use etsy_listings and check prices."}
    else:
        return {"error": f"Unsupported platform: {platform}. Use woocommerce."}


async def buzzposter_get_collections(
    user_ctx: UserContext,
    platform: str,
    store_id: str
) -> Dict[str, Any]:
    """
    Universal collections/categories getter - routes to correct platform

    Args:
        user_ctx: User context
        platform: Platform name (shopify, woocommerce, etsy)
        store_id: Store domain or shop ID

    Returns:
        Dict with collections/categories or error
    """
    if platform == "shopify":
        return await buzzposter_shopify_collections(user_ctx, store_id)
    elif platform == "woocommerce":
        return await buzzposter_woo_categories(user_ctx, store_id)
    elif platform == "etsy":
        return await buzzposter_etsy_shop_sections(user_ctx, store_id)
    else:
        return {"error": f"Unsupported platform: {platform}. Use shopify, woocommerce, or etsy."}
