import asyncio
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
    except (ValueError, TypeError):
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


def next_year(date, time_format):
    ptime = time.mktime(time.strptime(date, time_format))
    ptime += 31536000
    return time.strftime(time_format, time.localtime(ptime))


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
        if channel is None or query.illusts is None or len(query.illusts) == 0:
            return 0, 0, False
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
        return shown, len(query.illusts), True

    async def show_page_embed(self, query, query_type, chat, limit=None, save_query=True):
        shown, total, result = await self.show_page(query, chat, limit)
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

    @cog_ext.cog_slash(name='find', description='Find illustrations that satisfy the filters from random point of time',
                       options=[
                           create_option(
                               name="word",
                               description="Find by specific word (default = 猫耳)",
                               option_type=SlashCommandOptionType.STRING,
                               required=False,
                           ),
                           create_option(
                               name="match",
                               description="Word match rule (default = partial_match_for_tags)",
                               option_type=SlashCommandOptionType.STRING,
                               required=False,
                               choices=[
                                   create_choice("partial_match_for_tags", "partial_match_for_tags"),
                                   create_choice("exact_match_for_tags", "exact_match_for_tags"),
                                   create_choice("title_and_caption", "title_and_caption")
                               ]
                           ),
                           create_option(
                               name="limit",
                               description="Maximum amount of pictures that will be shown (default 5, maximum = 10)",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False,
                           ),
                           create_option(
                               name="views",
                               description="Required minimum amount of views (default = 3500)",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False,
                           ),
                           create_option(
                               name="rate",
                               description="Required minimum percent of views/bookmarks (default = 3)",
                               option_type=SlashCommandOptionType.FLOAT,
                               required=False,
                           ),
                           create_option(
                               name="since_date",
                               description="Fixed date in format YYYY-MM-DD from which search will be initialized",
                               option_type=SlashCommandOptionType.STRING,
                               required=False,
                           )])
    async def find(self, ctx, word='猫耳', match='partial_match_for_tags',
                   limit=5, views=3500, rate=3.0, since_date=None):
        await ctx.defer()
        limit = min(limit, 10)
        date = random_date('2009-01-01', current_date(), random.random())
        if is_date(since_date):
            date = since_date
        fetched, shown, offset, alive = 0, 0, 0, True
        while shown < limit and alive and fetched < 3000:
            query = self.api.search_illust(word, search_target=match,
                                           end_date=date, offset=offset)
            if len(query.illusts) == 0 and date < current_date():
                date = next_year(date, '%Y-%m-%d')
                offset = 0
                continue
            good, total, alive = await self.show_page(query, ctx.channel, limit - shown, views, rate)
            shown += good
            fetched += total
            if alive:
                offset += total
        embed = Embed(title="Find with word " + word + " called",
                      description=str(fetched) + " images fetched in total",
                      color=Colour.green())
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
        elif demojized in [':broken_heart:', ':thumbs_up:']:
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
