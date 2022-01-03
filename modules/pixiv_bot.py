import asyncio
import datetime
import emoji
import os
import time

from PIL import Image
from constants import PIXIV_AUTO_QUERY_DELAY
from discord import Embed, File
from discord.colour import Colour
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.utils.manage_commands import create_option, create_choice
from discord_slash.model import SlashCommandOptionType
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
    with open("pixiv_token.txt", "r") as f:
        token = f.readline()
    return token


class BetterAppPixivAPI(AppPixivAPI):
    def download(self, url, prefix='', path=os.path.curdir, name=None, replace=False, fname=None,
                 referer='https://app-api.pixiv.net/'):
        """Download image to file (use 6.0 app-api)"""
        file = name or os.path.basename(url)

        with self.requests_call('GET', url, headers={'Referer': referer}, stream=True) as response:
            return Image.open(response.raw)


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
        return ch == self.chat

    async def show_page(self, query, limit=None, save_query=True):
        if self.chat is not None:
            if query.illusts is None:
                return False
            for index, illust in enumerate(query.illusts):
                if limit is not None and index == limit:
                    break
                filename = str(illust.id) + '.png'
                title = illust.title
                with BytesIO() as image_binary:
                    img = self.api.download(illust.image_urls.large)
                    img.save(image_binary, 'PNG')
                    image_binary.seek(0)
                    await self.chat.send('Title: ' + title, file=File(fp=image_binary, filename=filename))
            if save_query:
                self.last_query = query
            return True
        return False
    
    async def show_page_embed(self, query, limit=None, save_query=True):
        success = await self.show_page(query, limit, save_query)
        if success:
            return Embed(title="Illustrations loaded", color=Colour.green())
        else:
            return Embed(title="Pixiv API can't process the request", color=Colour.red())

    @cog_ext.cog_slash(name="start", description="Select current channel as default for pixiv illustrations")
    async def start_pixiv(self, ctx):
        self.chat = ctx.channel
        embed = Embed(title="Art channel selected", color=Colour.green())
        await ctx.send(embed=embed)

    @cog_ext.cog_slash(name='next', description="Show next page from the last 'best' query",
                        options=[
                        create_option(
                            name="limit",
                            description="Amount of pictures will be displayed (default = 10)",
                            option_type=SlashCommandOptionType.INTEGER,
                            required=False,
                        )])
    async def next(self, ctx, limit=10):
        await ctx.defer()
        if self.check_picture_channel(ctx) and self.last_query is not None:
            query = self.api.parse_qs(self.last_query.next_url)
            embed = await self.show_page_embed(query, limit, save_query=True)
        else:
            embed = Embed(title="This channel is not defined as illustration channel", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='recommended', description="Show [10] recommended pixiv illustrations",
                        options=[
                        create_option(
                            name="limit",
                            description="Amount of pictures will be displayed (default = 10)",
                            option_type=SlashCommandOptionType.INTEGER,
                            required=False,
                        )])
    async def recommended(self, ctx, limit=10):
        await ctx.defer()
        if self.check_picture_channel(ctx):
            limit = int(limit)
            query = self.api.illust_recommended()
            embed = await self.show_page_embed(query, limit, save_query=False)
        else:
            embed = Embed(title="This channel is not defined as illustration channel", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='best', description='Find best [10] rated illutstrations with specific mode and date',
                        options=[
                        create_option(
                            name="mode",
                            description="Specify one of the types",
                            option_type=SlashCommandOptionType.STRING,
                            required=False,
                            choices=[
                                create_choice("day", "Day"),
                                create_choice("week", "Week"),
                                create_choice("month", "Month"),
                                create_choice("day_male", "Day Male likes"),
                                create_choice("day_female", "Day Female likes"),
                                create_choice("day_r18", "Day Ecchi"),
                                create_choice("day_male_r18", "Day Male likes Ecchi"),
                                create_choice("week_r18", "Week Ecchi"),
                            ]
                        ),
                        create_option(
                            name="limit",
                            description="Amount of pictures will be displayed (default = 10)",
                            option_type=SlashCommandOptionType.INTEGER,
                            required=False
                        ),
                        create_option(
                            name="date",
                            description="Date of sample in format: YYYY-MM-DD",
                            option_type=SlashCommandOptionType.STRING,
                            required=False
                        )
                        ])
    async def best(self, ctx, mode='month', limit=10, date=None):
        await ctx.defer()
        if self.check_picture_channel(ctx):
            query = self.api.illust_ranking(mode=mode, date=date, offset=None)
            embed = await self.show_page_embed(query, limit, save_query=True)
        else:
            embed = Embed(title="This channel is not defined as illustration channel", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='when', description='Show remaining time until new illustrations')
    async def time_to_update(self, ctx):
        if self.last_auto_update is None:
            embed = Embed(title="timer has not started", color=Colour.gold())
        else:
            delta = str(int(PIXIV_AUTO_QUERY_DELAY + self.last_auto_update - time.time()))
            embed = Embed(title=str(delta) + ' secs remain before autopost', color=Colour.green())
        await ctx.send(embed=embed, delete_after=10.0)

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
                elif demojized == ':growing_heart:':
                    self.api.illust_bookmark_add(illust_id)
                    query = self.api.illust_related(illust_id)
                    await self.show_page(query, limit=5, save_query=False)
                elif demojized == ':broken_heart:':
                    self.api.illust_bookmark_delete(illust_id)
                elif demojized == ':red_question_mark:':
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
            with open("pixiv_token.txt", "w") as out:
                out.write(token)
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
