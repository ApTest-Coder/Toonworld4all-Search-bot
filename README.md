# ToonWorld4All Telegram Bot

Complete Telegram bot for downloading anime episodes with direct links from ToonWorld4All.

## Features

- 🔍 **Search Anime** - Find any anime series
- 🎬 **Episode Downloads** - Get direct download links
- 🔗 **Shortener Bypass** - Auto-bypasses all link shorteners
- ✅ **Link Validation** - Filters out expired links
- ⚙️ **Admin Panel** - Full control over bot settings
- 📢 **Force Join** - Require users to join channels
- 🌐 **Public/Private Mode** - Toggle bot accessibility
- 📊 **Episode Limits** - Set max episodes per user

## Deployment on Render (Free Tier)

### Step 1: Prepare Your Bot

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Copy the bot token
3. Fork/clone this repository

### Step 2: Deploy to Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `toonworld4all-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && playwright install chromium`
   - **Start Command**: `python toonworld4all_bot_final.py`

5. Add Environment Variables:
   - `BOT_TOKEN`: Your bot token from BotFather
   - `OWNER_ID`: `829342319` (your Telegram ID)
   - `PORT`: `8080`

6. Click "Create Web Service"

### Step 3: Keep Bot Alive with UptimeRobot

Render free tier spins down after 15 minutes of inactivity. Use UptimeRobot to ping it:

1. Go to [UptimeRobot](https://uptimerobot.com/)
2. Create a new monitor:
   - **Monitor Type**: HTTP(s)
   - **URL**: `https://your-app-name.onrender.com/health`
   - **Interval**: 5 minutes
3. Save the monitor

Your bot will now stay online 24/7!

## Admin Commands

### Owner Features (ID: 829342319)

- `/start` - Start the bot
- Access Admin Panel via inline button

### Admin Panel Options

1. **🌐 Mode Toggle**
   - 🟢 Public: Anyone can use the bot
   - 🔴 Private: Force join required

2. **📊 Max Episodes**
   - Set limit on episodes per search

3. **📢 Force Join Channels**
   - Add channels users must join
   - Remove channels
   - Format: `@channelname`

4. **👥 Manage Admins**
   - Add admin by user ID
   - Remove admins
   - Get user ID: Send message to [@userinfobot](https://t.me/userinfobot)

## Bot Usage

### For Users

1. Start bot with `/start`
2. Click "🔍 Search Anime"
3. Type anime name (e.g., "Demon Slayer")
4. Select from results
5. Get direct download links with copy buttons

### For Admins

1. Click "⚙️ Admin Panel"
2. Configure settings as needed
3. Changes save automatically

## File Structure

```
toonworld4all-bot/
├── toonworld4all_bot_final.py  # Main bot file
├── requirements.txt            # Python dependencies
├── render.yaml                 # Render config
├── Procfile                    # Process file
├── .env.example                # Environment variables template
└── README.md                   # This file
```

## Technical Details

### Shortener Bypass

The bot uses Playwright (headless browser) to:
- Execute JavaScript redirects
- Click through verification buttons
- Handle Cloudflare challenges
- Wait for timers and generate links

### Link Validation

- **GoFile**: Uses API to get direct download URLs
- **Mega**: Checks link accessibility
- **Others**: HTTP HEAD request validation

### Database

Simple JSON-based storage (`bot_data.json`):
- User data
- Bot settings
- Admin list
- Force join channels

## Troubleshooting

### Bot Not Responding

1. Check Render logs for errors
2. Verify `BOT_TOKEN` is correct
3. Ensure UptimeRobot is pinging the health endpoint

### Playwright Issues

If Chromium fails to install:
```bash
playwright install chromium
playwright install-deps chromium
```

### Force Join Not Working

1. Ensure bot is admin in the channel
2. Check channel username format (`@channelname`)
3. Verify user actually joined the channel

## Support

- Owner ID: `829342319`
- Render Docs: https://render.com/docs
- UptimeRobot: https://uptimerobot.com/

## License

MIT License - Free to use and modify
