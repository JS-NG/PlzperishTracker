import discord
from discord.ext import tasks, commands
from discord import app_commands
import requests
import asyncio
import json
import os

TOKEN = os.environ["TOKEN"]


# Default user IDs (always present, cannot be removed)
DEFAULT_USER_IDS = [
    8447038336,
    8447064756,
    8447079827,
    8447109786,
    8447185938,
    8447226387,
    8447260393,
    8447660792,
    8447646077,
    8447668063,
    8447701884,
    8447818820,
    8447826973,
    8447863656,
    8447924262
]

TRACKED_USERS_FILE = "tracked_users.json"

# Load tracked users (includes default + added users)
if os.path.exists(TRACKED_USERS_FILE):
    try:
        with open(TRACKED_USERS_FILE, "r") as f:
            data = json.load(f)
            TRACKED_USERS = list(set(DEFAULT_USER_IDS + data))
    except:
        TRACKED_USERS = DEFAULT_USER_IDS.copy()
else:
    TRACKED_USERS = DEFAULT_USER_IDS.copy()

# Helper function to save only additional users (not defaults) to JSON
def save_tracked_users():
    additional_users = [uid for uid in TRACKED_USERS if uid not in DEFAULT_USER_IDS]
    with open(TRACKED_USERS_FILE, "w") as f:
        json.dump(additional_users, f, indent=4)

STATUS_MAP = {0: "offline", 1: "online", 2: "ingame", 3: "studio"}
tracked_channels = {}
discord_ratelimit_delay = 1.0

# Roblox API functions (same as before)
def get_user_id_from_username(username):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": False}
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        return None
    data = r.json().get("data", [])
    if not data:
        return None
    return data[0]["id"]

def get_user_info(user_id):
    r = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
    if r.status_code != 200:
        return None
    return r.json()

def get_presence(user_id):
    url = "https://presence.roblox.com/v1/presence/users"
    payload = {"userIds": [user_id]}
    r = requests.post(url, json=payload)
    if r.status_code != 200:
        return None
    data = r.json().get("userPresences", [])
    return data[0] if data else None

def get_status_string(user_id):
    info = get_user_info(user_id)
    if not info:
        return None, "unknown"
    if info.get("isBanned", False):
        return info["name"], "banned"
    presence = get_presence(user_id)
    if not presence:
        return info["name"], "unknown"
    return info["name"], STATUS_MAP.get(presence["userPresenceType"], "unknown")

# Discord setup
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    asyncio.create_task(bot.tree.sync())
    updater_loop.start()

# Safe edit for rate limits
async def safe_edit_channel(channel, **kwargs):
    global discord_ratelimit_delay
    while True:
        try:
            await asyncio.sleep(discord_ratelimit_delay)
            return await channel.edit(**kwargs)
        except discord.HTTPException as e:
            if e.status == 429:
                retry = getattr(e, "retry_after", discord_ratelimit_delay * 2)
                discord_ratelimit_delay = min(retry, 10)
                await asyncio.sleep(discord_ratelimit_delay)
            else:
                return None

# Create channel
async def create_tracking_channel(guild, user_id):
    name, status = get_status_string(user_id)
    if not name:
        return None
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
    channel_name = f"{name.lower()}-{status}"
    channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
    tracked_channels[user_id] = channel.id
    return channel

# /adduser command
@bot.tree.command(name="adduser", description="Start tracking a Roblox user.")
@app_commands.describe(query="Username or userId")
async def adduser(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    guild = interaction.guild
    if query.isdigit():
        user_id = int(query)
    else:
        user_id = get_user_id_from_username(query)
        if not user_id:
            await interaction.followup.send("User not found.")
            return
    if user_id in TRACKED_USERS:
        await interaction.followup.send("Already being tracked.")
        return
    TRACKED_USERS.append(user_id)
    save_tracked_users()
    channel = await create_tracking_channel(guild, user_id)
    await interaction.followup.send(f"Now tracking **{user_id}** in <#{channel.id}>")

# /removeuser command
@bot.tree.command(name="removeuser", description="Stop tracking a Roblox user.")
@app_commands.describe(query="Username or userId")
async def removeuser(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    guild = interaction.guild
    if query.isdigit():
        user_id = int(query)
    else:
        user_id = get_user_id_from_username(query)
        if not user_id:
            await interaction.followup.send("User not found.")
            return
    if user_id in DEFAULT_USER_IDS:
        await interaction.followup.send("Cannot remove default user IDs.")
        return
    if user_id not in TRACKED_USERS:
        await interaction.followup.send("User not tracked.")
        return
    TRACKED_USERS.remove(user_id)
    save_tracked_users()
    channel_id = tracked_channels.get(user_id)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.delete()
    tracked_channels.pop(user_id, None)
    await interaction.followup.send(f"Stopped tracking **{user_id}**.")

# /check command
@bot.tree.command(name="check", description="Check Roblox user status.")
@app_commands.describe(query="Username or userId")
async def check(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if query.isdigit():
        user_id = int(query)
    else:
        user_id = get_user_id_from_username(query)
        if not user_id:
            await interaction.followup.send("User not found.")
            return
    name, status = get_status_string(user_id)
    await interaction.followup.send(f"**{name}** is **{status.upper()}**")

# Updater loop with sync
@tasks.loop(seconds=5)
async def updater_loop():
    guild = bot.guilds[0]
    # Create channels for all users
    for user_id in TRACKED_USERS:
        if user_id not in tracked_channels:
            await create_tracking_channel(guild, user_id)
        channel = guild.get_channel(tracked_channels[user_id])
        if not channel:
            continue
        name, status = get_status_string(user_id)
        if not name:
            continue
        new_name = f"{name.lower()}-{status}"
        if channel.name != new_name:
            await safe_edit_channel(channel, name=new_name)
        await asyncio.sleep(0.7)  # avoid Discord rate limits

bot.run(TOKEN)

# ---------------- JSON Format Example ----------------
# The saved JSON file (tracked_users.json) will look like:
# [
#     123456789,    <- added user ID
#     987654321     <- added user ID
# ]
# The default user IDs are not stored in JSON, but always loaded in memory.
