# bot.py - AT! TICKET BOT WITH GROQ AI (FIXED)
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Select, Modal, TextInput
import json
import datetime
import asyncio
import aiohttp
from io import BytesIO

# ═══════════════════════════════════════════════════════════════
#                    🔑 CONFIGURATION
# ═══════════════════════════════════════════════════════════════

GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="at!", intents=intents, help_command=None)

DEFAULT_CONFIG = {
    "ticket_category": None,
    "log_channel": None,
    "support_role": None,
    "admin_role": None,
    "ticket_channel": None,
    "max_tickets": 3,
    "auto_close_hours": 48,
    "welcome_message": None,
    "close_message": None,
    "ticket_number": 0,
    "feedback_enabled": True,
    "auto_ping_staff": True,
    "claim_enabled": True,
    "priority_enabled": True,
    "blacklisted_users": [],
    "ticket_categories": {
        "🆘 General Support": "general",
        "💰 Billing & Purchases": "billing",
        "🐛 Bug Report": "bug",
        "💡 Suggestion": "suggestion",
        "🤝 Partnership": "partnership",
        "📋 Application": "application"
    },
    "dm_on_close": True,
    "require_reason": True,
    "ai_enabled": True,
    "ai_system_prompt": None,
    "server_info": ""
}

DEFAULT_STATS = {
    "total_tickets": 0,
    "closed_tickets": 0
}

# ═══════════════════════════════════════════════════════════════
#                    🕐 TIMEZONE-AWARE UTC HELPER
# ═══════════════════════════════════════════════════════════════

def utcnow():
    """Returns timezone-aware UTC datetime (no deprecation warning)"""
    return datetime.datetime.now(datetime.timezone.utc)

def utcnow_iso():
    """Returns UTC ISO string"""
    return utcnow().isoformat()

def parse_iso(iso_string):
    """Parse ISO string safely, handles both aware and naive"""
    dt = datetime.datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt

def utc_timestamp():
    """Returns UTC timestamp as int"""
    return int(utcnow().timestamp())

# ═══════════════════════════════════════════════════════════════
#                    🎨 STYLING
# ═══════════════════════════════════════════════════════════════

COLORS = {
    "main": 0x2B2D31,
    "success": 0x57F287,
    "warning": 0xFEE75C,
    "danger": 0xED4245,
    "info": 0x5865F2,
    "purple": 0x9B59B6,
    "pink": 0xFF79C6,
    "gold": 0xF1C40F,
    "teal": 0x1ABC9C,
    "blurple": 0x5865F2,
    "white": 0xFEFEFE,
    "dark": 0x2B2D31
}

E = {
    "ticket": "🎫", "close": "🔐", "open": "🔓", "claim": "✋",
    "priority": "⚡", "transcript": "📄", "delete": "🗑️",
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "💠",
    "star": "⭐", "user": "👤", "staff": "🛡️", "admin": "👑",
    "clock": "🕐", "ai": "🤖", "pin": "📌", "edit": "✏️",
    "send": "📨", "stats": "📊", "gear": "⚙️", "rocket": "🚀",
    "sparkle": "✨", "fire": "🔥", "heart": "💜", "arrow": "➜",
    "dot": "•", "loading": "⏳"
}

DIV = "───────────────────────────"


def make_embed(desc="", color="main", footer=None, thumb=None):
    embed = discord.Embed(
        description=desc,
        color=COLORS.get(color, COLORS["main"]),
        timestamp=utcnow()
    )
    bot_icon = bot.user.avatar.url if (bot.user and bot.user.avatar) else None
    embed.set_footer(
        text=footer or "AuraFlex Ticket System ✦ Powered by Groq AI",
        icon_url=bot_icon
    )
    if thumb:
        embed.set_thumbnail(url=thumb)
    return embed

# ═══════════════════════════════════════════════════════════════
#                    💾 DATA MANAGEMENT (FIXED)
# ═══════════════════════════════════════════════════════════════

def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)


def ensure_guild(data, guild_id):
    """Make sure guild data exists with ALL required keys"""
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {
            "config": DEFAULT_CONFIG.copy(),
            "tickets": {},
            "stats": DEFAULT_STATS.copy()
        }
    else:
        # Ensure stats keys exist
        if "stats" not in data[gid]:
            data[gid]["stats"] = DEFAULT_STATS.copy()
        for key, val in DEFAULT_STATS.items():
            if key not in data[gid]["stats"]:
                data[gid]["stats"][key] = val

        # Ensure config keys exist
        if "config" not in data[gid]:
            data[gid]["config"] = DEFAULT_CONFIG.copy()
        for key, val in DEFAULT_CONFIG.items():
            if key not in data[gid]["config"]:
                data[gid]["config"][key] = val

        # Ensure tickets dict exists
        if "tickets" not in data[gid]:
            data[gid]["tickets"] = {}

    return data


def get_config(guild_id):
    data = load_data()
    data = ensure_guild(data, guild_id)
    save_data(data)
    return data[str(guild_id)]


def update_config(guild_id, config):
    data = load_data()
    data = ensure_guild(data, guild_id)
    data[str(guild_id)]["config"] = config
    save_data(data)


def save_ticket(guild_id, channel_id, ticket):
    data = load_data()
    data = ensure_guild(data, guild_id)
    data[str(guild_id)]["tickets"][str(channel_id)] = ticket
    save_data(data)


def get_ticket(guild_id, channel_id):
    data = load_data()
    gid, cid = str(guild_id), str(channel_id)
    return data.get(gid, {}).get("tickets", {}).get(cid)


def remove_ticket(guild_id, channel_id):
    data = load_data()
    gid, cid = str(guild_id), str(channel_id)
    if gid in data and cid in data[gid].get("tickets", {}):
        del data[gid]["tickets"][cid]
        save_data(data)


def increment_stat(guild_id, stat_key):
    """Safely increment a stat counter"""
    data = load_data()
    data = ensure_guild(data, guild_id)
    gid = str(guild_id)
    data[gid]["stats"][stat_key] = data[gid]["stats"].get(stat_key, 0) + 1
    save_data(data)

# ═══════════════════════════════════════════════════════════════
#                    🤖 GROQ AI ENGINE
# ═══════════════════════════════════════════════════════════════

ai_conversations = {}


async def get_ai_response(channel_id, user_message, guild, ticket_data, config):
    cid = str(channel_id)
    if cid not in ai_conversations:
        ai_conversations[cid] = []

    server_info = config.get("server_info", "")
    category = ticket_data.get("category", "general")

    system_prompt = config.get("ai_system_prompt") or (
        f"You are **AuraFlex Assistant** — a helpful, friendly AI support assistant "
        f"for the Discord server **{guild.name}**.\n\n"
        f"## YOUR PERSONALITY:\n"
        f"- Warm, patient, genuinely helpful\n"
        f"- Use **bold**, *italics*, and emojis naturally\n"
        f"- Give step-by-step instructions when needed\n"
        f"- Concise but thorough\n\n"
        f"## CONTEXT:\n"
        f"- This is a **{category}** support ticket\n"
        f"- Server: **{guild.name}**\n"
        f"- You know Discord features (invites, roles, channels, permissions, bots, etc.)\n"
        f"{'- Server info: ' + server_info if server_info else ''}\n\n"
        f"## RULES:\n"
        f"- If you can't help: say *'A staff member will assist you shortly!'*\n"
        f"- NEVER make up server rules/info you don't know\n"
        f"- Keep responses under 1500 characters\n"
        f"- If asked something inappropriate, politely decline\n"
        f"- Format complex answers with numbered steps\n"
    )

    ai_conversations[cid].append({"role": "user", "content": user_message})

    if len(ai_conversations[cid]) > 15:
        ai_conversations[cid] = ai_conversations[cid][-15:]

    messages = [{"role": "system", "content": system_prompt}] + ai_conversations[cid]

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": messages,
                "max_tokens": 800,
                "temperature": 0.7,
                "top_p": 0.9
            }

            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ai_reply = data["choices"][0]["message"]["content"]
                    ai_conversations[cid].append({"role": "assistant", "content": ai_reply})
                    return ai_reply
                else:
                    err = await resp.text()
                    print(f"[Groq API Error] {resp.status}: {err}")
                    return None
    except Exception as ex:
        print(f"[AI Error] {ex}")
        return None


def clear_ai_conversation(channel_id):
    cid = str(channel_id)
    if cid in ai_conversations:
        del ai_conversations[cid]

# ═══════════════════════════════════════════════════════════════
#                    📝 MODALS
# ═══════════════════════════════════════════════════════════════

class TicketReasonModal(Modal, title="✨ Tell us what's up"):
    reason = TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe your issue, question, or request...",
        required=True,
        max_length=1000
    )

    def __init__(self, category):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.category, self.reason.value)


class CloseReasonModal(Modal, title="🔐 Close this ticket"):
    reason = TextInput(
        label="Why are you closing this ticket?",
        style=discord.TextStyle.paragraph,
        placeholder="Brief reason for closing...",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        await close_ticket(interaction, self.reason.value)


class FeedbackModal(Modal, title="⭐ Rate your experience"):
    rating = TextInput(
        label="Rating (1-5)",
        style=discord.TextStyle.short,
        placeholder="5",
        required=True,
        max_length=1
    )
    feedback = TextInput(
        label="Tell us more (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="How was your support experience?",
        required=False,
        max_length=500
    )

    def __init__(self, ticket_channel_id):
        super().__init__()
        self.ticket_channel_id = ticket_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.rating.value)
            if val < 1 or val > 5:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                f"{E['error']} **Enter a number from 1 to 5!**", ephemeral=True
            )

        stars = "★" * val + "☆" * (5 - val)
        star_emojis = "⭐" * val

        guild_data = get_config(interaction.guild.id)
        config = guild_data["config"]

        if config.get("log_channel"):
            log_ch = interaction.guild.get_channel(int(config["log_channel"]))
            if log_ch:
                embed = make_embed(
                    desc=(
                        f"## ⭐ Feedback Received\n{DIV}\n\n"
                        f"**{E['user']} From** {E['arrow']} {interaction.user.mention}\n"
                        f"**{E['star']} Rating** {E['arrow']} {star_emojis} `{val}/5`\n"
                        f"**{E['star']} Stars** {E['arrow']} `{stars}`\n\n"
                        f"**{E['edit']} Feedback:**\n"
                        f"> {self.feedback.value or '*No additional feedback*'}"
                    ),
                    color="gold"
                )
                await log_ch.send(embed=embed)

        await interaction.response.send_message(
            f"**Thank you!** {star_emojis}\n> Your feedback helps us improve {E['heart']}",
            ephemeral=True
        )


class WelcomeMessageModal(Modal, title="✏️ Custom Welcome Message"):
    message = TextInput(
        label="Welcome Message",
        style=discord.TextStyle.paragraph,
        placeholder="{user} = mention, {server} = server name",
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_data = get_config(interaction.guild.id)
        guild_data["config"]["welcome_message"] = self.message.value
        update_config(interaction.guild.id, guild_data["config"])
        embed = make_embed(
            desc=(
                f"## {E['success']} Welcome Message Updated\n{DIV}\n\n"
                f"**New message:**\n>>> {self.message.value[:500]}"
            ),
            color="success"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ServerInfoModal(Modal, title="📝 Server Info for AI"):
    info = TextInput(
        label="Tell the AI about your server",
        style=discord.TextStyle.paragraph,
        placeholder="e.g. We sell Minecraft ranks. Use /buy to purchase. Rules are in #rules...",
        required=True,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_data = get_config(interaction.guild.id)
        guild_data["config"]["server_info"] = self.info.value
        update_config(interaction.guild.id, guild_data["config"])
        embed = make_embed(
            desc=(
                f"## {E['ai']} AI Knowledge Updated\n{DIV}\n\n"
                f"The AI will now use this info:\n>>> {self.info.value[:500]}"
            ),
            color="success"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════════════
#                    🖱️ VIEWS & BUTTONS
# ═══════════════════════════════════════════════════════════════

class TicketCategorySelect(Select):
    def __init__(self, categories):
        options = []
        emoji_map = {
            "general": "🆘", "billing": "💰", "bug": "🐛",
            "suggestion": "💡", "partnership": "🤝", "application": "📋"
        }
        for label, value in categories.items():
            e = emoji_map.get(value, "📌")
            clean = label
            for em in emoji_map.values():
                clean = clean.replace(em + " ", "")
            options.append(discord.SelectOption(
                label=clean[:25], value=value, emoji=e,
                description=f"Create a {value} ticket"
            ))
        super().__init__(
            placeholder="◈ Choose your ticket type...",
            min_values=1, max_values=1, options=options,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        guild_data = get_config(interaction.guild.id)
        config = guild_data["config"]

        if str(interaction.user.id) in config.get("blacklisted_users", []):
            return await interaction.response.send_message(
                f"{E['error']} **You're blacklisted from creating tickets.**", ephemeral=True
            )

        open_count = sum(
            1 for t in guild_data.get("tickets", {}).values()
            if t.get("user_id") == str(interaction.user.id) and t.get("status") == "open"
        )

        if open_count >= config.get("max_tickets", 3):
            embed = make_embed(
                desc=(
                    f"## {E['error']} Ticket Limit Reached\n{DIV}\n\n"
                    f"You have **{open_count}** open ticket(s).\n"
                    f"Maximum allowed: **{config['max_tickets']}**\n\n"
                    f"> *Close an existing ticket first!*"
                ),
                color="danger"
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if config.get("require_reason", True):
            await interaction.response.send_modal(TicketReasonModal(self.values[0]))
        else:
            await create_ticket(interaction, self.values[0], "No reason specified")


class TicketPanelView(View):
    def __init__(self, categories):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories))


class TicketControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", emoji="🔐", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_btn(self, interaction: discord.Interaction, button: Button):
        guild_data = get_config(interaction.guild.id)
        if guild_data["config"].get("require_reason", True):
            await interaction.response.send_modal(CloseReasonModal())
        else:
            await close_ticket(interaction, "No reason")

    @discord.ui.button(label="Claim", emoji="✋", style=discord.ButtonStyle.success, custom_id="ticket_claim")
    async def claim_btn(self, interaction: discord.Interaction, button: Button):
        ticket = get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(f"{E['error']} **Not a ticket!**", ephemeral=True)

        guild_data = get_config(interaction.guild.id)
        config = guild_data["config"]
        sr = interaction.guild.get_role(int(config["support_role"])) if config.get("support_role") else None
        ar = interaction.guild.get_role(int(config["admin_role"])) if config.get("admin_role") else None

        is_staff = interaction.user.guild_permissions.administrator
        if sr and sr in interaction.user.roles:
            is_staff = True
        if ar and ar in interaction.user.roles:
            is_staff = True

        if not is_staff:
            return await interaction.response.send_message(f"{E['error']} **Staff only!**", ephemeral=True)

        if ticket.get("claimed_by"):
            return await interaction.response.send_message(
                f"{E['error']} **Already claimed by <@{ticket['claimed_by']}>!**", ephemeral=True
            )

        ticket["claimed_by"] = str(interaction.user.id)
        save_ticket(interaction.guild.id, interaction.channel.id, ticket)

        embed = make_embed(
            desc=(
                f"## {E['claim']} Ticket Claimed\n{DIV}\n\n"
                f"{E['staff']} **{interaction.user.display_name}** has claimed this ticket\n\n"
                f"> {E['ai']} *AI Assistant has been paused — a real human is here!*\n"
                f"> They'll handle your issue from here {E['heart']}"
            ),
            color="success"
        )
        await interaction.response.send_message(embed=embed)
        await log_action(interaction.guild, f"{E['claim']} Ticket Claimed",
                         f"**Staff:** {interaction.user.mention}\n**Channel:** {interaction.channel.mention}", "info")

    @discord.ui.button(label="Priority", emoji="⚡", style=discord.ButtonStyle.secondary, custom_id="ticket_priority")
    async def priority_btn(self, interaction: discord.Interaction, button: Button):
        ticket = get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(f"{E['error']} **Not a ticket!**", ephemeral=True)

        guild_data = get_config(interaction.guild.id)
        config = guild_data["config"]
        sr = interaction.guild.get_role(int(config["support_role"])) if config.get("support_role") else None
        is_staff = interaction.user.guild_permissions.administrator
        if sr and sr in interaction.user.roles:
            is_staff = True

        if not is_staff:
            return await interaction.response.send_message(f"{E['error']} **Staff only!**", ephemeral=True)

        await interaction.response.send_message(
            f"**{E['priority']} Select priority level:**",
            view=PrioritySelectView(), ephemeral=True
        )

    @discord.ui.button(label="Transcript", emoji="📄", style=discord.ButtonStyle.secondary, custom_id="ticket_transcript")
    async def transcript_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        await generate_transcript(interaction.channel, interaction)


class PrioritySelectView(View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(placeholder="◈ Select priority...", options=[
        discord.SelectOption(label="Low", value="low", emoji="🟢", description="Can wait — not urgent"),
        discord.SelectOption(label="Medium", value="medium", emoji="🟡", description="Needs attention soon"),
        discord.SelectOption(label="High", value="high", emoji="🟠", description="Urgent — needs quick fix"),
        discord.SelectOption(label="Critical", value="critical", emoji="🔴", description="EMERGENCY")
    ])
    async def select(self, interaction: discord.Interaction, select: Select):
        ticket = get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(f"{E['error']} **Error!**", ephemeral=True)

        p = {"low": ("🟢", "Low"), "medium": ("🟡", "Medium"), "high": ("🟠", "High"), "critical": ("🔴", "Critical")}
        emoji, name = p[select.values[0]]
        ticket["priority"] = select.values[0]
        save_ticket(interaction.guild.id, interaction.channel.id, ticket)

        embed = make_embed(
            desc=f"## {emoji} Priority → **{name}**\n{DIV}\n\nUpdated by {interaction.user.mention}",
            color="warning" if select.values[0] in ["high", "critical"] else "info"
        )
        await interaction.response.send_message(embed=embed)


class TicketDeleteView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="ticket_delete")
    async def delete_btn(self, interaction: discord.Interaction, button: Button):
        embed = make_embed(
            desc=f"## {E['delete']} Deleting in 5 seconds...\n> Saving transcript...",
            color="danger"
        )
        await interaction.response.send_message(embed=embed)
        await save_transcript_to_log(interaction.channel, interaction.guild, interaction.user)
        clear_ai_conversation(interaction.channel.id)
        remove_ticket(interaction.guild.id, interaction.channel.id)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Reopen", emoji="🔓", style=discord.ButtonStyle.success, custom_id="ticket_reopen")
    async def reopen_btn(self, interaction: discord.Interaction, button: Button):
        ticket = get_ticket(interaction.guild.id, interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(f"{E['error']} **Error!**", ephemeral=True)

        ticket["status"] = "open"
        ticket["claimed_by"] = None
        save_ticket(interaction.guild.id, interaction.channel.id, ticket)

        user = interaction.guild.get_member(int(ticket["user_id"]))
        if user:
            try:
                await interaction.channel.set_permissions(user, send_messages=True, read_messages=True, attach_files=True)
            except:
                pass

        try:
            await interaction.channel.edit(name=interaction.channel.name.replace("closed-", "ticket-"))
        except:
            pass

        embed = make_embed(
            desc=(
                f"## {E['open']} Ticket Reopened\n{DIV}\n\n"
                f"Reopened by {interaction.user.mention}\n"
                f"> {E['ai']} *AI Assistant is back online!*"
            ),
            color="success"
        )
        await interaction.response.send_message(embed=embed)

# ═══════════════════════════════════════════════════════════════
#                    ⚙️ SETUP VIEW
# ═══════════════════════════════════════════════════════════════

class SetupView(View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(placeholder="⚙️ What do you want to configure?", options=[
        discord.SelectOption(label="Ticket Category", value="category", emoji="📁"),
        discord.SelectOption(label="Log Channel", value="log", emoji="📋"),
        discord.SelectOption(label="Support Role", value="support_role", emoji="🛡️"),
        discord.SelectOption(label="Admin Role", value="admin_role", emoji="👑"),
        discord.SelectOption(label="Max Tickets/User", value="max_tickets", emoji="🔢"),
        discord.SelectOption(label="Welcome Message", value="welcome_msg", emoji="👋"),
        discord.SelectOption(label="AI Server Info", value="ai_info", emoji="🤖"),
        discord.SelectOption(label="Toggle Features", value="toggles", emoji="🔧"),
        discord.SelectOption(label="Auto-Close Timer", value="auto_close", emoji="⏰"),
        discord.SelectOption(label="Deploy Panel", value="deploy", emoji="🚀"),
        discord.SelectOption(label="View Config", value="view", emoji="📊")
    ])
    async def select_callback(self, interaction: discord.Interaction, select: Select):
        v = select.values[0]

        if v == "welcome_msg":
            return await interaction.response.send_modal(WelcomeMessageModal())

        if v == "ai_info":
            return await interaction.response.send_modal(ServerInfoModal())

        if v == "toggles":
            guild_data = get_config(interaction.guild.id)
            c = guild_data["config"]
            embed = make_embed(
                desc=(
                    f"## {E['gear']} Feature Toggles\n{DIV}\n\n"
                    f"{'✅' if c.get('feedback_enabled') else '❌'} **Feedback on close**\n"
                    f"{'✅' if c.get('auto_ping_staff') else '❌'} **Auto-ping staff**\n"
                    f"{'✅' if c.get('claim_enabled') else '❌'} **Claim system**\n"
                    f"{'✅' if c.get('priority_enabled') else '❌'} **Priority system**\n"
                    f"{'✅' if c.get('dm_on_close') else '❌'} **DM on close**\n"
                    f"{'✅' if c.get('require_reason') else '❌'} **Require reason**\n"
                    f"{'✅' if c.get('ai_enabled', True) else '❌'} **AI Assistant**"
                ),
                color="info"
            )
            return await interaction.response.send_message(embed=embed, view=ToggleView(), ephemeral=True)

        if v == "view":
            guild_data = get_config(interaction.guild.id)
            c = guild_data["config"]
            cat = interaction.guild.get_channel(int(c["ticket_category"])) if c.get("ticket_category") else None
            log = interaction.guild.get_channel(int(c["log_channel"])) if c.get("log_channel") else None
            sr = interaction.guild.get_role(int(c["support_role"])) if c.get("support_role") else None
            ar = interaction.guild.get_role(int(c["admin_role"])) if c.get("admin_role") else None

            embed = make_embed(
                desc=(
                    f"## {E['stats']} Server Configuration\n{DIV}\n\n"
                    f"**Channels**\n"
                    f"> {E['arrow']} Category: **{cat.name if cat else '`Not Set`'}**\n"
                    f"> {E['arrow']} Logs: **{log.mention if log else '`Not Set`'}**\n\n"
                    f"**Roles**\n"
                    f"> {E['arrow']} Support: **{sr.mention if sr else '`Not Set`'}**\n"
                    f"> {E['arrow']} Admin: **{ar.mention if ar else '`Not Set`'}**\n\n"
                    f"**Settings**\n"
                    f"> {E['arrow']} Max Tickets: **{c.get('max_tickets', 3)}**\n"
                    f"> {E['arrow']} Auto Close: **{c.get('auto_close_hours', 48)}h**\n"
                    f"> {E['arrow']} AI: **{'Enabled ✅' if c.get('ai_enabled', True) else 'Disabled ❌'}**\n\n"
                    f"**Features**\n"
                    f"> {'✅' if c.get('feedback_enabled') else '❌'} Feedback "
                    f"{'✅' if c.get('auto_ping_staff') else '❌'} AutoPing "
                    f"{'✅' if c.get('claim_enabled') else '❌'} Claim\n"
                    f"> {'✅' if c.get('priority_enabled') else '❌'} Priority "
                    f"{'✅' if c.get('dm_on_close') else '❌'} DM "
                    f"{'✅' if c.get('require_reason') else '❌'} Reason"
                ),
                color="purple"
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        prompts = {
            "category": ("📁 Set Ticket Category", "Send the **category name** or **ID**:"),
            "log": ("📋 Set Log Channel", "**Mention the channel** (e.g. #ticket-logs):"),
            "support_role": ("🛡️ Set Support Role", "**Mention the role** (e.g. @Support):"),
            "admin_role": ("👑 Set Admin Role", "**Mention the role** (e.g. @Admin):"),
            "max_tickets": ("🔢 Max Tickets", "Enter a **number (1-10)**:"),
            "auto_close": ("⏰ Auto-Close", "Enter **hours** (0 = disabled, max 168):"),
            "deploy": ("🚀 Deploy Panel", "**Mention the channel** to send it in:")
        }

        title, desc = prompts[v]
        embed = make_embed(desc=f"## {title}\n{DIV}\n\n{desc}", color="info")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        def check(m):
            return m.author.id == interaction.user.id and m.guild.id == interaction.guild.id

        try:
            msg = await bot.wait_for('message', timeout=60, check=check)
        except asyncio.TimeoutError:
            return await interaction.followup.send(f"{E['error']} **Timed out!**", ephemeral=True)

        try:
            await msg.delete()
        except:
            pass

        guild_data = get_config(interaction.guild.id)
        config = guild_data["config"]

        if v == "category":
            cat = None
            try:
                cat = interaction.guild.get_channel(int(msg.content))
            except:
                for c in interaction.guild.categories:
                    if c.name.lower() == msg.content.lower():
                        cat = c
                        break
            if cat and isinstance(cat, discord.CategoryChannel):
                config["ticket_category"] = str(cat.id)
                update_config(interaction.guild.id, config)
                await interaction.followup.send(embed=make_embed(
                    desc=f"## {E['success']} Category set to **{cat.name}**", color="success"), ephemeral=True)
            else:
                await interaction.followup.send(f"{E['error']} **Not found!**", ephemeral=True)

        elif v == "log":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if not ch:
                try:
                    ch = interaction.guild.get_channel(int(msg.content))
                except:
                    pass
            if ch:
                config["log_channel"] = str(ch.id)
                update_config(interaction.guild.id, config)
                await interaction.followup.send(embed=make_embed(
                    desc=f"## {E['success']} Log channel set to {ch.mention}", color="success"), ephemeral=True)
            else:
                await interaction.followup.send(f"{E['error']} **Not found!**", ephemeral=True)

        elif v in ["support_role", "admin_role"]:
            role = msg.role_mentions[0] if msg.role_mentions else None
            if not role:
                try:
                    role = interaction.guild.get_role(int(msg.content))
                except:
                    pass
            if role:
                config[v] = str(role.id)
                update_config(interaction.guild.id, config)
                name = "Support" if v == "support_role" else "Admin"
                await interaction.followup.send(embed=make_embed(
                    desc=f"## {E['success']} {name} role set to {role.mention}", color="success"), ephemeral=True)
            else:
                await interaction.followup.send(f"{E['error']} **Not found!**", ephemeral=True)

        elif v == "max_tickets":
            try:
                n = int(msg.content)
                if 1 <= n <= 10:
                    config["max_tickets"] = n
                    update_config(interaction.guild.id, config)
                    await interaction.followup.send(embed=make_embed(
                        desc=f"## {E['success']} Max tickets set to **{n}**", color="success"), ephemeral=True)
                else:
                    raise ValueError
            except:
                await interaction.followup.send(f"{E['error']} **Enter 1-10!**", ephemeral=True)

        elif v == "auto_close":
            try:
                h = int(msg.content)
                if 0 <= h <= 168:
                    config["auto_close_hours"] = h
                    update_config(interaction.guild.id, config)
                    t = "**Disabled**" if h == 0 else f"**{h} hours**"
                    await interaction.followup.send(embed=make_embed(
                        desc=f"## {E['success']} Auto-close set to {t}", color="success"), ephemeral=True)
                else:
                    raise ValueError
            except:
                await interaction.followup.send(f"{E['error']} **Enter 0-168!**", ephemeral=True)

        elif v == "deploy":
            ch = msg.channel_mentions[0] if msg.channel_mentions else None
            if not ch:
                try:
                    ch = interaction.guild.get_channel(int(msg.content))
                except:
                    pass
            if ch:
                if not config.get("ticket_category") or not config.get("support_role"):
                    return await interaction.followup.send(embed=make_embed(
                        desc=f"## {E['error']} Set **Category** & **Support Role** first!",
                        color="danger"), ephemeral=True)
                await deploy_panel(ch, interaction.guild)
                config["ticket_channel"] = str(ch.id)
                update_config(interaction.guild.id, config)
                await interaction.followup.send(embed=make_embed(
                    desc=f"## {E['rocket']} Panel deployed to {ch.mention}!", color="success"), ephemeral=True)
            else:
                await interaction.followup.send(f"{E['error']} **Not found!**", ephemeral=True)


class ToggleView(View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(placeholder="◈ Toggle a feature...", options=[
        discord.SelectOption(label="Feedback", value="feedback_enabled", emoji="⭐"),
        discord.SelectOption(label="Auto-Ping Staff", value="auto_ping_staff", emoji="🔔"),
        discord.SelectOption(label="Claim System", value="claim_enabled", emoji="✋"),
        discord.SelectOption(label="Priority System", value="priority_enabled", emoji="⚡"),
        discord.SelectOption(label="DM on Close", value="dm_on_close", emoji="📨"),
        discord.SelectOption(label="Require Reason", value="require_reason", emoji="📝"),
        discord.SelectOption(label="AI Assistant", value="ai_enabled", emoji="🤖")
    ])
    async def select_callback(self, interaction: discord.Interaction, select: Select):
        guild_data = get_config(interaction.guild.id)
        c = guild_data["config"]
        key = select.values[0]
        c[key] = not c.get(key, True)
        update_config(interaction.guild.id, c)

        status = "**Enabled** ✅" if c[key] else "**Disabled** ❌"
        name = key.replace("_", " ").title()

        embed = make_embed(
            desc=f"## {E['gear']} {name}\n{DIV}\n\nNow → {status}",
            color="success" if c[key] else "danger"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════════════
#                    🔧 CORE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def log_action(guild, title, desc, color="info"):
    guild_data = get_config(guild.id)
    c = guild_data["config"]
    if c.get("log_channel"):
        ch = guild.get_channel(int(c["log_channel"]))
        if ch:
            embed = make_embed(desc=f"## {title}\n{DIV}\n\n{desc}", color=color)
            try:
                await ch.send(embed=embed)
            except:
                pass


async def generate_transcript(channel, interaction):
    messages = []
    async for m in channel.history(limit=500, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        c = m.content or "[embed/attachment]"
        tag = " [BOT]" if m.author.bot else ""
        messages.append(f"[{ts}] {m.author.display_name}{tag}: {c}")

    if not messages:
        return await interaction.followup.send(f"{E['error']} **No messages!**", ephemeral=True)

    text = f"=== TRANSCRIPT: #{channel.name} ===\nGenerated: {utcnow()}\nMessages: {len(messages)}\n{'=' * 50}\n\n" + "\n".join(messages)
    file = discord.File(BytesIO(text.encode()), filename=f"transcript-{channel.name}.txt")
    await interaction.followup.send(f"**{E['transcript']} Transcript:**", file=file, ephemeral=True)


async def save_transcript_to_log(channel, guild, user):
    guild_data = get_config(guild.id)
    c = guild_data["config"]

    messages = []
    async for m in channel.history(limit=500, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        content = m.content or "[embed/attachment]"
        tag = " [BOT]" if m.author.bot else ""
        messages.append(f"[{ts}] {m.author.display_name}{tag}: {content}")

    if messages and c.get("log_channel"):
        ch = guild.get_channel(int(c["log_channel"]))
        if ch:
            text = f"=== TRANSCRIPT: #{channel.name} ===\nDeleted by: {user}\n{'=' * 50}\n\n" + "\n".join(messages)
            file = discord.File(BytesIO(text.encode()), filename=f"transcript-{channel.name}.txt")
            embed = make_embed(
                desc=f"## {E['delete']} Ticket Deleted\n{DIV}\n\n**Channel:** `#{channel.name}`\n**By:** {user.mention}",
                color="danger"
            )
            try:
                await ch.send(embed=embed, file=file)
            except:
                pass


async def deploy_panel(channel, guild):
    guild_data = get_config(guild.id)
    config = guild_data["config"]
    cats = config.get("ticket_categories", DEFAULT_CONFIG["ticket_categories"])
    cat_list = "\n".join([f"> {E['arrow']} {k}" for k in cats.keys()])

    embed = discord.Embed(
        description=(
            f"# {E['ticket']} Support Center\n"
            f"*We're here to help — 24/7*\n\n"
            f"{DIV}\n\n"
            f"**{E['sparkle']} How it works:**\n"
            f"> **1.** Select a category below\n"
            f"> **2.** Describe your issue\n"
            f"> **3.** Our **AI** will help instantly\n"
            f"> **4.** A staff member will follow up\n\n"
            f"**{E['pin']} Categories:**\n"
            f"{cat_list}\n\n"
            f"{DIV}\n\n"
            f"**{E['ai']} Powered by AI** — Get instant help while waiting!\n"
            f"*{E['dot']} Be patient {E['dot']} Be respectful {E['dot']} One issue per ticket*"
        ),
        color=COLORS["blurple"],
        timestamp=utcnow()
    )
    embed.set_footer(
        text=f"{guild.name} ✦ Ticket System",
        icon_url=guild.icon.url if guild.icon else None
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    await channel.send(embed=embed, view=TicketPanelView(cats))


async def create_ticket(interaction, category, reason):
    guild_data = get_config(interaction.guild.id)
    config = guild_data["config"]

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    config["ticket_number"] = config.get("ticket_number", 0) + 1
    num = config["ticket_number"]
    update_config(interaction.guild.id, config)

    tc = interaction.guild.get_channel(int(config["ticket_category"])) if config.get("ticket_category") else None
    sr = interaction.guild.get_role(int(config["support_role"])) if config.get("support_role") else None
    ar = interaction.guild.get_role(int(config["admin_role"])) if config.get("admin_role") else None

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True, embed_links=True
        ),
        interaction.guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True, manage_messages=True
        )
    }
    if sr:
        overwrites[sr] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True, manage_messages=True
        )
    if ar:
        overwrites[ar] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True, manage_channels=True
        )

    safe = interaction.user.name[:10].replace(" ", "-").lower()
    name = f"ticket-{num:04d}-{safe}"

    try:
        ch = await interaction.guild.create_text_channel(name=name, category=tc, overwrites=overwrites)
    except Exception as ex:
        return await interaction.followup.send(f"{E['error']} **Failed:** {ex}", ephemeral=True)

    now_iso = utcnow_iso()
    ticket_data = {
        "user_id": str(interaction.user.id),
        "channel_id": str(ch.id),
        "category": category,
        "reason": reason,
        "status": "open",
        "priority": "medium",
        "claimed_by": None,
        "created_at": now_iso,
        "last_activity": now_iso,
        "ticket_number": num
    }
    save_ticket(interaction.guild.id, ch.id, ticket_data)

    # FIXED: Use safe increment
    increment_stat(interaction.guild.id, "total_tickets")

    cat_e = {
        "general": "🆘", "billing": "💰", "bug": "🐛",
        "suggestion": "💡", "partnership": "🤝", "application": "📋"
    }
    ce = cat_e.get(category, "📌")

    custom_welcome = config.get("welcome_message")
    if custom_welcome:
        welcome_text = custom_welcome.replace("{user}", interaction.user.mention).replace("{server}",
                                                                                          interaction.guild.name)
    else:
        welcome_text = (
            f"Hey {interaction.user.mention}! {E['sparkle']}\n\n"
            f"**Thanks for reaching out** — I've created this ticket for you.\n"
            f"A **staff member** will be with you shortly!"
        )

    embed = discord.Embed(
        description=(
            f"# {ce} Ticket `#{num:04d}`\n"
            f"{DIV}\n\n"
            f"{welcome_text}\n\n"
            f"**{E['pin']} Ticket Details:**\n"
            f"> {E['user']} **User** {E['arrow']} {interaction.user.mention}\n"
            f"> {ce} **Type** {E['arrow']} `{category.title()}`\n"
            f"> ⚡ **Priority** {E['arrow']} 🟡 `Medium`\n"
            f"> {E['clock']} **Opened** {E['arrow']} <t:{utc_timestamp()}:R>\n\n"
            f"**{E['edit']} Your message:**\n"
            f">>> {reason[:500]}\n\n"
            f"{DIV}\n"
            f"*{E['ai']} AI Assistant is active — ask questions while waiting!*"
        ),
        color=COLORS["blurple"],
        timestamp=utcnow()
    )
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)
    embed.set_footer(text="AuraFlex Tickets ✦ Use buttons below to manage")

    ping = sr.mention if (config.get("auto_ping_staff") and sr) else None
    await ch.send(content=ping, embed=embed, view=TicketControlView())

    # AI Initial Response
    if (config.get("ai_enabled", True) and GROQ_API_KEY
            and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE"):
        try:
            async with ch.typing():
                ai_reply = await get_ai_response(ch.id, reason, interaction.guild, ticket_data, config)

            if ai_reply:
                ai_embed = discord.Embed(
                    description=(
                        f"**{E['ai']} AuraFlex! Assistant**\n{DIV}\n\n"
                        f"{ai_reply}\n\n"
                        f"*{E['info']} I'm an AI assistant helping while staff is on the way!*"
                    ),
                    color=COLORS["teal"],
                    timestamp=utcnow()
                )
                ai_embed.set_footer(text="AI-Powered ✦ A staff member will claim your ticket soon")
                await ch.send(embed=ai_embed)
        except Exception as ex:
            print(f"[AI Initial Error] {ex}")

    await interaction.followup.send(
        embed=make_embed(
            desc=f"## {E['success']} Ticket Created!\n{DIV}\n\n{E['arrow']} {ch.mention}\n> *{E['ai']} AI is ready to help!*",
            color="success"
        ),
        ephemeral=True
    )

    await log_action(interaction.guild, f"{E['ticket']} New Ticket",
                     f"**User:** {interaction.user.mention}\n**Type:** {ce} `{category}`\n"
                     f"**Channel:** {ch.mention}\n**ID:** `#{num:04d}`", "success")


async def close_ticket(interaction, reason):
    ticket = get_ticket(interaction.guild.id, interaction.channel.id)
    if not ticket:
        if not interaction.response.is_done():
            return await interaction.response.send_message(f"{E['error']} **Not a ticket!**", ephemeral=True)
        return
    if ticket["status"] == "closed":
        if not interaction.response.is_done():
            return await interaction.response.send_message(f"{E['error']} **Already closed!**", ephemeral=True)
        return

    guild_data = get_config(interaction.guild.id)
    config = guild_data["config"]

    if not interaction.response.is_done():
        await interaction.response.defer()

    ticket["status"] = "closed"
    ticket["closed_at"] = utcnow_iso()
    ticket["closed_by"] = str(interaction.user.id)
    ticket["close_reason"] = reason
    save_ticket(interaction.guild.id, interaction.channel.id, ticket)
    clear_ai_conversation(interaction.channel.id)

    # FIXED: Use safe increment
    increment_stat(interaction.guild.id, "closed_tickets")

    user = interaction.guild.get_member(int(ticket["user_id"]))
    if user:
        try:
            await interaction.channel.set_permissions(user, send_messages=False, read_messages=True)
        except:
            pass

    created = parse_iso(ticket["created_at"])
    dur = utcnow() - created
    h, rem = divmod(int(dur.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    dur_str = f"{h}h {m}m {s}s"

    try:
        await interaction.channel.edit(name=f"closed-{interaction.channel.name}")
    except:
        pass

    close_msg = config.get("close_message") or f"Thank you for contacting us! Your feedback matters. {E['heart']}"

    embed = discord.Embed(
        description=(
            f"# {E['close']} Ticket Closed\n{DIV}\n\n"
            f"**{E['user']} Closed by** {E['arrow']} {interaction.user.mention}\n"
            f"**{E['edit']} Reason** {E['arrow']} {reason}\n"
            f"**{E['clock']} Duration** {E['arrow']} `{dur_str}`\n\n"
            f"*{close_msg}*\n\n{DIV}"
        ),
        color=COLORS["danger"],
        timestamp=utcnow()
    )
    embed.set_footer(text="AuraFlex! Tickets ✦ Use buttons below")
    await interaction.followup.send(embed=embed, view=TicketDeleteView())

    # Transcript to log
    messages = []
    async for m in interaction.channel.history(limit=500, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        c = m.content or "[embed/attachment]"
        tag = " [BOT]" if m.author.bot else ""
        messages.append(f"[{ts}] {m.author.display_name}{tag}: {c}")

    if messages and config.get("log_channel"):
        log_ch = interaction.guild.get_channel(int(config["log_channel"]))
        if log_ch:
            text = (
                f"=== TICKET #{ticket.get('ticket_number', 0):04d} CLOSED ===\n"
                f"By: {interaction.user}\nReason: {reason}\nDuration: {dur_str}\n"
                f"{'=' * 50}\n\n" + "\n".join(messages)
            )
            file = discord.File(BytesIO(text.encode()), filename=f"transcript-{interaction.channel.name}.txt")
            log_embed = make_embed(
                desc=(
                    f"## {E['close']} Ticket Closed\n{DIV}\n\n"
                    f"**Ticket:** `#{ticket.get('ticket_number', 0):04d}`\n"
                    f"**User:** <@{ticket['user_id']}>\n"
                    f"**Closed by:** {interaction.user.mention}\n"
                    f"**Category:** `{ticket.get('category', 'N/A')}`\n"
                    f"**Reason:** {reason}\n"
                    f"**Duration:** `{dur_str}`\n"
                    f"**Claimed by:** {'<@' + ticket['claimed_by'] + '>' if ticket.get('claimed_by') else '`Unclaimed`'}"
                ),
                color="danger"
            )
            try:
                await log_ch.send(embed=log_embed, file=file)
            except:
                pass

    # DM user
    if config.get("dm_on_close") and user:
        try:
            dm_embed = make_embed(
                desc=(
                    f"## {E['close']} Your Ticket Was Closed\n{DIV}\n\n"
                    f"**Server:** {interaction.guild.name}\n"
                    f"**Reason:** {reason}\n"
                    f"**Duration:** `{dur_str}`\n"
                    f"**Closed by:** {interaction.user.display_name}"
                ),
                color="info"
            )

            if config.get("feedback_enabled"):
                class FeedbackBtn(View):
                    def __init__(self):
                        super().__init__(timeout=86400)

                    @discord.ui.button(label="Leave Feedback", emoji="⭐", style=discord.ButtonStyle.primary)
                    async def fb(self, i, b):
                        await i.response.send_modal(FeedbackModal(interaction.channel.id))

                await user.send(embed=dm_embed, view=FeedbackBtn())
            else:
                await user.send(embed=dm_embed)
        except:
            pass

# ═══════════════════════════════════════════════════════════════
#                    🤖 AI MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    if message.guild:
        ticket = get_ticket(message.guild.id, message.channel.id)
        if ticket and ticket.get("status") == "open":
            ticket["last_activity"] = utcnow_iso()
            save_ticket(message.guild.id, message.channel.id, ticket)

            guild_data = get_config(message.guild.id)
            config = guild_data["config"]

            # AI responds ONLY if:
            # 1) AI enabled
            # 2) NOT claimed (no staff yet)
            # 3) Message from ticket creator
            # 4) API key is set
            # 5) Not a bot command
            if (config.get("ai_enabled", True)
                    and not ticket.get("claimed_by")
                    and str(message.author.id) == ticket.get("user_id")
                    and GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE"
                    and not message.content.startswith("at!")):

                try:
                    async with message.channel.typing():
                        ai_reply = await get_ai_response(
                            message.channel.id, message.content,
                            message.guild, ticket, config
                        )

                    if ai_reply:
                        ai_embed = discord.Embed(
                            description=(
                                f"**{E['ai']} AuraFlex Assistant**\n{DIV}\n\n"
                                f"{ai_reply}"
                            ),
                            color=COLORS["teal"],
                            timestamp=utcnow()
                        )
                        ai_embed.set_footer(text="AI-Powered ✦ Staff will claim your ticket soon")
                        await message.channel.send(embed=ai_embed)
                except Exception as ex:
                    print(f"[AI Reply Error] {ex}")

    await bot.process_commands(message)

# ═══════════════════════════════════════════════════════════════
#                    ⏰ AUTO-CLOSE TASK
# ═══════════════════════════════════════════════════════════════

@tasks.loop(minutes=5)
async def auto_close_loop():
    try:
        data = load_data()
        for gid, gdata in data.items():
            c = gdata.get("config", {})
            hrs = c.get("auto_close_hours", 0)
            if hrs <= 0:
                continue

            guild = bot.get_guild(int(gid))
            if not guild:
                continue

            for cid, t in list(gdata.get("tickets", {}).items()):
                if t.get("status") != "open":
                    continue
                last = t.get("last_activity", t.get("created_at"))
                if not last:
                    continue

                elapsed = (utcnow() - parse_iso(last)).total_seconds()
                if elapsed > hrs * 3600:
                    ch = guild.get_channel(int(cid))
                    if ch:
                        t["status"] = "closed"
                        t["closed_at"] = utcnow_iso()
                        t["close_reason"] = f"Auto-closed ({hrs}h inactivity)"
                        save_ticket(gid, cid, t)
                        clear_ai_conversation(int(cid))

                        user = guild.get_member(int(t["user_id"]))
                        if user:
                            try:
                                await ch.set_permissions(user, send_messages=False, read_messages=True)
                            except:
                                pass
                        try:
                            await ch.edit(name=f"closed-{ch.name}")
                        except:
                            pass

                        embed = make_embed(
                            desc=(
                                f"## ⏰ Auto-Closed\n{DIV}\n\n"
                                f"Closed after **{hrs}h** of inactivity.\n"
                                f"> *Feel free to reopen if needed!*"
                            ),
                            color="warning"
                        )
                        try:
                            await ch.send(embed=embed, view=TicketDeleteView())
                        except:
                            pass
    except Exception as ex:
        print(f"[Auto-Close Error] {ex}")


@auto_close_loop.before_loop
async def before_auto_close():
    await bot.wait_until_ready()

# ═══════════════════════════════════════════════════════════════
#                    🟢 BOT READY
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"""
╔═══════════════════════════════════════════╗
║  {E['ticket']}  Auraflex! Ticket Bot — ONLINE            ║
║  {E['ai']}  AI: Groq Llama 3.1                 ║
║  {E['pin']}  Prefix: at!                        ║
║  🏠  Servers: {len(bot.guilds):<27} ║
║  {E['sparkle']}  {bot.user.name:<36} ║
╚═══════════════════════════════════════════╝
    """)

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="at!help ✦ AI Tickets 🎫"),
        status=discord.Status.online
    )

    bot.add_view(TicketControlView())
    bot.add_view(TicketDeleteView())

    data = load_data()
    for gid, gdata in data.items():
        cats = gdata.get("config", {}).get("ticket_categories", DEFAULT_CONFIG["ticket_categories"])
        bot.add_view(TicketPanelView(cats))

    if not auto_close_loop.is_running():
        auto_close_loop.start()

    # Fix existing data on startup
    for gid in data:
        ensure_guild(data, gid)
    save_data(data)

    print(f"{E['success']} Ready! All data validated.")

# ═══════════════════════════════════════════════════════════════
#                    📖 COMMANDS
# ═══════════════════════════════════════════════════════════════

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        description=(
            f"# {E['ticket']} AuraFlex! Ticket Bot\n"
            f"*All-in-one ticket system with **AI support***\n\n"
            f"{DIV}\n\n"

            f"## ⚙️ Setup & Config\n"
            f"> **`at!setup`** {E['arrow']} Interactive setup wizard\n"
            f"> **`at!deploy`** {E['arrow']} Deploy ticket panel\n"
            f"> **`at!config`** {E['arrow']} View current config\n"
            f"> **`at!setcategory`** {E['arrow']} Set ticket category\n"
            f"> **`at!setlog`** {E['arrow']} Set log channel\n"
            f"> **`at!setrole`** {E['arrow']} Set support role\n"
            f"> **`at!setadminrole`** {E['arrow']} Set admin role\n"
            f"> **`at!setmaxtickets`** {E['arrow']} Max tickets/user\n"
            f"> **`at!setwelcome`** {E['arrow']} Custom welcome msg\n"
            f"> **`at!setclosemsg`** {E['arrow']} Custom close msg\n\n"

            f"## {E['ticket']} Ticket Management\n"
            f"> **`at!close [reason]`** {E['arrow']} Close ticket\n"
            f"> **`at!open`** {E['arrow']} Create a ticket\n"
            f"> **`at!claim`** {E['arrow']} Claim *(pauses AI)*\n"
            f"> **`at!unclaim`** {E['arrow']} Unclaim *(resumes AI)*\n"
            f"> **`at!add @user`** {E['arrow']} Add user\n"
            f"> **`at!remove @user`** {E['arrow']} Remove user\n"
            f"> **`at!rename <name>`** {E['arrow']} Rename ticket\n"
            f"> **`at!transfer @user`** {E['arrow']} Transfer ownership\n"
            f"> **`at!priority <lvl>`** {E['arrow']} Set priority\n"
            f"> **`at!transcript`** {E['arrow']} Generate transcript\n\n"

            f"## {E['ai']} AI Features\n"
            f"> **`at!toggle ai`** {E['arrow']} Enable/disable AI\n"
            f"> **`at!setserverinfo`** {E['arrow']} Teach AI your server\n"
            f"> **`at!aistatus`** {E['arrow']} Check AI status\n"
            f"> *AI auto-responds until staff claims!*\n\n"

            f"## {E['staff']} Moderation\n"
            f"> **`at!blacklist @user`** {E['arrow']} Block from tickets\n"
            f"> **`at!unblacklist @user`** {E['arrow']} Unblock\n"
            f"> **`at!blacklistshow`** {E['arrow']} View blacklist\n"
            f"> **`at!closeall`** {E['arrow']} Close all tickets\n"
            f"> **`at!forceclose`** {E['arrow']} Force close\n\n"

            f"## {E['stats']} Stats & Info\n"
            f"> **`at!stats`** {E['arrow']} Statistics\n"
            f"> **`at!ticketinfo`** {E['arrow']} Current ticket info\n"
            f"> **`at!usertickets @u`** {E['arrow']} User's tickets\n"
            f"> **`at!leaderboard`** {E['arrow']} Staff rankings\n"
            f"> **`at!ping`** / **`at!botinfo`**\n\n"

            f"## {E['gear']} Toggles\n"
            f"> **`at!toggle <feature>`**\n"
            f"> `feedback` `autoping` `claim` `priority` `dm` `reason` `ai`\n\n"

            f"## 📂 Categories\n"
            f"> **`at!addcategory <emoji> <name> <value>`**\n"
            f"> **`at!removecategory <value>`** / **`at!listcategories`**\n\n"
            f"{DIV}\n"
            f"*{E['heart']} Prefix: `at!`*"
        ),
        color=COLORS["blurple"],
        timestamp=utcnow()
    )
    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text="AuraFlex! Ticket Bot ✦ AI-Powered")
    await ctx.send(embed=embed)


@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_cmd(ctx):
    embed = make_embed(
        desc=(
            f"# {E['gear']} Setup Wizard\n"
            f"*Configure your ticket system*\n\n"
            f"{DIV}\n\n"
            f"Use the **dropdown** below:\n\n"
            f"**{E['sparkle']} Quick Setup:**\n"
            f"> **1.** Set **Ticket Category**\n"
            f"> **2.** Set **Support Role**\n"
            f"> **3.** Set **Log Channel** *(optional)*\n"
            f"> **4.** Set **AI Server Info** *(teach AI!)*\n"
            f"> **5.** **Deploy** the panel\n"
            f"> **6.** Done! {E['fire']}"
        ),
        color="blurple"
    )
    await ctx.send(embed=embed, view=SetupView())


@bot.command(name="deploy")
@commands.has_permissions(administrator=True)
async def deploy_cmd(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    if not c.get("ticket_category") or not c.get("support_role"):
        return await ctx.send(embed=make_embed(
            desc=f"## {E['error']} Run `at!setup` first!\n> Set **Category** & **Support Role**", color="danger"))
    await deploy_panel(channel, ctx.guild)
    c["ticket_channel"] = str(channel.id)
    update_config(ctx.guild.id, c)
    await ctx.send(embed=make_embed(desc=f"## {E['rocket']} Panel deployed to {channel.mention}!", color="success"))


@bot.command(name="close")
async def close_cmd(ctx, *, reason: str = None):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket channel!**", color="danger"))
    guild_data = get_config(ctx.guild.id)
    if guild_data["config"].get("require_reason") and not reason:
        return await ctx.send(embed=make_embed(
            desc=f"{E['warning']} **Provide a reason:** `at!close <reason>`", color="warning"))

    r = reason or "No reason"

    class Confirm(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label="Close Ticket", emoji="🔐", style=discord.ButtonStyle.danger)
        async def yes(self, i, b):
            await close_ticket(i, r)

        @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.secondary)
        async def no(self, i, b):
            await i.response.send_message(f"{E['error']} Cancelled.", ephemeral=True)

    await ctx.send(embed=make_embed(
        desc=f"## {E['warning']} Close this ticket?\n{DIV}\n\n**Reason:** {r}", color="warning"), view=Confirm())


@bot.command(name="open")
async def open_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    cats = guild_data["config"].get("ticket_categories", DEFAULT_CONFIG["ticket_categories"])
    await ctx.send(embed=make_embed(
        desc=f"## {E['ticket']} Create a Ticket\n{DIV}\n\n> Select a category:", color="info"),
        view=TicketPanelView(cats))


@bot.command(name="claim")
async def claim_cmd(ctx):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    sr = ctx.guild.get_role(int(c["support_role"])) if c.get("support_role") else None
    is_staff = ctx.author.guild_permissions.administrator or (sr and sr in ctx.author.roles)
    if not is_staff:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Staff only!**", color="danger"))
    if ticket.get("claimed_by"):
        return await ctx.send(embed=make_embed(
            desc=f"{E['error']} **Already claimed by <@{ticket['claimed_by']}>!**", color="danger"))

    ticket["claimed_by"] = str(ctx.author.id)
    save_ticket(ctx.guild.id, ctx.channel.id, ticket)
    await ctx.send(embed=make_embed(
        desc=(f"## {E['claim']} Ticket Claimed!\n{DIV}\n\n"
              f"**{ctx.author.mention}** is now handling this\n"
              f"> {E['ai']} *AI has been paused*"), color="success"))


@bot.command(name="unclaim")
async def unclaim_cmd(ctx):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    if ticket.get("claimed_by") != str(ctx.author.id) and not ctx.author.guild_permissions.administrator:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **You didn't claim this!**", color="danger"))
    ticket["claimed_by"] = None
    save_ticket(ctx.guild.id, ctx.channel.id, ticket)
    await ctx.send(embed=make_embed(
        desc=f"## 📤 Unclaimed\n{DIV}\n\n> {E['ai']} *AI Assistant is back online!*", color="warning"))


@bot.command(name="add")
async def add_cmd(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!add @user`", color="danger"))
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True)
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Added {member.mention}", color="success"))


@bot.command(name="remove")
async def remove_cmd(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!remove @user`", color="danger"))
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Removed {member.mention}", color="success"))


@bot.command(name="rename")
async def rename_cmd(ctx, *, name: str = None):
    if not name:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!rename <name>`", color="danger"))
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    old = ctx.channel.name
    await ctx.channel.edit(name=name[:100])
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Renamed\n> `{old}` → `{name}`", color="success"))


@bot.command(name="transfer")
async def transfer_cmd(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!transfer @user`", color="danger"))
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    old = ctx.guild.get_member(int(ticket["user_id"]))
    if old:
        await ctx.channel.set_permissions(old, overwrite=None)
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True)
    ticket["user_id"] = str(member.id)
    save_ticket(ctx.guild.id, ctx.channel.id, ticket)
    await ctx.send(embed=make_embed(desc=f"## 🔄 Transferred to {member.mention}", color="success"))


@bot.command(name="priority")
async def priority_cmd(ctx, level: str = None):
    lvls = ["low", "medium", "high", "critical"]
    if not level or level.lower() not in lvls:
        return await ctx.send(embed=make_embed(
            desc=f"{E['error']} `at!priority <low/medium/high/critical>`", color="danger"))
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    em = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    ticket["priority"] = level.lower()
    save_ticket(ctx.guild.id, ctx.channel.id, ticket)
    await ctx.send(embed=make_embed(desc=f"## {em[level.lower()]} Priority → **{level.title()}**", color="info"))


@bot.command(name="transcript")
async def transcript_cmd(ctx):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    msg = await ctx.send(embed=make_embed(desc=f"{E['loading']} **Generating...**", color="info"))
    messages = []
    async for m in ctx.channel.history(limit=500, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        c = m.content or "[embed/attachment]"
        messages.append(f"[{ts}] {m.author.display_name}: {c}")
    if not messages:
        return await msg.edit(embed=make_embed(desc=f"{E['error']} **No messages!**", color="danger"))
    text = f"=== #{ctx.channel.name} ===\n{'=' * 50}\n\n" + "\n".join(messages)
    await msg.delete()
    await ctx.send(f"**{E['transcript']} Transcript:**",
                   file=discord.File(BytesIO(text.encode()), filename=f"transcript-{ctx.channel.name}.txt"))


@bot.command(name="blacklist")
@commands.has_permissions(administrator=True)
async def blacklist_cmd(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!blacklist @user`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    if str(member.id) in c.get("blacklisted_users", []):
        return await ctx.send(embed=make_embed(desc=f"{E['warning']} **Already blacklisted!**", color="warning"))
    c.setdefault("blacklisted_users", []).append(str(member.id))
    update_config(ctx.guild.id, c)
    await ctx.send(embed=make_embed(
        desc=f"## 🚫 Blacklisted\n> {member.mention} can't create tickets", color="danger"))


@bot.command(name="unblacklist")
@commands.has_permissions(administrator=True)
async def unblacklist_cmd(ctx, member: discord.Member = None):
    if not member:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!unblacklist @user`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    if str(member.id) not in c.get("blacklisted_users", []):
        return await ctx.send(embed=make_embed(desc=f"{E['warning']} **Not blacklisted!**", color="warning"))
    c["blacklisted_users"].remove(str(member.id))
    update_config(ctx.guild.id, c)
    await ctx.send(embed=make_embed(
        desc=f"## {E['success']} Removed {member.mention} from blacklist", color="success"))


@bot.command(name="blacklistshow")
@commands.has_permissions(administrator=True)
async def blshow_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    bl = guild_data["config"].get("blacklisted_users", [])
    if not bl:
        return await ctx.send(embed=make_embed(desc=f"## 📋 Blacklist is empty!", color="info"))
    users = "\n".join([f"> {E['dot']} <@{u}>" for u in bl])
    await ctx.send(embed=make_embed(desc=f"## 🚫 Blacklisted Users\n{DIV}\n\n{users}", color="danger"))


@bot.command(name="closeall")
@commands.has_permissions(administrator=True)
async def closeall_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    ot = {k: v for k, v in guild_data.get("tickets", {}).items() if v.get("status") == "open"}
    if not ot:
        return await ctx.send(embed=make_embed(desc=f"## {E['info']} No open tickets!", color="info"))
    n = len(ot)

    class Confirm(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label=f"Close All ({n})", emoji="🔐", style=discord.ButtonStyle.danger)
        async def yes(self, interaction, button):
            await interaction.response.send_message(f"{E['loading']} **Closing {n} tickets...**")
            closed = 0
            for cid, td in ot.items():
                ch = ctx.guild.get_channel(int(cid))
                if ch:
                    td["status"] = "closed"
                    td["closed_at"] = utcnow_iso()
                    save_ticket(ctx.guild.id, cid, td)
                    clear_ai_conversation(int(cid))
                    try:
                        u = ctx.guild.get_member(int(td["user_id"]))
                        if u:
                            await ch.set_permissions(u, send_messages=False, read_messages=True)
                        await ch.edit(name=f"closed-{ch.name}")
                        closed += 1
                    except:
                        pass
            await ctx.send(embed=make_embed(
                desc=f"## {E['success']} Closed **{closed}** ticket(s)!", color="success"))

        @discord.ui.button(label="Cancel", emoji="❌", style=discord.ButtonStyle.secondary)
        async def no(self, i, b):
            await i.response.send_message("Cancelled.", ephemeral=True)

    await ctx.send(embed=make_embed(
        desc=f"## {E['warning']} Close **{n}** ticket(s)?", color="warning"), view=Confirm())


@bot.command(name="forceclose")
@commands.has_permissions(administrator=True)
async def forceclose_cmd(ctx, *, reason: str = "Force closed"):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    ticket["status"] = "closed"
    ticket["closed_at"] = utcnow_iso()
    save_ticket(ctx.guild.id, ctx.channel.id, ticket)
    clear_ai_conversation(ctx.channel.id)
    u = ctx.guild.get_member(int(ticket["user_id"]))
    if u:
        try:
            await ctx.channel.set_permissions(u, send_messages=False, read_messages=True)
        except:
            pass
    try:
        await ctx.channel.edit(name=f"closed-{ctx.channel.name}")
    except:
        pass
    await ctx.send(embed=make_embed(
        desc=f"## {E['close']} Force Closed\n{DIV}\n\n**By:** {ctx.author.mention}\n**Reason:** {reason}",
        color="danger"), view=TicketDeleteView())


@bot.command(name="stats")
async def stats_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    s = guild_data.get("stats", {})
    t = guild_data.get("tickets", {})
    o = sum(1 for x in t.values() if x.get("status") == "open")
    cl = sum(1 for x in t.values() if x.get("status") == "closed")
    cats = {}
    for x in t.values():
        cat = x.get("category", "?")
        cats[cat] = cats.get(cat, 0) + 1
    ct = "\n".join([f"> {E['dot']} **{k.title()}:** `{v}`" for k, v in cats.items()]) or "> *No data yet*"

    await ctx.send(embed=make_embed(
        desc=(
            f"# {E['stats']} Ticket Statistics\n{DIV}\n\n"
            f"**{E['ticket']} Total** {E['arrow']} `{s.get('total_tickets', 0)}`\n"
            f"**🟢 Open** {E['arrow']} `{o}`\n"
            f"**🔴 Closed** {E['arrow']} `{cl}`\n\n"
            f"**By Category:**\n{ct}"
        ),
        color="gold",
        thumb=ctx.guild.icon.url if ctx.guild.icon else None
    ))


@bot.command(name="ticketinfo")
async def tinfo_cmd(ctx):
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    if not ticket:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Not a ticket!**", color="danger"))
    pe = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    cr = parse_iso(ticket["created_at"])
    d = utcnow() - cr
    h, rem = divmod(int(d.total_seconds()), 3600)
    m, _ = divmod(rem, 60)

    ai_status = "🟢 **Active**" if (not ticket.get("claimed_by")) else "⏸️ **Paused** (claimed)"

    await ctx.send(embed=make_embed(
        desc=(
            f"# {E['pin']} Ticket `#{ticket.get('ticket_number', 0):04d}`\n{DIV}\n\n"
            f"**{E['user']} Creator** {E['arrow']} <@{ticket['user_id']}>\n"
            f"**📂 Category** {E['arrow']} `{ticket.get('category', 'N/A').title()}`\n"
            f"**📌 Status** {E['arrow']} {'🟢 **Open**' if ticket['status'] == 'open' else '🔴 **Closed**'}\n"
            f"**{pe.get(ticket.get('priority', 'medium'), '🟡')} Priority** {E['arrow']} "
            f"`{ticket.get('priority', 'medium').title()}`\n"
            f"**{E['claim']} Claimed** {E['arrow']} "
            f"{'<@' + ticket['claimed_by'] + '>' if ticket.get('claimed_by') else '`Unclaimed`'}\n"
            f"**{E['ai']} AI** {E['arrow']} {ai_status}\n"
            f"**{E['clock']} Created** {E['arrow']} <t:{int(cr.timestamp())}:R>\n"
            f"**⏱️ Open for** {E['arrow']} `{h}h {m}m`\n\n"
            f"**{E['edit']} Reason:**\n>>> {ticket.get('reason', 'N/A')[:400]}"
        ),
        color="info"
    ))


@bot.command(name="usertickets")
async def utix_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    guild_data = get_config(ctx.guild.id)
    ut = {k: v for k, v in guild_data.get("tickets", {}).items() if v.get("user_id") == str(member.id)}
    if not ut:
        return await ctx.send(embed=make_embed(desc=f"## {E['info']} {member.mention} has no tickets", color="info"))
    tl = "\n".join([
        f"> {'🟢' if t['status'] == 'open' else '🔴'} **#{t.get('ticket_number', 0):04d}** "
        f"— `{t.get('category', '?').title()}` — <#{c}>"
        for c, t in ut.items()
    ])
    await ctx.send(embed=make_embed(
        desc=f"## {E['user']} {member.display_name}'s Tickets\n{DIV}\n\n**Total:** `{len(ut)}`\n\n{tl}",
        color="info", thumb=member.avatar.url if member.avatar else None
    ))


@bot.command(name="leaderboard")
async def lb_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    claims = {}
    for t in guild_data.get("tickets", {}).values():
        if t.get("claimed_by"):
            claims[t["claimed_by"]] = claims.get(t["claimed_by"], 0) + 1
    if not claims:
        return await ctx.send(embed=make_embed(desc=f"## 🏆 No data yet!", color="info"))
    s = sorted(claims.items(), key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lb = "\n".join([
        f"> {medals[i] if i < 3 else f'**{i + 1}.**'} <@{u}> — **{c}** tickets"
        for i, (u, c) in enumerate(s[:10])
    ])
    await ctx.send(embed=make_embed(desc=f"# 🏆 Staff Leaderboard\n{DIV}\n\n{lb}", color="gold"))


@bot.command(name="ping")
async def ping_cmd(ctx):
    lat = round(bot.latency * 1000)
    s = "🟢 **Excellent**" if lat < 100 else "🟡 **Good**" if lat < 200 else "🔴 **High**"
    await ctx.send(embed=make_embed(
        desc=f"## 🏓 Pong!\n{DIV}\n\n**Latency:** `{lat}ms`\n**Status:** {s}",
        color="success" if lat < 200 else "danger"
    ))


@bot.command(name="botinfo")
async def binfo_cmd(ctx):
    data = load_data()
    total = sum(g.get("stats", {}).get("total_tickets", 0) for g in data.values())
    has_ai = GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE"
    await ctx.send(embed=make_embed(
        desc=(
            f"# {E['ai']} AuraFlexTicket Bot\n{DIV}\n\n"
            f"**{E['stats']} Stats:**\n"
            f"> 🏠 Servers: **{len(bot.guilds)}**\n"
            f"> 👥 Users: **{sum(g.member_count for g in bot.guilds)}**\n"
            f"> {E['ticket']} Tickets: **{total}**\n"
            f"> 🏓 Latency: **{round(bot.latency * 1000)}ms**\n\n"
            f"**{E['gear']} Powered by:**\n"
            f"> {E['ai']} Groq AI: **{'Connected ✅' if has_ai else 'No Key ❌'}**\n"
            f"> 🐍 discord.py\n"
            f"> {E['pin']} Prefix: `at!`"
        ),
        color="purple",
        thumb=bot.user.avatar.url if bot.user.avatar else None
    ))


@bot.command(name="toggle")
@commands.has_permissions(administrator=True)
async def toggle_cmd(ctx, feature: str = None):
    fm = {
        "feedback": "feedback_enabled", "autoping": "auto_ping_staff",
        "claim": "claim_enabled", "priority": "priority_enabled",
        "dm": "dm_on_close", "reason": "require_reason", "ai": "ai_enabled"
    }
    if not feature or feature.lower() not in fm:
        opts = " ".join([f"`{k}`" for k in fm])
        return await ctx.send(embed=make_embed(desc=f"{E['error']} **Options:** {opts}", color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    k = fm[feature.lower()]
    c[k] = not c.get(k, True)
    update_config(ctx.guild.id, c)
    s = "**Enabled** ✅" if c[k] else "**Disabled** ❌"
    await ctx.send(embed=make_embed(
        desc=f"## {E['gear']} {feature.title()} → {s}", color="success" if c[k] else "danger"))


@bot.command(name="addcategory")
@commands.has_permissions(administrator=True)
async def addcat_cmd(ctx, emoji: str = None, name: str = None, value: str = None):
    if not all([emoji, name, value]):
        return await ctx.send(embed=make_embed(
            desc=f"{E['error']} `at!addcategory <emoji> <name> <value>`\n> Example: `at!addcategory 🎮 Gaming gaming`",
            color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    c.setdefault("ticket_categories", {})[f"{emoji} {name}"] = value.lower()
    update_config(ctx.guild.id, c)
    await ctx.send(embed=make_embed(
        desc=f"## {E['success']} Added `{emoji} {name}` → `{value.lower()}`\n> {E['warning']} Run `at!deploy` to apply!",
        color="success"))


@bot.command(name="removecategory")
@commands.has_permissions(administrator=True)
async def rmcat_cmd(ctx, *, value: str = None):
    if not value:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!removecategory <value>`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    found = None
    for l, v in c.get("ticket_categories", {}).items():
        if v == value.lower():
            found = l
            break
    if found:
        del c["ticket_categories"][found]
        update_config(ctx.guild.id, c)
        await ctx.send(embed=make_embed(
            desc=f"## {E['success']} Removed **{found}**\n> {E['warning']} Run `at!deploy` to apply!",
            color="success"))
    else:
        await ctx.send(embed=make_embed(desc=f"{E['error']} **Not found:** `{value}`", color="danger"))


@bot.command(name="listcategories")
async def lscat_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    cats = guild_data["config"].get("ticket_categories", {})
    if not cats:
        return await ctx.send(embed=make_embed(desc=f"## 📂 No categories!", color="info"))
    cl = "\n".join([f"> {E['arrow']} {k} → `{v}`" for k, v in cats.items()])
    await ctx.send(embed=make_embed(desc=f"## 📂 Categories\n{DIV}\n\n{cl}", color="info"))


@bot.command(name="setcategory")
@commands.has_permissions(administrator=True)
async def setcat_cmd(ctx, *, name: str = None):
    if not name:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setcategory <name/ID>`", color="danger"))
    cat = None
    try:
        cat = ctx.guild.get_channel(int(name))
    except:
        for c in ctx.guild.categories:
            if c.name.lower() == name.lower():
                cat = c
                break
    if cat and isinstance(cat, discord.CategoryChannel):
        guild_data = get_config(ctx.guild.id)
        guild_data["config"]["ticket_category"] = str(cat.id)
        update_config(ctx.guild.id, guild_data["config"])
        await ctx.send(embed=make_embed(desc=f"## {E['success']} Category → **{cat.name}**", color="success"))
    else:
        await ctx.send(embed=make_embed(desc=f"{E['error']} **Not found!**", color="danger"))


@bot.command(name="setlog")
@commands.has_permissions(administrator=True)
async def setlog_cmd(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setlog #channel`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["log_channel"] = str(channel.id)
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Logs → {channel.mention}", color="success"))


@bot.command(name="setrole")
@commands.has_permissions(administrator=True)
async def setrole_cmd(ctx, role: discord.Role = None):
    if not role:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setrole @role`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["support_role"] = str(role.id)
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Support → {role.mention}", color="success"))


@bot.command(name="setadminrole")
@commands.has_permissions(administrator=True)
async def setarole_cmd(ctx, role: discord.Role = None):
    if not role:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setadminrole @role`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["admin_role"] = str(role.id)
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Admin → {role.mention}", color="success"))


@bot.command(name="setmaxtickets")
@commands.has_permissions(administrator=True)
async def setmax_cmd(ctx, num: int = None):
    if not num or not (1 <= num <= 10):
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setmaxtickets <1-10>`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["max_tickets"] = num
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(desc=f"## {E['success']} Max tickets → **{num}**", color="success"))


@bot.command(name="setwelcome")
@commands.has_permissions(administrator=True)
async def setwel_cmd(ctx, *, msg: str = None):
    if not msg:
        return await ctx.send(embed=make_embed(
            desc=f"{E['error']} `at!setwelcome <msg>`\n> Use `{{user}}` and `{{server}}`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["welcome_message"] = msg
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(
        desc=f"## {E['success']} Welcome updated!\n>>> {msg[:300]}", color="success"))


@bot.command(name="setclosemsg")
@commands.has_permissions(administrator=True)
async def setclose_cmd(ctx, *, msg: str = None):
    if not msg:
        return await ctx.send(embed=make_embed(desc=f"{E['error']} `at!setclosemsg <msg>`", color="danger"))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["close_message"] = msg
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(
        desc=f"## {E['success']} Close msg updated!\n>>> {msg[:300]}", color="success"))


@bot.command(name="setserverinfo")
@commands.has_permissions(administrator=True)
async def setsinfo_cmd(ctx, *, info: str = None):
    if not info:
        return await ctx.send(embed=make_embed(
            desc=(
                f"## {E['ai']} Teach AI About Your Server\n{DIV}\n\n"
                f"**Usage:** `at!setserverinfo <info>`\n\n"
                f"**Example:**\n"
                f"> `at!setserverinfo We are a Minecraft server. "
                f"Use /play to join. Ranks cost $5-$20. "
                f"Rules are in #rules. IP: play.example.com`\n\n"
                f"> *The AI uses this to answer questions!*"
            ),
            color="info"
        ))
    guild_data = get_config(ctx.guild.id)
    guild_data["config"]["server_info"] = info
    update_config(ctx.guild.id, guild_data["config"])
    await ctx.send(embed=make_embed(
        desc=f"## {E['ai']} AI Knowledge Updated!\n{DIV}\n\n>>> {info[:500]}", color="success"))


@bot.command(name="aistatus")
async def aistatus_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    ticket = get_ticket(ctx.guild.id, ctx.channel.id)
    has_key = GROQ_API_KEY and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE"

    claimed = ticket.get("claimed_by") if ticket else None
    if not has_key:
        reason = "> ❌ No API key set"
        responding = "🔴 **Inactive**"
    elif not c.get("ai_enabled", True):
        reason = "> ❌ AI disabled (`at!toggle ai`)"
        responding = "🔴 **Inactive**"
    elif not ticket:
        reason = "> ℹ️ Not in a ticket channel"
        responding = "🔴 **Inactive**"
    elif claimed:
        reason = f"> ⏸️ Claimed by <@{claimed}>"
        responding = "⏸️ **Paused**"
    else:
        reason = "> ✅ Responding to user messages"
        responding = "🟢 **Active**"

    await ctx.send(embed=make_embed(
        desc=(
            f"## {E['ai']} AI Status\n{DIV}\n\n"
            f"**Enabled:** {'✅' if c.get('ai_enabled', True) else '❌'}\n"
            f"**API Key:** {'✅ Set' if has_key else '❌ Missing'}\n"
            f"**In Ticket:** {'Yes' if ticket else 'No'}\n"
            f"**Status:** {responding}\n\n{reason}\n\n"
            f"**Server Info:** {'✅ Set' if c.get('server_info') else '❌ Not set (`at!setserverinfo`)'}"
        ),
        color="teal"
    ))


@bot.command(name="config")
@commands.has_permissions(administrator=True)
async def config_cmd(ctx):
    guild_data = get_config(ctx.guild.id)
    c = guild_data["config"]
    cat = ctx.guild.get_channel(int(c["ticket_category"])) if c.get("ticket_category") else None
    log = ctx.guild.get_channel(int(c["log_channel"])) if c.get("log_channel") else None
    sr = ctx.guild.get_role(int(c["support_role"])) if c.get("support_role") else None
    ar = ctx.guild.get_role(int(c["admin_role"])) if c.get("admin_role") else None

    await ctx.send(embed=make_embed(
        desc=(
            f"# {E['gear']} Configuration\n{DIV}\n\n"
            f"**Channels:**\n"
            f"> 📁 Category: **{cat.name if cat else '`Not Set`'}**\n"
            f"> 📋 Logs: **{log.mention if log else '`Not Set`'}**\n\n"
            f"**Roles:**\n"
            f"> {E['staff']} Support: **{sr.mention if sr else '`Not Set`'}**\n"
            f"> {E['admin']} Admin: **{ar.mention if ar else '`Not Set`'}**\n\n"
            f"**Settings:**\n"
            f"> 🔢 Max Tickets: **{c.get('max_tickets', 3)}**\n"
            f"> ⏰ Auto-Close: **{c.get('auto_close_hours', 48)}h**\n\n"
            f"**Features:**\n"
            f"> {'✅' if c.get('feedback_enabled') else '❌'} Feedback | "
            f"{'✅' if c.get('auto_ping_staff') else '❌'} AutoPing | "
            f"{'✅' if c.get('claim_enabled') else '❌'} Claim\n"
            f"> {'✅' if c.get('priority_enabled') else '❌'} Priority | "
            f"{'✅' if c.get('dm_on_close') else '❌'} DM | "
            f"{'✅' if c.get('require_reason') else '❌'} Reason\n"
            f"> {'✅' if c.get('ai_enabled', True) else '❌'} **AI Assistant**"
        ),
        color="purple"
    ))

# ═══════════════════════════════════════════════════════════════
#                    ❌ ERROR HANDLING
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=make_embed(
            desc=f"## {E['close']} No Permission\n> You need **Administrator**!", color="danger"))
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, (commands.MemberNotFound, commands.RoleNotFound, commands.ChannelNotFound)):
        await ctx.send(embed=make_embed(desc=f"{E['error']} **Not found!**", color="danger"))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=make_embed(desc=f"{E['error']} **Bad argument:** `{error}`", color="danger"))
    else:
        print(f"[Error] {type(error).__name__}: {error}")

# ═══════════════════════════════════════════════════════════════
#                    🚀 START
# ═══════════════════════════════════════════════════════════════

bot.run(BOT_TOKEN)