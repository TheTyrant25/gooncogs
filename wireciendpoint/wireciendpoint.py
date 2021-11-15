import asyncio
import urllib
from collections import OrderedDict
import struct
import discord
from redbot.core import commands, Config, checks
from redbot.core.data_manager import cog_data_path, bundled_data_path
import discord.errors
from redbot.core.bot import Red
from typing import *
from fastapi import Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import re
import time
import functools
import inspect
import collections
from pydantic import BaseModel
import datetime
import random
from bisect import bisect
from itertools import accumulate

EMOJI_RANGES_UNICODE = {
    6: [
        ('\U0001F300', '\U0001F320'),
        ('\U0001F330', '\U0001F335'),
        ('\U0001F337', '\U0001F37C'),
        ('\U0001F380', '\U0001F393'),
        ('\U0001F3A0', '\U0001F3C4'),
        ('\U0001F3C6', '\U0001F3CA'),
        ('\U0001F3E0', '\U0001F3F0'),
        ('\U0001F400', '\U0001F43E'),
        ('\U0001F440', ),
        ('\U0001F442', '\U0001F4F7'),
        ('\U0001F4F9', '\U0001F4FC'),
        ('\U0001F500', '\U0001F53C'),
        ('\U0001F540', '\U0001F543'),
        ('\U0001F550', '\U0001F567'),
        ('\U0001F5FB', '\U0001F5FF')
    ],
    7: [
        ('\U0001F300', '\U0001F32C'),
        ('\U0001F330', '\U0001F37D'),
        ('\U0001F380', '\U0001F3CE'),
        ('\U0001F3D4', '\U0001F3F7'),
        ('\U0001F400', '\U0001F4FE'),
        ('\U0001F500', '\U0001F54A'),
        ('\U0001F550', '\U0001F579'),
        ('\U0001F57B', '\U0001F5A3'),
        ('\U0001F5A5', '\U0001F5FF')
    ],
    8: [
        ('\U0001F300', '\U0001F579'),
        ('\U0001F57B', '\U0001F5A3'),
        ('\U0001F5A5', '\U0001F5FF')
    ]
}

def random_emoji(unicode_version = 8, rnd = random):
    if unicode_version in EMOJI_RANGES_UNICODE:
        emoji_ranges = EMOJI_RANGES_UNICODE[unicode_version]
    else:
        emoji_ranges = EMOJI_RANGES_UNICODE[-1]

    # Weighted distribution
    count = [ord(r[-1]) - ord(r[0]) + 1 for r in emoji_ranges]
    weight_distr = list(accumulate(count))

    # Get one point in the multiple ranges
    point = rnd.randrange(weight_distr[-1])

    # Select the correct range
    emoji_range_idx = bisect(weight_distr, point)
    emoji_range = emoji_ranges[emoji_range_idx]

    # Calculate the index in the selected range
    point_in_range = point
    if emoji_range_idx != 0:
        point_in_range = point - weight_distr[emoji_range_idx - 1]

    # Emoji 😄
    emoji = chr(ord(emoji_range[0]) + point_in_range)
    emoji_codepoint = "U+{}".format(hex(ord(emoji))[2:].upper())

    return (emoji, emoji_codepoint)


class WireCiEndpoint(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, 1482189223515)
        self.config.register_global(channels={}, repo=None)
        self.rnd = random.Random()
        self.funny_messages = open(bundled_data_path(self) / "code_quality.txt").readlines()

    def register_to_general_api(self, app):
        class BuildFinishedModel(BaseModel):
            api_key: str
            last_compile: str
            branch: str
            author: str
            message: str
            commit: str
            server: str
            error: Optional[str]

        @app.post("/wireci/build_finished")
        async def build_finished(data: BuildFinishedModel):
            if data.api_key != (await self.bot.get_shared_api_tokens('wireciendpoint'))['api_key']:
                return 
            success = data.error is None
            channels = await self.config.channels()
            if not len(channels):
                return
            data.branch = data.branch.strip()
            repo = await self.config.repo()
            message = ""
            embed = None
            goonservers = self.bot.get_cog('GoonServers')
            server = goonservers.resolve_server(data.server)
            if success:
                commit_message = data.message.strip()
                if '\n' in commit_message:
                    commit_message = commit_message.split('\n')[0]
                guild = self.bot.get_channel(int(next(iter(channels)))).guild
                message = f"__{data.branch}__ on {server.short_name} \N{white heavy check mark} `{data.commit[:7]}` by {data.author}: `{commit_message}`\nCode quality: {self.funny_message(data.commit, guild)}"
            else:
                embed = discord.Embed()
                embed.title = f"`{data.branch}` on {server.short_name}: " + ("succeeded" if success else "failed")
                embed.colour = discord.Colour.from_rgb(60, 100, 45) if success else discord.Colour.from_rgb(150, 60, 45)
                embed.description = f"```\n{data.last_compile}\n```"
                if not success:
                    error_message = data.error
                    if error_message.lower() == "true":
                        pass
                    elif '\n' in error_message.strip():
                        embed.description += f"\nError:\n```{error_message}```"
                    else:
                        embed.description += f"\nError: `{error_message.strip()}`"
                embed.timestamp = datetime.datetime.utcnow()
                embed.set_image(url=f"https://opengraph.githubassets.com/1/{repo}/commit/{data.commit}")
                embed.add_field(name="commit", value=f"[{data.commit[:7]}](https://github.com/{repo}/commit/{data.commit})")
                embed.add_field(name="message", value=data.message)
                embed.add_field(name="author", value=data.author)
                embed.set_footer(text="Code quality: " + self.funny_message(data.commit))
                if not success:
                    author_discord_id = None
                    githubendpoint = self.bot.get_cog("GithubEndpoint")
                    if githubendpoint:
                        author_discord_id = await githubendpoint.config.custom("contributors", data.author).discord_id()
                    if author_discord_id is not None:
                        message = self.bot.get_user(author_discord_id).mention
            for channel_id in channels:
                channel = self.bot.get_channel(int(channel_id))
                if embed:
                    await channel.send(message, embed=embed)
                else:
                    await channel.send(message)

    def funny_message(self, seed, guild=None):
        self.rnd.seed(seed)
        if self.rnd.randint(1, 30) == 1:
            if guild and self.rnd.randint(1, 2) == 1:
                return str(self.rnd.choice(guild.emojis))
            else:
                return random_emoji(rnd=self.rnd)[0]
        if self.rnd.randint(1, 1 + len(self.funny_messages)) == 1:
            return "Rolling a d20 for a quality check: " + str(self.rnd.randint(1, 20))
        if self.rnd.randint(1, 1 + len(self.funny_messages)) == 1:
            githubendpoint = self.bot.get_cog("GithubEndpoint")
            if githubendpoint:
                person = self.rnd.choice(list(githubendpoint.config.custom("contributors").all().keys()))
                return f"Like a thing {person} wrote."
        return self.rnd.choice(self.funny_messages)

    @commands.group()
    @checks.admin()
    async def wireciendpoint(self, ctx: commands.Context):
        """Manage messages sent from GitHub."""
        pass

    @wireciendpoint.command()
    async def addchannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
        if channel is None:
            channel = ctx.channel
        async with self.config.channels() as channels:
            channels[str(channel.id)] = None
        await ctx.send(f"Channel {channel.mention} will now receive notifications about builds.")

    @wireciendpoint.command()
    async def setrepo(self, ctx: commands.Context, repo: str):
        await self.config.repo.set(repo)
        await ctx.send(f"Repo set to `{repo}`.")

    @wireciendpoint.command()
    async def removechannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
        if channel is None:
            channel = ctx.channel
        async with self.config.channels() as channels:
            del channels[str(channel.id)]
        await ctx.send(f"Channel {channel.mention} will no longer receive notifications about builds.")

    @wireciendpoint.command()
    async def checkchannels(self, ctx: commands.Context):
        channel_ids = await self.config.channels()
        if not channel_ids:
            await ctx.send("No channels.")
        else:
            await ctx.send("\n".join(self.bot.get_channel(int(ch)).mention for ch in channel_ids))

