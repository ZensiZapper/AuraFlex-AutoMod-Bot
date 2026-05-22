# ==========================================
# ⚙️ AURAFLEX MOD - CORE CONFIGURATION
# ==========================================
TOKEN = "UR_B0T_TOKEN_HERE"
GROQ_API_KEY = "UR_GR0Q_API_HERE"
PREFIX = "am!"
EMBED_COLOR_SUCCESS = 0x00FFAA  # Neon Green
EMBED_COLOR_ERROR = 0xFF0033    # Crimson Red
EMBED_COLOR_INFO = 0x2B2D31     # Discord Dark Theme
TIMEOUT_DURATION = 300          # Default: 5 minutes (in seconds)
MAX_WARNINGS = 3                # Warns before 1hr timeout
GROQ_MODEL = "llama-3.1-8b-instant"  # Primary model
GROQ_FALLBACK_MODEL = "gemma2-9b-it"  # Fallback model

# Built-in bad words categorized by language
BUILT_IN_BADWORDS = {
    "en": ["fuck", "shit", "bitch", "asshole", "bastard", "cunt", "dick", "piss", "cock", "whore"],
    "hi": ["madarchod", "bhenchod", "chutiya", "gaandu", "randi", "harami", "kutta", "saala", "gandu", "bakchod"],
    "bn": ["magi", "khankir", "chudi", "baal", "shala", "kuttar", "haramjada", "chod", "rendi", "bokachoda"]
}
# ==========================================

import discord
from discord.ext import commands
import json
import os
import re
import asyncio
import aiohttp
import logging
import datetime
import shutil
import sys
from collections import defaultdict

# ── Suppress PyNaCl / voice warning ──────────────────────────────────────────
logging.getLogger("discord.client").setLevel(logging.ERROR)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AuraFlexMod")

# ── File paths ────────────────────────────────────────────────────────────────
DB_FILE    = "server_data.json"
QUEUE_FILE = "queue.json"

# ── Leetspeak mapping (comprehensive) ────────────────────────────────────────
LEET_MAP = {
    "a": r"[aA@4^]",
    "b": r"[bB8ß]",
    "c": r"[cC\(kK<\[\{]",
    "d": r"[dD\)]",
    "e": r"[eE3€]",
    "f": r"[fFphPH]",
    "g": r"[gG96]",
    "h": r"[hH#\-n]",
    "i": r"[iI1!l\|]",
    "j": r"[jJ]",
    "k": r"[kKxX]",
    "l": r"[lL1!iI\|]",
    "m": r"[mM]",
    "n": r"[nNñÑ]",
    "o": r"[oO0\*\(\)]",
    "p": r"[pP]",
    "q": r"[qQ9]",
    "r": r"[rR®]",
    "s": r"[sS5\$zZ]",
    "t": r"[tT7\+]",
    "u": r"[uUvV\^]",
    "v": r"[vVuU]",
    "w": r"[wWvvVV]",
    "x": r"[xX\*\+]",
    "y": r"[yY¥]",
    "z": r"[zZ2sS]",
}

# ── Invisible / zero-width characters to strip ────────────────────────────────
ZERO_WIDTH_PATTERN = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u00ad\ufeff\u2060\u180e]"
)

# ─────────────────────────────────────────────────────────────────────────────
# UTILITY: Build a regex pattern from a word using leet mapping
# ─────────────────────────────────────────────────────────────────────────────
def build_leet_pattern(word: str) -> str:
    """
    Convert a plain word into a comprehensive leetspeak-aware regex pattern.
    E.g. "bad" -> r"[bB8ß]+[\W_]*[aA@4^]+[\W_]*[dD\)]+"
    """
    word = word.lower().strip()
    parts = []
    for ch in word:
        mapped = LEET_MAP.get(ch)
        if mapped:
            parts.append(mapped + r"+")
        else:
            # escape special regex chars for unmapped characters
            parts.append(re.escape(ch) + r"+")
    return r"[\W_]*".join(parts)


def compile_word_regex(word: str) -> re.Pattern:
    pattern = build_leet_pattern(word)
    return re.compile(pattern, re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Strip zero-width chars and normalize to lowercase."""
    text = ZERO_WIDTH_PATTERN.sub("", text)
    return text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE LAYER
# ─────────────────────────────────────────────────────────────────────────────
class Database:
    def __init__(self):
        self._data: dict = {}
        self._lock = asyncio.Lock()

    def load(self):
        """Load JSON from disk into RAM. Called once at startup (sync)."""
        if not os.path.exists(DB_FILE):
            self._data = {}
            self._write_sync()
            logger.info("server_data.json not found – created fresh database.")
            return

        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(f"Database loaded – {len(self._data)} guild(s) cached.")
        except json.JSONDecodeError:
            bak = DB_FILE + ".bak"
            shutil.copy(DB_FILE, bak)
            logger.error(f"Corrupt JSON detected! Backed up to {bak}. Starting fresh.")
            self._data = {}
            self._write_sync()

    def _write_sync(self):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    async def save(self):
        """Async write to disk under lock."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_sync)

    # ── Guild scaffold ────────────────────────────────────────────────────────
    def _ensure_guild(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self._data:
            self._data[gid] = {
                "settings": {
                    "log_channel": None,
                    "ai_enabled": True,
                    "prefix": PREFIX,
                },
                "whitelists": {"channels": [], "roles": []},
                "custom_badwords": [],
                "warnings": {},
            }
        return self._data[gid]

    # ── Getters / setters ─────────────────────────────────────────────────────
    def get_guild(self, guild_id: int) -> dict:
        return self._ensure_guild(guild_id)

    def get_settings(self, guild_id: int) -> dict:
        return self._ensure_guild(guild_id)["settings"]

    def get_log_channel(self, guild_id: int):
        return self.get_settings(guild_id).get("log_channel")

    def set_log_channel(self, guild_id: int, channel_id):
        self.get_settings(guild_id)["log_channel"] = channel_id

    def is_ai_enabled(self, guild_id: int) -> bool:
        return self.get_settings(guild_id).get("ai_enabled", True)

    def toggle_ai(self, guild_id: int) -> bool:
        s = self.get_settings(guild_id)
        s["ai_enabled"] = not s.get("ai_enabled", True)
        return s["ai_enabled"]

    def get_whitelist(self, guild_id: int) -> dict:
        return self._ensure_guild(guild_id)["whitelists"]

    def get_custom_badwords(self, guild_id: int) -> list:
        return self._ensure_guild(guild_id)["custom_badwords"]

    def add_badwords(self, guild_id: int, words: list) -> list:
        """Add words, return list of actually-added words (deduplication)."""
        existing = self.get_custom_badwords(guild_id)
        added = []
        for w in words:
            w = w.strip().lower()
            if w and w not in existing:
                existing.append(w)
                added.append(w)
        return added

    def remove_badwords(self, guild_id: int, words: list) -> list:
        """Remove words, return list of removed words."""
        existing = self.get_custom_badwords(guild_id)
        removed = []
        for w in words:
            w = w.strip().lower()
            if w in existing:
                existing.remove(w)
                removed.append(w)
        return removed

    def clear_badwords(self, guild_id: int):
        self._ensure_guild(guild_id)["custom_badwords"] = []

    # ── Warning helpers ───────────────────────────────────────────────────────
    def get_warnings(self, guild_id: int, user_id: int) -> list:
        uid = str(user_id)
        return self._ensure_guild(guild_id)["warnings"].get(uid, [])

    def add_warning(self, guild_id: int, user_id: int, reason: str) -> int:
        uid = str(user_id)
        guild = self._ensure_guild(guild_id)
        if uid not in guild["warnings"]:
            guild["warnings"][uid] = []
        guild["warnings"][uid].append({
            "reason": reason,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        })
        return len(guild["warnings"][uid])

    def clear_warnings(self, guild_id: int, user_id: int):
        uid = str(user_id)
        self._ensure_guild(guild_id)["warnings"].pop(uid, None)


db = Database()


# ─────────────────────────────────────────────────────────────────────────────
# QUEUE LAYER  (AI Moderation queue backed by queue.json)
# ─────────────────────────────────────────────────────────────────────────────
class AIQueue:
    """
    Persistent, file-backed AI moderation queue.
    Items are stored to queue.json so a crash won't lose them.
    A semaphore limits concurrent Groq calls to 3.
    """
    def __init__(self, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._file_lock = asyncio.Lock()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    def _load_pending(self) -> list:
        if not os.path.exists(QUEUE_FILE):
            return []
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    async def _write_pending(self, items: list):
        async with self._file_lock:
            loop = asyncio.get_event_loop()
            def _w():
                with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(items, f)
            await loop.run_in_executor(None, _w)

    async def _remove_from_file(self, item_id: str):
        pending = self._load_pending()
        pending = [p for p in pending if p.get("id") != item_id]
        await self._write_pending(pending)

    async def enqueue(self, item: dict):
        """Add an item to both the in-memory queue and queue.json."""
        pending = self._load_pending()
        pending.append(item)
        await self._write_pending(pending)
        await self._queue.put(item)

    async def start_worker(self, process_fn):
        """
        Background worker – pulls items off the queue one-by-one
        but allows up to max_concurrent simultaneous Groq calls.
        """
        self._running = True
        # Re-hydrate in-memory queue from file on startup
        for item in self._load_pending():
            await self._queue.put(item)

        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            asyncio.ensure_future(self._process_with_sem(item, process_fn))

    async def _process_with_sem(self, item: dict, process_fn):
        async with self._semaphore:
            try:
                await process_fn(item)
            except Exception as exc:
                logger.error(f"AIQueue worker error: {exc}")
            finally:
                await self._remove_from_file(item.get("id", ""))
                self._queue.task_done()

    def stop(self):
        self._running = False


ai_queue = AIQueue(max_concurrent=3)


# ─────────────────────────────────────────────────────────────────────────────
# REGEX CACHE  (per-guild compiled patterns)
# ─────────────────────────────────────────────────────────────────────────────
class RegexCache:
    def __init__(self):
        self._cache: dict[str, list[re.Pattern]] = {}

    def _build_all_patterns(self, guild_id: int) -> list[re.Pattern]:
        patterns = []
        # Built-in words
        for lang_words in BUILT_IN_BADWORDS.values():
            for word in lang_words:
                try:
                    patterns.append(compile_word_regex(word))
                except re.error as e:
                    logger.warning(f"Regex compile error for built-in '{word}': {e}")
        # Custom words
        for word in db.get_custom_badwords(guild_id):
            try:
                patterns.append(compile_word_regex(word))
            except re.error as e:
                logger.warning(f"Regex compile error for custom '{word}': {e}")
        return patterns

    def get(self, guild_id: int) -> list[re.Pattern]:
        gid = str(guild_id)
        if gid not in self._cache:
            self._cache[gid] = self._build_all_patterns(guild_id)
        return self._cache[gid]

    def invalidate(self, guild_id: int):
        self._cache.pop(str(guild_id), None)

    def check(self, guild_id: int, text: str):
        """
        Returns the matched string if a badword is found, else None.
        """
        normalized = normalize_text(text)
        for pattern in self.get(guild_id):
            m = pattern.search(normalized)
            if m:
                return m.group(0)
        return None


regex_cache = RegexCache()


# ─────────────────────────────────────────────────────────────────────────────
# GROQ AI CLIENT
# ─────────────────────────────────────────────────────────────────────────────
class GroqClient:
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    SYSTEM_PROMPT = (
        "You are AuraFlex Mod, a strict Discord Auto-Moderator.\n"
        "Analyze the following text. Does it contain extreme insults, racism, "
        "inappropriate/NSFW content, or severe toxicity?\n"
        "Respond ONLY with one of these two exact formats:\n"
        "SAFE\n"
        "VIOLATION: [Short 3 word reason]\n"
        "Do not add any other text, explanations, or punctuation."
    )

    def __init__(self):
        self._session: aiohttp.ClientSession | None = None
        self.ai_on_cooldown = False
        self._cooldown_until: datetime.datetime | None = None
        self._model_decommissioned = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _check_cooldown(self) -> bool:
        if self.ai_on_cooldown:
            if datetime.datetime.utcnow() >= self._cooldown_until:
                self.ai_on_cooldown = False
                logger.info("Groq AI cooldown expired – resuming normal operation.")
                return False
            return True
        return False

    def _set_cooldown(self, seconds: int = 60):
        self.ai_on_cooldown = True
        self._cooldown_until = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)

    async def moderate(self, text: str, guild_id: int) -> tuple[str, str | None]:
        """
        Returns ("SAFE", None) or ("VIOLATION", reason).
        May also return ("SKIP", reason) when AI is unavailable.
        """
        if self._model_decommissioned:
            return ("SKIP", "Model decommissioned")
        if self._check_cooldown():
            return ("SKIP", "AI on cooldown")

        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            "max_tokens": 30,
            "temperature": 0,
        }

        try:
            async with session.post(self.BASE_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    reply = data["choices"][0]["message"]["content"].strip()
                    if reply.startswith("VIOLATION"):
                        reason = reply.split(":", 1)[1].strip() if ":" in reply else "Policy violation"
                        return ("VIOLATION", reason)
                    return ("SAFE", None)

                elif resp.status == 429:
                    logger.warning("Groq rate-limited (429) – entering 60s cooldown.")
                    self._set_cooldown(60)
                    return ("SKIP", "Rate limited")

                elif resp.status == 400:
                    body = await resp.text()
                    if "decommissioned" in body.lower() or "no longer supported" in body.lower():
                        logger.critical("Groq model decommissioned! Switching to Regex-only mode.")
                        self._model_decommissioned = True
                        return ("DECOMMISSIONED", None)
                    logger.error(f"Groq 400 error: {body[:200]}")
                    return ("SKIP", "Bad request")

                else:
                    body = await resp.text()
                    logger.error(f"Groq unexpected status {resp.status}: {body[:200]}")
                    self._set_cooldown(30)
                    return ("SKIP", f"HTTP {resp.status}")

        except asyncio.TimeoutError:
            logger.warning("Groq request timed out – entering 30s cooldown.")
            self._set_cooldown(30)
            return ("SKIP", "Timeout")
        except aiohttp.ClientError as exc:
            logger.warning(f"Groq client error: {exc} – entering 30s cooldown.")
            self._set_cooldown(30)
            return ("SKIP", str(exc))

    async def ping(self) -> float | None:
        """Returns Groq API response time in milliseconds, or None on failure."""
        start = asyncio.get_event_loop().time()
        try:
            session = await self._get_session()
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "Reply OK"},
                    {"role": "user",   "content": "ping"},
                ],
                "max_tokens": 5,
                "temperature": 0,
            }
            async with session.post(self.BASE_URL, headers=headers, json=payload) as resp:
                await resp.read()
                return (asyncio.get_event_loop().time() - start) * 1000
        except Exception:
            return None


groq_client = GroqClient()


# ─────────────────────────────────────────────────────────────────────────────
# BOT INTENTS & SETUP
# ─────────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds          = True
intents.guild_messages  = True
intents.members         = True
intents.voice_states    = False   # AuraFlex is text-only; suppresses PyNaCl warning

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


def has_bot_bypass(member: discord.Member, guild_id: int) -> bool:
    """True if member is a bot, an admin, or has a whitelisted role."""
    if member.bot:
        return True
    if is_admin(member):
        return True
    wl = db.get_whitelist(guild_id)
    for role in member.roles:
        if role.id in wl["roles"]:
            return True
    return False


def is_channel_whitelisted(channel_id: int, guild_id: int) -> bool:
    return channel_id in db.get_whitelist(guild_id)["channels"]


def make_embed(
    title: str = "",
    description: str = "",
    color: int = EMBED_COLOR_INFO,
    fields: list[tuple[str, str, bool]] | None = None,
    footer: str | None = None,
    author_name: str | None = None,
    author_icon: str | None = None,
    timestamp: bool = False,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    if footer:
        embed.set_footer(text=footer)
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon or discord.Embed.Empty)
    if timestamp:
        embed.timestamp = datetime.datetime.utcnow()
    return embed


async def send_log(guild: discord.Guild, embed: discord.Embed):
    """Post a moderation log embed to the configured log channel."""
    log_id = db.get_log_channel(guild.id)
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot post to log channel {log_id} in guild {guild.id}")


async def apply_timeout(member: discord.Member, seconds: int, reason: str) -> str | None:
    """
    Apply a Discord timeout. Returns error string on failure, None on success.
    Never acts on admins.
    """
    if is_admin(member):
        return "Target is an administrator."
    until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
    try:
        await member.timeout(until, reason=reason)
        return None
    except discord.Forbidden:
        return "Role hierarchy prevents timeout."
    except discord.HTTPException as e:
        return str(e)


async def automod_action(
    message: discord.Message,
    reason: str,
    action_label: str = "Message Deleted & Muted (5m)",
):
    """
    Core moderation action: delete message, timeout user, send log.
    """
    guild  = message.guild
    member = message.author

    # Delete the offending message
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass

    # Timeout
    timeout_err = await apply_timeout(member, TIMEOUT_DURATION, reason)

    # Build log embed
    fields = [
        ("Action Taken", action_label if not timeout_err else f"Message Deleted\n⚠️ {timeout_err}", False),
        ("Reason",       reason,                                                                     False),
        ("Trigger Message", f"|| {message.content[:900]} ||",                                       False),
        ("Channel",      message.channel.mention,                                                   True),
    ]
    embed = make_embed(
        title="🛡️ Auto-Moderation Triggered",
        color=EMBED_COLOR_ERROR,
        fields=fields,
        footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        author_name=f"{member} ({member.id})",
        author_icon=member.display_avatar.url,
    )
    await send_log(guild, embed)


# ─────────────────────────────────────────────────────────────────────────────
# AI QUEUE PROCESSOR
# ─────────────────────────────────────────────────────────────────────────────
async def process_ai_queue_item(item: dict):
    """
    Called by AIQueue worker for each queued message.
    item keys: id, guild_id, channel_id, message_id, author_id, content
    """
    guild   = bot.get_guild(item["guild_id"])
    if not guild:
        return
    channel = guild.get_channel(item["channel_id"])
    if not channel:
        return

    # Re-fetch message to see if it still exists
    try:
        message = await channel.fetch_message(item["message_id"])
    except (discord.NotFound, discord.Forbidden):
        return  # Already deleted or inaccessible

    result, reason = await groq_client.moderate(item["content"], item["guild_id"])

    if result == "VIOLATION":
        await automod_action(
            message,
            reason=f"AI Detection: {reason}",
            action_label="Message Deleted & Muted (5m)",
        )

    elif result == "DECOMMISSIONED":
        # Notify log channel
        log_id = db.get_log_channel(item["guild_id"])
        if log_id:
            ch = guild.get_channel(log_id)
            if ch:
                embed = make_embed(
                    title="🚨 AI Model Decommissioned",
                    description=(
                        "🚨 Groq AI Model decommissioned by provider. "
                        "Bot is running in **Regex-Only** mode.\n"
                        "Please update `GROQ_MODEL` in `bot.py`."
                    ),
                    color=EMBED_COLOR_ERROR,
                )
                try:
                    await ch.send(embed=embed)
                except discord.Forbidden:
                    pass

    elif result == "SKIP" and groq_client.ai_on_cooldown:
        # Notify log channel about cooldown (once)
        log_id = db.get_log_channel(item["guild_id"])
        if log_id:
            ch = guild.get_channel(log_id)
            if ch:
                embed = make_embed(
                    title="⚠️ Groq AI Cooldown Active",
                    description=(
                        f"Groq API is rate-limited or unavailable. "
                        f"Bot running in **Regex-Only** mode for ~60 seconds.\n"
                        f"**Reason:** {reason}"
                    ),
                    color=EMBED_COLOR_ERROR,
                )
                try:
                    await ch.send(embed=embed)
                except discord.Forbidden:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    db.load()
    asyncio.ensure_future(
        ai_queue.start_worker(process_ai_queue_item)
    )
    logger.info(f"AuraFlex Mod online as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{PREFIX}help | Protecting your server"
        )
    )


@bot.event
async def on_message(message: discord.Message):
    # ── Step 1: Bypass checks ─────────────────────────────────────────────────
    if not message.guild:
        await bot.process_commands(message)
        return
    if message.author.bot:
        return
    if has_bot_bypass(message.author, message.guild.id):
        await bot.process_commands(message)
        return
    if is_channel_whitelisted(message.channel.id, message.guild.id):
        await bot.process_commands(message)
        return
    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return

    # ── Step 2: Regex engine ──────────────────────────────────────────────────
    matched = regex_cache.check(message.guild.id, message.content)
    if matched:
        await automod_action(
            message,
            reason=f"Banned word detected: `{matched}`",
            action_label="Message Deleted & Muted (5m)",
        )
        return  # STOP pipeline

    # ── Step 3: Length & media check ─────────────────────────────────────────
    text_to_analyse = message.content.strip()

    # Extract GIF slugs from tenor/giphy links
    gif_pattern = re.compile(
        r"https?://(?:www\.)?(?:tenor\.com/view|giphy\.com/gifs)/([a-zA-Z0-9\-]+)",
        re.IGNORECASE,
    )
    for match in gif_pattern.finditer(text_to_analyse):
        slug = match.group(1).replace("-", " ")
        text_to_analyse += f" {slug}"

    if len(text_to_analyse.strip()) < 3:
        return  # Too short – saves API calls

    # ── Step 4: Groq AI (async, queued) ──────────────────────────────────────
    if not db.is_ai_enabled(message.guild.id):
        return
    if groq_client._model_decommissioned:
        return

    import uuid
    item = {
        "id":         str(uuid.uuid4()),
        "guild_id":   message.guild.id,
        "channel_id": message.channel.id,
        "message_id": message.id,
        "author_id":  message.author.id,
        "content":    text_to_analyse[:1500],  # Trim to save tokens
    }
    await ai_queue.enqueue(item)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        embed = make_embed(
            title="❌ Missing Argument",
            description=f"**Usage:** `{ctx.command.usage or ctx.command.qualified_name}`",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed, delete_after=10)
    elif isinstance(error, commands.BadArgument):
        embed = make_embed(
            title="❌ Bad Argument",
            description=f"One or more arguments were invalid.\n**Usage:** `{ctx.command.usage or ctx.command.qualified_name}`",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed, delete_after=10)
    elif isinstance(error, commands.MissingPermissions):
        embed = make_embed(
            title="❌ Missing Permissions",
            description="You don't have the required permissions for this command.",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed, delete_after=10)
    elif isinstance(error, commands.BotMissingPermissions):
        embed = make_embed(
            title="❌ Bot Missing Permissions",
            description="I lack the necessary permissions to execute this action.",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed, delete_after=10)
    elif isinstance(error, commands.NoPrivateMessage):
        pass
    else:
        logger.error(f"Unhandled command error in {ctx.command}: {error}", exc_info=error)


# ─────────────────────────────────────────────────────────────────────────────
# ⚙️  SYSTEM & SETUP COMMANDS
# ─────────────────────────────────────────────────────────────────────────────
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    embed = make_embed(
        title="📖 AuraFlex™ Mod — Command Reference",
        description=(
            "All commands use the `am!` prefix. "
            "Admin commands require **Administrator** permission.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=EMBED_COLOR_INFO,
    )

    embed.add_field(
        name="⚙️ System & Setup",
        value=(
            "`am!help` — This menu\n"
            "`am!ping` — WebSocket & Groq latency\n"
            "`am!logs <#channel>` — Set log channel\n"
            "`am!logs disable` — Disable logging\n"
            "`am!ai toggle` — Toggle AI moderation\n"
            "`am!whitelist add <#ch/@role>` — Whitelist channel/role\n"
            "`am!whitelist remove <#ch/@role>` — Remove whitelist"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Badword Management",
        value=(
            "`am!banword add <word1, word2>` — Add ban words\n"
            "`am!banword remove <word1, word2>` — Remove ban words\n"
            "`am!banword list` — List all custom ban words\n"
            "`am!banword clear` — Wipe all custom ban words"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛑 Discord AutoMod Integration",
        value=(
            "`am!automod spam <on/off>` — Native anti-spam rule\n"
            "`am!automod invites <on/off>` — Block invite links\n"
            "`am!automod links <on/off>` — Block external links\n"
            "`am!automod sync` — Push banwords to Discord AutoMod"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔨 Manual Moderation",
        value=(
            "`am!timeout <@user> [mins] [reason]` — Timeout a user\n"
            "`am!untimeout <@user>` — Remove timeout\n"
            "`am!warn <@user> [reason]` — Warn a user\n"
            "`am!warnings <@user>` — View user warnings\n"
            "`am!clearwarns <@user>` — Clear user warnings\n"
            "`am!kick <@user> [reason]` — Kick a user\n"
            "`am!ban <@user> [reason]` — Ban a user\n"
            "`am!unban <user_id>` — Unban by ID"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔐 Server Security & Utility",
        value=(
            "`am!purge <1-100>` — Bulk delete messages\n"
            "`am!lockdown` — Lock current channel\n"
            "`am!unlock` — Unlock current channel\n"
            "`am!slowmode <seconds>` — Set slowmode (0 = off)"
        ),
        inline=False,
    )
    embed.set_footer(text="AuraFlex™ Mod • Protecting your community")
    await ctx.send(embed=embed)


@bot.command(name="ping")
async def ping_cmd(ctx: commands.Context):
    ws_latency = round(bot.latency * 1000, 2)

    # Measure Groq ping
    groq_ms = await groq_client.ping()
    groq_str = f"`{round(groq_ms, 2)} ms`" if groq_ms else "`Unavailable`"

    embed = make_embed(
        title="🏓 Pong!",
        color=EMBED_COLOR_INFO,
        fields=[
            ("Discord WebSocket", f"`{ws_latency} ms`", True),
            ("Groq API",          groq_str,             True),
        ],
    )
    await ctx.send(embed=embed)


@bot.command(name="logs")
@commands.has_permissions(administrator=True)
async def logs_cmd(ctx: commands.Context, *, arg: str = None):
    if arg and arg.strip().lower() == "disable":
        db.set_log_channel(ctx.guild.id, None)
        await db.save()
        embed = make_embed(
            description="✅ Logging has been **disabled**.",
            color=EMBED_COLOR_INFO,
        )
        await ctx.send(embed=embed)
        return

    if ctx.message.channel_mentions:
        channel = ctx.message.channel_mentions[0]
        db.set_log_channel(ctx.guild.id, channel.id)
        await db.save()
        embed = make_embed(
            description=f"✅ Log channel has been successfully bound to {channel.mention}.",
            color=EMBED_COLOR_INFO,
        )
        await ctx.send(embed=embed)
    else:
        embed = make_embed(
            title="❌ Invalid Usage",
            description="**Usage:** `am!logs <#channel>` or `am!logs disable`",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed)


@bot.command(name="ai")
@commands.has_permissions(administrator=True)
async def ai_cmd(ctx: commands.Context, action: str = None):
    if action and action.lower() == "toggle":
        new_state = db.toggle_ai(ctx.guild.id)
        await db.save()
        state_str = "**enabled** ✅" if new_state else "**disabled** ❌"
        embed = make_embed(
            description=f"🤖 Groq AI moderation is now {state_str}.",
            color=EMBED_COLOR_INFO,
        )
        await ctx.send(embed=embed)
    else:
        embed = make_embed(
            title="❌ Invalid Usage",
            description="**Usage:** `am!ai toggle`",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed)


@bot.command(name="whitelist")
@commands.has_permissions(administrator=True)
async def whitelist_cmd(ctx: commands.Context, action: str = None, *, target: str = None):
    if action not in ("add", "remove") or not target:
        embed = make_embed(
            title="❌ Invalid Usage",
            description=(
                "**Usage:**\n"
                "`am!whitelist add <#channel / @role>`\n"
                "`am!whitelist remove <#channel / @role>`"
            ),
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed)
        return

    wl = db.get_whitelist(ctx.guild.id)

    # Determine if target is a channel or role mention
    if ctx.message.channel_mentions:
        obj = ctx.message.channel_mentions[0]
        key = "channels"
        mention = obj.mention
    elif ctx.message.role_mentions:
        obj = ctx.message.role_mentions[0]
        key = "roles"
        mention = obj.mention
    else:
        embed = make_embed(
            title="❌ Invalid Target",
            description="Please mention a valid **#channel** or **@role**.",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed)
        return

    if action == "add":
        if obj.id not in wl[key]:
            wl[key].append(obj.id)
            await db.save()
            msg = f"✅ {mention} has been **added** to the whitelist."
        else:
            msg = f"ℹ️ {mention} is already whitelisted."
    else:
        if obj.id in wl[key]:
            wl[key].remove(obj.id)
            await db.save()
            msg = f"✅ {mention} has been **removed** from the whitelist."
        else:
            msg = f"ℹ️ {mention} was not in the whitelist."

    embed = make_embed(description=msg, color=EMBED_COLOR_INFO)
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────────────────────────────────────
# 🛡️  BADWORD MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
@bot.group(name="banword", invoke_without_command=True)
@commands.has_permissions(manage_messages=True)
async def banword_group(ctx: commands.Context):
    embed = make_embed(
        title="❌ Invalid Usage",
        description=(
            "**Subcommands:**\n"
            "`am!banword add <word1, word2>` — Add words\n"
            "`am!banword remove <word1, word2>` — Remove words\n"
            "`am!banword list` — List custom words\n"
            "`am!banword clear` — Clear all custom words"
        ),
        color=EMBED_COLOR_ERROR,
    )
    await ctx.send(embed=embed)


@banword_group.command(name="add")
@commands.has_permissions(manage_messages=True)
async def banword_add(ctx: commands.Context, *, words_raw: str):
    words = [w.strip().lower() for w in words_raw.split(",") if w.strip()]
    if not words:
        await ctx.send(embed=make_embed(description="❌ No valid words provided.", color=EMBED_COLOR_ERROR))
        return

    added = db.add_badwords(ctx.guild.id, words)
    regex_cache.invalidate(ctx.guild.id)
    await db.save()

    if added:
        embed = make_embed(
            title="✅ Banwords Added",
            description=f"Added **{len(added)}** word(s): `{'`, `'.join(added)}`",
            color=EMBED_COLOR_INFO,
        )
    else:
        embed = make_embed(
            description="ℹ️ All provided words already exist in the banlist.",
            color=EMBED_COLOR_INFO,
        )
    await ctx.send(embed=embed)


@banword_group.command(name="remove")
@commands.has_permissions(manage_messages=True)
async def banword_remove(ctx: commands.Context, *, words_raw: str):
    words = [w.strip().lower() for w in words_raw.split(",") if w.strip()]
    if not words:
        await ctx.send(embed=make_embed(description="❌ No valid words provided.", color=EMBED_COLOR_ERROR))
        return

    removed = db.remove_badwords(ctx.guild.id, words)
    if removed:
        regex_cache.invalidate(ctx.guild.id)
        await db.save()
        embed = make_embed(
            title="✅ Banwords Removed",
            description=f"Removed **{len(removed)}** word(s): `{'`, `'.join(removed)}`",
            color=EMBED_COLOR_INFO,
        )
    else:
        embed = make_embed(
            description="ℹ️ None of the provided words were found in the banlist.",
            color=EMBED_COLOR_INFO,
        )
    await ctx.send(embed=embed)


@banword_group.command(name="list")
@commands.has_permissions(manage_messages=True)
async def banword_list(ctx: commands.Context):
    custom = db.get_custom_badwords(ctx.guild.id)
    if not custom:
        await ctx.send(embed=make_embed(description="ℹ️ No custom banwords set for this server.", color=EMBED_COLOR_INFO))
        return

    content = ", ".join(f"`{w}`" for w in custom)
    title = f"🚫 Custom Banwords ({len(custom)})"

    if len(content) <= 1024:
        embed = make_embed(title=title, description=content, color=EMBED_COLOR_INFO)
        await ctx.send(embed=embed)
    else:
        # Send via DM if too long
        try:
            await ctx.author.send(embed=make_embed(title=title, description=content, color=EMBED_COLOR_INFO))
            await ctx.send(embed=make_embed(description="📬 The banword list was too long – sent to your DMs.", color=EMBED_COLOR_INFO))
        except discord.Forbidden:
            # Chunk into multiple embeds
            chunks = []
            current = []
            cur_len = 0
            for word in custom:
                entry = f"`{word}`, "
                if cur_len + len(entry) > 1000:
                    chunks.append(current)
                    current = [word]
                    cur_len = len(entry)
                else:
                    current.append(word)
                    cur_len += len(entry)
            if current:
                chunks.append(current)

            for i, chunk in enumerate(chunks, 1):
                embed = make_embed(
                    title=f"{title} (Page {i}/{len(chunks)})",
                    description=", ".join(f"`{w}`" for w in chunk),
                    color=EMBED_COLOR_INFO,
                )
                await ctx.send(embed=embed)


@banword_group.command(name="clear")
@commands.has_permissions(administrator=True)
async def banword_clear(ctx: commands.Context):
    db.clear_badwords(ctx.guild.id)
    regex_cache.invalidate(ctx.guild.id)
    await db.save()
    embed = make_embed(description="✅ All custom banwords have been cleared.", color=EMBED_COLOR_INFO)
    await ctx.send(embed=embed)


# ─────────────────────────────────────────────────────────────────────────────
# 🛑  DISCORD NATIVE AUTOMOD INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────
async def _get_automod_rule(guild: discord.Guild, name: str):
    """Fetch an existing AutoMod rule by name."""
    try:
        rules = await guild.fetch_automod_rules()
        for rule in rules:
            if rule.name == name:
                return rule
    except discord.Forbidden:
        pass
    return None


@bot.group(name="automod", invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def automod_group(ctx: commands.Context):
    embed = make_embed(
        title="❌ Invalid Usage",
        description=(
            "**Subcommands:**\n"
            "`am!automod spam <on/off>`\n"
            "`am!automod invites <on/off>`\n"
            "`am!automod links <on/off>`\n"
            "`am!automod sync`"
        ),
        color=EMBED_COLOR_ERROR,
    )
    await ctx.send(embed=embed)


@automod_group.command(name="spam")
@commands.has_permissions(administrator=True)
async def automod_spam(ctx: commands.Context, state: str):
    state = state.lower()
    if state not in ("on", "off"):
        await ctx.send(embed=make_embed(description="❌ Use `on` or `off`.", color=EMBED_COLOR_ERROR))
        return

    rule_name = "AuraFlex – Anti-Spam"
    existing = await _get_automod_rule(ctx.guild, rule_name)

    try:
        if state == "on":
            if existing:
                await existing.edit(enabled=True, reason="AuraFlex: spam on")
                msg = "✅ Native Anti-Spam rule **enabled**."
            else:
                await ctx.guild.create_automod_rule(
                    name=rule_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.mention_spam,
                        mention_total_limit=5,
                    ),
                    actions=[
                        discord.AutoModRuleAction(
                            type=discord.AutoModRuleActionType.block_message
                        )
                    ],
                    enabled=True,
                    reason="AuraFlex: spam rule created",
                )
                msg = "✅ Native Anti-Spam rule **created and enabled**."
        else:
            if existing:
                await existing.edit(enabled=False, reason="AuraFlex: spam off")
                msg = "✅ Native Anti-Spam rule **disabled**."
            else:
                msg = "ℹ️ No spam rule exists to disable."

        await ctx.send(embed=make_embed(description=msg, color=EMBED_COLOR_INFO))

    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to manage AutoMod rules.", color=EMBED_COLOR_ERROR))
    except discord.HTTPException as e:
        await ctx.send(embed=make_embed(description=f"❌ Discord error: {e}", color=EMBED_COLOR_ERROR))


@automod_group.command(name="invites")
@commands.has_permissions(administrator=True)
async def automod_invites(ctx: commands.Context, state: str):
    state = state.lower()
    if state not in ("on", "off"):
        await ctx.send(embed=make_embed(description="❌ Use `on` or `off`.", color=EMBED_COLOR_ERROR))
        return

    rule_name = "AuraFlex – Block Invites"
    existing = await _get_automod_rule(ctx.guild, rule_name)

    try:
        if state == "on":
            if existing:
                await existing.edit(enabled=True, reason="AuraFlex: invites on")
                msg = "✅ Invite-link blocking rule **enabled**."
            else:
                await ctx.guild.create_automod_rule(
                    name=rule_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=["discord.gg/*", "discord.com/invite/*"],
                    ),
                    actions=[
                        discord.AutoModRuleAction(
                            type=discord.AutoModRuleActionType.block_message
                        )
                    ],
                    enabled=True,
                    reason="AuraFlex: invites rule created",
                )
                msg = "✅ Invite-link blocking rule **created and enabled**."
        else:
            if existing:
                await existing.edit(enabled=False, reason="AuraFlex: invites off")
                msg = "✅ Invite-link blocking rule **disabled**."
            else:
                msg = "ℹ️ No invite-block rule exists to disable."

        await ctx.send(embed=make_embed(description=msg, color=EMBED_COLOR_INFO))

    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to manage AutoMod rules.", color=EMBED_COLOR_ERROR))
    except discord.HTTPException as e:
        await ctx.send(embed=make_embed(description=f"❌ Discord error: {e}", color=EMBED_COLOR_ERROR))


@automod_group.command(name="links")
@commands.has_permissions(administrator=True)
async def automod_links(ctx: commands.Context, state: str):
    state = state.lower()
    if state not in ("on", "off"):
        await ctx.send(embed=make_embed(description="❌ Use `on` or `off`.", color=EMBED_COLOR_ERROR))
        return

    rule_name = "AuraFlex – Block Links"
    existing = await _get_automod_rule(ctx.guild, rule_name)

    try:
        if state == "on":
            if existing:
                await existing.edit(enabled=True, reason="AuraFlex: links on")
                msg = "✅ External link blocking rule **enabled**."
            else:
                await ctx.guild.create_automod_rule(
                    name=rule_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=["http://*", "https://*"],
                    ),
                    actions=[
                        discord.AutoModRuleAction(
                            type=discord.AutoModRuleActionType.block_message
                        )
                    ],
                    enabled=True,
                    reason="AuraFlex: links rule created",
                )
                msg = "✅ External link blocking rule **created and enabled**."
        else:
            if existing:
                await existing.edit(enabled=False, reason="AuraFlex: links off")
                msg = "✅ External link blocking rule **disabled**."
            else:
                msg = "ℹ️ No link-block rule exists to disable."

        await ctx.send(embed=make_embed(description=msg, color=EMBED_COLOR_INFO))

    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to manage AutoMod rules.", color=EMBED_COLOR_ERROR))
    except discord.HTTPException as e:
        await ctx.send(embed=make_embed(description=f"❌ Discord error: {e}", color=EMBED_COLOR_ERROR))


@automod_group.command(name="sync")
@commands.has_permissions(administrator=True)
async def automod_sync(ctx: commands.Context):
    """Push custom JSON banwords into Discord Native AutoMod."""
    custom = db.get_custom_badwords(ctx.guild.id)
    if not custom:
        await ctx.send(embed=make_embed(description="ℹ️ No custom banwords to sync.", color=EMBED_COLOR_INFO))
        return

    rule_name = "AuraFlex – Custom Banwords Sync"
    existing  = await _get_automod_rule(ctx.guild, rule_name)

    # Discord AutoMod keyword filter has a 1000 keyword limit
    keywords = custom[:1000]

    try:
        if existing:
            await existing.edit(
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    keyword_filter=keywords,
                ),
                enabled=True,
                reason="AuraFlex: sync banwords",
            )
            msg = f"✅ Synced **{len(keywords)}** banword(s) to Discord AutoMod (rule updated)."
        else:
            await ctx.guild.create_automod_rule(
                name=rule_name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    keyword_filter=keywords,
                ),
                actions=[
                    discord.AutoModRuleAction(
                        type=discord.AutoModRuleActionType.block_message
                    )
                ],
                enabled=True,
                reason="AuraFlex: sync banwords",
            )
            msg = f"✅ Synced **{len(keywords)}** banword(s) to Discord AutoMod (rule created)."

        await ctx.send(embed=make_embed(description=msg, color=EMBED_COLOR_INFO))

    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to manage AutoMod rules.", color=EMBED_COLOR_ERROR))
    except discord.HTTPException as e:
        await ctx.send(embed=make_embed(description=f"❌ Discord error: {e}", color=EMBED_COLOR_ERROR))


# ─────────────────────────────────────────────────────────────────────────────
# 🔨  MANUAL MODERATION COMMANDS
# ─────────────────────────────────────────────────────────────────────────────
@bot.command(name="timeout", usage="am!timeout <@user> [mins] [reason]")
@commands.has_permissions(moderate_members=True)
async def timeout_cmd(ctx: commands.Context, member: discord.Member, mins: int = 5, *, reason: str = "No reason provided"):
    if is_admin(member):
        await ctx.send(embed=make_embed(description="❌ You cannot timeout an administrator.", color=EMBED_COLOR_ERROR))
        return

    seconds = mins * 60
    err = await apply_timeout(member, seconds, reason)
    if err:
        embed = make_embed(description=f"❌ {err}", color=EMBED_COLOR_ERROR)
    else:
        embed = make_embed(
            title="⏱️ User Timed Out",
            color=EMBED_COLOR_INFO,
            fields=[
                ("User",     f"{member.mention} (`{member.id}`)", True),
                ("Duration", f"{mins} minute(s)",                 True),
                ("Reason",   reason,                              False),
                ("Moderator", ctx.author.mention,                 True),
            ],
        )
        # Log
        await send_log(ctx.guild, make_embed(
            title="⏱️ Manual Timeout Applied",
            color=EMBED_COLOR_ERROR,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Duration",  f"{mins} minute(s)",         True),
                ("Reason",    reason,                      False),
                ("Moderator", str(ctx.author),             True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    await ctx.send(embed=embed)


@bot.command(name="untimeout", usage="am!untimeout <@user>")
@commands.has_permissions(moderate_members=True)
async def untimeout_cmd(ctx: commands.Context, member: discord.Member):
    try:
        await member.timeout(None, reason=f"Timeout removed by {ctx.author}")
        embed = make_embed(description=f"✅ Timeout removed for {member.mention}.", color=EMBED_COLOR_INFO)
        await send_log(ctx.guild, make_embed(
            title="✅ Timeout Removed",
            color=EMBED_COLOR_INFO,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Moderator", str(ctx.author),             True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        embed = make_embed(description="❌ I lack permissions to remove this timeout.", color=EMBED_COLOR_ERROR)
    except discord.HTTPException as e:
        embed = make_embed(description=f"❌ Error: {e}", color=EMBED_COLOR_ERROR)
    await ctx.send(embed=embed)


@bot.command(name="warn", usage="am!warn <@user> [reason]")
@commands.has_permissions(manage_messages=True)
async def warn_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if is_admin(member):
        await ctx.send(embed=make_embed(description="❌ You cannot warn an administrator.", color=EMBED_COLOR_ERROR))
        return

    warn_count = db.add_warning(ctx.guild.id, member.id, reason)
    await db.save()

    embed = make_embed(
        title="⚠️ Warning Issued",
        color=EMBED_COLOR_ERROR,
        fields=[
            ("User",           f"{member.mention} (`{member.id}`)", True),
            ("Total Warnings", f"{warn_count}/{MAX_WARNINGS}",      True),
            ("Reason",         reason,                              False),
            ("Moderator",      ctx.author.mention,                  True),
        ],
    )
    await ctx.send(embed=embed)

    # Auto-timeout at MAX_WARNINGS
    if warn_count >= MAX_WARNINGS:
        err = await apply_timeout(member, 3600, f"Reached {MAX_WARNINGS} warnings")
        auto_action = "⏱️ Auto-timed out for 1 hour (max warnings reached)"
        if err:
            auto_action = f"⚠️ Could not auto-timeout: {err}"
        notice = make_embed(description=auto_action, color=EMBED_COLOR_ERROR)
        await ctx.send(embed=notice)

    # Log
    await send_log(ctx.guild, make_embed(
        title="⚠️ Warning Issued",
        color=EMBED_COLOR_ERROR,
        fields=[
            ("User",           f"{member} (`{member.id}`)", True),
            ("Total Warnings", f"{warn_count}/{MAX_WARNINGS}", True),
            ("Reason",         reason,                       False),
            ("Moderator",      str(ctx.author),              True),
        ],
        footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ))


@bot.command(name="warnings", usage="am!warnings <@user>")
@commands.has_permissions(manage_messages=True)
async def warnings_cmd(ctx: commands.Context, member: discord.Member):
    warns = db.get_warnings(ctx.guild.id, member.id)
    if not warns:
        embed = make_embed(
            description=f"✅ {member.mention} has no warnings.",
            color=EMBED_COLOR_INFO,
        )
    else:
        lines = "\n".join(
            f"**{i+1}.** {w['reason']} — <t:{int(datetime.datetime.fromisoformat(w['timestamp'].rstrip('Z')).timestamp())}:R>"
            for i, w in enumerate(warns)
        )
        embed = make_embed(
            title=f"⚠️ Warnings for {member.display_name}",
            description=lines,
            color=EMBED_COLOR_ERROR,
            fields=[("Total", f"{len(warns)}/{MAX_WARNINGS}", True)],
        )
    await ctx.send(embed=embed)


@bot.command(name="clearwarns", usage="am!clearwarns <@user>")
@commands.has_permissions(manage_messages=True)
async def clearwarns_cmd(ctx: commands.Context, member: discord.Member):
    db.clear_warnings(ctx.guild.id, member.id)
    await db.save()
    embed = make_embed(
        description=f"✅ Cleared all warnings for {member.mention}.",
        color=EMBED_COLOR_INFO,
    )
    await ctx.send(embed=embed)
    await send_log(ctx.guild, make_embed(
        title="🗑️ Warnings Cleared",
        color=EMBED_COLOR_INFO,
        fields=[
            ("User",      f"{member} (`{member.id}`)", True),
            ("Moderator", str(ctx.author),             True),
        ],
        footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ))


@bot.command(name="kick", usage="am!kick <@user> [reason]")
@commands.has_permissions(kick_members=True)
@commands.bot_has_permissions(kick_members=True)
async def kick_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if is_admin(member):
        await ctx.send(embed=make_embed(description="❌ You cannot kick an administrator.", color=EMBED_COLOR_ERROR))
        return
    try:
        await member.kick(reason=f"{ctx.author}: {reason}")
        embed = make_embed(
            title="👢 User Kicked",
            color=EMBED_COLOR_INFO,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Reason",    reason,                      False),
                ("Moderator", ctx.author.mention,          True),
            ],
        )
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="👢 User Kicked",
            color=EMBED_COLOR_ERROR,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Reason",    reason,                      False),
                ("Moderator", str(ctx.author),             True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permissions to kick this user.", color=EMBED_COLOR_ERROR))


@bot.command(name="ban", usage="am!ban <@user> [reason]")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def ban_cmd(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    if is_admin(member):
        await ctx.send(embed=make_embed(description="❌ You cannot ban an administrator.", color=EMBED_COLOR_ERROR))
        return
    try:
        await member.ban(reason=f"{ctx.author}: {reason}", delete_message_days=1)
        embed = make_embed(
            title="🔨 User Banned",
            color=EMBED_COLOR_INFO,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Reason",    reason,                      False),
                ("Moderator", ctx.author.mention,          True),
            ],
        )
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="🔨 User Banned",
            color=EMBED_COLOR_ERROR,
            fields=[
                ("User",      f"{member} (`{member.id}`)", True),
                ("Reason",    reason,                      False),
                ("Moderator", str(ctx.author),             True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permissions to ban this user.", color=EMBED_COLOR_ERROR))


@bot.command(name="unban", usage="am!unban <user_id>")
@commands.has_permissions(ban_members=True)
@commands.bot_has_permissions(ban_members=True)
async def unban_cmd(ctx: commands.Context, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author}")
        embed = make_embed(
            title="✅ User Unbanned",
            description=f"**{user}** (`{user.id}`) has been unbanned.",
            color=EMBED_COLOR_INFO,
        )
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="✅ User Unbanned",
            color=EMBED_COLOR_INFO,
            fields=[
                ("User",      f"{user} (`{user.id}`)", True),
                ("Moderator", str(ctx.author),         True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.NotFound:
        await ctx.send(embed=make_embed(description="❌ No ban found for that user ID.", color=EMBED_COLOR_ERROR))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permissions to unban.", color=EMBED_COLOR_ERROR))
    except discord.HTTPException as e:
        await ctx.send(embed=make_embed(description=f"❌ Error: {e}", color=EMBED_COLOR_ERROR))


# ─────────────────────────────────────────────────────────────────────────────
# 🔐  SERVER SECURITY & UTILITY
# ─────────────────────────────────────────────────────────────────────────────
@bot.command(name="purge", usage="am!purge <1-100>")
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def purge_cmd(ctx: commands.Context, amount: int):
    if not 1 <= amount <= 100:
        await ctx.send(
            embed=make_embed(description="❌ Amount must be between **1** and **100**.", color=EMBED_COLOR_ERROR),
            delete_after=5,
        )
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include the command msg
        embed = make_embed(
            description=f"🗑️ Deleted **{len(deleted) - 1}** message(s).",
            color=EMBED_COLOR_INFO,
        )
        confirm = await ctx.send(embed=embed)
        await asyncio.sleep(4)
        try:
            await confirm.delete()
        except discord.NotFound:
            pass
        await send_log(ctx.guild, make_embed(
            title="🗑️ Purge Executed",
            color=EMBED_COLOR_INFO,
            fields=[
                ("Channel",   ctx.channel.mention,  True),
                ("Count",     str(len(deleted) - 1), True),
                ("Moderator", str(ctx.author),        True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to delete messages here.", color=EMBED_COLOR_ERROR))


@bot.command(name="lockdown")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lockdown_cmd(ctx: commands.Context):
    overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = False
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Lockdown by {ctx.author}")
        embed = make_embed(
            title="🔒 Channel Locked",
            description=f"{ctx.channel.mention} has been locked. No one can send messages.",
            color=EMBED_COLOR_ERROR,
        )
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="🔒 Lockdown Activated",
            color=EMBED_COLOR_ERROR,
            fields=[
                ("Channel",   ctx.channel.mention, True),
                ("Moderator", str(ctx.author),      True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to modify this channel.", color=EMBED_COLOR_ERROR))


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock_cmd(ctx: commands.Context):
    overwrites = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrites.send_messages = None  # Reset to default
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrites, reason=f"Unlock by {ctx.author}")
        embed = make_embed(
            title="🔓 Channel Unlocked",
            description=f"{ctx.channel.mention} has been unlocked.",
            color=EMBED_COLOR_INFO,
        )
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="🔓 Channel Unlocked",
            color=EMBED_COLOR_INFO,
            fields=[
                ("Channel",   ctx.channel.mention, True),
                ("Moderator", str(ctx.author),      True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to modify this channel.", color=EMBED_COLOR_ERROR))


@bot.command(name="slowmode", usage="am!slowmode <seconds>")
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def slowmode_cmd(ctx: commands.Context, seconds: int):
    if not 0 <= seconds <= 21600:
        await ctx.send(embed=make_embed(description="❌ Slowmode must be between **0** and **21600** seconds.", color=EMBED_COLOR_ERROR))
        return
    try:
        await ctx.channel.edit(slowmode_delay=seconds, reason=f"Slowmode by {ctx.author}")
        if seconds == 0:
            msg = f"✅ Slowmode **disabled** in {ctx.channel.mention}."
        else:
            msg = f"⏱️ Slowmode set to **{seconds}s** in {ctx.channel.mention}."
        embed = make_embed(description=msg, color=EMBED_COLOR_INFO)
        await ctx.send(embed=embed)
        await send_log(ctx.guild, make_embed(
            title="⏱️ Slowmode Updated",
            color=EMBED_COLOR_INFO,
            fields=[
                ("Channel",   ctx.channel.mention,    True),
                ("Delay",     f"{seconds}s",           True),
                ("Moderator", str(ctx.author),          True),
            ],
            footer=f"AuraFlex Security • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ))
    except discord.Forbidden:
        await ctx.send(embed=make_embed(description="❌ I lack permission to modify this channel.", color=EMBED_COLOR_ERROR))


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Invalid Discord token. Please check TOKEN in bot.py.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down AuraFlex Mod...")
    finally:
        # Clean shutdown of aiohttp session
        loop = asyncio.new_event_loop()
        loop.run_until_complete(groq_client.close())
        loop.close()
        ai_queue.stop()