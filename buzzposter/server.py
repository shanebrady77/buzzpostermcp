"""
BuzzPoster Remote MCP Server
Main FastAPI application with SSE transport and REST endpoints
"""
import os
import secrets
from typing import Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

from .db import (
    User, init_db, get_db, AsyncSessionLocal
)
from .auth import (
    get_user_from_request,
    validate_api_key,
    get_authorization_url,
    exchange_code_for_token,
    save_tokens,
    check_connection_status,
    create_checkout_session,
    handle_checkout_completed,
    verify_webhook_signature,
)
from .tools import (
    buzzposter_get_feed,
    buzzposter_get_topic,
    buzzposter_search_news,
    buzzposter_add_feed,
    buzzposter_remove_feed,
    buzzposter_list_feeds,
    buzzposter_set_profile,
    buzzposter_my_feed,
    buzzposter_list_social_accounts,
    buzzposter_post,
    buzzposter_cross_post,
    buzzposter_schedule_post,
    buzzposter_list_posts,
    buzzposter_post_analytics,
)


# Initialize database on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    await init_db()
    print("Database initialized")
    yield


# Create FastAPI app
app = FastAPI(
    title="BuzzPoster MCP Server",
    description="Remote MCP server for content sourcing and social media posting",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create MCP server instance
mcp_server = Server("buzzposter")


# =============================================================================
# MCP TOOL DEFINITIONS
# =============================================================================

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools"""
    return [
        # Content sourcing tools
        Tool(
            name="buzzposter_get_feed",
            description="Fetch and parse any RSS feed. Returns articles with title, link, description, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_url": {
                        "type": "string",
                        "description": "URL of the RSS feed to fetch"
                    }
                },
                "required": ["feed_url"]
            }
        ),
        Tool(
            name="buzzposter_get_topic",
            description="Get news articles from built-in topic feeds (tech, business, science). Free tier limited to these 3 topics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic category (tech, business, science)",
                        "enum": ["tech", "business", "science"]
                    }
                },
                "required": ["topic"]
            }
        ),
        Tool(
            name="buzzposter_search_news",
            description="Search news articles using NewsAPI. Requires Pro or Business tier. Search by keywords and get recent news.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords"
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code (default: en)",
                        "default": "en"
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order",
                        "enum": ["publishedAt", "relevancy", "popularity"],
                        "default": "publishedAt"
                    }
                },
                "required": ["query"]
            }
        ),
        # Feed management tools
        Tool(
            name="buzzposter_add_feed",
            description="Add a custom RSS feed to your collection. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_url": {
                        "type": "string",
                        "description": "URL of the RSS feed"
                    },
                    "feed_name": {
                        "type": "string",
                        "description": "Display name for the feed"
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional topic category"
                    }
                },
                "required": ["feed_url", "feed_name"]
            }
        ),
        Tool(
            name="buzzposter_remove_feed",
            description="Remove a custom feed from your collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "feed_id": {
                        "type": "integer",
                        "description": "ID of the feed to remove"
                    }
                },
                "required": ["feed_id"]
            }
        ),
        Tool(
            name="buzzposter_list_feeds",
            description="List all custom feeds in your collection.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # Profile tools
        Tool(
            name="buzzposter_set_profile",
            description="Set your content profile (topics, location, description) for personalized feed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of topics of interest"
                    },
                    "location": {
                        "type": "string",
                        "description": "Your location"
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of content preferences"
                    }
                }
            }
        ),
        Tool(
            name="buzzposter_my_feed",
            description="Get personalized feed based on your profile and custom feeds.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        # Social posting tools
        Tool(
            name="buzzposter_list_social_accounts",
            description="List all connected social media accounts. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="buzzposter_post",
            description="Post content to a specific social media platform. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "Platform name (twitter, linkedin, facebook, etc.)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to post"
                    },
                    "media_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of media URLs to attach"
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional specific account ID"
                    }
                },
                "required": ["platform", "content"]
            }
        ),
        Tool(
            name="buzzposter_cross_post",
            description="Post same content to multiple platforms at once. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "platforms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of platform names"
                    },
                    "content": {
                        "type": "string",
                        "description": "Base text content to post"
                    },
                    "media_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of media URLs"
                    },
                    "customize_per_platform": {
                        "type": "object",
                        "description": "Optional platform-specific content overrides"
                    }
                },
                "required": ["platforms", "content"]
            }
        ),
        Tool(
            name="buzzposter_schedule_post",
            description="Schedule a post for later. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "Platform name"
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to post"
                    },
                    "scheduled_at": {
                        "type": "string",
                        "description": "ISO 8601 timestamp for when to post"
                    },
                    "media_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of media URLs"
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional specific account ID"
                    }
                },
                "required": ["platform", "content", "scheduled_at"]
            }
        ),
        Tool(
            name="buzzposter_list_posts",
            description="List scheduled, published, or draft posts. Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status (scheduled, published, draft, failed)",
                        "enum": ["scheduled", "published", "draft", "failed"]
                    },
                    "platform": {
                        "type": "string",
                        "description": "Filter by platform"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of posts to return (default 20)",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="buzzposter_post_analytics",
            description="Get engagement analytics for a post (likes, shares, comments, etc.). Requires Pro or Business tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "ID of the post"
                    }
                },
                "required": ["post_id"]
            }
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict, request: Request) -> list[TextContent]:
    """Handle MCP tool calls"""

    # Get database session
    async with AsyncSessionLocal() as db:
        # Validate API key and get user context
        user_ctx = await get_user_from_request(request, db)

        # Route to appropriate tool handler
        tool_map = {
            "buzzposter_get_feed": lambda: buzzposter_get_feed(user_ctx, **arguments),
            "buzzposter_get_topic": lambda: buzzposter_get_topic(user_ctx, **arguments),
            "buzzposter_search_news": lambda: buzzposter_search_news(user_ctx, **arguments),
            "buzzposter_add_feed": lambda: buzzposter_add_feed(user_ctx, **arguments),
            "buzzposter_remove_feed": lambda: buzzposter_remove_feed(user_ctx, **arguments),
            "buzzposter_list_feeds": lambda: buzzposter_list_feeds(user_ctx),
            "buzzposter_set_profile": lambda: buzzposter_set_profile(user_ctx, **arguments),
            "buzzposter_my_feed": lambda: buzzposter_my_feed(user_ctx),
            "buzzposter_list_social_accounts": lambda: buzzposter_list_social_accounts(user_ctx),
            "buzzposter_post": lambda: buzzposter_post(user_ctx, **arguments),
            "buzzposter_cross_post": lambda: buzzposter_cross_post(user_ctx, **arguments),
            "buzzposter_schedule_post": lambda: buzzposter_schedule_post(user_ctx, **arguments),
            "buzzposter_list_posts": lambda: buzzposter_list_posts(user_ctx, **arguments),
            "buzzposter_post_analytics": lambda: buzzposter_post_analytics(user_ctx, **arguments),
        }

        handler = tool_map.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")

        result = await handler()

        # Convert result to string for MCP response
        import json
        result_text = json.dumps(result, indent=2)

        return [TextContent(type="text", text=result_text)]


# =============================================================================
# MCP SSE ENDPOINT
# =============================================================================

@app.get("/mcp/sse")
@app.post("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """MCP Server-Sent Events endpoint"""
    async with SseServerTransport("/mcp/message") as transport:
        # Pass request to transport for auth header access
        transport.request = request
        await mcp_server.run(
            transport.read_stream,
            transport.write_stream,
            mcp_server.create_initialization_options()
        )


@app.post("/mcp/message")
async def mcp_message_endpoint(request: Request):
    """Handle MCP messages (used by SSE transport)"""
    # This is handled by the SSE transport
    return {"status": "ok"}


# =============================================================================
# REST ENDPOINTS - SIGNUP & ONBOARDING
# =============================================================================

@app.post("/signup")
async def signup(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Create new free-tier user account
    Body: {"email": "user@example.com"}
    Returns: {"api_key": "bp_xxx", "tier": "free"}
    """
    body = await request.json()
    email = body.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Email required")

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Generate API key
    api_key = f"bp_{secrets.token_urlsafe(32)}"

    # Create user
    user = User(
        email=email,
        buzzposter_api_key=api_key,
        tier="free"
    )
    db.add(user)
    await db.commit()

    return {
        "api_key": api_key,
        "tier": "free",
        "email": email,
        "message": "Account created successfully"
    }


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding(
    api_key: str = Query(..., description="BuzzPoster API key"),
    upgraded: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Onboarding page showing API key and setup instructions"""

    # Validate API key
    try:
        user_ctx = await validate_api_key(api_key, db)
    except HTTPException:
        return HTMLResponse("<h1>Invalid API Key</h1><p>Please check your API key and try again.</p>", status_code=401)

    # Get connection status
    connection_status = await check_connection_status(db, api_key)

    # Build social accounts display
    social_accounts_html = ""
    if connection_status["connected"]:
        accounts = connection_status.get("accounts", {})
        if isinstance(accounts, dict) and "data" in accounts:
            accounts_list = accounts["data"]
        elif isinstance(accounts, list):
            accounts_list = accounts
        else:
            accounts_list = []

        if accounts_list:
            social_accounts_html = "<ul style='list-style: none; padding: 0;'>"
            for account in accounts_list:
                platform = account.get("platform", "Unknown")
                username = account.get("username", account.get("name", ""))
                social_accounts_html += f"<li style='margin: 5px 0;'>✅ {platform}: @{username}</li>"
            social_accounts_html += "</ul>"
        else:
            social_accounts_html = "<p>No accounts connected yet. Click the button below to connect.</p>"
    else:
        social_accounts_html = "<p>Not connected. Click the button below to connect your social accounts.</p>"

    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    config_snippet = f'''{{
    "mcpServers": {{
        "buzzposter": {{
            "type": "url",
            "url": "{base_url}/mcp/sse",
            "headers": {{
                "Authorization": "Bearer {api_key}"
            }}
        }}
    }}
}}'''

    upgrade_message = ""
    if upgraded:
        upgrade_message = '<div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 5px; margin-bottom: 20px;">✅ Successfully upgraded! Your new features are now active.</div>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>BuzzPoster - Onboarding</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                line-height: 1.6;
            }}
            h1 {{ color: #333; }}
            h2 {{ color: #666; margin-top: 30px; }}
            .api-key {{
                background: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                font-family: monospace;
                word-break: break-all;
                margin: 15px 0;
            }}
            pre {{
                background: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
            .button {{
                display: inline-block;
                background: #007bff;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px 10px 10px 0;
            }}
            .button:hover {{ background: #0056b3; }}
            .tier {{
                background: #e7f3ff;
                padding: 10px;
                border-radius: 5px;
                display: inline-block;
                font-weight: bold;
            }}
            .status {{
                margin: 20px 0;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <h1>🎉 Welcome to BuzzPoster!</h1>
        {upgrade_message}

        <h2>📊 Your Account</h2>
        <p><strong>Email:</strong> {user_ctx.user.email}</p>
        <p><strong>Tier:</strong> <span class="tier">{user_ctx.tier.upper()}</span></p>

        <h2>🔑 Your API Key</h2>
        <p>Keep this secret! You'll need it to configure Claude Desktop.</p>
        <div class="api-key">{api_key}</div>

        <h2>🔗 Connect Social Accounts</h2>
        <div class="status">
            <strong>Connection Status:</strong><br>
            {social_accounts_html}
        </div>
        <a href="/auth/late/connect?api_key={api_key}" class="button">Connect Social Accounts</a>

        <h2>⚙️ Claude Desktop Configuration</h2>
        <p>Add this to your Claude Desktop configuration file:</p>
        <pre>{config_snippet}</pre>

        <h2>🚀 Next Steps</h2>
        <ol>
            <li>Connect your social accounts using the button above</li>
            <li>Copy the configuration above to your Claude Desktop config</li>
            <li>Restart Claude Desktop</li>
            <li>Start using BuzzPoster tools in your conversations!</li>
        </ol>

        <h2>💰 Upgrade Your Plan</h2>
        <a href="/billing?api_key={api_key}" class="button">View Billing & Upgrade</a>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


# =============================================================================
# REST ENDPOINTS - LATE.DEV OAUTH
# =============================================================================

@app.get("/auth/late/connect")
async def late_connect(api_key: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Initiate Late.dev OAuth flow"""

    # Validate API key exists
    try:
        await validate_api_key(api_key, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Generate authorization URL
    auth_url = get_authorization_url(api_key)

    return RedirectResponse(url=auth_url)


@app.get("/auth/late/callback")
async def late_callback(
    code: str = Query(...),
    state: str = Query(...),  # This is the API key
    db: AsyncSession = Depends(get_db)
):
    """Handle Late.dev OAuth callback"""

    api_key = state

    # Validate API key
    try:
        await validate_api_key(api_key, db)
    except HTTPException:
        return HTMLResponse("<h1>Invalid API Key</h1>", status_code=401)

    # Exchange code for tokens
    try:
        tokens = await exchange_code_for_token(code)
        await save_tokens(
            db,
            api_key,
            tokens["access_token"],
            tokens["refresh_token"]
        )
    except Exception as e:
        return HTMLResponse(f"<h1>OAuth Error</h1><p>{str(e)}</p>", status_code=500)

    # Redirect to onboarding
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return RedirectResponse(url=f"{base_url}/onboarding?api_key={api_key}")


@app.get("/auth/late/status")
async def late_status(
    api_key: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Check Late.dev connection status"""

    # Validate API key
    try:
        await validate_api_key(api_key, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = await check_connection_status(db, api_key)
    return JSONResponse(content=status)


# =============================================================================
# REST ENDPOINTS - STRIPE BILLING
# =============================================================================

@app.post("/checkout")
async def checkout(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Create Stripe checkout session
    Body: {"api_key": "bp_xxx", "tier": "pro"}
    Returns: {"checkout_url": "https://..."}
    """
    body = await request.json()
    api_key = body.get("api_key")
    tier = body.get("tier")

    if not api_key or not tier:
        raise HTTPException(status_code=400, detail="api_key and tier required")

    checkout_url = await create_checkout_session(db, api_key, tier)

    return {"checkout_url": checkout_url}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhooks"""

    # Verify webhook signature
    event = await verify_webhook_signature(request)

    # Handle checkout.session.completed event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await handle_checkout_completed(db, session)

    return {"status": "success"}


@app.get("/billing", response_class=HTMLResponse)
async def billing(
    api_key: str = Query(...),
    canceled: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Billing page showing current tier and upgrade options"""

    # Validate API key
    try:
        user_ctx = await validate_api_key(api_key, db)
    except HTTPException:
        return HTMLResponse("<h1>Invalid API Key</h1>", status_code=401)

    current_tier = user_ctx.tier

    cancel_message = ""
    if canceled:
        cancel_message = '<div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin-bottom: 20px;">Payment canceled. You can upgrade anytime.</div>'

    # Prepare button HTML for each tier
    free_button = '<button class="button" disabled>Current Plan</button>'
    pro_button = '<button class="button" disabled>Current Plan</button>' if current_tier == 'pro' else '<button class="button" onclick="upgradeTo(\'pro\')">Upgrade to Pro</button>'
    business_button = '<button class="button" disabled>Current Plan</button>' if current_tier == 'business' else '<button class="button" onclick="upgradeTo(\'business\')">Upgrade to Business</button>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>BuzzPoster - Billing</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                max-width: 900px;
                margin: 50px auto;
                padding: 20px;
            }}
            h1 {{ color: #333; }}
            .current-tier {{
                background: #e7f3ff;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }}
            .plans {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .plan {{
                border: 2px solid #ddd;
                border-radius: 10px;
                padding: 20px;
                text-align: center;
            }}
            .plan.current {{
                border-color: #007bff;
                background: #f0f7ff;
            }}
            .plan h3 {{
                margin-top: 0;
                color: #333;
            }}
            .price {{
                font-size: 2em;
                font-weight: bold;
                color: #007bff;
                margin: 15px 0;
            }}
            .features {{
                list-style: none;
                padding: 0;
                margin: 20px 0;
                text-align: left;
            }}
            .features li {{
                margin: 8px 0;
                padding-left: 25px;
                position: relative;
            }}
            .features li:before {{
                content: "✓";
                position: absolute;
                left: 0;
                color: #28a745;
                font-weight: bold;
            }}
            .button {{
                display: inline-block;
                background: #007bff;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 5px;
                border: none;
                cursor: pointer;
                font-size: 16px;
            }}
            .button:hover {{ background: #0056b3; }}
            .button:disabled {{
                background: #ccc;
                cursor: not-allowed;
            }}
        </style>
    </head>
    <body>
        <h1>💰 Billing & Plans</h1>
        {cancel_message}

        <div class="current-tier">
            <h2>Current Plan: {current_tier.upper()}</h2>
            <p>Email: {user_ctx.user.email}</p>
        </div>

        <div class="plans">
            <div class="plan {'current' if current_tier == 'free' else ''}">
                <h3>Free</h3>
                <div class="price">$0</div>
                <ul class="features">
                    <li>50 tool calls/day</li>
                    <li>3 built-in topics</li>
                    <li>Basic RSS feeds</li>
                    <li>No social posting</li>
                </ul>
                {free_button}
            </div>

            <div class="plan {'current' if current_tier == 'pro' else ''}">
                <h3>Pro</h3>
                <div class="price">$49<span style="font-size: 0.5em;">/month</span></div>
                <ul class="features">
                    <li>500 tool calls/day</li>
                    <li>Unlimited topics</li>
                    <li>Custom RSS feeds</li>
                    <li>NewsAPI search</li>
                    <li>Social media posting</li>
                    <li>Post scheduling</li>
                    <li>Analytics</li>
                </ul>
                {pro_button}
            </div>

            <div class="plan {'current' if current_tier == 'business' else ''}">
                <h3>Business</h3>
                <div class="price">$149<span style="font-size: 0.5em;">/month</span></div>
                <ul class="features">
                    <li>Unlimited tool calls</li>
                    <li>Everything in Pro</li>
                    <li>Priority support</li>
                    <li>Advanced analytics</li>
                    <li>Team features (soon)</li>
                </ul>
                {business_button}
            </div>
        </div>

        <p style="text-align: center; margin-top: 30px;">
            <a href="/onboarding?api_key={api_key}">← Back to Dashboard</a>
        </p>

        <script>
            async function upgradeTo(tier) {{
                try {{
                    const response = await fetch('/checkout', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            api_key: '{api_key}',
                            tier: tier
                        }})
                    }});
                    const data = await response.json();
                    if (data.checkout_url) {{
                        window.location.href = data.checkout_url;
                    }}
                }} catch (error) {{
                    alert('Error creating checkout session. Please try again.');
                }}
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "name": "BuzzPoster MCP Server",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "mcp": "/mcp/sse",
            "signup": "/signup",
            "onboarding": "/onboarding",
            "billing": "/billing",
            "oauth": "/auth/late/connect",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


# =============================================================================
# RUN SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("buzzposter.server:app", host="0.0.0.0", port=port, reload=False)
