#!/usr/bin/env python3
"""
ToonWorld4All Telegram Bot - Final Version
Complete bot with scraper, admin panel, force join, and inline buttons
Optimized for Render free tier
"""

import os
import json
import asyncio
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from urllib.parse import urlparse
from threading import Thread

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, BrowserContext
import cloudscraper
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from flask import Flask, jsonify

# ============= CONFIGURATION =============
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "829342319"))
DATABASE_FILE = "bot_data.json"

DEFAULT_SETTINGS = {
    "public_mode": False,
    "max_episodes": 5,
    "force_join_channels": [],
    "admins": [],
    "banned_users": []
}

# ============= DATABASE =============
class Database:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> Dict:
        try:
            if os.path.exists(DATABASE_FILE):
                with open(DATABASE_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {"settings": DEFAULT_SETTINGS.copy(), "users": {}}

    def _save(self):
        try:
            with open(DATABASE_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except:
            pass

    def get_settings(self) -> Dict:
        return self.data.get("settings", DEFAULT_SETTINGS.copy())

    def update_settings(self, settings: Dict):
        self.data["settings"] = settings
        self._save()

    def get_user(self, user_id: int) -> Dict:
        return self.data.get("users", {}).get(str(user_id), {})

    def update_user(self, user_id: int, data: Dict):
        if "users" not in self.data:
            self.data["users"] = {}
        self.data["users"][str(user_id)] = data
        self._save()

    def is_admin(self, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        settings = self.get_settings()
        return user_id in settings.get("admins", [])

    def is_owner(self, user_id: int) -> bool:
        return user_id == OWNER_ID

db = Database()

# ============= DATA STRUCTURES =============
@dataclass
class DownloadLink:
    source: str
    url: str
    direct_url: Optional[str] = None
    status: str = "unknown"

@dataclass
class EpisodeFormat:
    quality: str
    codec: str
    bit_depth: str = ""
    extra: str = ""
    size: Optional[str] = None
    links: List[DownloadLink] = field(default_factory=list)

@dataclass
class Episode:
    number: int
    title: str = ""
    url: str = ""
    formats: List[EpisodeFormat] = field(default_factory=list)

# ============= SHORTENER BYPASS =============
class ShortenerBypass:
    @staticmethod
    async def bypass_with_playwright(url: str, context: BrowserContext) -> Tuple[str, bool]:
        page = await context.new_page()
        try:
            await page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            })

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            domain = urlparse(url).netloc.lower()

            # Special handling for archive.toonworld4all.me redirects
            if "archive.toonworld4all.me" in domain and "/redirect/" in url:
                final_url = await ShortenerBypass._bypass_archive_redirect(page)
            elif "exeygo" in domain:
                final_url = await ShortenerBypass._bypass_exeygo(page)
            elif "linkvertise" in domain:
                final_url = await ShortenerBypass._bypass_linkvertise(page)
            else:
                final_url = await ShortenerBypass._bypass_generic(page)

            is_filehost = ShortenerBypass._is_file_host(final_url)
            return final_url, is_filehost
        except Exception as e:
            # Fallback: return original URL
            return url, False
        finally:
            await page.close()

    @staticmethod
    async def _bypass_archive_redirect(page: Page) -> str:
        """
        Specifically handles redirect links from archive.toonworld4all.me/redirect/...
        Waits for the 'Get Link' button, clicks it, and captures the navigation to the final file host.
        """
        try:
            # Wait for the 'Get Link' button to appear
            await page.wait_for_selector("text='Get Link'", timeout=15000)
            # Click and wait for navigation to complete
            async with page.expect_navigation(wait_until="networkidle", timeout=30000):
                await page.click("text='Get Link'")
            final_url = page.url
            return final_url
        except Exception as e:
            # If the expected button is not found, try generic fallback
            return await ShortenerBypass._bypass_generic(page)

    @staticmethod
    async def _bypass_exeygo(page: Page) -> str:
        await asyncio.sleep(3)

        for attempt in range(20):
            await asyncio.sleep(1)

            buttons = await page.query_selector_all('button, a.btn, a.button, input[type="submit"]')

            for btn in buttons:
                try:
                    text = await btn.inner_text()
                    text_lower = text.lower()

                    if any(x in text_lower for x in ["verify", "continue", "generate", "download", 
                                                       "get link", "click here", "i am not a robot",
                                                       "submit", "next"]):
                        await btn.click()
                        await asyncio.sleep(2)
                        break
                except:
                    pass

            current_url = page.url
            if ShortenerBypass._is_file_host(current_url):
                return current_url

            if attempt > 5:
                page_html = await page.content()
                urls = re.findall(r'https?://[^\s"\'<>]+', page_html)
                for u in urls:
                    if ShortenerBypass._is_file_host(u):
                        return u

        return page.url

    @staticmethod
    async def _bypass_linkvertise(page: Page) -> str:
        for _ in range(20):
            await asyncio.sleep(1)

            buttons = await page.query_selector_all('button, a')
            for btn in buttons:
                try:
                    text = await btn.inner_text()
                    if any(x in text.lower() for x in ["continue", "skip", "enter", "next"]):
                        await btn.click()
                        await asyncio.sleep(1)
                except:
                    pass

            if ShortenerBypass._is_file_host(page.url):
                return page.url

        return page.url

    @staticmethod
    async def _bypass_generic(page: Page) -> str:
        for _ in range(20):
            await asyncio.sleep(1)

            buttons = await page.query_selector_all('button, a.btn, a.button')
            for btn in buttons:
                try:
                    text = await btn.inner_text()
                    if any(x in text.lower() for x in ["continue", "generate", "download", "get", "skip", "next"]):
                        await btn.click()
                        await asyncio.sleep(2)
                except:
                    pass

            if ShortenerBypass._is_file_host(page.url):
                return page.url

        page_html = await page.content()
        urls = re.findall(r'https?://[^\s"\'<>]+', page_html)
        for u in urls:
            if ShortenerBypass._is_file_host(u):
                return u

        return page.url

    @staticmethod
    def _is_file_host(url: str) -> bool:
        url_lower = url.lower()
        file_hosts = [
            "mega.nz", "gofile.io", "mediafire.com", "drive.google.com",
            "pixeldrain.com", "terabox.com", "filepress", "appdrive",
            "1drv.ms", "dropbox.com"
        ]
        return any(host in url_lower for host in file_hosts)

# ============= LINK VALIDATOR =============
class LinkValidator:
    @staticmethod
    async def validate_gofile(url: str) -> Tuple[bool, Optional[str]]:
        try:
            code_match = re.search(r'gofile\.io/d/([A-Za-z0-9]+)', url)
            if not code_match:
                return False, None

            code = code_match.group(1)

            server_resp = requests.get("https://api.gofile.io/servers", timeout=10)
            if server_resp.status_code != 200:
                return False, None

            servers = server_resp.json().get("data", {}).get("servers", [])
            if not servers:
                return False, None

            server = servers[0]["name"]

            content_resp = requests.get(f"https://api.gofile.io/content/{code}", timeout=10)
            if content_resp.status_code != 200:
                return False, None

            data = content_resp.json().get("data", {})
            if data.get("status") != "ok":
                return False, None

            children = data.get("children", {})
            for child_id, child in children.items():
                if child.get("type") == "file":
                    direct_link = f"https://{server}.gofile.io/download/{child_id}/{child.get('name')}"
                    return True, direct_link

            return True, url
        except:
            return False, None

    @staticmethod
    async def validate_link(link: DownloadLink) -> DownloadLink:
        url = link.url

        if "gofile.io" in url:
            valid, direct = await LinkValidator.validate_gofile(url)
            link.status = "valid" if valid else "expired"
            link.direct_url = direct
        else:
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                link.status = "valid" if response.status_code == 200 else "expired"
            except:
                link.status = "unknown"

        return link

# ============= SCRAPER =============
class ToonWorld4AllScraper:
    BASE_URL = "https://toonworld4all.me"
    ARCHIVE_URL = "https://archive.toonworld4all.me"

    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    async def search_anime(self, query: str) -> List[Dict]:
        search_url = f"{self.BASE_URL}/?s={query.replace(' ', '+')}"

        try:
            response = self.scraper.get(search_url, headers=self.headers, timeout=30)
            soup = BeautifulSoup(response.text, "lxml")

            results = []

            # Try multiple selectors for article containers
            articles = (
                soup.find_all("article") or
                soup.find_all("div", class_=re.compile(r"post|entry|item|result")) or
                soup.find_all("li", class_=re.compile(r"post|entry"))
            )

            if not articles:
                # Fallback: find any link that contains "season" or "s\d+" in the URL
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    title = a.get_text(strip=True)
                    if href and title and len(title) > 3:
                        if "season" in href.lower() or re.search(r's\d+', href, re.I):
                            results.append({
                                "title": title,
                                "url": href,
                                "type": "season"
                            })
                # Limit to first 10
                return results[:10]

            for article in articles:
                # Find title element
                title_elem = (
                    article.find("h2", class_=re.compile(r"entry-title|title|post-title")) or
                    article.find("h1") or
                    article.find("a", class_=re.compile(r"title|entry-title"))
                )
                # Find link
                link_elem = article.find("a", href=True)
                if not link_elem and title_elem and title_elem.name == "a":
                    link_elem = title_elem

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    url = link_elem.get("href")
                    if url and ("season" in url.lower() or re.search(r's\d+', url, re.I)):
                        results.append({
                            "title": title,
                            "url": url,
                            "type": "season"
                        })

            return results[:10]
        except Exception as e:
            return []

    async def get_episode_info(self, url: str, ep_num: int) -> Episode:
        episode = Episode(number=ep_num, url=url)

        try:
            response = self.scraper.get(url, headers=self.headers, timeout=30)
            soup = BeautifulSoup(response.text, "lxml")

            title_elem = soup.find("title")
            if title_elem:
                title_match = re.search(r'S\d+E\d+\s*-\s*(.+)', title_elem.get_text())
                if title_match:
                    episode.title = title_match.group(1).strip()

            content = soup.find(class_=re.compile(r"entry-content|post-content"))
            if not content:
                content = soup.find("article")

            if not content:
                return episode

            redirect_links = []
            for a in content.find_all("a", href=True):
                href = a["href"]
                if "redirect" in href.lower():
                    full_url = href if href.startswith("http") else f"{self.ARCHIVE_URL}{href}"
                    redirect_links.append(full_url)

            if not redirect_links:
                return episode

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1920, "height": 1080}
                )

                for i, redirect_url in enumerate(redirect_links[:4], 1):
                    final_url, success = await ShortenerBypass.bypass_with_playwright(redirect_url, context)

                    if success:
                        source = self._detect_source(final_url)
                        link = DownloadLink(source=source, url=final_url)
                        link = await LinkValidator.validate_link(link)

                        if not episode.formats:
                            fmt = EpisodeFormat(quality="720p", codec="x264")
                            episode.formats.append(fmt)

                        if link.status == "valid":
                            episode.formats[0].links.append(link)

                await browser.close()
        except:
            pass

        return episode

    def _detect_source(self, url: str) -> str:
        url_lower = url.lower()
        if "mega.nz" in url_lower:
            return "Mega"
        elif "gofile.io" in url_lower:
            return "GoFile"
        elif "mediafire.com" in url_lower:
            return "MediaFire"
        elif "drive.google.com" in url_lower:
            return "GDrive"
        elif "pixeldrain.com" in url_lower:
            return "PixelDrain"
        elif "terabox.com" in url_lower:
            return "TeraBox"
        elif "filepress" in url_lower:
            return "FilePress"
        else:
            return "Unknown"

# ============= FORCE JOIN CHECKER =============
class ForceJoinChecker:
    @staticmethod
    async def check_membership(user_id: int, bot) -> tuple[bool, List[str]]:
        settings = db.get_settings()
        channels = settings.get("force_join_channels", [])

        if not channels:
            return True, []

        not_joined = []

        for channel in channels:
            try:
                member = await bot.get_chat_member(channel, user_id)
                if member.status not in ["member", "administrator", "creator"]:
                    not_joined.append(channel)
            except:
                not_joined.append(channel)

        return len(not_joined) == 0, not_joined

# ============= BOT HANDLERS =============
class BotHandlers:
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id

        user_data = db.get_user(user_id)
        if not user_data:
            db.update_user(user_id, {
                "username": user.username,
                "first_name": user.first_name,
                "joined_at": datetime.now().isoformat(),
                "usage_count": 0
            })

        settings = db.get_settings()
        if not settings.get("public_mode", False):
            is_member, not_joined = await ForceJoinChecker.check_membership(user_id, context.bot)

            if not is_member:
                keyboard = []
                for channel in not_joined:
                    keyboard.append([InlineKeyboardButton(f"Join {channel}", url=f"https://t.me/{channel.replace('@', '')}")])
                keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data="check_join")])

                await update.message.reply_text(
                    "⚠️ *Join Required Channels*\n\n"
                    "Please join the following channels to use this bot:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        await BotHandlers.show_main_menu(update, context)

    @staticmethod
    async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🔍 Search Anime", callback_data="search")],
            [InlineKeyboardButton("📺 My Downloads", callback_data="my_downloads")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ]

        if db.is_admin(update.effective_user.id):
            keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")])

        text = (
            "🎬 *ToonWorld4All Bot*\n\n"
            "Download anime episodes with direct links!\n\n"
            "👋 Welcome!"
        )

        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

    @staticmethod
    async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = query.from_user.id

        if data == "search":
            await query.edit_message_text("🔍 Send me the anime name to search:")
            context.user_data["waiting_search"] = True

        elif data == "check_join":
            is_member, not_joined = await ForceJoinChecker.check_membership(user_id, context.bot)
            if is_member:
                await query.edit_message_text("✅ Thanks for joining! Now you can use the bot.")
                await BotHandlers.show_main_menu(update, context)
            else:
                await query.edit_message_text("❌ You haven't joined all channels yet.")

        elif data == "help":
            help_text = (
                "ℹ️ *Help*\n\n"
                "🔍 *Search*: Find anime episodes\n"
                "📺 *Downloads*: View your download history\n"
                "⚙️ *Admin*: Manage bot settings (admins only)\n\n"
                "💡 *Tips*:\n"
                "• Use exact anime names for better results\n"
                "• Links are validated before showing\n"
                "• Some links may expire over time"
            )
            await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)

        elif data == "admin":
            if not db.is_admin(user_id):
                await query.edit_message_text("❌ Access denied")
                return
            await BotHandlers.show_admin_panel(update, context)

        elif data.startswith("admin_"):
            await BotHandlers.handle_admin_actions(update, context, data)

        elif data.startswith("copy_"):
            link = data.replace("copy_", "")
            await query.edit_message_text(f"📋 Link copied:\n`{link}`", parse_mode=ParseMode.MARKDOWN)

    @staticmethod
    async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = db.get_settings()

        public_status = "🟢 Public" if settings.get("public_mode") else "🔴 Private"
        max_eps = settings.get("max_episodes", 5)
        channels = settings.get("force_join_channels", [])
        admins = settings.get("admins", [])

        keyboard = [
            [InlineKeyboardButton(f"🌐 Mode: {public_status}", callback_data="admin_toggle_public")],
            [InlineKeyboardButton(f"📊 Max Episodes: {max_eps}", callback_data="admin_set_limit")],
            [InlineKeyboardButton(f"📢 Force Join ({len(channels)})", callback_data="admin_channels")],
            [InlineKeyboardButton(f"👥 Admins ({len(admins)})", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]

        text = (
            "⚙️ *Admin Panel*\n\n"
            f"🌐 *Mode*: {public_status}\n"
            f"📊 *Max Episodes*: {max_eps}\n"
            f"📢 *Force Join Channels*: {len(channels)}\n"
            f"👥 *Admins*: {len(admins)}"
        )

        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    @staticmethod
    async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
        query = update.callback_query
        user_id = query.from_user.id

        if not db.is_admin(user_id):
            await query.edit_message_text("❌ Access denied")
            return

        settings = db.get_settings()

        if action == "admin_toggle_public":
            settings["public_mode"] = not settings.get("public_mode", False)
            db.update_settings(settings)
            await BotHandlers.show_admin_panel(update, context)

        elif action == "admin_set_limit":
            await query.edit_message_text("📊 Send the new max episodes limit (number):")
            context.user_data["waiting_limit"] = True

        elif action == "admin_channels":
            keyboard = [
                [InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")],
                [InlineKeyboardButton("🗑️ Remove Channel", callback_data="admin_remove_channel")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin")]
            ]

            channels = settings.get("force_join_channels", [])
            text = "📢 *Force Join Channels*\n\n"
            if channels:
                for i, ch in enumerate(channels, 1):
                    text += f"{i}. {ch}\n"
            else:
                text += "No channels added"

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        elif action == "admin_add_channel":
            await query.edit_message_text("📢 Send channel username (e.g., @channelname):")
            context.user_data["waiting_channel"] = True

        elif action == "admin_remove_channel":
            channels = settings.get("force_join_channels", [])
            if not channels:
                await query.edit_message_text("❌ No channels to remove")
                return

            keyboard = []
            for ch in channels:
                keyboard.append([InlineKeyboardButton(f"🗑️ {ch}", callback_data=f"admin_remove_{ch}")])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_channels")])

            await query.edit_message_text(
                "🗑️ Select channel to remove:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif action.startswith("admin_remove_"):
            channel = action.replace("admin_remove_", "")
            if channel in settings.get("force_join_channels", []):
                settings["force_join_channels"].remove(channel)
                db.update_settings(settings)
            await BotHandlers.show_admin_panel(update, context)

        elif action == "admin_manage_admins":
            keyboard = [
                [InlineKeyboardButton("➕ Add Admin", callback_data="admin_add_admin")],
                [InlineKeyboardButton("🗑️ Remove Admin", callback_data="admin_remove_admin")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin")]
            ]

            admins = settings.get("admins", [])
            text = "👥 *Admins*\n\n"
            if admins:
                for i, admin_id in enumerate(admins, 1):
                    text += f"{i}. `{admin_id}`\n"
            else:
                text += "No admins added"

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        elif action == "admin_add_admin":
            await query.edit_message_text("👥 Send admin user ID (number):")
            context.user_data["waiting_admin"] = True

        elif action == "main_menu":
            await BotHandlers.show_main_menu(update, context)

    @staticmethod
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text

        if context.user_data.get("waiting_search"):
            context.user_data["waiting_search"] = False

            loading_msg = await update.message.reply_text("🔍 Searching...")

            scraper = ToonWorld4AllScraper()
            results = await scraper.search_anime(text)

            if not results:
                await loading_msg.edit_text("❌ No results found")
                return

            keyboard = []
            for i, result in enumerate(results[:5], 1):
                keyboard.append([InlineKeyboardButton(
                    f"{i}. {result['title'][:40]}",
                    callback_data=f"select_{i}"
                )])

            context.user_data["search_results"] = results

            await loading_msg.edit_text(
                f"🔍 Found {len(results)} results:\n\nSelect an anime:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif context.user_data.get("waiting_limit"):
            context.user_data["waiting_limit"] = False

            try:
                limit = int(text)
                settings = db.get_settings()
                settings["max_episodes"] = limit
                db.update_settings(settings)
                await update.message.reply_text(f"✅ Max episodes set to {limit}")
            except:
                await update.message.reply_text("❌ Invalid number")

        elif context.user_data.get("waiting_channel"):
            context.user_data["waiting_channel"] = False

            channel = text.strip()
            if not channel.startswith("@"):
                channel = "@" + channel

            settings = db.get_settings()
            if "force_join_channels" not in settings:
                settings["force_join_channels"] = []

            if channel not in settings["force_join_channels"]:
                settings["force_join_channels"].append(channel)
                db.update_settings(settings)
                await update.message.reply_text(f"✅ Channel {channel} added")
            else:
                await update.message.reply_text("❌ Channel already added")

        elif context.user_data.get("waiting_admin"):
            context.user_data["waiting_admin"] = False

            try:
                admin_id = int(text)
                settings = db.get_settings()
                if "admins" not in settings:
                    settings["admins"] = []

                if admin_id not in settings["admins"]:
                    settings["admins"].append(admin_id)
                    db.update_settings(settings)
                    await update.message.reply_text(f"✅ Admin {admin_id} added")
                else:
                    await update.message.reply_text("❌ Admin already exists")
            except:
                await update.message.reply_text("❌ Invalid user ID")

# ============= FLASK APP =============
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

# ============= BOT SETUP =============
def create_bot() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", BotHandlers.start))
    app.add_handler(CallbackQueryHandler(BotHandlers.button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, BotHandlers.handle_message))

    return app

def run_bot():
    flask_thread = Thread(target=lambda: flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080))))
    flask_thread.daemon = True
    flask_thread.start()

    bot_app = create_bot()
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
