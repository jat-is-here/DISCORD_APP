# bot.py
import os
import discord
from discord.ext import commands
from flask import Flask
from duckduckgo_search import DDGS
from threading import Thread
import dotenv
from datetime import timedelta
import requests

# -------------------- ENV --------------------
dotenv.load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
OWNER_IDS = [int(x.strip()) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0") or 0)
OPENROUTER_API_KEY = os.getenv("API_KEY")
AI_MODEL = "openrouter-gpt-3.5-mini"

# -------------------- RULES STORAGE --------------------
rules = []  # Each rule = {"condition": str, "action": str}

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

# -------------------- WEB SEARCH --------------------
def web_search(query, max_results=3):
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
    summary = "\n".join([f"- {r['title']} ({r['href']})" for r in results])
    return summary or "No results found."

# -------------------- OPENROUTER AI --------------------
conversation_histories = {}

def add_to_history(user_id, message):
    history = conversation_histories.get(user_id, [])
    history.append(message)
    conversation_histories[user_id] = history[-20:]  # Keep last 20 messages

def generate_reply_openrouter(user_id, user_message):
    add_to_history(user_id, f"User: {user_message}")
    messages = [{"role": "user", "content": msg} for msg in conversation_histories[user_id]]

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "max_tokens": 150
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://api.openrouter.ai/v1/chat/completions", json=payload, headers=headers, timeout=15)
        reply = response.json()["choices"][0]["message"]["content"].strip()
        add_to_history(user_id, f"AI: {reply}")
        return reply
    except Exception as e:
        print("OpenRouter API error:", e)
        return "❌ Sorry, I cannot respond right now."

# -------------------- ACTION DECIDER --------------------
def decide_action_local(user_message):
    msg = user_message.lower()
    if msg.startswith("kick"):
        return "KICK"
    elif msg.startswith("ban"):
        return "BAN"
    elif msg.startswith("mute"):
        return "MUTE"
    elif msg.startswith("unmute"):
        return "UNMUTE"
    elif msg.startswith("search"):
        return "SEARCH"
    elif msg.startswith("ping"):
        return "PING"
    elif "who am i" in msg:
        return "WHO AM I"
    elif msg.startswith("set logs"):
        return "SET LOGS"
    elif msg.startswith("set prefix"):
        return "SET PREFIX"
    elif msg.startswith("rule") or "mute" in msg or "ban" in msg:
        return "RULES"
    else:
        return "CHAT"

def parse_rule_local(user_text):
    try:
        if "mute" in user_text.lower():
            word = user_text.split("mute")[-1].strip()
            return {"condition": f"message contains {word}", "action": "MUTE"}
        if "kick" in user_text.lower():
            return {"condition": "message mentions owner", "action": "KICK"}
        if "ban" in user_text.lower():
            return {"condition": "message contains abuse words", "action": "BAN"}
        if "unban" in user_text.lower():
            return {"condition": "message contains sorry", "action": "UNBAN"}
    except:
        return None

# -------------------- RULES HANDLING --------------------
async def apply_rules(message):
    for rule in rules:
        cond = rule["condition"].lower()
        act = rule["action"].upper()
        triggered = False
        if "contains" in cond:
            word = cond.replace("message contains", "").strip()
            if word in message.content.lower():
                triggered = True
        elif "mentions owner" in cond:
            if any(oid == message.author.id for oid in OWNER_IDS):
                triggered = True
        if triggered:
            try:
                if act == "MUTE":
                    await message.author.timeout(timedelta(minutes=10), reason="Rule violation")
                    await message.channel.send(f"⏱️ {message.author.mention} muted (rule: {cond})")
                elif act == "KICK":
                    await message.author.kick(reason="Rule violation")
                    await message.channel.send(f"👢 {message.author.mention} kicked (rule: {cond})")
                elif act == "BAN":
                    await message.author.ban(reason="Rule violation")
                    await message.channel.send(f"🔨 {message.author.mention} banned (rule: {cond})")
                elif act == "UNMUTE":
                    await message.author.timeout(None, reason="Rule violation")
                    await message.channel.send(f"✅ {message.author.mention} unmuted (rule: {cond})")
                elif act == "UNBAN":
                    bans = await message.guild.bans()
                    for ban_entry in bans:
                        if ban_entry.user.name.lower() in message.content.lower():
                            await message.guild.unban(ban_entry.user, reason="Rule violation - UNBAN")
                            await message.channel.send(f"✅ Unbanned {ban_entry.user} (rule: {cond})")
                            break
            except discord.Forbidden:
                await message.channel.send(f"❌ No permission to perform {act}!")
            await log_action(message.guild, f"Rule triggered: {rule} → {message.author}")
            break

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
    except Exception as e:
        print("log_action error:", e)

# -------------------- DISCORD EVENTS --------------------
@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name="Serving the Jaat Clan"))
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

# -------------------- MESSAGE HANDLING --------------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await apply_rules(message)

    user_text = None
    reply_context = None

    if message.reference and isinstance(message.reference.resolved, discord.Message):
        replied_message = message.reference.resolved
        if replied_message.author == bot.user:
            reply_context = replied_message.content
            user_text = message.content
    elif bot.user.mentioned_in(message):
        user_text = message.content.replace(f"<@!{bot.user.id}>", "").strip()
    elif message.content.startswith(PREFIX):
        user_text = message.content[len(PREFIX):].strip()

    if not user_text:
        await bot.process_commands(message)
        return

    await bot.process_commands(message)

    try:
        ai_input = f"You are replying to: '{reply_context}'\nUser: '{user_text}'" if reply_context else user_text
        action = decide_action_local(ai_input)

        if action == "CHAT":
            reply = generate_reply_openrouter(message.author.id, ai_input)
            await message.reply(reply, mention_author=False)
        elif action == "SEARCH":
            results = web_search(ai_input)
            await message.reply(f"🔍 Search results:\n{results}", mention_author=False)
        elif action == "PING":
            await message.reply(f"Pong! {int(bot.latency*1000)}ms", mention_author=False)
        elif action == "WHO AM I":
            await message.reply("Hey ♕Master, you are an owner!" if is_owner(message.author) else "You are a member.", mention_author=False)
        elif action in {"KICK","BAN","MUTE","UNMUTE"}:
            if not is_owner(message.author):
                await message.reply(f"❌ '{action}' requires owner permissions!", mention_author=False)
                return
            if not message.mentions:
                await message.reply(f"❌ You must mention a member to {action.lower()}!", mention_author=False)
                return
            member = message.mentions[0]
            reason = user_text.replace(member.mention,"").strip() or "No reason provided"
            if action == "KICK":
                await member.kick(reason=reason)
                await message.reply(f"Kicked {member}", mention_author=False)
            elif action == "BAN":
                await member.ban(reason=reason)
                await message.reply(f"Banned {member}", mention_author=False)
            elif action == "MUTE":
                await member.timeout(timedelta(minutes=10), reason=reason)
                await message.reply(f"Muted {member} for 10 mins", mention_author=False)
            elif action == "UNMUTE":
                await member.timeout(None, reason=reason)
                await message.reply(f"Unmuted {member}", mention_author=False)
        elif action in {"SET LOGS","SET PREFIX"} and is_owner(message.author):
            if action=="SET LOGS" and message.channel_mentions:
                global LOG_CHANNEL_ID
                LOG_CHANNEL_ID = message.channel_mentions[0].id
                await message.reply(f"✅ Log channel set to {message.channel_mentions[0].mention}", mention_author=False)
            elif action=="SET PREFIX":
                parts = user_text.split()
                if len(parts)>=2:
                    global PREFIX
                    PREFIX = parts[1]
                    bot.command_prefix = PREFIX
                    await message.reply(f"✅ Updated prefix to `{PREFIX}`", mention_author=False)
        elif action=="RULES" and is_owner(message.author):
            rule = parse_rule_local(user_text)
            if rule and "condition" in rule and "action" in rule:
                rules.append(rule)
                await message.reply(f"✅ Added rule: If {rule['condition']} then {rule['action']}", mention_author=False)
            else:
                await message.reply("❌ Failed to parse rule.", mention_author=False)
        else:
            await message.reply("❌ Unable to determine action.", mention_author=False)
    except Exception as e:
        await message.reply(f"❌ Error: {e}", mention_author=False)
        print("Error in on_message:", e)

# -------------------- COMMANDS --------------------
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {int(bot.latency*1000)}ms")

@bot.command()
async def shutdown(ctx):
    if is_owner(ctx):
        await ctx.send("Shutting down...")
        await bot.close()
    else:
        await ctx.send("❌ You are not an owner!")

# -------------------- MAIN --------------------
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
