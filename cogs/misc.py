import json
import random
import urllib.request
from datetime import datetime, timezone

from nextcord import Embed, slash_command
from nextcord.ext import commands
import git
import pymongo
from config import DB_ADDRESS, DB_NAME
from modules.message_analysis import AnalysisModule


start_time = datetime.now()
start_time.isoformat(sep='T')

history = {}

async def cringe(ctx):
    if random.random() >= 0.005 and ctx.clean_content[:5] != 'balab':
        return
    query = ctx.clean_content
    if query[:5] == 'balab':
        query = query[6:]

    api_url = 'https://zeapi.yandex.net/lab/api/yalm/text3'
    payload = {"query": query, "intro": 1, "filter": 1}
    params = json.dumps(payload).encode('utf8')
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_4)\
                AppleWebKit/605.1.15 ' '(KHTML, like Gecko) Version/14.1.1 Safari/605.1.15', 'Origin': 'https://yandex.ru',
               'Referer': 'https://yandex.ru/', }

    req = urllib.request.Request(api_url, data=params, headers=headers)
    response = urllib.request.urlopen(req)

    msg = json.loads(response.read())['text']
    await ctx.channel.send(msg)


async def random_emote(ctx):
    if random.random() < 0.05:
        await ctx.add_reaction(random.choice(ctx.guild.emojis))


async def reference_reaction(ctx, client):
    if not ctx.reference or ctx.reference.resolved.author.id != client.user.id or ctx.author.id == client.user.id:
        return


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.db = pymongo.MongoClient(DB_ADDRESS)[DB_NAME]
        self.client = bot
        self.analyzer = AnalysisModule(self.client, self.db)

    @commands.Cog.listener()
    async def on_message(self, ctx):
        if ctx.author.id == self.client.user.id:
            return

        stupid_things = [cringe, random_emote]
        await reference_reaction(ctx, self.client)
        await random.choice(stupid_things)(ctx)

        await self.client.process_commands(ctx)
        self.analyzer.save_message(ctx)

    @slash_command(name='info')
    async def send_start_time(self, ctx):
        repo = git.Repo(search_parent_directories=True)
        sha = repo.head.object.hexsha
        committed_date = repo.head.object.committed_date
        now = datetime.now()
        local_now = now.astimezone()
        local_tz = local_now.tzinfo
        local_tzname = local_tz.tzname(local_now)
        embed = Embed(title='info', description='Bot working since ' +
                      str(start_time.strftime('%b %d %Y %H:%M:%S') + ' ' + local_tzname + '\n \
                          Last commit: ' + sha +'\n \
                          Commit\'s date: ' + str(datetime.fromtimestamp(committed_date, timezone.utc))))
        await ctx.send(embed=embed, ephemeral=True)

    @slash_command(name='top')
    async def send_top(self, ctx):
        await self.analyzer.get_user_scores(ctx)

    @slash_command(name='voice')
    async def send_voice_activity(self, ctx):
        await self.analyzer.get_voice_activity(ctx)

    @slash_command(name='activity_date_plot')
    async def send_activity_date_plot(self, ctx):
        answer = await self.analyzer.get_activity_date_plot(ctx)
        await ctx.send(embed=answer, ephemeral=True)


def setup(bot):
    bot.add_cog(MiscCog(bot))
