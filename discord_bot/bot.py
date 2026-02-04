import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("Missing DISCORD_TOKEN. Copy .env.example to .env and set the token.")
    sys.exit(1)

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.event
async def on_member_join(member: discord.Member) -> None:
    channel = member.guild.system_channel
    if channel is None:
        return

    await channel.send(f"Welcome {member.mention}!")


if __name__ == "__main__":
    bot.run(TOKEN)
