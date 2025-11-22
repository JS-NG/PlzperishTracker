import discord
from discord.ext import tasks, commands
import requests
import asyncio
import json
import os

# ---------------- CONFIG ---------------- #
TOKEN = os.environ["TOKEN"]
GUILD_ID = 1441878472170406031  # replace with your Discord server ID
CHECK_INTERVAL = 60  # seconds between status updates

# Default Roblox IDs (always tracked)
DEFAULT_USER_IDS = [
    8447038336, 8447064756, 8447079827, 8447109786, 8447185938,
    8447226387, 8447260393, 8447660792, 8447646077, 8447668063,
    8447701884, 8447818820, 8447826973, 8447863656, 8447924262
]

# JSON files
USERS_JSON = "tracked_users.json"
CHANNELS_JSON = "tracked_channels.json"

# ---------------- INIT ---------------- #
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load additional tracked users from JSON
if os.path.exists(USERS_JSON):
    with open(USERS_JSON, "r") as f:
        additional_users = json.load(f)
else:
    additional_users = []

tracked_users = list(set(DEFAULT_USER_IDS + additional_users))

# Load tracked channels
if os.path.exists(CHANNELS_JSON):
    with open(CHANNELS_JSON, "r") as f:
        tracked_channels = json.load(f)
else:
    tracked_channels = {}

# ---------------- HELPERS ---------------- #
def save_tracked_users():
    with open(USERS_JSON, "w") as f:
        json.dump(list(set(additional_users)), f)

def save_tracked_channels():
    with open(CHANNELS_JSON, "w") as f:
        json.dump(tracked_channels, f)

async def get_roblox_status(user_id):
    try:
        response = requests.get(f"https://api.roblox.com/users/{user_id}/onlinestatus").json()
        # Example API response handling
        if response.get("IsOnline") is True:
            return "Online"
        elif response.get("IsOnline") is False:
            return "Offline"
        elif response.get("IsBanned"):
            return "Banned"
        else:
            return "Unknown"
    except Exception:
        return "Error"

# ---------------- STATUS UPDATER ---------------- #
@tasks.loop(seconds=CHECK_INTERVAL)
async def update_status_channels():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    for user_id in tracked_users:
        status = await get_roblox_status(user_id)
        channel_name = f"{user_id} : {status}"

        # Use existing channel if exists
        if str(user_id) in tracked_channels:
            channel = bot.get_channel(tracked_channels[str(user_id)])
            if channel:
                try:
                    await channel.edit(name=channel_name)
                except discord.errors.Forbidden:
                    pass
        else:
            # Create new private channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
            tracked_channels[str(user_id)] = channel.id
            save_tracked_channels()
        await asyncio.sleep(1)  # avoid rate limits

# ---------------- BOT EVENTS ---------------- #
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_status_channels.start()

# ---------------- SLASH COMMANDS ---------------- #
@bot.slash_command(name="check", description="Check status of a Roblox user by ID")
async def check(ctx, user_id: int):
    status = await get_roblox_status(user_id)
    await ctx.respond(f"User {user_id} status: {status}")

@bot.slash_command(name="adduser", description="Add a Roblox user to track")
async def adduser(ctx, user_id: int):
    if user_id not in tracked_users:
        tracked_users.append(user_id)
        additional_users.append(user_id)
        save_tracked_users()
        await ctx.respond(f"Added user {user_id} to tracking list.")
    else:
        await ctx.respond(f"User {user_id} is already tracked.")

@bot.slash_command(name="removeuser", description="Remove a Roblox user from tracking")
async def removeuser(ctx, user_id: int):
    if user_id in additional_users:
        tracked_users.remove(user_id)
        additional_users.remove(user_id)
        save_tracked_users()
        await ctx.respond(f"Removed user {user_id} from tracking list.")
    elif user_id in DEFAULT_USER_IDS:
        await ctx.respond(f"Cannot remove default user {user_id}.")
    else:
        await ctx.respond(f"User {user_id} is not tracked.")

# ---------------- RUN BOT ---------------- #
bot.run(TOKEN)
