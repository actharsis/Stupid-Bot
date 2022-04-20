import asyncio
import contextlib
import math
import random
from collections import deque

import emoji
from config import *
from modules import wavelink
from modules.wavelink import Node, Track
from modules.wavelink.ext import spotify
from modules.wavelink.utils import MISSING
from nextcord import (ButtonStyle, ChannelType, Client, Embed, Interaction,
                      SelectOption, SlashOption, errors, slash_command)
from nextcord.abc import GuildChannel
from nextcord.channel import VoiceChannel
from nextcord.colour import Colour
from nextcord.ext import commands
from nextcord.ui import Button, Select, View

if safety:
    from modules.predict import is_nsfw


async def anext(ait):
    return await ait.__anext__()


def my_shuffle(x, *s):
    x[slice(*s)] = random.sample(x[slice(*s)], len(x[slice(*s)]))


def time_to_str(time):
    return f"{int(time // 60)} minutes, {int(time % 60)} seconds"


def short_time(time):
    return f"{int(time // 60)}:{int(time % 60)}"


def render_bar(cells, time, duration):
    filled = max(1, math.floor(cells * (time / duration)))
    empty = cells - filled
    filled -= 1
    return f"[{('=' * filled)}O{('-' * empty)}]"


def cut_text(text, limit):
    return f"{text[:limit]}..." if len(text) > limit else text


async def get_track(queue):
    while queue:
        if isinstance(queue[0], wavelink.tracks.YouTubePlaylist):
            playlist = queue[0]
            if playlist.selected_track >= len(playlist.tracks):
                queue.popleft()
                continue
            track = playlist.tracks[playlist.selected_track]
            playlist.selected_track += 1
            if playlist.selected_track == len(playlist.tracks):
                queue.popleft()
        elif isinstance(queue[0], spotify.SpotifyAsyncIterator):
            try:
                playlist = queue[0]
                track = await anext(playlist)
            except StopAsyncIteration:
                queue.popleft()
                continue
        else:
            track = queue.popleft()
        return track
    return None


def build_queue_embed(player):
    if not player.queue:
        text = "*Empty*"
    else:
        text = ""
        for i, item in enumerate(player.queue):
            if isinstance(item, wavelink.tracks.YouTubePlaylist):
                text += f"*{i}*. Playlist '**{item.name}**'\n"
                j = 0
                while j + item.selected_track < len(item.tracks) and j < 10:
                    idx = item.selected_track + j
                    track = item.tracks[idx]
                    text += f"--->{i}.{idx}. [**{track.title}**]({track.uri}), length: {int(track.length)} sec.\n"
                    j += 1
                if j + item.selected_track < len(item.tracks):
                    text += "...\n"
            elif isinstance(item, spotify.SpotifyAsyncIterator):
                text += f"*{i}*. '**{item.name}**'\n"
                idx = 0
                while idx < len(item.tracks) and idx < 10:
                    track = item.tracks[idx]
                    text += f"--->{i}.{idx}. {track['name']} - {track['artists'][0]['name']}'\n"
                    idx += 1
                if idx + item.selected_track < len(item.tracks):
                    text += "...\n"
            else:
                text += f"*{i}*. [**{item.title}**]({item.uri}), length: {int(item.length)} sec.\n"
            text += '\n'
            if len(text) > 3000:
                break
    embed = Embed(description=text, color=Colour.blurple())
    embed.set_author(name="Queue", icon_url="https://cdn.discordapp.com/emojis/695126168680005662.webp")
    return embed


def build_history_embed(player):
    text = ""
    if not player.history:
        text = "*Empty*"
    else:
        for i, item in enumerate(reversed(player.history)):
            text += f"*{i}*. [**{item['track'].title}**]({item['track'].uri}), " \
                    f"length: *{short_time(item['track'].length)}*"
            if item['cnt'] > 1:
                text += f", **{item['cnt']}**x"
            text += '\n\n'
            if len(text) > 3000:
                break
    embed = Embed(description=text)
    embed.set_author(name="History:", icon_url="https://cdn.discordapp.com/emojis/695126168680005662.webp")
    return embed


def player_embed(player):
    track = player.track
    if track is not None:
        embed = Embed(description=f"[**{track.title}**]({track.uri})\n"
                                  f"**Length**: *{time_to_str(track.length)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**Timeline**: *{short_time(player.position)}/{short_time(track.length)}*\n"
                                  f"```{render_bar(36, player.position, track.length)}```"
                                  f"{'*On repeat*' if player.loop else ''}",
                      color=Colour.blurple())
        if player.is_paused():
            embed.set_author(name='On pause:',
                             icon_url='https://cdn.discordapp.com/emojis/884559976016805888.webp')
        else:
            embed.set_author(name='Currently playing:',
                             icon_url='https://cdn.discordapp.com/emojis/751692077779124316.gif')
        url = f'https://img.youtube.com/vi/{track.uri[32:]}/mqdefault.jpg'
        if safety and is_nsfw(url) and not player.message.channel.nsfw:
            url = 'https://img.youtube.com/vi/nter2axWgoA/mqdefault.jpg'
        embed.set_image(url=url)
    else:
        embed = Embed(description=f"**Nothing**\n"
                                  f"**Length**: *{time_to_str(0)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**Timeline**: *{short_time(0)}/{short_time(0)}*\n"
                                  f"```{render_bar(36, 1, 1)}```"
                                  f"{'*On repeat*' if player.loop else ''}",
                      color=Colour.blurple())
        embed.set_author(name='Stopped.',
                         icon_url='https://cdn.discordapp.com/emojis/884559976016805888.webp')
        embed.set_image(url='https://media.discordapp.net/attachments/959918146238689364/964988238852935770/cirno.gif')
    return embed


async def play_next(player: wavelink.player):
    if player.queue:
        track = await get_track(player.queue)
        await player.play(track)


async def message_auto_update(player):
    idx = player.message.id
    while player.message is not None and idx == player.message.id:
        try:
            view = PlayerView(player)
            await player.message.edit(
                embed=player_embed(player),
                view=view
            )
        except AttributeError:
            return
        await asyncio.sleep(1)


class ExtPlayer(wavelink.Player):
    def __init__(self,
                 client: Client = MISSING,
                 channel: VoiceChannel = MISSING,
                 *,
                 node: Node = MISSING):
        super().__init__(client, channel, node=node)
        self.loop = False
        self.queue = deque()
        self.history = deque()
        self.message = None
        self.controls = None
        self.ctx = None


# class PlayerView(View):
#     def __init__(self, player):
#         super().__init__(timeout=None)
#         self.player = player
#         self.player.controls = self
#
#     async def interaction_check(self, interaction: Interaction) -> bool:
#         print('called')
#
#     @ui.button(style=ButtonStyle.blurple, emoji=emoji.emojize(':last_track_button:'), row=0)
#     async def previous(self, button: Button, interaction: Interaction):
#         if self.player.history:
#             prev = self.player.history.pop()['track']
#             self.player.queue.appendleft(prev)
#             await self.player.stop()
#             ttl = 5
#             while (self.player.track is None or self.player.track.title != prev.title) and ttl > 0:
#                 await asyncio.sleep(1)
#                 ttl -= 1
#             if ttl > 0:
#                 self.player.queue.appendleft(self.player.history.pop()['track'])
#         else:
#             await self.player.seek(0)
#
#     @ui.button(style=ButtonStyle.green, emoji=emoji.emojize(':reverse_button:'), row=0)
#     async def back(self, button: Button, interaction: Interaction):
#         cur = self.player.position
#         await self.player.seek(int(1000 * (cur - 30)))
#
#     @ui.button(style=ButtonStyle.green, emoji=emoji.emojize(':pause_button:'), row=0)
#     async def pause(self, button: Button, interaction: Interaction):
#         if self.player.is_playing():
#             if self.player.is_paused():
#                 await self.player.resume()
#             else:
#                 await self.player.pause()
#
#     @ui.button(style=ButtonStyle.green, emoji=emoji.emojize(':play_button:'), row=0)
#     async def forward(self, button: Button, interaction: Interaction):
#         cur = self.player.position
#         await self.player.seek(int(1000 * (cur + 30)))
#
#     @ui.button(style=ButtonStyle.blurple, emoji=emoji.emojize(':next_track_button:'), row=0)
#     async def next(self, button: Button, interaction: Interaction):
#         await self.player.stop()
#
#     @ui.button(label="Mute", emoji=(emoji.emojize(':muted_speaker:')), row=1)
#     async def mute(self, button: Button, interaction: Interaction):
#         if self.player.volume > 0:
#             await self.player.set_volume(0)
#             button.refresh_component(Button(label="Unmute", emoji=emoji.emojize(':speaker_high_volume:'), row=1))
#         else:
#             await self.player.set_volume(100)
#             button.refresh_component(Button(label="Mute", emoji=emoji.emojize(':speaker_high_volume:'), row=1))
#
#     @ui.button(label="Loop", emoji=(emoji.emojize(':repeat_button:')), row=1)
#     async def loop(self, button: Button, interaction: Interaction):
#         self.player.loop ^= True
#
#     @ui.button(label="Log", emoji=emoji.emojize(':scroll:'), row=1)
#     async def history(self, button: Button, interaction: Interaction):
#         await interaction.response.send_message(embed=build_history_embed(self.player))
#
#     @ui.button(label="Quit", style=ButtonStyle.red, emoji=emoji.emojize(':black_large_square:'))
#     async def quit(self):
#         self.player.loop = False
#         self.player.queue.clear()
#         await self.player.stop()
#
#     @ui.select(placeholder="Queue", options=[SelectOption(label='empty')], row=2, disabled=True)
#     async def queue_list(self, select: Select, interaction: Interaction):
#         for i in range(int(interaction.values[0])):
#             get_track(self.player.queue)
#         self.player.loop = False
#         await self.player.stop()


class PlayerView(View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self.player.controls = self
        self.player_components()

    def player_components(self):
        self.add_item(Button(custom_id="prev", style=ButtonStyle.blurple,
                             emoji=emoji.emojize(':last_track_button:'), row=0))
        self.add_item(Button(custom_id="back", style=ButtonStyle.green,
                             emoji=emoji.emojize(':reverse_button:'), row=0))
        if self.player.is_paused():
            self.add_item(Button(custom_id="pause", style=ButtonStyle.red,
                                 emoji=emoji.emojize(':pause_button:'), row=0))
        else:
            self.add_item(Button(custom_id="pause", style=ButtonStyle.green,
                                 emoji=emoji.emojize(':pause_button:'), row=0))
        self.add_item(Button(custom_id="forw", style=ButtonStyle.green,
                             emoji=emoji.emojize(':play_button:'), row=0))
        self.add_item(Button(custom_id="next", style=ButtonStyle.blurple,
                             emoji=emoji.emojize(':next_track_button:'), row=0))
        if volume_lock:
            self.add_item(Button(label="Mute", custom_id="mute", disabled=True,
                                 emoji=emoji.emojize(':muted_speaker:'), row=1))
        elif self.player.volume > 0:
            self.add_item(Button(label="Mute", custom_id="mute",
                                 emoji=emoji.emojize(':muted_speaker:'), row=1))
        else:
            self.add_item(Button(label="Unmute", custom_id="mute",
                                 emoji=emoji.emojize(':speaker_high_volume:'), row=1))
        self.add_item(Button(label="Loop", custom_id="repeat", emoji=emoji.emojize(':repeat_button:'), row=1))
        self.add_item(Button(label="Log", custom_id="history", emoji=emoji.emojize(':scroll:'), row=1))
        self.add_item(Button(label="Quit", custom_id="stop", style=ButtonStyle.red,
                             emoji=emoji.emojize(':black_large_square:'), row=1))

        options = []
        for item in self.player.queue:
            if isinstance(item, wavelink.tracks.YouTubePlaylist):
                j = 0
                while j + item.selected_track < len(item.tracks) and len(options) < 10:
                    idx = item.selected_track + j
                    track = item.tracks[idx]
                    word = f"{cut_text(track.title, 48)}, {short_time(track.length)}"
                    num = str(len(options))
                    options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
                    j += 1
            elif isinstance(item, spotify.SpotifyAsyncIterator):
                idx = 0
                while idx < len(item.tracks) and len(options) < 10:
                    track = item.tracks[idx]
                    name = f"{track['name']} - {track['artists'][0]['name']}"
                    word = f"{cut_text(name, 48)}"
                    num = str(len(options))
                    options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
                    idx += 1
            else:
                word = f"{cut_text(item.title, 48)}, {short_time(item.length)}"
                num = str(len(options))
                options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
            if len(options) == 10:
                break
        if options:
            self.add_item(Select(placeholder="Queue", options=options, custom_id="queue_list", row=2))

    async def interaction_check(self, interaction: Interaction) -> bool:
        custom_id = interaction.data['custom_id']
        if custom_id == 'prev':
            if self.player.history:
                prev = self.player.history.pop()['track']
                self.player.loop = False
                if self.player.is_playing():
                    self.player.queue.appendleft(prev)
                    await self.player.stop()
                    ttl = 5
                    while (self.player.track is None or self.player.track.title != prev.title) and ttl > 0:
                        await asyncio.sleep(1)
                        ttl -= 1
                    if ttl > 0:
                        self.player.queue.appendleft(self.player.history.pop()['track'])
                else:
                    await self.player.play(prev)
            else:
                await self.player.seek(0)
        elif custom_id == 'back':
            cur = self.player.position
            await self.player.seek(int(1000 * (cur - 30)))
        elif custom_id == 'pause':
            if self.player.is_playing():
                if self.player.is_paused():
                    await self.player.resume()
                else:
                    await self.player.pause()
        elif custom_id == 'forw':
            cur = self.player.position
            await self.player.seek(int(1000 * (cur + 30)))
        elif custom_id == 'next':
            self.player.loop = False
            await self.player.stop()
        elif custom_id == 'mute':
            if self.player.volume > 0:
                await self.player.set_volume(0)
            else:
                await self.player.set_volume(100)
        elif custom_id == 'repeat':
            self.player.loop ^= True
        elif custom_id == 'stop':
            self.player.loop = False
            self.player.queue.clear()
            await self.player.stop()
        elif custom_id == 'history':
            await interaction.response.send_message(embed=build_history_embed(self.player), ephemeral=True)
            return True
        elif custom_id == 'queue_list':
            value = interaction.data['values'][0]
            for i in range(int(value)):
                await get_track(self.player.queue)
            self.player.loop = False
            await self.player.stop()
        await interaction.response.edit_message()
        return True


class MusicPlayerCog(commands.Cog, name="Music player"):
    """
    **Music cog** - music player. Designed for control via buttons.

    ***Available commands:***

    **/play** - play song by name (also url from youtube/soundcloud supported)
    **/playlist** - play youtube playlist
    **/spotify** - play spotify playlist

    **/seek** - play from the specified second
    **/skip** - skip current song
    **/pause** - pause/continue
    **/stfu** - clear queue and stop playing

    **/queue** - song queue
    **/history** - song history
    """

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.connect_nodes())
        self.players = {}

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host=wavelink_host,
                                            port=wavelink_port,
                                            password=wavelink_password,
                                            spotify_client=spotify.SpotifyClient(
                                                client_id=spotify_client_id,
                                                client_secret=spotify_client_secret))

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        print("Connected to lavalink!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: ExtPlayer, track: Track):
        if player.message is None:
            await self.player_message(player)

    async def soft_destroy(self, player):
        await asyncio.sleep(10)
        if not player.is_playing():
            with contextlib.suppress(Exception):
                await player.disconnect()
                await player.message.delete()
            if player.guild.id in self.players and self.players[player.guild.id] == player:
                self.players.pop(player.guild.id)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: ExtPlayer, track: Track, reason):
        if player.history and player.history[-1]['track'].title == track.title:
            player.history[-1]['cnt'] += 1
        else:
            player.history.append({'track': track, 'cnt': 1})

        if not player.is_playing():
            self.bot.loop.create_task(self.soft_destroy(player))
        if player.loop:
            await player.play(track)
        else:
            await play_next(player)

    async def player_message(self, player: ExtPlayer):
        ctx = player.ctx
        view = PlayerView(player)
        msg = await ctx.send(embed=player_embed(player),
                             view=view)
        player.message = msg
        self.bot.loop.create_task(message_auto_update(player))

    async def update_server_player(self, ctx, vc):
        server_id = ctx.guild.id
        try:
            if vc is None:
                if server_id not in self.players:
                    self.players[server_id] = await ctx.user.voice.channel.connect(cls=ExtPlayer)
            elif server_id in self.players:
                await self.players[server_id].move_to(vc)
            else:
                self.players[server_id] = await vc.connect(cls=ExtPlayer)
        except Exception:
            await ctx.send(embed=Embed(title="Which voice channel?", color=Colour.green()), delete_after=10.0)
            return 0
        if self.players[server_id].ctx is None:
            self.players[server_id].ctx = ctx.channel
        return 1

    @slash_command(name='spotify', description="Play something from Spotify")
    async def spotify(self, ctx,
                      url: str = SlashOption(description="Album URL or ID", required=True),
                      vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False)):
        await ctx.response.defer()
        if not await self.update_server_player(ctx, vc):
            return
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = player.queue
        try:
            playlist = spotify.SpotifyTrack.iterator(query=url)
            await playlist.fill_queue()
        except Exception:
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.green()),
                           delete_after=10.0)
            return
        queue.append(playlist)
        if player.is_playing():
            await ctx.send(embed=Embed(title=f"'**{playlist.name}**' added to queue",
                                       color=Colour.green()),
                           delete_after=10.0)
            return
        else:
            await ctx.send(embed=Embed(title=f"'**{playlist.name}**' is now playing",
                                       color=Colour.green()),
                           delete_after=10.0)
        await play_next(player)

    @slash_command(name='play', description='Play a song from Youtube')
    async def play(self, ctx,
                   track: str = SlashOption(description="Track name", required=True),
                   vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False)):
        await ctx.response.defer()
        if not await self.update_server_player(ctx, vc):
            return
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = player.queue
        try:
            track = await wavelink.YouTubeTrack.search(query=track, return_first=True)
        except Exception:
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.green()),
                           delete_after=10.0)
            return
        queue.append(track)
        if player.is_playing():
            await ctx.send(embed=Embed(title=f"Song '**{track.title}**' (*{short_time(track.length)}*) added to queue",
                                       color=Colour.green()),
                           delete_after=10.0)
            return
        else:
            await ctx.send(embed=Embed(title=f"Song '**{track.title}**' (*{short_time(track.length)}*) is now playing",
                                       color=Colour.green()),
                           delete_after=10.0)
        await play_next(player)

    @slash_command(name='playlist', description='Add playlist')
    async def playlist(self, ctx,
                       url: str = SlashOption(description="Playlist URL", required=True),
                       offset: int = SlashOption(description="Track index from which to start playing songs",
                                                 default=0,
                                                 required=False),
                       vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False)):
        await ctx.response.defer()
        if not await self.update_server_player(ctx, vc):
            return
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = player.queue
        try:
            playlist = await wavelink.YouTubePlaylist.search(query=url)
            playlist.selected_track = max(0, offset)
        except Exception:
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.green()), delete_after=10.0)
            return
        queue.append(playlist)
        if player.is_playing():
            await ctx.send(embed=Embed(title=f"Playlist '**{playlist.name}**' added to queue",
                                       color=Colour.green()),
                           delete_after=10.0)
            return
        else:
            await ctx.send(embed=Embed(title=f"Playlist '**{playlist.name}**' is now playing",
                                       color=Colour.green()),
                           delete_after=10.0)
        await play_next(player)

    @slash_command(name='spawn_player', description='Resend player body')
    async def spawn_player(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id not in self.players:
            await ctx.send(embed=Embed(title="Nothing is playing", color=Colour.red()), delete_after=5)
        else:
            await ctx.send(embed=Embed(title="Player respawned", color=Colour.green()), delete_after=5)
            player = self.players[server_id]
            player.ctx = ctx.channel
            await player.message.delete()
            player.message = None
            await self.player_message(player)

    @slash_command(name='shuffle', description='Queue random shuffle')
    async def shuffle(self, ctx):
        await ctx.response.defer()
        if ctx.guild.id in self.players:
            player = self.players[ctx.guild.id]
            for item in player.queue:
                if isinstance(item, wavelink.tracks.YouTubePlaylist):
                    my_shuffle(item.tracks, len(item.tracks) - item.selected_track, None)
                elif isinstance(item, spotify.SpotifyAsyncIterator):
                    random.shuffle(item.tracks)
            random.shuffle(player.queue)
        await ctx.send(embed=Embed(title="Done", color=Colour.green()), delete_after=5)

    @slash_command(name='move', description='Move to specified voice channel (default=<user voice channel>)')
    async def move(self, ctx,
                   vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            try:
                player = self.players[server_id]
                if vc is None:
                    await player.move_to(ctx.author.voice.channel)
                else:
                    await player.move_to(vc)
                embed = Embed(title="Ok", color=Colour.green())
            except Exception:
                embed = Embed(title="Can't move in this channel", color=Colour.red())
        else:
            embed = Embed(title="Player not initialized", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='pop', description='Delete specific song/playlist from queue by index')
    async def pop(self, ctx,
                  idx: int = SlashOption(description="ID of the song/playlist from the queue", required=True)):
        server_id = ctx.guild.id
        if server_id in self.players:
            queue = self.players[server_id].queue
            if idx >= 0 or idx < len(queue):
                item = queue[idx]
                del queue[idx]
                if isinstance(item, (wavelink.tracks.YouTubePlaylist, spotify.SpotifyAsyncIterator)):
                    embed = Embed(title=f"Playlist: '**{item.name}**' was deleted", color=Colour.blurple())
                else:
                    embed = Embed(title=f"Song: '**{item.title}**' was deleted", color=Colour.blurple())
            else:
                embed = Embed(title="Wrong index given", color=Colour.red())
        else:
            embed = Embed(title="Player not initialized", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            self.players[server_id].loop = False
            await self.players[server_id].stop()
            embed = Embed(title="Current track skipped", color=Colour.gold())
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='pause', description='Pause/resume current song')
    async def pause(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            if self.players[server_id].is_paused():
                await self.players[server_id].resume()
                embed = Embed(title="Playing again", color=Colour.gold())
            else:
                await self.players[server_id].pause()
                embed = Embed(title="Song paused", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to pause", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='stfu', description='Stop current song and clear song queue')
    async def disconnect(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            player = self.players[server_id]
            player.queue.clear()
            player.loop = False
            await self.players[server_id].stop()
            embed = Embed(color=Colour.blurple())
            embed.set_author(name='Ok', icon_url="https://cdn.discordapp.com/emojis/807417229976272896.webp")
        else:
            embed = Embed(color=Colour.blurple())
            embed.set_author(name="I've been quiet enough",
                             icon_url="https://cdn.discordapp.com/emojis/807417229976272896.webp")
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='queue', description='Show current song queue')
    async def queue(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.players:
            await ctx.response.send_message(embed=build_queue_embed(self.players[server_id]),
                                            delete_after=60.0, ephemeral=True)
        else:
            await ctx.response.send_message(embed=Embed(title="Player not initialized", color=Colour.red()),
                                            delete_after=5.0, ephemeral=True)

    @slash_command(name='history', description='Show song history')
    async def history(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.players:
            await ctx.response.send_message(embed=build_history_embed(self.players[server_id]),
                                            delete_after=60.0, ephemeral=True)
        else:
            await ctx.response.send_message(Embed(title="Player not initialized", color=Colour.red()),
                                            delete_after=5.0, ephemeral=True)

    @slash_command(name='seek', description='Move timeline to specific time in seconds')
    async def seek(self, ctx, time: int = SlashOption(description="Time to seek in seconds", required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            await self.players[server_id].seek(1000 * time)
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="Nothing to move", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='volume', description='Change volume to specific value')
    async def volume(self, ctx, value: int = SlashOption(description="Volume value", required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if volume_lock:
            await ctx.send(embed=Embed(
                title="This feature is disabled", color=Colour.red()
            ), delete_after=10.0)
            return
        if server_id in self.players:
            await self.players[server_id].set_volume(value)
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="Player not initialized", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='loop', description='Repeat song infinitely (disables on skip/stop)')
    async def loop(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            player = self.players[server_id]
            if player.loop[server_id]:
                embed = Embed(title="Replay disabled", color=Colour.blurple())
            else:
                embed = Embed(title="On replay", color=Colour.blurple())
            player.loop ^= True
        else:
            embed = Embed(title="Nothing to loop", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        server_id = payload.guild_id
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        user = self.bot.get_user(payload.user_id)
        if server_id not in self.players or self.players[server_id].message.id != message.id:
            return
        if payload.user_id != self.bot.user.id:
            await message.add_reaction(emoji.emojize(':angry_face:'))
        else:
            await asyncio.sleep(2)
            with contextlib.suppress(errors.NotFound):
                await message.remove_reaction(payload.emoji, user)


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
