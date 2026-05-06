import discord
from discord.ext import commands, tasks
import asyncio
import re
from datetime import datetime, timedelta
import json
import os

# ─── Configuration ───────────────────────────────────────────────────────────
PREFIX = "+"
BOT_TOKEN = os.getenv("TOKEN")
OWNER_IDS = [1501610350108475394, 1308472749219516530]

# Rôles autorisés à utiliser le bot
AUTHORIZED_ROLES = [
    "✨ · Créateur",
    "🌎 · Monde",
    "🪄 · Origine",
    "👑 · Couronne",
    "🖥️ · Système",
    "👑 · Crown",
    "♦️ · Royal",
    "💝 · Écho",
    "❄️ · Froid",
    "🌙 · Lune",
    "🌟 · Aube",
]

# ─── Utilisateurs autorisés manuellement ─────────────────────────────────────
AUTHORIZED_USERS_FILE = "authorized_users.json"

def load_authorized_users():
    if os.path.exists(AUTHORIZED_USERS_FILE):
        with open(AUTHORIZED_USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_authorized_users(data):
    with open(AUTHORIZED_USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

authorized_users = load_authorized_users()

def is_user_authorized(guild_id, user_id):
    return str(user_id) in authorized_users.get(str(guild_id), [])

def add_authorized_user(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in authorized_users:
        authorized_users[gid] = []
    if uid not in authorized_users[gid]:
        authorized_users[gid].append(uid)
    save_authorized_users(authorized_users)

def remove_authorized_user(guild_id, user_id):
    gid = str(guild_id)
    uid = str(user_id)
    if gid in authorized_users and uid in authorized_users[gid]:
        authorized_users[gid].remove(uid)
    save_authorized_users(authorized_users)

def has_authorized_role():
    async def predicate(ctx):
        if ctx.author == ctx.guild.owner:
            return True
        if ctx.author.id in OWNER_IDS:
            return True
        if is_user_authorized(ctx.guild.id, ctx.author.id):
            return True
        user_roles = [r.name for r in ctx.author.roles]
        if any(role in user_roles for role in AUTHORIZED_ROLES):
            return True
        await ctx.send(embed=discord.Embed(
            description="❌ Tu n'as pas la permission d'utiliser cette commande.",
            color=0xFF4444
        ), delete_after=5)
        return False
    return commands.check(predicate)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ─── Stockage en mémoire (remplaçable par une DB) ────────────────────────────
tempmute_tasks = {}       # {member_id: asyncio.Task}
ticket_counter = {}       # {guild_id: int}
spam_tracker = {}         # {user_id: [timestamps]}
warned_users = {}         # {user_id: count}

# ─── Chargement / Sauvegarde config ──────────────────────────────────────────
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

config = load_config()

def get_guild_config(guild_id):
    return config.get(str(guild_id), {})

def set_guild_config(guild_id, key, value):
    gid = str(guild_id)
    if gid not in config:
        config[gid] = {}
    config[gid][key] = value
    save_config(config)


# ════════════════════════════════════════════════════════════════════════════
#  EVENTS
# ════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user} (ID: {bot.user.id})")
    print(f"   Préfixe : {PREFIX}")
    activity = discord.Activity(type=discord.ActivityType.watching, name=f"{PREFIX}help | Gestion serveur")
    await bot.change_presence(status=discord.Status.idle, activity=activity)


@bot.event
async def on_member_join(member):
    """Donne automatiquement le rôle configuré à chaque nouveau membre."""
    gc = get_guild_config(member.guild.id)
    autorole_id = gc.get("autorole")
    if not autorole_id:
        return
    role = member.guild.get_role(int(autorole_id))
    if role:
        try:
            await member.add_roles(role, reason="Auto-rôle à l'arrivée")
        except discord.Forbidden:
            pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=error_embed("❌ Tu n'as pas la permission d'utiliser cette commande."))
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=error_embed("❌ Membre introuvable. Vérifie l'ID ou la mention."))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=error_embed(f"❌ Argument manquant : `{error.param.name}`"))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=error_embed("❌ Argument invalide fourni."))
    else:
        print(f"Erreur non gérée : {error}")


# ─── Auto-modération ─────────────────────────────────────────────────────────
SPAM_THRESHOLD = 5        # messages max
SPAM_WINDOW = 5           # en secondes
LINK_PATTERN = re.compile(r"(https?://|discord\.gg/|www\.)", re.IGNORECASE)

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    gc = get_guild_config(message.guild.id)
    automod_enabled = gc.get("automod", True)

    if automod_enabled:
        # Anti-liens
        if gc.get("antilink", True) and LINK_PATTERN.search(message.content):
            bypass_role_id = gc.get("antilink_bypass_role")
            has_bypass = any(r.id == bypass_role_id for r in message.author.roles) if bypass_role_id else False
            if not has_bypass and not message.author.guild_permissions.manage_messages:
                try:
                    await message.delete()
                    warn_count = warned_users.get(message.author.id, 0) + 1
                    warned_users[message.author.id] = warn_count
                    await message.channel.send(
                        embed=warn_embed(message.author, f"Liens non autorisés. (Avertissement {warn_count})"),
                        delete_after=5
                    )
                    await log_action(message.guild, "🔗 Anti-Lien", message.author, f"Lien supprimé dans {message.channel.mention}")
                except discord.Forbidden:
                    pass

        # Anti-spam
        if gc.get("antispam", True):
            uid = message.author.id
            now = datetime.utcnow().timestamp()
            if uid not in spam_tracker:
                spam_tracker[uid] = []
            spam_tracker[uid] = [t for t in spam_tracker[uid] if now - t < SPAM_WINDOW]
            spam_tracker[uid].append(now)

            if len(spam_tracker[uid]) >= SPAM_THRESHOLD:
                spam_tracker[uid] = []
                mute_role = await get_or_create_mute_role(message.guild)
                if mute_role and mute_role not in message.author.roles:
                    try:
                        await message.author.add_roles(mute_role, reason="Auto-mod : spam détecté")
                        await message.channel.send(
                            embed=warn_embed(message.author, "Spam détecté ! Mute automatique de 5 minutes."),
                            delete_after=8
                        )
                        await log_action(message.guild, "🤐 Auto-Mute (Spam)", message.author, "Spam détecté automatiquement")
                        await asyncio.sleep(300)
                        await message.author.remove_roles(mute_role, reason="Auto-mute expiré")
                    except discord.Forbidden:
                        pass

    await bot.process_commands(message)


# ════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════════════

def error_embed(msg):
    return discord.Embed(description=msg, color=0xFF4444)

def success_embed(msg):
    return discord.Embed(description=msg, color=0x2ECC71)

def info_embed(title, msg, color=0x5865F2):
    return discord.Embed(title=title, description=msg, color=color)

def warn_embed(member, reason):
    e = discord.Embed(
        title="⚠️ Avertissement",
        description=f"{member.mention} | {reason}",
        color=0xF39C12
    )
    return e

async def get_or_create_mute_role(guild):
    mute_role = discord.utils.get(guild.roles, name="Muted")
    if not mute_role:
        try:
            mute_role = await guild.create_role(name="Muted", reason="Création auto du rôle Muted")
            for channel in guild.channels:
                try:
                    await channel.set_permissions(mute_role, send_messages=False, speak=False, add_reactions=False)
                except Exception:
                    pass
        except discord.Forbidden:
            return None
    return mute_role

async def log_action(guild, action, target, reason="", moderator=None):
    gc = get_guild_config(guild.id)
    log_channel_id = gc.get("log_channel")
    if not log_channel_id:
        return
    channel = guild.get_channel(int(log_channel_id))
    if not channel:
        return
    e = discord.Embed(title=f"📋 {action}", color=0x3498DB, timestamp=datetime.utcnow())
    e.add_field(name="Cible", value=f"{target} ({target.id})", inline=False)
    if reason:
        e.add_field(name="Raison", value=reason, inline=False)
    if moderator:
        e.add_field(name="Modérateur", value=str(moderator), inline=False)
    e.set_footer(text=f"Serveur : {guild.name}")
    try:
        await channel.send(embed=e)
    except Exception:
        pass

def parse_duration(duration_str):
    """Convertit '5min', '2h', '1j' etc. en secondes."""
    units = {"s": 1, "sec": 1, "min": 60, "h": 3600, "j": 86400, "d": 86400}
    match = re.fullmatch(r"(\d+)(s|sec|min|h|j|d)", duration_str.lower())
    if match:
        return int(match.group(1)) * units[match.group(2)]
    return None


# ════════════════════════════════════════════════════════════════════════════
#  MODÉRATION
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    if member.top_role >= ctx.author.top_role:
        return await ctx.send(embed=error_embed("❌ Tu ne peux pas kick ce membre (rôle supérieur ou égal)."))
    try:
        await member.kick(reason=reason)
        await ctx.send(embed=success_embed(f"👢 **{member}** a été expulsé.\n📝 Raison : {reason}"))
        await log_action(ctx.guild, "👢 Kick", member, reason, ctx.author)
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Je n'ai pas la permission de kick ce membre."))


@has_authorized_role()
@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    if member.top_role >= ctx.author.top_role:
        return await ctx.send(embed=error_embed("❌ Tu ne peux pas bannir ce membre (rôle supérieur ou égal)."))
    try:
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.send(embed=success_embed(f"🔨 **{member}** a été banni.\n📝 Raison : {reason}"))
        await log_action(ctx.guild, "🔨 Ban", member, reason, ctx.author)
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Je n'ai pas la permission de bannir ce membre."))


@has_authorized_role()
@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason="Aucune raison fournie"):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(embed=success_embed(f"✅ **{user}** a été débanni."))
        await log_action(ctx.guild, "✅ Unban", user, reason, ctx.author)
    except discord.NotFound:
        await ctx.send(embed=error_embed("❌ Cet utilisateur n'est pas banni ou introuvable."))


@has_authorized_role()
@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    mute_role = await get_or_create_mute_role(ctx.guild)
    if not mute_role:
        return await ctx.send(embed=error_embed("❌ Impossible de créer/trouver le rôle Muted."))
    if mute_role in member.roles:
        return await ctx.send(embed=error_embed("❌ Ce membre est déjà mute."))
    await member.add_roles(mute_role, reason=reason)
    await ctx.send(embed=success_embed(f"🔇 **{member}** a été mute.\n📝 Raison : {reason}"))
    await log_action(ctx.guild, "🔇 Mute", member, reason, ctx.author)


@has_authorized_role()
@bot.command(name="unmute")
@commands.has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role or mute_role not in member.roles:
        return await ctx.send(embed=error_embed("❌ Ce membre n'est pas mute."))
    if member.id in tempmute_tasks:
        tempmute_tasks[member.id].cancel()
        del tempmute_tasks[member.id]
    await member.remove_roles(mute_role)
    await ctx.send(embed=success_embed(f"🔊 **{member}** a été unmute."))
    await log_action(ctx.guild, "🔊 Unmute", member, moderator=ctx.author)


@has_authorized_role()
@bot.command(name="tempmute")
@commands.has_permissions(manage_roles=True)
async def tempmute(ctx, member: discord.Member, duration: str, *, reason="Aucune raison fournie"):
    seconds = parse_duration(duration)
    if not seconds:
        return await ctx.send(embed=error_embed("❌ Durée invalide.\nFormats acceptés : `5min`, `2h`, `1j`, `30s`"))

    mute_role = await get_or_create_mute_role(ctx.guild)
    if not mute_role:
        return await ctx.send(embed=error_embed("❌ Impossible de créer/trouver le rôle Muted."))
    if mute_role in member.roles:
        return await ctx.send(embed=error_embed("❌ Ce membre est déjà mute."))
    if member.id in tempmute_tasks:
        tempmute_tasks[member.id].cancel()

    await member.add_roles(mute_role, reason=reason)
    expire_time = datetime.utcnow() + timedelta(seconds=seconds)
    e = discord.Embed(title="🔇 Tempmute appliqué", color=0xE67E22)
    e.add_field(name="Membre", value=f"{member.mention} (`{member.id}`)", inline=False)
    e.add_field(name="Durée", value=duration, inline=True)
    e.add_field(name="Expire à", value=f"<t:{int(expire_time.timestamp())}:R>", inline=True)
    e.add_field(name="Raison", value=reason, inline=False)
    e.set_footer(text=f"Par {ctx.author}")
    await ctx.send(embed=e)
    await log_action(ctx.guild, "🔇 Tempmute", member, f"{reason} | Durée : {duration}", ctx.author)

    async def unmute_after():
        await asyncio.sleep(seconds)
        try:
            await member.remove_roles(mute_role, reason="Tempmute expiré")
            await log_action(ctx.guild, "🔊 Unmute automatique", member, f"Tempmute de {duration} expiré")
        except Exception:
            pass
        tempmute_tasks.pop(member.id, None)

    task = asyncio.create_task(unmute_after())
    tempmute_tasks[member.id] = task


@has_authorized_role()
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    warned_users[member.id] = warned_users.get(member.id, 0) + 1
    count = warned_users[member.id]
    await ctx.send(embed=discord.Embed(
        title="⚠️ Avertissement",
        description=f"{member.mention} a reçu un avertissement.\n📝 {reason}\n⚠️ Total : **{count}**",
        color=0xF39C12
    ))
    try:
        await member.send(embed=discord.Embed(
            title=f"⚠️ Avertissement sur {ctx.guild.name}",
            description=f"Tu as reçu un avertissement.\n📝 Raison : {reason}\n⚠️ Total : {count}",
            color=0xF39C12
        ))
    except Exception:
        pass
    await log_action(ctx.guild, "⚠️ Warn", member, reason, ctx.author)


@has_authorized_role()
@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    count = warned_users.get(member.id, 0)
    await ctx.send(embed=info_embed("⚠️ Avertissements", f"{member.mention} a **{count}** avertissement(s)."))


@has_authorized_role()
@bot.command(name="clearwarns")
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, member: discord.Member):
    warned_users[member.id] = 0
    await ctx.send(embed=success_embed(f"✅ Avertissements de {member.mention} effacés."))


@has_authorized_role()
@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    if amount < 1 or amount > 100:
        return await ctx.send(embed=error_embed("❌ Nombre entre 1 et 100."))
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(embed=success_embed(f"🗑️ {len(deleted)-1} messages supprimés."), delete_after=4)
    await log_action(ctx.guild, "🗑️ Purge", ctx.author, f"{len(deleted)-1} messages dans {ctx.channel.mention}")


# ════════════════════════════════════════════════════════════════════════════
#  GESTION DES RÔLES
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        return await ctx.send(embed=error_embed("❌ Ce membre possède déjà ce rôle."))
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        return await ctx.send(embed=error_embed("❌ Tu ne peux pas attribuer un rôle supérieur au tien."))
    await member.add_roles(role)
    await ctx.send(embed=success_embed(f"✅ Rôle {role.mention} ajouté à {member.mention}."))
    await log_action(ctx.guild, "🎭 Ajout de rôle", member, f"Rôle : {role.name}", ctx.author)


@has_authorized_role()
@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    if role not in member.roles:
        return await ctx.send(embed=error_embed("❌ Ce membre ne possède pas ce rôle."))
    await member.remove_roles(role)
    await ctx.send(embed=success_embed(f"✅ Rôle {role.mention} retiré à {member.mention}."))
    await log_action(ctx.guild, "🎭 Suppression de rôle", member, f"Rôle : {role.name}", ctx.author)


@has_authorized_role()
@bot.command(name="roles")
async def roles(ctx, member: discord.Member = None):
    member = member or ctx.author
    role_list = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    await ctx.send(embed=info_embed(
        f"🎭 Rôles de {member.display_name}",
        ", ".join(role_list) if role_list else "Aucun rôle."
    ))


# ════════════════════════════════════════════════════════════════════════════
#  AUTO-RÔLE
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="autorole")
@commands.has_permissions(manage_roles=True)
async def autorole(ctx, role: discord.Role = None):
    """
    Configure le rôle donné automatiquement à chaque nouveau membre.
    Utilisation : +autorole @rôle
    Pour désactiver : +autorole
    """
    if role is None:
        set_guild_config(ctx.guild.id, "autorole", None)
        return await ctx.send(embed=success_embed("✅ Auto-rôle désactivé."))
    set_guild_config(ctx.guild.id, "autorole", role.id)
    await ctx.send(embed=success_embed(
        f"✅ Auto-rôle configuré sur {role.mention}.\nTout nouveau membre recevra ce rôle automatiquement."
    ))
    await log_action(ctx.guild, "🎭 Auto-rôle configuré", ctx.author, f"Rôle : {role.name}", ctx.author)


# ════════════════════════════════════════════════════════════════════════════
#  TICKETS
# ════════════════════════════════════════════════════════════════════════════

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not channel.name.startswith("ticket-"):
            return await interaction.response.send_message("❌ Ce n'est pas un salon de ticket.", ephemeral=True)
        await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
        await asyncio.sleep(5)
        await channel.delete(reason=f"Ticket fermé par {interaction.user}")


class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        gc = get_guild_config(guild.id)
        category_id = gc.get("ticket_category")
        support_role_id = gc.get("support_role")
        category = guild.get_channel(int(category_id)) if category_id else None

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            return await interaction.response.send_message(
                f"❌ Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role_id:
            support_role = guild.get_role(int(support_role_id))
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user} ({interaction.user.id})"
        )

        e = discord.Embed(
            title="🎫 Ticket ouvert",
            description=(
                f"Bienvenue {interaction.user.mention} !\n\n"
                "Explique ton problème en détail et un membre du support te répondra.\n"
                "Clique sur **Fermer le ticket** quand ton problème est résolu."
            ),
            color=0x5865F2
        )
        e.set_footer(text=f"Ticket créé par {interaction.user}")
        await channel.send(embed=e, view=TicketCloseView())
        await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)
        await log_action(guild, "🎫 Ticket ouvert", interaction.user, f"Salon : {channel.name}")


@has_authorized_role()
@bot.command(name="ticket-setup")
@commands.has_permissions(administrator=True)
async def ticket_setup(ctx, category: discord.CategoryChannel = None, support_role: discord.Role = None):
    if category:
        set_guild_config(ctx.guild.id, "ticket_category", category.id)
    if support_role:
        set_guild_config(ctx.guild.id, "support_role", support_role.id)
    e = discord.Embed(
        title="🎫 Support — Ouvre un ticket",
        description=(
            "Tu as besoin d'aide ou tu as un problème ?\n\n"
            "Clique sur le bouton ci-dessous pour ouvrir un ticket privé.\n"
            "Notre équipe te répondra dès que possible."
        ),
        color=0x5865F2
    )
    e.set_footer(text=ctx.guild.name)
    await ctx.send(embed=e, view=TicketOpenView())
    await ctx.message.delete()


@has_authorized_role()
@bot.command(name="add-to-ticket")
@commands.has_permissions(manage_channels=True)
async def add_to_ticket(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("ticket-"):
        return await ctx.send(embed=error_embed("❌ Ce n'est pas un salon de ticket."))
    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)
    await ctx.send(embed=success_embed(f"✅ {member.mention} ajouté au ticket."))


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION AUTO-MOD & LOGS
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="setlog")
@commands.has_permissions(administrator=True)
async def setlog(ctx, channel: discord.TextChannel):
    set_guild_config(ctx.guild.id, "log_channel", channel.id)
    await ctx.send(embed=success_embed(f"✅ Salon de logs défini sur {channel.mention}."))


@has_authorized_role()
@bot.command(name="automod")
@commands.has_permissions(administrator=True)
async def automod_toggle(ctx, feature: str, state: str):
    enabled = state.lower() == "on"
    feature = feature.lower()
    if feature in ("antispam", "all"):
        set_guild_config(ctx.guild.id, "antispam", enabled)
    if feature in ("antilink", "all"):
        set_guild_config(ctx.guild.id, "antilink", enabled)
    status = "✅ activé" if enabled else "❌ désactivé"
    await ctx.send(embed=success_embed(f"Auto-mod `{feature}` {status}."))


@has_authorized_role()
@bot.command(name="antilink-bypass")
@commands.has_permissions(administrator=True)
async def antilink_bypass(ctx, role: discord.Role):
    set_guild_config(ctx.guild.id, "antilink_bypass_role", role.id)
    await ctx.send(embed=success_embed(f"✅ Le rôle {role.mention} peut désormais envoyer des liens."))


# ════════════════════════════════════════════════════════════════════════════
#  COMMANDES UTILITAIRES
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    e = discord.Embed(title=f"👤 {member}", color=member.color)
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="ID", value=member.id, inline=True)
    e.add_field(name="Surnom", value=member.display_name, inline=True)
    e.add_field(name="Bot", value="Oui" if member.bot else "Non", inline=True)
    e.add_field(name="Compte créé", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
    e.add_field(name="A rejoint", value=f"<t:{int(member.joined_at.timestamp())}:R>", inline=True)
    e.add_field(name=f"Rôles ({len(roles)})", value=", ".join(roles[:10]) or "Aucun", inline=False)
    await ctx.send(embed=e)


@has_authorized_role()
@bot.command(name="serverinfo")
async def serverinfo(ctx):
    g = ctx.guild
    e = discord.Embed(title=f"🏠 {g.name}", color=0x5865F2)
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="ID", value=g.id, inline=True)
    e.add_field(name="Propriétaire", value=str(g.owner), inline=True)
    e.add_field(name="Membres", value=g.member_count, inline=True)
    e.add_field(name="Salons", value=len(g.channels), inline=True)
    e.add_field(name="Rôles", value=len(g.roles), inline=True)
    e.add_field(name="Boosters", value=g.premium_subscription_count, inline=True)
    e.add_field(name="Créé", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
    await ctx.send(embed=e)


@has_authorized_role()
@bot.command(name="ping")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(embed=info_embed("🏓 Pong !", f"Latence : **{latency}ms**"))


# ════════════════════════════════════════════════════════════════════════════
#  AIDE
# ════════════════════════════════════════════════════════════════════════════

@has_authorized_role()
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="📖 Commandes du bot", color=0x5865F2)
    e.set_footer(text=f"Préfixe : {PREFIX}")

    e.add_field(name="🔨 Modération", value=(
        f"`{PREFIX}kick @membre raison`\n"
        f"`{PREFIX}ban @membre raison`\n"
        f"`{PREFIX}unban ID raison`\n"
        f"`{PREFIX}mute @membre raison`\n"
        f"`{PREFIX}unmute @membre`\n"
        f"`{PREFIX}tempmute @membre durée raison`\n"
        f"`{PREFIX}warn @membre raison`\n"
        f"`{PREFIX}warnings @membre`\n"
        f"`{PREFIX}clearwarns @membre`\n"
        f"`{PREFIX}purge nombre`"
    ), inline=False)

    e.add_field(name="🎭 Rôles", value=(
        f"`{PREFIX}addrole @membre @rôle`\n"
        f"`{PREFIX}removerole @membre @rôle`\n"
        f"`{PREFIX}roles [@membre]`"
    ), inline=False)

    e.add_field(name="🎫 Tickets", value=(
        f"`{PREFIX}ticket-setup [catégorie] [rôle]`\n"
        f"`{PREFIX}add-to-ticket @membre`"
    ), inline=False)

    e.add_field(name="🛡️ Auto-mod & Config", value=(
        f"`{PREFIX}setlog #salon`\n"
        f"`{PREFIX}automod antispam/antilink/all on/off`\n"
        f"`{PREFIX}antilink-bypass @rôle`"
    ), inline=False)

    e.add_field(name="🎭 Auto-rôle", value=(
        f"`{PREFIX}autorole @rôle` — Définit le rôle auto à l'arrivée\n"
        f"`{PREFIX}autorole` — Désactive l'auto-rôle"
    ), inline=False)

    e.add_field(name="👥 Gestion des accès (Owner)", value=(
        f"`{PREFIX}adduser @membre` — Autorise un utilisateur\n"
        f"`{PREFIX}removeuser @membre` — Retire l'autorisation\n"
        f"`{PREFIX}listusers` — Liste les utilisateurs autorisés"
    ), inline=False)

    e.add_field(name="ℹ️ Utilitaires", value=(
        f"`{PREFIX}userinfo [@membre]`\n"
        f"`{PREFIX}serverinfo`\n"
        f"`{PREFIX}ping`"
    ), inline=False)

    e.add_field(name="⏱️ Durées pour tempmute", value=(
        "`30s` · `5min` · `2h` · `1j`"
    ), inline=False)

    await ctx.send(embed=e)


# ════════════════════════════════════════════════════════════════════════════
#  GESTION DES UTILISATEURS AUTORISÉS
# ════════════════════════════════════════════════════════════════════════════

@bot.command(name="adduser")
async def adduser(ctx, member: discord.Member):
    if ctx.author.id not in OWNER_IDS:
        return await ctx.send(embed=error_embed("❌ Seul le propriétaire du bot peut utiliser cette commande."), delete_after=5)
    if is_user_authorized(ctx.guild.id, member.id):
        return await ctx.send(embed=error_embed(f"❌ {member.mention} est déjà autorisé."))
    add_authorized_user(ctx.guild.id, member.id)
    await ctx.send(embed=success_embed(f"✅ {member.mention} peut maintenant utiliser le bot."))
    await log_action(ctx.guild, "✅ Utilisateur autorisé", member, "Ajouté manuellement", ctx.author)


@bot.command(name="removeuser")
async def removeuser(ctx, member: discord.Member):
    if ctx.author.id not in OWNER_IDS:
        return await ctx.send(embed=error_embed("❌ Seul le propriétaire du bot peut utiliser cette commande."), delete_after=5)
    if not is_user_authorized(ctx.guild.id, member.id):
        return await ctx.send(embed=error_embed(f"❌ {member.mention} n'est pas dans la liste manuelle."))
    remove_authorized_user(ctx.guild.id, member.id)
    await ctx.send(embed=success_embed(f"✅ {member.mention} a été retiré de la liste."))
    await log_action(ctx.guild, "❌ Utilisateur retiré", member, "Retiré manuellement", ctx.author)


@bot.command(name="listusers")
async def listusers(ctx):
    if ctx.author.id not in OWNER_IDS:
        return await ctx.send(embed=error_embed("❌ Seul le propriétaire du bot peut utiliser cette commande."), delete_after=5)
    uids = authorized_users.get(str(ctx.guild.id), [])
    if not uids:
        return await ctx.send(embed=info_embed("👥 Utilisateurs autorisés", "Aucun utilisateur ajouté manuellement."))
    members = []
    for uid in uids:
        member = ctx.guild.get_member(int(uid))
        members.append(f"• {member.mention} (`{uid}`)" if member else f"• ID inconnu (`{uid}`)")
    await ctx.send(embed=info_embed(
        f"👥 Utilisateurs autorisés manuellement ({len(uids)})",
        "\n".join(members)
    ))


# ════════════════════════════════════════════════════════════════════════════
#  LANCEMENT
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
