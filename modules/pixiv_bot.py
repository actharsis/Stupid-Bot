import asyncio
import base64
import datetime
import emoji
import json
import os
import random
import time

from PIL import Image
from discord import Embed, File
from discord.colour import Colour
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option, create_choice
from io import BytesIO
from main import client
from modules.pixiv_auth import get_refresh_token
from pixivpy3 import *


def is_date(date_text):
    try:
        datetime.datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def str_time_prop(start, end, time_format, prop):
    stime = time.mktime(time.strptime(start, time_format))
    etime = time.mktime(time.strptime(end, time_format))
    ptime = stime + prop * (etime - stime)
    return time.strftime(time_format, time.localtime(ptime))


def random_date(start, end, prop):
    return str_time_prop(start, end, '%Y-%m-%d', prop)


def current_date():
    return time.strftime('%Y-%m-%d', time.localtime(time.time()))


def read_pixiv_refresh_token():
    with open("pixiv_token.txt", "r") as f:
        token = f.readline()
    return token


class BetterAppPixivAPI(AppPixivAPI):
    def download(self, url, prefix='', path=os.path.curdir, name=None, replace=False, fname=None,
                 referer='https://app-api.pixiv.net/'):
        with self.requests_call('GET', url, headers={'Referer': referer}, stream=True) as response:
            return Image.open(response.raw)


class PixivCog(commands.Cog):
    api = BetterAppPixivAPI()
    api.auth(refresh_token=read_pixiv_refresh_token())

    def __init__(self, bot):
        self.bot = bot
        self.channels = {}
        self.timers = {}
        self.last_query = None
        self.last_type = None
        self.token_expiration_time = None
        self.load()

    def save(self, channels=False, timers=False):
        if channels:
            with open('auto_pixiv_channels.json', 'w') as file:
                file.write(json.dumps(self.channels))
        if timers:
            with open('auto_pixiv_timers.json', 'w') as file:
                file.write(json.dumps(self.timers))

    def load(self):
        try:
            with open('auto_pixiv_channels.json', 'r') as file:
                self.channels = json.load(file)
            with open('auto_pixiv_timers.json', 'r') as file:
                self.timers = json.load(file)
        except:
            pass

    async def show_page(self, query, channel, limit=30, minimum_views=None, minimum_rate=None):
        if channel is None or query.illusts is None:
            return 0, False
        shown = 0
        print('fetched', len(query.illusts), 'images')
        for illust in query.illusts:
            if shown == limit:
                break
            if minimum_views is not None and illust.total_view < minimum_views:
                continue
            if minimum_rate is not None and illust.total_bookmarks / illust.total_view * 100 < minimum_rate:
                continue
            filename = str(illust.id) + '.png'
            title = illust.title
            with BytesIO() as image_binary:
                img = self.api.download(illust.image_urls.large)
                img.save(image_binary, 'PNG')
                image_binary.seek(0)
                message = await channel.send('Title: ' + title, file=File(fp=image_binary, filename=filename))
                shown += 1
            if illust.is_bookmarked:
                await message.add_reaction(emoji.emojize(':red_heart:'))
        return shown, True

    async def show_page_embed(self, query, query_type, chat, limit=None, save_query=True):
        shown, result = await self.show_page(query, chat, limit)
        if result:
            if save_query:
                self.last_query = query
                self.last_type = query_type
            return Embed(title="Illustrations loaded", color=Colour.green())
        else:
            return Embed(title="Pixiv API can't process the request", color=Colour.red())

    @cog_ext.cog_slash(name="start_auto_pixiv", description="Add channel to the auto Pixiv list",
                       options=[
                           create_option(
                               name="refresh_time",
                               description="Delay between auto update in minutes (default = 180)",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False,
                           ),
                           create_option(
                               name="limit",
                               description="Amount of pictures will be displayed (default = 20)",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False,
                           )])
    async def add_auto_pixiv(self, ctx, refresh_time=180, limit=20):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channels.keys():
            embed = Embed(title="Auto Pixiv already running on this channel", color=Colour.gold())
        else:
            self.channels[channel_id] = {"refresh_time": refresh_time * 60, "limit": limit}
            embed = Embed(title="Auto Pixiv is now running on this channel", color=Colour.green())
        await ctx.send(embed=embed)
        self.save(channels=True)

    @cog_ext.cog_slash(name="stop_auto_pixiv", description="Delete channel from the auto Pixiv list")
    async def delete_auto_pixiv(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channels.keys():
            self.channels.pop(channel_id)
            if channel_id in self.timers.keys():
                self.timers.pop(channel_id)
            embed = Embed(title="Channel has been deleted", color=Colour.green())
        else:
            embed = Embed(title="This channel not exist in the list", color=Colour.gold())
        await ctx.send(embed=embed)
        self.save(channels=True, timers=True)

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
        if self.last_query is not None:
            next_qs = self.api.parse_qs(self.last_query.next_url)
            query = None
            if self.last_type == 'recommended':
                query = self.api.illust_recommended(**next_qs)
            elif self.last_type == 'best':
                query = self.api.illust_ranking(**next_qs)
            embed = await self.show_page_embed(query, self.last_type, ctx.channel, limit, save_query=True)
        else:
            embed = Embed(title="Previous request not found", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='recommended', description="Show [10] recommended Pixiv illustrations",
                       options=[
                           create_option(
                               name="limit",
                               description="Amount of pictures will be displayed (default = 10)",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False,
                           )])
    async def recommended(self, ctx, limit=10):
        await ctx.defer()
        query = self.api.illust_recommended()
        embed = await self.show_page_embed(query, 'recommended', ctx.channel, limit, save_query=True)
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
        query = self.api.illust_ranking(mode=mode, date=date, offset=None)
        embed = await self.show_page_embed(query, 'best', ctx.channel, limit, save_query=True)
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='when', description='Show remaining time until new illustrations')
    async def time_to_update(self, ctx):
        channel_id = str(ctx.channel.id)
        if channel_id in self.timers.keys() and channel_id in self.channels:
            refresh_time = self.channels[channel_id]['refresh_time']
            last_update_time = self.timers[channel_id]
            delta = int(refresh_time + last_update_time - time.time())
            embed = Embed(title=str(delta // 60) + ' min ' + str(delta % 60) + ' secs until autopost',
                          color=Colour.green())
        else:
            embed = Embed(title="Timer has not started", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='secret', description='???')
    async def test_feature(self, ctx):
        await ctx.defer()
        if ctx.author_id == 360641399713955843:
            limit = 5
            min_views = 4000
            min_rate = 15.0
            date = random_date('2017-01-01', current_date(), random.random())
            counter = 0
            offset = 0
            fetched = 0
            alive = True
            while counter < limit and alive:
                query = self.api.search_illust(base64.b64decode('6KqV55Sf5pel').decode("utf-8"),
                                               sort='date_asc', end_date=date, offset=offset)
                shown, alive = await self.show_page(query, ctx.channel, limit - counter, min_views, min_rate)
                counter += shown
                fetched += 30
                if alive:
                    offset += len(query.illusts)
            embed = Embed(title="Secret feature called", description="Fetched " + str(fetched) + " images in total",
                          color=Colour.green())
        else:
            embed = Embed(title="You can't use this query", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        try:
            demojized = emoji.demojize(reaction.emoji)
        except TypeError:
            demojized = None
        if not reaction.me:
            if reaction.message.attachments is not None and len(reaction.message.attachments) == 1 and \
                    reaction.message.author == client.user:
                illust_id = reaction.message.attachments[0].filename.split('.')[0]
                emojis = {':red_heart:', ':growing_heart:', ':magnifying_glass_tilted_left:',
                          ':broken_heart:', ':red_question_mark:'}
                if demojized in emojis:
                    await reaction.remove(user)
                if demojized == ':red_heart:':
                    self.api.illust_bookmark_add(illust_id)
                    await reaction.message.add_reaction(emoji.emojize(':red_heart:'))
                elif demojized == ':growing_heart:':
                    self.api.illust_bookmark_add(illust_id)
                    await reaction.message.add_reaction(emoji.emojize(':red_heart:'))
                    query = self.api.illust_related(illust_id)
                    await self.show_page(query, reaction.message.channel, limit=5)
                elif demojized == ':magnifying_glass_tilted_left:':
                    await reaction.message.add_reaction(emoji.emojize(':thumbs_up:'))
                    query = self.api.illust_related(illust_id)
                    await self.show_page(query, reaction.message.channel, limit=5)
                elif demojized == ':broken_heart:':
                    self.api.illust_bookmark_delete(illust_id)
                    for r in reaction.message.reactions:
                        if r.me:
                            await r.remove(client.user)
                    await reaction.message.add_reaction(emoji.emojize(':broken_heart:'))
                elif demojized == ':red_question_mark:':
                    await reaction.message.add_reaction(emoji.emojize(':thumbs_up:'))
                    detail = self.api.illust_bookmark_detail(illust_id)
                    msg = "Tags: "
                    for tag in detail.bookmark_detail.tags:
                        msg += tag.name + ', '
                    msg = msg[:-2]
                    await reaction.message.reply(msg, delete_after=30.0)
        else:
            if demojized == ':broken_heart:' or demojized == ':thumbs_up:':
                await asyncio.sleep(5)
                await reaction.remove(user)

    async def auto_draw(self):
        try:
            for channel_id, options in self.channels.items():
                channel = self.bot.get_channel(int(channel_id))
                if channel is None:
                    continue
                refresh_time = options['refresh_time']
                limit = options['limit']
                timestamp = time.time()
                if channel_id not in self.timers.keys() or timestamp - self.timers[channel_id] > refresh_time:
                    query = self.api.illust_recommended()
                    await self.show_page(query, channel, limit=limit)
                    self.timers[str(channel_id)] = timestamp
                    self.save(timers=True)
        except RuntimeError:
            pass

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
