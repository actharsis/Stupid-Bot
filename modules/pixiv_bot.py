import asyncio
import datetime
import discord
import emoji
import os
import time

from PIL import Image
from constants import PIXIV_AUTO_QUERY_DELAY
from discord.ext import commands
from io import BytesIO
from modules.pixiv_auth import get_refresh_token
from pixivpy3 import *


def is_date(date_text):
    try:
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def read_pixiv_refresh_token():
    f = open("pixiv_token.txt", "r")
    token = f.readline()
    f.close()
    return token


class BetterAppPixivAPI(AppPixivAPI):
    def download(self, url, prefix='', path=os.path.curdir, name=None, replace=False, fname=None,
                 referer='https://app-api.pixiv.net/'):
        """Download image to file (use 6.0 app-api)"""
        file = name or os.path.basename(url)

        with self.requests_call('GET', url, headers={'Referer': referer}, stream=True) as response:
            img = Image.open(response.raw)
            return img


class PixivCog(commands.Cog):
    api = BetterAppPixivAPI()
    api.auth(refresh_token=read_pixiv_refresh_token())

    def __init__(self, bot):
        self.bot = bot
        self.chat = None
        self.last_auto_update = None
        self.last_query = None
        self.token_expiration_time = None

    def check_picture_channel(self, ctx):
        ch = ctx.channel
        if ch == self.chat:
            return True
        return False

    async def show_page(self, query, limit=None, save_query=True):
        if self.chat is not None:
            if query.illusts is None:
                await self.chat.send('Bad request')
                return
            for index, illust in enumerate(query.illusts):
                if limit is not None and index == limit:
                    break
                filename = str(illust.id) + '.png'
                title = illust.title
                with BytesIO() as image_binary:
                    img = self.api.download(illust.image_urls.large)
                    img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    await self.chat.send('Title: ' + title, file=discord.File(fp=image_binary, filename=filename))
            if save_query:
                self.last_query = query

    @commands.command(name='start')
    async def start_pixiv(self, ctx):
        self.chat = ctx.channel
        await ctx.send('Art channel selected')

    @commands.command(name='next')
    async def next(self, ctx):
        if self.check_picture_channel(ctx) and self.last_query is not None:
            query = self.api.parse_qs(self.last_query.next_url)
            await self.show_page(query)

    @commands.command(name='recommended')
    async def recommended(self, ctx, *args):
        limit = 10
        if self.check_picture_channel(ctx):
            if len(args) >= 1:
                limit = args[0]
            query = self.api.illust_recommended()
            await self.show_page(query, limit=limit, save_query=False)

    @commands.command(name='best')
    async def best(self, ctx, *args):
        limit = None
        date = None
        mode = 'week'
        # date: '2016-08-01'
        # mode: [day, week, month, day_male, day_female, week_original, week_rookie,
        #               day_r18, day_male_r18, day_female_r18, week_r18, week_r18g]
        if self.check_picture_channel(ctx):
            for arg in args:
                if arg.isnumeric():
                    limit = arg
                elif is_date(arg):
                    date = arg
                else:
                    mode = arg
            query = self.api.illust_ranking(mode=mode, date=date, offset=None)
            await self.show_page(query, limit=limit, save_query=True)

    @commands.command(name='when')
    async def time_to_update(self, ctx):
        if self.last_auto_update is None:
            self.chat.send('autopost turned off')
        delta = str(time.time() - self.last_auto_update)
        self.chat.send(delta + ' secs remain before autopost')

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if not user.bot:
            if reaction.message.attachments is not None and len(reaction.message.attachments) == 1 and \
                    reaction.message.author.bot:
                illust_id = reaction.message.attachments[0].filename.split('.')[0]
                emojis = {':red_heart:', ':growing_heart:', ':broken_heart:', ':red_question_mark:'}
                demojized = emoji.demojize(reaction.emoji)
                if demojized == ':red_heart:':
                    self.api.illust_bookmark_add(illust_id)
                if demojized == ':growing_heart:':
                    self.api.illust_bookmark_add(illust_id)
                    query = self.api.illust_related(illust_id)
                    await self.show_page(query, limit=5, save_query=False)
                if demojized == ':broken_heart:':
                    self.api.illust_bookmark_delete(illust_id)
                if demojized == ':red_question_mark:':
                    detail = self.api.illust_bookmark_detail(illust_id)
                    self.chat.send("Art detail:\n" + detail)
                if demojized in emojis:
                    await reaction.remove(user)
                    await reaction.message.add_reaction(emoji.emojize(':thumbs_up:'))
        else:
            time.sleep(5)
            await reaction.remove(user)

    async def auto_draw(self):
        if self.chat is not None:
            timestamp = time.time()
            if self.last_auto_update is None or timestamp - self.last_auto_update > PIXIV_AUTO_QUERY_DELAY:
                query = self.api.illust_recommended()
                await self.show_page(query, limit=20, save_query=False)
                self.last_auto_update = timestamp

    async def auto_refresh_token(self):
        timestamp = time.time()
        if self.token_expiration_time is None or self.token_expiration_time - timestamp < 1000:
            token, ttl = get_refresh_token(read_pixiv_refresh_token())
            out = open("pixiv_token.txt", "w")
            out.write(token)
            out.close()
            self.token_expiration_time = timestamp + ttl
            self.api.auth(refresh_token=token)
            print('pixiv token updated')

    @commands.Cog.listener()
    async def on_ready(self):
        while True:
            await asyncio.sleep(10)
            await self.auto_draw()
            await self.auto_refresh_token()


def setup(bot):
    bot.add_cog(PixivCog(bot))
