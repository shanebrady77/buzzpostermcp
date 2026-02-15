# BuzzPoster MCP Server

## Overview

BuzzPoster is a remote MCP (Model Context Protocol) server built with FastAPI that combines content sourcing with social media posting. It provides MCP tools that Claude Desktop and other MCP clients can connect to via SSE (Server-Sent Events) transport. The server has two core capabilities:

1. **Content Sourcing** — Fetching RSS feeds, curated topic-based news (tech, business, science), and keyword-based news search via NewsAPI
2. **Social Media Posting** — Multi-platform social media management (posting, cross-posting, scheduling, analytics) via Late.dev's API

The server implements a tiered billing model (Free/Pro/Business) with Stripe integration, API key authentication, and rate limiting.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Web Framework & MCP Transport
- **FastAPI** serves as the main web framework, handling both REST endpoints and MCP SSE transport
- The MCP SDK (`mcp` package v1.1.2) provides the Server-Sent Events transport layer for real-time tool communication
- Entry point is `buzzposter/server.py` which sets up the FastAPI app, registers MCP tools, and defines REST routes for auth flows

### Project Structure
The codebase follows a modular architecture under the `buzzposter/` package:
- **`server.py`** — Main FastAPI app, MCP server setup, SSE endpoint, REST routes for OAuth and Stripe
- **`tools/`** — MCP tool implementations, organized by domain:
  - `feeds.py` — RSS parsing (feedparser + BeautifulSoup) and NewsAPI integration
  - `profile.py` — User feed management and personalization
  - `social.py` — Late.dev API wrapper for social media operations
  - `media.py` — Cloudflare R2 media upload/management via boto3 S3-compatible client
  - `integrations.py` — Newsletter/CMS integrations (Beehiiv, Kit, Mailchimp, WordPress, Ghost, Webflow)
- **`auth/`** — Authentication and billing:
  - `middleware.py` — API key validation (`bp_` prefix), rate limiting, feature access control, usage logging
  - `late_oauth.py` — OAuth 2.0 flow with Late.dev for social media account connection
  - `stripe.py` — Stripe checkout session creation and webhook handling for tier upgrades
- **`db/`** — Database layer with SQLAlchemy async ORM

### Database
- **PostgreSQL** with async driver (`asyncpg`)
- **SQLAlchemy 2.0** async ORM with `declarative_base`
- Connection string read from `DATABASE_URL` env var, with automatic conversion from `postgres://` to `postgresql+asyncpg://` format (for Railway/Heroku compatibility)
- Uses `NullPool` for connection pooling (suitable for serverless-style deployments)
- Key models: `User`, `UsageLog`, `UserFeed`, `UserProfile`, `Media`, `UserIntegration`
- Migrations are simple `create_all` based (no Alembic)

### Authentication & Authorization
- Custom API key system with `bp_` prefix — keys stored on User model
- `UserContext` object carries authenticated user + db session through tool handlers
- Rate limiting tracked via `UsageLog` table with per-day counting
- Feature gating based on tier (free/pro/business)
- Late.dev OAuth 2.0 for social media account linking (authorization code flow with token refresh)

### Tier System & Billing
- Three tiers: Free (50 calls/day), Pro (500 calls/day, $49/mo), Business (unlimited, $149/mo)
- Stripe Checkout for upgrades with webhook-based tier activation
- Storage limits per tier for media uploads (Free: 0, Pro: 1GB, Business: 10GB)

### Media Storage
- **Cloudflare R2** via boto3 S3-compatible client
- Supports images (JPEG, PNG, GIF, WebP, SVG) and videos (MP4, WebM)
- Per-file size limits enforced by tier

### Tool Pattern
Every MCP tool function follows a consistent pattern:
1. Accept `UserContext` as first parameter
2. Call `check_rate_limit()` and optionally `check_feature_access()`
3. Execute business logic
4. Call `log_usage()` to track the call
5. Return a dict result

## External Dependencies

### APIs & Services
- **Late.dev** — OAuth-based social media posting API (Twitter, LinkedIn, Facebook, etc.). Requires `LATE_CLIENT_ID` and `LATE_CLIENT_SECRET`
- **NewsAPI** (`newsapi.org`) — Keyword-based news search across thousands of sources. Requires `NEWSAPI_KEY`. Pro+ tier only
- **Stripe** — Payment processing for tier upgrades. Requires `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_BUSINESS_PRICE_ID`
- **Cloudflare R2** — S3-compatible object storage for media files. Requires `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL`
- **Newsletter/CMS platforms** — Beehiiv, Kit (ConvertKit), Mailchimp, WordPress, Ghost, Webflow integrations stored per-user in `UserIntegration` table

### Database
- **PostgreSQL** — Primary data store. Connection via `DATABASE_URL` environment variable

### Key Python Packages
- `fastapi` + `uvicorn` — Web server
- `mcp` (v1.1.2) — MCP SDK for SSE transport
- `sqlalchemy` + `asyncpg` — Async PostgreSQL ORM
- `httpx` — Async HTTP client for external API calls
- `feedparser` + `beautifulsoup4` — RSS feed parsing and HTML content extraction
- `boto3` — S3-compatible client for Cloudflare R2
- `stripe` — Stripe API client
- `PyJWT` — JWT token handling

### Environment Variables Required
- `DATABASE_URL` — PostgreSQL connection string
- `BASE_URL` — Public URL of the server (defaults to `http://localhost:8000`)
- `LATE_CLIENT_ID`, `LATE_CLIENT_SECRET` — Late.dev OAuth credentials
- `NEWSAPI_KEY` — NewsAPI access key
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID`, `STRIPE_BUSINESS_PRICE_ID` — Stripe config
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_PUBLIC_URL` — Cloudflare R2 config