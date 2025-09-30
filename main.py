# bot.py
import os
import discord
from discord.ext import commands
from threading import Thread
from flask import Flask
import dotenv
from datetime import timedelta

# -------------------- ENV --------------------
dotenv.load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
OWNER_IDS = [int(x.strip()) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0") or 0)

# -------------------- KEEP ALIVE --------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8000)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# -------------------- DISCORD SETUP --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# -------------------- HELPERS --------------------
def is_owner(ctx_or_user):
    user_id = getattr(ctx_or_user, "id", getattr(ctx_or_user, "author", None) and ctx_or_user.author.id)
    return user_id in OWNER_IDS

async def log_action(guild, text):
    try:
        if LOG_CHANNEL_ID:
            ch = guild.get_channel(LOG_CHANNEL_ID)
            if ch:
                await ch.send(text)
    except:
        pass

# -------------------- DISCORD EVENTS --------------------
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="Serving the Clan"))
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# -------------------- COMMANDS --------------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {int(bot.latency*1000)}ms")

@bot.command()
async def whoami(ctx):
    await ctx.send("You are an owner!" if is_owner(ctx.author) else "You are a member.")

@bot.command()
async def kick(ctx, member: discord.Member, *, reason=None):
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to kick members!")
        return
    await member.kick(reason=reason)
    await ctx.send(f"👢 Kicked {member.mention}")

@bot.command()
async def ban(ctx, member: discord.Member, *, reason=None):
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to ban members!")
        return
    await member.ban(reason=reason)
    await ctx.send(f"🔨 Banned {member.mention}")

@bot.command()
async def mute(ctx, member: discord.Member, minutes: int = 10):
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to mute members!")
        return
    await member.timeout(timedelta(minutes=minutes))
    await ctx.send(f"⏱️ Muted {member.mention} for {minutes} minutes")

@bot.command()
async def unmute(ctx, member: discord.Member):
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to unmute members!")
        return
    await member.timeout(None)
    await ctx.send(f"✅ Unmuted {member.mention}")

@bot.command()
async def setprefix(ctx, new_prefix):
    global PREFIX
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to change prefix!")
        return
    PREFIX = new_prefix
    bot.command_prefix = PREFIX
    await ctx.send(f"✅ Updated command prefix to `{PREFIX}`")

@bot.command()
async def setlog(ctx, channel: discord.TextChannel):
    global LOG_CHANNEL_ID
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to set log channel!")
        return
    LOG_CHANNEL_ID = channel.id
    await ctx.send(f"✅ Log channel set to {channel.mention}")

@bot.command()
async def shutdown(ctx):
    if not is_owner(ctx.author):
        await ctx.send("❌ You are not allowed to shutdown!")
        return
    await ctx.send("Shutting down...")
    await bot.close()

# -------------------- MAIN --------------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
