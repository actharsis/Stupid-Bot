import asyncio
import emoji
import json
import modules.date as date
import os
import random
import requests
import time

from PIL import Image
from config import pixiv_show_embed_illust, use_selenium, safety
from nextcord import Interaction, Embed, File, slash_command, SlashOption, TextInputStyle, ui
from nextcord.colour import Colour
from nextcord.ext import commands
from io import BytesIO
from modules.pixiv_auth import refresh_token, selenium_login
from pixivpy_async import *


class BetterAppPixivAPI(AppPixivAPI):
    def __init__(self, **requests_kwargs):
        super(AppPixivAPI, self).__init__(**requests_kwargs)

    async def download(self, url, prefix='', path=os.path.curdir, fname=None, auto_ext=True,
                       name=None, replace=False, referer='https://app-api.pixiv.net/'):
        stream = await self.down(url, referer, _request_content_type=False)
        response = await stream.__anext__()
        await stream.aclose()
        return Image.open(BytesIO(response))

    async def search_autocomplete(self, word, req_auth=True):
        hosts = 'https://app-api.pixiv.net'
        method = 'GET'
        url = '%s/v2/search/autocomplete' % hosts
        params = {
            'word': word,
        }
        return await self.requests_(method=method, url=url, params=params, auth=req_auth)


class LoginModal(ui.Modal):
    def __init__(self, ctx, pixiv) -> None:
        super().__init__(title="Pixiv login form", custom_id="login_form")
        self.ctx = ctx
        self.pixiv = pixiv
        self.add_item(
            ui.TextInput(
                label="Login",
                placeholder="login@gmail.com",
                custom_id="login",
                style=TextInputStyle.short,
                min_length=1,
                required=True
            )
        )
        self.add_item(
            ui.TextInput(
                label="Password",
                placeholder="p@ssw0rd",
                custom_id="password",
                style=TextInputStyle.short,
                min_length=1,
                required=True
            )
        )

    async def auth(self, login, password):
        try:
            token = await selenium_login(login, password)
            if token is None:
                await self.ctx.send(embed=Embed(title="Can't log in.\n"
                                                      "Incorrect account details or captcha required :(\n"
                                                      "Try pixiv token instead",
                                                color=Colour.red()),
                                    delete_after=10.0)
                return
            a = BetterAppPixivAPI()
            await a.login(refresh_token=token)
            server = str(self.ctx.guild.id)
            self.pixiv.api[token] = a
            self.pixiv.tokens[server] = {"value": token, "time": str(0)}
            embed = Embed(title="Successfully logged in :)", color=Colour.green())
            self.pixiv.save(tokens=True)
        except:
            embed = Embed(title="Can't log in with given token :(", color=Colour.red())
        await self.ctx.send(embed=embed, delete_after=10.0)

    async def callback(self, inter: Interaction) -> None:
        login = self.children[0].value
        password = self.children[1].value
        await inter.response.send_message(embed=Embed(title="Task created", color=Colour.green()),
                                          ephemeral=True, delete_after=5)
        await self.auth(login, password)


class TokenModal(ui.Modal):
    def __init__(self, ctx, pixiv) -> None:
        super().__init__(title="Pixiv token form", custom_id="login_form")
        self.ctx = ctx
        self.pixiv = pixiv
        self.add_item(
            ui.TextInput(
                label="Refresh token",
                placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                custom_id="token",
                style=TextInputStyle.short,
                min_length=1,
                required=True
            )
        )

    async def auth(self, token):
        try:
            a = BetterAppPixivAPI()
            await a.login(refresh_token=token)
            server = str(self.ctx.guild.id)
            self.pixiv.api[token] = a
            self.pixiv.tokens[server] = {"value": token, "time": str(0)}
            embed = Embed(title="Successfully logged in :)", color=Colour.green())
            self.pixiv.save(tokens=True)
        except:
            embed = Embed(title="Can't login with given token :(", color=Colour.red())
        await self.ctx.send(embed=embed, delete_after=10.0)

    async def callback(self, inter: Interaction) -> None:
        token = self.children[0].value
        await inter.response.send_message(embed=Embed(title="Task created", color=Colour.green()),
                                          ephemeral=True, delete_after=5)
        await self.auth(token)


def good_image(illust, minimum_views, minimum_rate, max_sanity):
    if minimum_views is not None and illust.total_view < minimum_views or \
            minimum_rate is not None and illust.total_bookmarks / illust.total_view * 100 < minimum_rate or \
            max_sanity < illust.sanity_level:
        return False
    return True


class PixivCog(commands.Cog, name="Pixiv"):
    """
    **Pixiv cog** - interaction with pixiv. Allows you to search
    by name and use filters, see similar, add to favorites, see
    recommended and much more.

    To use this cog, you need to authenticate once on your server.
    Please create an empty pixiv account and then use /pixiv_login
    to authenticate. I don't keep entered logins and passwords and
    I use them to get refresh_token via automatic queries.

    DO NOT GIVE ME DATA FROM YOUR MAIN ACCOUNT.
    **I DON'T NEED IT**.

    If /pixiv_login is disabled or not working, use /pixiv_token and
    paste your refresh token in form. A guide on how to get a
    refresh_token at the link below (required python 3):
    https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362

    Use /pixiv_status to check your connection to api
    and /pixiv_logout to remove your token from my db.
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ***Authenticate is required to work on multiple servers and for
    unique recommendations. Read how to do that in the text above.***

    ***Available commands***:
    **/find** - find images by specific name/tag
    **/start_auto_pixiv** - send recommendations in a certain quantity
    once in a while in a current channel
    **/when** - time until next auto recommendations
    **/best** - show best images in specific category
    **/recommended** - show your recommendations
    **/illust** - find image by pixiv id
    **/spoil_nsfw** - on/off nsfw picture spoiler
    **/next** - command to display the next stack of pictures (wip)

    ***Picture reactions (works only on pixiv images)***:
    :heart: or :elephant: - bookmark image
    :broken_heart: - remove from bookmarks
    :seedling: - show 5 similar images
    :mag: - show all images of this work in original quality
    :question: - image info
    :face_vomiting: - delete image
    """

    def __init__(self, bot):
        self.bot = bot
        self.api = {}
        self.channels = {}
        self.timers = {}
        self.tokens = {}
        self.last_query = {}
        self.last_type = {}
        self.token_expiration_time = None
        self.spoilers = {}
        self.fetched = {}
        self.queues = asyncio.Queue(0)
        self.queues.put_nowait(0)
        self.bot.loop.create_task(self.load())
        self.delay = 1

    def save(self, channels=False, timers=False, tokens=False):
        if channels:
            with open('json/auto_pixiv_channels.json', 'w') as file:
                file.write(json.dumps(self.channels))
        if timers:
            with open('json/auto_pixiv_timers.json', 'w') as file:
                file.write(json.dumps(self.timers))
        if tokens:
            with open('json/pixiv_tokens.json', 'w') as file:
                file.write(json.dumps(self.tokens))

    async def load(self):
        try:
            with open('json/auto_pixiv_channels.json', 'r') as file:
                self.channels = json.load(file)
            with open('json/auto_pixiv_timers.json', 'r') as file:
                self.timers = json.load(file)
            with open('json/pixiv_tokens.json', 'r') as file:
                self.tokens = json.load(file)
            for guild, item in self.tokens.items():
                token = item["value"]
                self.api[token] = BetterAppPixivAPI()
                await self.api[token].login(refresh_token=token)
        except:
            pass

    async def waited_download(self, api, url):
        req_time = await self.queues.get()
        new_time = max(req_time + self.delay, time.time() + self.delay)
        await self.queues.put(new_time)
        await asyncio.sleep(req_time - time.time())
        return await api.download(url)

    async def send_illust(self, api, illust, url, channel, num=None, show_title=False, color=None):
        img = await self.waited_download(api, url)
        img_type = url.split('.')[-1]
        filename = f'{str(illust.id)}.{img_type}'
        if num is not None:
            filename = f'{num}_{filename}'
        if channel.guild.id in self.spoilers and self.spoilers[channel.guild.id] and illust.sanity_level >= 6:
            filename = f'SPOILER_{filename}'
        with BytesIO() as image_binary:
            img.save(image_binary, img.format)
            image_binary.seek(0)
            file = File(fp=image_binary, filename=filename)
        if safety and illust.sanity_level > 4 and not channel.nsfw:
            response = requests.get('https://img.youtube.com/vi/nter2axWgoA/mqdefault.jpg')
            with BytesIO(response.content) as image_binary:
                file = File(fp=image_binary, filename=filename)
        if show_title:
            title = illust.title
            if pixiv_show_embed_illust:
                embed = Embed(description=f'Title: [{title}](https://www.pixiv.net/en/artworks/{illust.id})',
                              color=color)
                embed.set_image(url=f'attachment://{filename}')
                message = await channel.send(embed=embed, file=file)
            else:
                text = f'Title: {title}'
                if len(illust.meta_pages) > 0:
                    text += f', {len(illust.meta_pages)} images'
                message = await channel.send(text, file=file)
        else:
            message = await channel.send(file=file)
        if illust.is_bookmarked:
            await message.add_reaction(emoji.emojize(':red_heart:'))

    async def show_illust(self, api, illust_id, channel):
        try:
            illust = (await api.illust_detail(illust_id)).illust
            await channel.send(embed=Embed(title=f'Fetching illustration {illust.title} in original quality...',
                                           color=Colour.green()), delete_after=5.0)
            if isinstance(channel, Interaction):
                channel = channel.channel
            if len(illust.meta_single_page) > 0:
                url = illust.meta_single_page.original_image_url
                await self.send_illust(api, illust, url, channel)
            for idx, item in enumerate(illust.meta_pages):
                url = item.image_urls.original
                await self.send_illust(api, illust, url, channel, idx)
            return True
        except:
            await channel.send(embed=Embed(title=f'Fail', color=Colour.red()), delete_after=5.0)
            return None

    async def show_page(self, api, query, chat, limit=30,
                        minimum_views=None, minimum_rate=None, max_sanity=6, dry_run=False):
        if chat is None or query is None or query.illusts is None or len(query.illusts) == 0:
            return 0, 0, False
        shown = 0
        # print('fetched', len(query.illusts), 'images')
        color = Colour.random()
        for illust in query.illusts:
            if not good_image(illust, minimum_views, minimum_rate, max_sanity):
                continue
            if not dry_run:
                self.bot.loop.create_task(self.send_illust(api, illust, illust.image_urls.large,
                                                           chat, show_title=True, color=color))
            shown += 1
            if shown == limit:
                break
        return shown, len(query.illusts), True

    async def show_page_embed(self, api, query, query_type, chat, limit=None, save_query=True, user_id=None):
        shown, total, result = await self.show_page(api, query, chat, limit)
        if result:
            if save_query:
                self.last_query[user_id] = query
                self.last_type[user_id] = query_type
            return Embed(title="Illustrations loaded", color=Colour.green())
        else:
            return Embed(title="Pixiv API didn't give any illustrations", color=Colour.red())

    def get_api(self, server_id):
        server_id = str(server_id)
        if server_id in self.tokens:
            return self.api[self.tokens[server_id]['value']]
        else:
            return None

    @slash_command(name="pixiv_logout", description="Remove pixiv token from bot db")
    async def pixiv_logout(self, ctx):
        server = str(ctx.guild.id)
        if server in self.tokens:
            self.tokens.pop(server)
            embed = Embed(title="Successfully logged out", color=Colour.green())
        else:
            embed = Embed(title="This server is not logged in", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name="pixiv_token", description="Log in to Pixiv via refresh token")
    async def pixiv_token(self, ctx):
        await ctx.response.send_modal(modal=TokenModal(ctx, self))

    if use_selenium:
        @slash_command(name="pixiv_login", description="Log in to Pixiv")
        async def pixiv_login(self, ctx):
            await ctx.response.send_modal(modal=LoginModal(ctx, self))

    @slash_command(name="pixiv_status", description="Show pixiv connection status")
    async def pixiv_status(self, ctx):
        await ctx.response.defer()
        server = str(ctx.guild.id)
        try:
            self.api[self.tokens[server]['value']].trending_tags_illust()
            embed = Embed(title="You logged in and API is working fine", color=Colour.green())
        except:
            embed = Embed(title="Either you are not connected or there is a problem with the API", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name="start_auto_pixiv", description="Add channel to the auto Pixiv list")
    async def add_auto_pixiv(self, ctx,
                             refresh_time: int = SlashOption(
                                 description="Delay between auto update in minutes (default = 180)",
                                 required=False,
                                 default=180,
                                 min_value=60
                             ),
                             limit: int = SlashOption(
                                 description="Amount of pictures will be displayed (default = 20)",
                                 required=False,
                                 default=20,
                                 max_value=60
                             )):
        channel_id = str(ctx.channel.id)
        if channel_id in self.channels.keys():
            embed = Embed(title="Auto Pixiv already running on this channel", color=Colour.gold())
        else:
            self.channels[channel_id] = {"refresh_time": refresh_time * 60, "limit": limit}
            embed = Embed(title="Auto Pixiv is now running on this channel", color=Colour.green())
        await ctx.send(embed=embed)
        self.save(channels=True)

    @slash_command(name="stop_auto_pixiv", description="Delete channel from the auto Pixiv list")
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

    @slash_command(name="spoil_nsfw", description="Spoil NSFW in this server")
    async def change_spoiler(self, ctx):
        server_id = ctx.guild.id
        if server_id not in self.spoilers:
            self.spoilers[server_id] = False
        self.spoilers[server_id] = not self.spoilers[server_id]
        if self.spoilers[server_id]:
            embed = Embed(title="NSFW pictures now will be spoiled", color=Colour.green())
        else:
            embed = Embed(title="NSFW spoiler feature turned off", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='next', description="Show the next page of your last 'best' or 'recommended' query")
    async def next(self, ctx, limit: int = SlashOption(
                                 description="Amount of pictures will be displayed (default = 20)",
                                 required=False,
                                 default=20,
                                 max_value=30
                             )):
        await ctx.response.defer()
        api = self.get_api(ctx.guild.id)
        if ctx.user.id in self.last_query:
            next_qs = await api.parse_qs(self.last_query[ctx.user.id].next_url)
            query = None
            if self.last_type[ctx.user.id] == 'recommended':
                query = await api.illust_recommended(**next_qs)
            elif self.last_type[ctx.user.id] == 'best':
                query = await api.illust_ranking(**next_qs)
            embed = await self.show_page_embed(api, query, self.last_type[ctx.user.id], ctx.channel,
                                               limit, save_query=True, user_id=ctx.user.id)
        else:
            embed = Embed(title="Previous request not found", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='recommended', description="Show [10] recommended Pixiv illustrations")
    async def recommended(self, ctx, limit: int = SlashOption(
                                 description="Amount of pictures will be displayed (default = 10)",
                                 required=False,
                                 default=10,
                                 max_value=30
                             )):
        await ctx.response.defer()
        api = self.get_api(ctx.guild.id)
        try:
            query = await api.illust_recommended()
            embed = await self.show_page_embed(api, query, 'recommended', ctx.channel, limit,
                                               save_query=True, user_id=ctx.user.id)
        except:
            embed = Embed(title="Authentication required!\nCall /pixiv_login first for more info", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='best', description='Find best [10] rated illustrations with specific mode and date')
    async def best(self, ctx,
                   mode: str = SlashOption(description="Specify one of the types",
                                           choices={"Day": "day",
                                                    "Week": "week",
                                                    "Month": "month",
                                                    "Day Male likes": "day_male",
                                                    "Day Female likes": "day_female",
                                                    "Day Ecchi": "day_r18",
                                                    "Day Male likes Ecchi": "day_male_r18",
                                                    "Week Ecchi": "week_r18",
                                                    },
                                           required=False,
                                           default="month"
                                           ),
                   limit: int = SlashOption(
                       description="Amount of pictures will be displayed (default = 10)",
                       required=False,
                       default=10,
                       max_value=30
                   ),
                   from_date: str = SlashOption(
                       description="Date of sample in format: YYYY-MM-DD",
                       required=False,
                       default=None
                   )):
        await ctx.response.defer()
        api = self.get_api(ctx.guild.id)
        try:
            query = await api.illust_ranking(mode=mode, date=from_date, offset=None)
            embed = await self.show_page_embed(api, query, 'best', ctx.channel, limit,
                                               save_query=True, user_id=ctx.user.id)
        except:
            embed = Embed(title="Authentication required!\nCall /pixiv_login first for more info", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='when', description='Show remaining time until new illustrations')
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

    @slash_command(name='tag', description='Get tagged name of word')
    async def tag(self, ctx,
                  word: str = SlashOption(description="Word, that will be translated to most popular related tag",
                                          required=True)):
        api = self.get_api(ctx.guild.id)
        try:
            query = await api.search_autocomplete(word)
            tags = ''
            for i, tag in enumerate(query.tags):
                tags += str(i) + '. ' + tag.name
                if tag.translated_name is not None:
                    tags += ' - ' + tag.translated_name
                tags += '\n'
            embed = Embed(title="Tags on word '" + word + "' sorted from high to low popularity:",
                          description=tags, color=Colour.gold())
        except:
            embed = Embed(title="Authentication required!\nCall /pixiv_login first for more info", color=Colour.red())
        await ctx.send(embed=embed, delete_after=30.0)

    async def recursive_find(self, api, ctx, word, match, limit,
                             views, rate, max_sanity_level, selected_date,
                             offset=0, shown=0, rv=None, lvl=0):
        find_next = False
        query = None
        if shown < limit and lvl < 10:
            query = await api.search_illust(word, search_target=match,
                                            end_date=selected_date, offset=offset)
            alive = True
            if len(query.illusts) == 0 and selected_date < date.current():
                selected_date = date.next_year(selected_date)
                offset = 0
            else:
                good, total, alive = await self.show_page(api, query, ctx.channel, limit - shown,
                                                          views, rate, max_sanity_level, dry_run=True)
                shown += good
                self.fetched[rv] += total
                if alive:
                    offset += total
            if alive:
                find_next = True
        if find_next:
            self.bot.loop.create_task(
                self.recursive_find(api, ctx, word, match, limit,
                                    views, rate, max_sanity_level, selected_date,
                                    offset=offset, shown=shown, rv=rv, lvl=lvl+1)
            )
            self.bot.loop.create_task(
                self.show_page(api, query, ctx.channel, limit - shown, views, rate, max_sanity_level)
            )
        else:
            embed = Embed(title="Find with word " + word + " called",
                          description=str(self.fetched[rv]) + " images fetched in total",
                          color=Colour.green())
            self.fetched.pop(rv)
            await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='find', description='Find illustrations that satisfy the filters from random point of time')
    async def find(self, ctx,
                   word: str = SlashOption(
                       description="Find by specific word",
                       required=True
                   ),
                   match: str = SlashOption(
                       description="Word match rule (default = exact_match_for_tags)",
                       default="exact_match_for_tags",
                       choices={
                           "Partial match for tags": "partial_match_for_tags",
                           "Exact match for tags": "exact_match_for_tags",
                           "Title and caption": "title_and_caption"
                       },
                       required=False
                   ),
                   limit: int = SlashOption(
                       description="Maximum amount of pictures that will be shown (default 5, maximum = 20)",
                       default=5,
                       min_value=1,
                       max_value=20,
                       required=False
                   ),
                   views: int = SlashOption(
                       description="Required minimum amount of views (default = 5000)",
                       default=5000,
                       min_value=0,
                       max_value=100000,
                       required=False
                   ),
                   rate: float = SlashOption(
                       description="Required minimum percent of views/bookmarks (default = 10)",
                       default=10,
                       min_value=0,
                       max_value=75,
                       required=False
                   ),
                   max_sanity_level: int = SlashOption(
                       description="Filter illusts to a specified sanity level (default = 5, min = 2, max = 6)",
                       default=5,
                       min_value=2,
                       max_value=6,
                       required=False
                   ),
                   period: str = SlashOption(
                       description="Random Date period (no impact if from_date given)",
                       choices={
                           "very new": date.back_in_months(3),
                           "new": date.back_in_months(1 * 12),
                           "2 years range": date.back_in_months(2 * 12),
                           "3 years range": date.back_in_months(3 * 12),
                           "6 years range": date.back_in_months(6 * 12),
                           "9 years range": date.back_in_months(9 * 12),
                           "all time period": date.back_in_months(14 * 12)
                       },
                       default=date.back_in_months(4 * 12),
                       required=False
                   ),
                   from_date: str = SlashOption(
                       description="Fixed date in format YYYY-MM-DD from which search will be initialized",
                       default=None,
                       required=False
                   )):
        await ctx.response.defer()
        api = self.get_api(ctx.guild.id)
        try:
            word = (await api.search_autocomplete(word)).tags[0].name
        except:
            pass
        selected_date = date.random(period, date.current(), random.random())
        if date.is_valid(from_date):
            selected_date = from_date
        rv = random.random()
        self.fetched[rv] = 0
        try:
            await self.recursive_find(api, ctx, word, match, limit, views, rate,
                                      max_sanity_level, selected_date, 0, 0, rv, 0)
        except:
            embed = Embed(title="Authentication required!\nCall /pixiv_login first for more info", color=Colour.red())
            await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='illust', description='Get pixiv illustration by ID')
    async def get_illust(self, ctx,
                         idx: str = SlashOption(description="Illustration ID", required=True)):
        await self.show_illust(self.get_api(ctx.guild.id), idx, ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        api = self.get_api(payload.guild_id)
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        user = self.bot.get_user(payload.user_id)

        try:
            demojized = emoji.demojize(payload.emoji.name)
        except TypeError:
            demojized = None
        if payload.user_id != self.bot.user.id:
            if message.attachments is not None and message.author == self.bot.user:
                illust_id = None
                lock_info = False
                if len(message.attachments) == 1:
                    illust_id = message.attachments[0].filename.split('.')[0].split('_')[-1]
                    if not illust_id.isnumeric():
                        illust_id = None
                try:
                    if "Pixiv ID" in message.embeds[0].fields[1].name:
                        illust_id = message.embeds[0].fields[1].value
                        lock_info = True
                except:
                    pass
                if illust_id is None:
                    return
                emojis = {':red_heart:', ':growing_heart:', ':magnifying_glass_tilted_left:', ':seedling:',
                          ':broken_heart:', ':red_question_mark:', ':elephant:', ':face_vomiting:'}
                if demojized in emojis:
                    await message.remove_reaction(payload.emoji, user)

                if demojized == ':red_heart:' or demojized == ':elephant:':
                    try:
                        await api.illust_bookmark_add(illust_id)
                        await message.add_reaction(emoji.emojize(':red_heart:'))
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
                elif demojized == ':growing_heart:':
                    try:
                        await api.illust_bookmark_add(illust_id)
                        await message.add_reaction(emoji.emojize(':red_heart:'))
                        query = await api.illust_related(illust_id)
                        await self.show_page(api, query, message.channel, limit=5)
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
                elif demojized == ':magnifying_glass_tilted_left:':
                    try:
                        await message.add_reaction(emoji.emojize(':thumbs_up:'))
                        await self.show_illust(api, illust_id, message.channel)
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
                elif demojized == ':seedling:':
                    try:
                        query = await api.illust_related(illust_id)
                        await message.add_reaction(emoji.emojize(':thumbs_up:'))
                        await self.show_page(api, query, message.channel, limit=5)
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
                elif demojized == ':face_vomiting:' and not lock_info:
                    await message.delete()
                elif demojized == ':broken_heart:':
                    try:
                        await api.illust_bookmark_delete(illust_id)
                        for r in message.reactions:
                            if r.me:
                                await r.remove(self.bot.user)
                        await message.add_reaction(emoji.emojize(':broken_heart:'))
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
                elif demojized == ':red_question_mark:' and not lock_info:
                    try:
                        await message.add_reaction(emoji.emojize(':thumbs_up:'))
                        illust = (await api.illust_detail(illust_id)).illust
                        tags = ""
                        for tag in illust.tags:
                            tags += f'{tag.name}'
                            if tag.translated_name is not None:
                                tags += f' - {tag.translated_name}'
                            tags += ', '
                        tags = tags[:-2]
                        embed = Embed(title="Illustration info:", color=Colour.green())
                        embed.add_field(name="Title:",
                                        value=f"[{illust.title}](https://www.pixiv.net/en/artworks/{illust.id})",
                                        inline=False)
                        embed.add_field(name="ID:", value=illust_id, inline=True)
                        embed.add_field(name="Views:", value=illust.total_view, inline=True)
                        embed.add_field(name="Bookmarks:", value=illust.total_bookmarks, inline=True)
                        embed.add_field(name="Tags:", value=tags, inline=False)
                        await message.edit(embed=embed, suppress=False)
                        await asyncio.sleep(20)
                        await message.edit(suppress=True)
                    except:
                        await message.add_reaction(emoji.emojize(':thumbs_down:'))
        elif demojized in [':broken_heart:', ':thumbs_up:', ':thumbs_down:']:
            await asyncio.sleep(5)
            await message.remove_reaction(payload.emoji, user)

    async def auto_draw(self):
        try:
            for channel_id, options in self.channels.items():
                channel = self.bot.get_channel(int(channel_id))
                if channel is None:
                    continue
                api = self.get_api(channel.guild.id)
                refresh_time = options['refresh_time']
                limit = options['limit']
                timestamp = time.time()
                if channel_id not in self.timers.keys() or timestamp - self.timers[channel_id] > refresh_time:
                    self.timers[str(channel_id)] = timestamp
                    query = await api.illust_recommended()
                    await self.show_page(api, query, channel, limit=limit)
                    self.save(timers=True)
        except RuntimeError:
            pass

    async def auto_refresh_tokens(self):
        timestamp = time.time()
        for server_id in self.tokens:
            if int(self.tokens[server_id]['time']) - timestamp < 1000:
                token, ttl = refresh_token(self.tokens[server_id]['value'])
                self.tokens[server_id]['time'] = str(int(timestamp + ttl))
                await self.api[token].login(refresh_token=token)
                print('pixiv token updated')

    @commands.Cog.listener()
    async def on_ready(self):
        while True:
            await asyncio.sleep(30)
            await self.auto_refresh_tokens()
            await self.auto_draw()
            self.save(channels=True, timers=True)


def setup(bot):
    bot.add_cog(PixivCog(bot))
