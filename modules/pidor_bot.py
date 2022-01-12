import asyncio
import json
import random
import time

from discord import Embed
from discord.colour import Colour
from discord.ext import commands
from discord_slash import cog_ext


def current_date():
    return time.strftime('%Y-%m-%d', time.localtime(time.time()))


class PidorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pidor_channels = {}
        self.load()

    def save(self):
        with open('pidor_channels.json', 'w') as file:
            file.write(json.dumps(self.pidor_channels))

    def load(self):
        try:
            with open('pidor_channels.json', 'r') as file:
                self.pidor_channels = json.load(file)
        except:
            pass

    @cog_ext.cog_slash(name='pidor')
    async def roll(self, ctx):
        await ctx.defer()
        cur_time = str(current_date())
        if ctx.guild.id not in self.pidor_channels.keys():
            self.pidor_channels[ctx.guild.id] = {'time': cur_time, 'pidor': None}

        if self.pidor_channels[ctx.guild.id]['time'] != cur_time or \
                self.pidor_channels[ctx.guild.id]['pidor'] is None:
            await ctx.send(embed=Embed(title="Rolling cubes to decide Pidor Of The Day",
                                       color=Colour.gold()), delete_after=15.0)
            await asyncio.sleep(3)
            for i in range(5, 0, -1):
                await ctx.send(embed=Embed(title="COUNTDOWN: " + str(i),
                                           color=Colour.gold()), delete_after=12.0 - i)
                await asyncio.sleep(1)
            idx = random.randint(0, len(ctx.guild.members) - 1)
            user = str(ctx.guild.members[idx])
            self.pidor_channels[ctx.guild.id]['pidor'] = user
            self.pidor_channels[ctx.guild.id]['time'] = cur_time
            embed = Embed(title="Pidor of the day: " + user, color=Colour.gold())
            self.save()
        else:
            embed = Embed(title="Pidor of the day has already been chosen. Pidor: " +
                                self.pidor_channels[ctx.guild.id]['pidor'], color=Colour.gold())
        await ctx.send(embed=embed, delete_after=180.0)


def setup(bot):
    bot.add_cog(PidorCog(bot))
