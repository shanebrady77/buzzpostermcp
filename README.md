# BuzzPoster MCP Server

A production-ready remote MCP (Model Context Protocol) server that combines content sourcing (RSS feeds, news search) with social media posting (via Late.dev's API). Users install one MCP in Claude Desktop and get a complete content pipeline: find stories → write with Claude → post everywhere.

## Features

### Content Sourcing
- **RSS Feed Reader**: Fetch and parse any RSS feed
- **Topic-Based News**: Built-in curated feeds for tech, business, and science
- **NewsAPI Integration**: Keyword search across thousands of news sources (Pro+)
- **Custom Feeds**: Add your own RSS feeds (Pro+)
- **Personalized Feed**: Get content tailored to your interests

### Social Media Posting
- **Multi-Platform Posting**: Post to Twitter, LinkedIn, Facebook, and more
- **Cross-Posting**: Share content across multiple platforms at once
- **Scheduling**: Schedule posts for optimal timing
- **Analytics**: Track engagement and performance
- **Account Management**: Connect and manage multiple social accounts

### Tier System
- **Free**: 50 calls/day, 3 built-in topics, basic RSS
- **Pro ($49/mo)**: 500 calls/day, unlimited topics, NewsAPI, social posting
- **Business ($149/mo)**: Unlimited calls, everything in Pro, priority support

## Architecture

```
buzzposter/
├── server.py          # Main FastAPI app with MCP SSE endpoint
├── tools/             # MCP tool implementations
│   ├── feeds.py       # RSS and NewsAPI tools
│   ├── profile.py     # User profile and feed management
│   └── social.py      # Late.dev social posting tools
├── auth/              # Authentication and billing
│   ├── middleware.py  # API key validation and rate limiting
│   ├── late_oauth.py  # Late.dev OAuth flow
│   └── stripe.py      # Stripe checkout and webhooks
└── db/                # Database models and connection
    ├── models.py      # SQLAlchemy models
    ├── connection.py  # Async database connection
    └── migrations.py  # Database migrations
```

## MCP Tools

### Content Sourcing Tools

| Tool | Description | Tier |
|------|-------------|------|
| `buzzposter_get_feed` | Fetch any RSS feed | All |
| `buzzposter_get_topic` | Get news by category | All |
| `buzzposter_search_news` | Search news via NewsAPI | Pro+ |
| `buzzposter_add_feed` | Add custom RSS feeds | Pro+ |
| `buzzposter_remove_feed` | Remove custom feeds | All |
| `buzzposter_list_feeds` | List your feeds | All |
| `buzzposter_set_profile` | Set content preferences | All |
| `buzzposter_my_feed` | Get personalized feed | All |

### Social Posting Tools

| Tool | Description | Tier |
|------|-------------|------|
| `buzzposter_list_social_accounts` | List connected accounts | Pro+ |
| `buzzposter_post` | Post to a platform | Pro+ |
| `buzzposter_cross_post` | Post to multiple platforms | Pro+ |
| `buzzposter_schedule_post` | Schedule a post | Pro+ |
| `buzzposter_list_posts` | List your posts | Pro+ |
| `buzzposter_post_analytics` | Get post analytics | Pro+ |

## Setup & Deployment

### Prerequisites

1. **PostgreSQL Database**
   - Railway provides this automatically
   - Or use any PostgreSQL hosting service

2. **NewsAPI Key**
   - Sign up at [newsapi.org](https://newsapi.org/)
   - Free tier: 1000 requests/day

3. **Stripe Account**
   - Create account at [stripe.com](https://stripe.com/)
   - Set up products and prices for Pro ($49/mo) and Business ($149/mo)
   - Get your secret key and webhook secret

4. **Late.dev OAuth App**
   - Visit [getlate.dev](https://getlate.dev/)
   - Register OAuth application in settings
   - Get client ID and secret

### Deploy to Railway

1. **Create Railway Project**
   ```bash
   # Install Railway CLI
   npm install -g @railway/cli

   # Login
   railway login

   # Initialize project
   railway init
   ```

2. **Add PostgreSQL Database**
   ```bash
   railway add --database postgresql
   ```

3. **Set Environment Variables**
   ```bash
   railway variables set NEWSAPI_KEY=your_key
   railway variables set STRIPE_SECRET_KEY=sk_test_xxx
   railway variables set STRIPE_WEBHOOK_SECRET=whsec_xxx
   railway variables set STRIPE_PRO_PRICE_ID=price_xxx
   railway variables set STRIPE_BUSINESS_PRICE_ID=price_xxx
   railway variables set LATE_CLIENT_ID=your_client_id
   railway variables set LATE_CLIENT_SECRET=your_client_secret
   railway variables set BASE_URL=https://your-domain.railway.app
   railway variables set SERVER_SECRET_KEY=$(openssl rand -base64 32)
   ```

4. **Deploy**
   ```bash
   railway up
   ```

5. **Configure Custom Domain (Optional)**
   ```bash
   railway domain
   ```

### Configure Stripe Webhooks

1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://your-domain.com/webhooks/stripe`
3. Select event: `checkout.session.completed`
4. Copy webhook secret and add to Railway

### Local Development

1. **Clone and Install**
   ```bash
   git clone <your-repo>
   cd buzzpostermcp
   pip install -r requirements.txt
   ```

2. **Set Up Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your keys
   ```

3. **Run Local Database**
   ```bash
   docker run -d -p 5432:5432 \
     -e POSTGRES_PASSWORD=postgres \
     -e POSTGRES_DB=buzzposter \
     postgres:15
   ```

4. **Run Server**
   ```bash
   python -m buzzposter.server
   ```

5. **Test MCP Connection**
   ```bash
   # Add to Claude Desktop config (~/.config/claude/claude_desktop_config.json)
   {
     "mcpServers": {
       "buzzposter": {
         "type": "url",
         "url": "http://localhost:8000/mcp/sse",
         "headers": {
           "Authorization": "Bearer your_api_key"
         }
       }
     }
   }
   ```

## Usage Flow

### For End Users

1. **Sign Up**
   - Visit `/signup` endpoint
   - Provide email
   - Receive API key (`bp_xxx`)

2. **Onboarding**
   - Visit `/onboarding?api_key=bp_xxx`
   - Connect social accounts via Late.dev OAuth
   - Copy Claude Desktop config snippet

3. **Configure Claude Desktop**
   - Paste config into Claude Desktop settings
   - Restart Claude Desktop
   - Start using BuzzPoster tools in conversations

4. **Upgrade (Optional)**
   - Visit `/billing?api_key=bp_xxx`
   - Choose Pro or Business tier
   - Complete Stripe checkout

### Example Conversations

**Content Discovery:**
```
User: Find me the latest tech news about AI
Claude: [Uses buzzposter_get_topic with "tech" and buzzposter_search_news with "AI"]
```

**Social Posting:**
```
User: Post this to Twitter and LinkedIn: "Just discovered an amazing AI tool..."
Claude: [Uses buzzposter_cross_post with platforms=["twitter", "linkedin"]]
```

**Scheduled Posting:**
```
User: Schedule this for tomorrow at 9am: "Monday motivation..."
Claude: [Uses buzzposter_schedule_post with scheduled_at="2024-01-15T09:00:00Z"]
```

## API Endpoints

### Public Endpoints

- `GET /` - Health check and API info
- `POST /signup` - Create new user account
- `GET /onboarding?api_key=xxx` - Onboarding page
- `GET /billing?api_key=xxx` - Billing and upgrade page

### OAuth Endpoints

- `GET /auth/late/connect?api_key=xxx` - Initiate Late.dev OAuth
- `GET /auth/late/callback` - OAuth callback handler
- `GET /auth/late/status?api_key=xxx` - Check connection status

### Billing Endpoints

- `POST /checkout` - Create Stripe checkout session
- `POST /webhooks/stripe` - Stripe webhook handler

### MCP Endpoints

- `GET/POST /mcp/sse` - MCP Server-Sent Events endpoint
- `POST /mcp/message` - MCP message handler

## Database Schema

### users
- `id` - Primary key
- `email` - User email (unique)
- `buzzposter_api_key` - API key with `bp_` prefix
- `tier` - Subscription tier (free, pro, business)
- `late_oauth_token` - Late.dev access token
- `late_refresh_token` - Late.dev refresh token
- `created_at` - Account creation timestamp
- `updated_at` - Last update timestamp

### usage_logs
- `id` - Primary key
- `user_id` - Foreign key to users
- `tool_name` - Name of tool called
- `timestamp` - Call timestamp (indexed for daily queries)

### user_feeds
- `id` - Primary key
- `user_id` - Foreign key to users
- `feed_url` - RSS feed URL
- `feed_name` - Display name
- `topic` - Optional category
- `created_at` - Feed added timestamp

### user_profiles
- `id` - Primary key
- `user_id` - Foreign key to users (unique)
- `topics` - JSON array of interests
- `location` - User location
- `description` - Content preferences

## Security

- **API Key Authentication**: All MCP requests require valid `bp_` prefixed key
- **Rate Limiting**: Daily limits enforced per tier
- **Feature Gating**: Pro/Business features blocked for Free tier
- **OAuth Security**: State parameter prevents CSRF attacks
- **Stripe Webhooks**: Signature verification prevents tampering
- **Database**: Async PostgreSQL with connection pooling

## Monitoring

### Health Checks
- `GET /health` - Returns `{"status": "healthy"}`
- Railway automatically monitors this endpoint

### Usage Tracking
- All tool calls logged to `usage_logs` table
- Query daily usage: `SELECT COUNT(*) FROM usage_logs WHERE user_id=? AND timestamp > NOW() - INTERVAL '1 day'`

## Troubleshooting

### MCP Connection Issues
1. Check API key is valid and starts with `bp_`
2. Verify Authorization header: `Bearer bp_xxx`
3. Check Railway logs for errors
4. Ensure DATABASE_URL is set correctly

### OAuth Issues
1. Verify Late.dev client ID and secret
2. Check redirect URI matches: `{BASE_URL}/auth/late/callback`
3. Ensure BASE_URL environment variable is set

### Rate Limit Errors
1. Check current usage: Query `usage_logs` table
2. Upgrade to higher tier for more calls
3. Usage resets daily at midnight UTC

## Contributing

Contributions welcome! Areas for improvement:
- Additional social platforms
- More RSS feed sources
- Advanced analytics
- Team features
- Webhooks for events

## License

MIT License - see LICENSE file

## Support

- GitHub Issues: Report bugs and feature requests
- Email: support@buzzposter.com
- Documentation: [docs.buzzposter.com](https://docs.buzzposter.com)

## Roadmap

- [ ] Team collaboration features
- [ ] Webhook notifications
- [ ] Content calendar view
- [ ] Advanced analytics dashboard
- [ ] Mobile app
- [ ] Browser extension
- [ ] WordPress plugin
- [ ] Zapier integration

---

Built with [FastAPI](https://fastapi.tiangolo.com/), [MCP SDK](https://github.com/anthropics/python-sdk), and ❤️