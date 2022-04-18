import asyncio
import json
import modules.date as date
import random

from nextcord.ext import commands
from nextcord.colour import Colour
from nextcord import Embed, slash_command


class PidorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pidor_channels = {}
        self.pidor_stats = {}
        self.load()

    def save(self):
        with open('json/pidor_channels.json', 'w') as file:
            file.write(json.dumps(self.pidor_channels))
        with open('json/pidor_stats.json', 'w') as file:
            file.write(json.dumps(self.pidor_stats))

    def load(self):
        try:
            with open('json/pidor_channels.json', 'r') as file:
                self.pidor_channels = json.load(file)
            with open('json/pidor_stats.json', 'r') as file:
                self.pidor_stats = json.load(file)
        except (json.JSONDecodeError, TypeError, FileNotFoundError):
            pass

    @slash_command(name='pidor')
    async def roll(self, ctx):
        await ctx.response.defer()
        cur_time = str(date.current())
        channel_id = str(ctx.guild.id)
        if channel_id not in self.pidor_channels.keys():
            self.pidor_channels[channel_id] = {'time': cur_time, 'pidor': None}

        if self.pidor_channels[channel_id]['time'] != cur_time or \
                self.pidor_channels[channel_id]['pidor'] is None:
            await ctx.send(embed=Embed(title="Rolling cubes to decide Pidor Of The Day",
                                       color=Colour.random()), delete_after=15.0)
            await asyncio.sleep(3)
            for i in range(5, 0, -1):
                await ctx.send(embed=Embed(title="COUNTDOWN: " + str(i),
                                           color=Colour.random()), delete_after=12.0 - i)
                await asyncio.sleep(1)
            idx = random.randint(0, len(ctx.guild.members) - 1)
            user = str(ctx.guild.members[idx])
            self.pidor_channels[channel_id]['pidor'] = user
            self.pidor_channels[channel_id]['time'] = cur_time
            self.pidor_stats.setdefault(channel_id, {}).setdefault(user, 0)
            self.pidor_stats[channel_id][user] += 1
            embed = Embed(title="Pidor of the day: " + user, color=Colour.purple())
            self.save()
            await ctx.send(embed=embed)
        else:
            embed = Embed(title="Pidor of the day has already been chosen. Pidor: " +
                                self.pidor_channels[channel_id]['pidor'], color=Colour.random())
            await ctx.send(embed=embed, delete_after=180.0)

    @slash_command(name='pidor_board')
    async def get_pidor_stats(self, ctx):
        await ctx.response.defer()
        channel_id = str(ctx.guild.id)
        if channel_id not in self.pidor_stats.keys() or len(self.pidor_stats[channel_id]) == 0:
            embed = Embed(title="No stats for this server", color=Colour.blurple())
        else:
            stats = []
            for user in self.pidor_stats[channel_id]:
                stats.append([self.pidor_stats[channel_id][user], user])
            stats.sort(key=lambda t: (-t[0], t[1]))
            text = ''
            for idx, item in enumerate(stats):
                count = item[0]
                user = item[1]
                text += str(idx + 1) + '. ' + user
                text += ' (chosen ' + str(count) + ' ' + ('time' if count == 1 else 'times') + ')\n'
            embed = Embed(title="Pidor leaderboard:", description=text, color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=180.0)


def setup(bot):
    bot.add_cog(PidorCog(bot))
