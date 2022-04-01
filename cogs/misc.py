import json
import random
import constants
import urllib.request

from datetime import datetime
from modules.message_analysis import Analysis_module
from discord import Embed, File
from discord.ext import commands
from discord_slash import cog_ext


start_time = datetime.now()
start_time.isoformat(sep='T')
history = {}

very_clever_quotes = None
with open(constants.CLEVER_QUOTES_DIR, encoding='utf-8') as file:
    very_clever_quotes = file.read().split(";")

replies = None
with open(constants.REPLIES_DIR, encoding="utf-8") as f:
    lines = f.read().splitlines()
if len(lines) > 0:
    pairs = [l.split('//')[1].split('->') for l in lines]
    for p in pairs:
        p[1] = p[1].split(";")
    replies = {int(p[0]): p[1] for p in pairs}


def get_special_replies(author_id):
    if author_id in replies:
        return replies[author_id]
    else:
        return []


async def random_vot_da(ctx):
    if random.random() < 0.01:
        await ctx.channel.send('вот да')
    elif random.random() < 0.005:
        await ctx.channel.send(random.choice(very_clever_quotes))


async def cringe(ctx):
    if random.random() < 0.005 or ctx.clean_content[:5] == 'balab':
        query = ctx.clean_content
        if query[:5] == 'balab':
            query = query[6:]

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_4) AppleWebKit/605.1.15 '
                          '(KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Origin': 'https://yandex.ru',
            'Referer': 'https://yandex.ru/',
        }
        API_URL = 'https://zeapi.yandex.net/lab/api/yalm/text3'
        payload = {"query": query, "intro": 1, "filter": 1}
        params = json.dumps(payload).encode('utf8')
        req = urllib.request.Request(API_URL, data=params, headers=headers)
        response = urllib.request.urlopen(req)

        msg = json.loads(response.read())['text']
        await ctx.channel.send(msg)


async def random_emote(ctx):
    if random.random() < 0.05:
        await ctx.add_reaction(random.choice(ctx.guild.emojis))


async def message_repeating(ctx):
    if ctx.channel.id in history and ctx.content != '':
        if history[ctx.channel.id]['text'] == ctx.content:
            history[ctx.channel.id]['count'] += 1
            if (history[ctx.channel.id]['count'] == constants.MESSAGES_TO_REPEAT):
                await ctx.channel.send(history[ctx.channel.id]['text'])
                history[ctx.channel.id]['text'] = ''
                history[ctx.channel.id]['count'] = 0
        else:
            history[ctx.channel.id]['text'] = ctx.content
            history[ctx.channel.id]['count'] = 1
    else:
        history[ctx.channel.id] = {'text': ctx.content, 'count': 1}


async def reference_reaction(ctx, client):
    if (not ctx.reference
            or ctx.reference.resolved.author.id != client.user.id
            or ctx.author.id == client.user.id):
        return

    if replies:
        special_replies = get_special_replies(ctx.author.id)
        if special_replies:
            special_reply = random.choice(special_replies)
            if special_reply.startswith("&") or special_reply.startswith("№"):
                reply = f"{special_reply[1:]}"
            else:
                reply = f"{ctx.author.mention}, {special_reply}"
            await ctx.channel.send(reply)


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.client = bot
        self.analyzer = Analysis_module(self.client)

    @commands.Cog.listener()
    async def on_message(self, ctx):
        if ctx.author.id == self.client.user.id:
            return

        stupid_things = [random_vot_da, cringe, random_emote]
        await reference_reaction(ctx, self.client)
        await message_repeating(ctx)
        await random.choice(stupid_things)(ctx)

        await self.client.process_commands(ctx)
        self.analyzer.save_message(ctx)

    @cog_ext.cog_slash(name='RenaStare')
    async def rena_stare(self, ctx):
        await ctx.defer()
        await ctx.send(file=File(constants.GIF_DIRECTORY))

    @cog_ext.cog_slash(name='StartTime')
    async def send_start_time(self, ctx):
        embed = Embed(title='Bot working since ' + str(start_time.strftime('%b %d %Y %H:%M:%S') + ' UTC+03:00'))
        await ctx.send(embed=embed)

    @cog_ext.cog_slash(name='Top')
    async def send_top(self, ctx):
        await ctx.defer()
        await self.analyzer.get_top(ctx)

    @cog_ext.cog_slash(name='Voice')
    async def send_voice_activity(self, ctx):
        await ctx.defer()
        await self.analyzer.get_voice_activity(ctx)


def setup(bot):
    bot.add_cog(MiscCog(bot))