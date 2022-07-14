import asyncio
import contextlib
import emoji
import io
import json
import math
import pickle
import random
import re
import string

from config import *
from collections import deque
from cryptography.fernet import Fernet
from modules import wavelink
from modules.wavelink import Node, Track
from modules.wavelink.ext import spotify
from modules.wavelink.utils import MISSING
from nextcord import (ButtonStyle, ChannelType, Client, Embed, Interaction, File,
                      SelectOption, SlashOption, errors, slash_command)
from nextcord.abc import GuildChannel
from nextcord.channel import VoiceChannel
from nextcord.colour import Colour
from nextcord.ext import commands
from nextcord.ui import Button, Select, View
from os.path import exists
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from youtube_transcript_api import YouTubeTranscriptApi

if SAFETY:
    from modules.predict import is_nsfw


async def anext(ait, parse=True):
    if parse:
        return await ait.__anext__()
    else:
        await ait.__skipanext__()
        return None


def my_shuffle(x, s):
    x[s:] = random.sample(x[s:], len(x[s:]))
    print(x)


def time_to_str(time):
    return f"{int(time // 60)} minutes, {int(time % 60)} seconds"


def short_time(time):
    return f"{int(time // 60):02d}:{int(time % 60):02d}"


def render_bar(cells, time, duration):
    filled = max(1, math.floor(cells * (time / duration)))
    empty = cells - filled
    filled -= 1
    return f"[{('=' * filled)}O{('-' * empty)}]"


def cut_text(text, limit):
    return f"{text[:limit]}..." if len(text) > limit else text


async def get_track(queue, parse=True):
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
                track = await anext(playlist, parse)
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


def build_history_embed(player, title: str):
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
    embed.set_author(name=title, icon_url="https://cdn.discordapp.com/emojis/695126168680005662.webp")
    return embed


def player_embed(player):
    track = player.track
    options = []
    if player.loop:
        options.append('*On repeat*')
    if player.related:
        options.append('*Plays related*')
    if track is not None:
        embed = Embed(description=f"[**{track.title}**]({track.uri})\n"
                                  f"**Length**: *{time_to_str(track.length)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**Timeline**: *{short_time(player.position)}/{short_time(track.length)}*\n"
                                  f"```{render_bar(36, player.position, track.length)}```"
                                  f"{', '.join(options)}",
                      color=Colour.blurple())
        if player.is_paused():
            embed.set_author(name='On pause:',
                             icon_url='https://cdn.discordapp.com/emojis/884559976016805888.webp')
        else:
            embed.set_author(name='Currently playing:',
                             icon_url='https://cdn.discordapp.com/emojis/751692077779124316.gif')
        url = f'https://img.youtube.com/vi/{track.uri[32:]}/mqdefault.jpg'
        if SAFETY and is_nsfw(url) and not player.message.channel.nsfw:
            url = 'https://img.youtube.com/vi/nter2axWgoA/mqdefault.jpg'
        embed.set_image(url=url)
    else:
        embed = Embed(description=f"**Nothing**\n"
                                  f"**Length**: *{time_to_str(0)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**Timeline**: *{short_time(0)}/{short_time(0)}*\n"
                                  f"```{render_bar(36, 1, 1)}```"
                                  f"{','.join(options)}",
                      color=Colour.blurple())
        embed.set_author(name='Stopped.',
                         icon_url='https://cdn.discordapp.com/emojis/884559976016805888.webp')
        embed.set_image(url='https://s10.gifyu.com/images/cirno.gif')
    return embed


def get_related(identifier):
    with urlopen(f'https://www.googleapis.com/youtube/v3/search?relatedToVideoId={identifier}'
                 f'&part=snippet&maxResults=4&fields=items(snippet/title)&type=video'
                 f'&key={YOUTUBE_API_TOKEN}') as url:
        data = json.loads(url.read().decode())
        random.shuffle(data['items'])
        for item in data['items']:
            if 'snippet' in item:
                return item['snippet']['title']


async def play_next(player: wavelink.player, prev=None):
    try:
        if prev is not None:
            if player.loop:
                await player.play(prev)
                return
            if player.related:
                try:
                    track = await wavelink.YouTubeTrack.search(query=get_related(prev.identifier), return_first=True)
                    await player.play(track)
                    return
                except HTTPError:
                    player.ctx.send(Embed(title="Related disabled - quota limit reached",
                                          color=Colour.red()), delete_after=5.0)
                    player.related = False
                except Exception:
                    player.ctx.send(Embed(title="No related for this song",
                                          color=Colour.gold()), delete_after=5.0)
        if player.queue:
            track = await get_track(player.queue)
            await player.play(track)
    finally:
        if player.lyrics_message is not None:
            load_lyrics(player)


async def player_terminate(player, players, history=False):
    with contextlib.suppress(Exception):
        await player.disconnect()
    with contextlib.suppress(Exception):
        await player.lyrics_message.delete()
    with contextlib.suppress(Exception):
        await player.message.delete()
    if history:
        with contextlib.suppress(Exception):
            await player.ctx.send(embed=build_history_embed(player, "Songs played during the session:"))
    if player.guild.id in players and players[player.guild.id] == player:
        players.pop(player.guild.id)


async def message_auto_update(player):
    idx = player.message.id
    while player.message is not None and idx == player.message.id:
        try:
            view = PlayerView(player)
            await player.message.edit(
                embed=player_embed(player),
                view=view
            )
        except errors.HTTPException:
            pass
        except (errors.NotFound, AttributeError):
            player.message = None
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
        self.related = False
        self.queue = deque()
        self.history = deque()
        self.message = None
        self.controls = None
        self.ctx = None
        self.lyrics_message = None
        self.lyrics_lang = None
        self.hash = None


def serialize_music(player: ExtPlayer):
    if not exists('secret.key'):
        key = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(key)
    key = open("secret.key", "rb").read()
    dump = pickle.dumps({'queue': player.queue, 'history': player.history, 'track': player.track})
    f = Fernet(key)
    encrypted = f.encrypt(dump)
    return encrypted


def deserialize_music(data: bytes):
    if not exists('secret.key'):
        key = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(key)
    key = open("secret.key", "rb").read()
    f = Fernet(key)
    decrypted = f.decrypt(data)
    obj = pickle.loads(decrypted)
    return obj


class Lyrics(object):
    time: float
    duration: float
    text: str


# def beautify_lyrics(t):
#     pt = -900
#     a = [deque(), deque()]
#     ptr = 0
#     c = [0, 0]
#     printable = set(string.printable)
#     printable.remove('*')
#     # rx = r'[^\u0020-\u007e\u00a0-\u00ff\u0152\u0153\u0178]'
#     for i in t:
#         i['text'] = ''.join(filter(lambda x: x in printable or x.isalpha(), i['text']))
#     for i in t:
#         if i['start'] == pt:
#             ptr += 1
#         else:
#             ptr = 0
#         if ptr < 2:
#             if c[ptr] == 0:
#                 l = Lyrics()
#                 l.time = i['start']
#                 l.duration = i['duration']
#                 l.text = i['text']
#                 a[ptr].append(l)
#             else:
#                 if c[ptr] > 0 and i['text'] in a[ptr][-1].text:
#                     pass
#                 else:
#                     a[ptr][-1].text += ' ' + i['text']
#                 a[ptr][-1].duration += i['duration']
#             if i['duration'] + c[ptr] <= 1.2:
#                 c[ptr] += i['duration']
#             else:
#                 c[ptr] = 0
#         pt = i['start']
#     if min(len(a[0]), len(a[1])) / max(len(a[0]), len(a[1])) < 0.60:
#         a.pop()
#     return a


def beautify_lyrics(t):
    eps = 0.1
    printable = set(string.printable)
    printable.remove('*')
    rx = r'(\u00a9|\u00ae|[\u2000-\u3300]|\ud83c[\ud000-\udfff]|\ud83d[\ud000-\udfff]|\ud83e[\ud000-\udfff])'
    for i in t:
        i['text'] = ''.join(filter(lambda x: x in printable or x.isalpha() or re.match(rx, x), i['text']))
    a = [deque(), deque()]
    for ptr in range(2):
        c = 0
        rt = -1
        for i in range(len(t)):
            if t[i] is None or t[i]['start'] + eps < rt:
                continue
            if c == 0:
                l = Lyrics()
                l.time = t[i]['start']
                l.duration = t[i]['duration']
                l.text = t[i]['text']
                a[ptr].append(l)
            else:
                if c > 0 and t[i]['text'] in a[ptr][-1].text:
                    pass
                else:
                    a[ptr][-1].text += ' ' + t[i]['text']
                a[ptr][-1].duration += t[i]['duration']
            if t[i]['duration'] + c <= 1.2:
                c += t[i]['duration']
            else:
                c = 0
            rt = t[i]['start'] + t[i]['duration']
            t[i] = None

    if min(len(a[0]), len(a[1])) / max(len(a[0]), len(a[1])) < 0.60:
        a.pop()
    return a


def load_lyrics(player: ExtPlayer):
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(player.track.identifier)
        transcript = transcript_list.find_manually_created_transcript([player.lyrics_lang])
        if transcript is not None:
            transcript = transcript.fetch()
            player.track.lyrics = beautify_lyrics(transcript)
            return
    except Exception as e:
        with contextlib.suppress(AttributeError):
            player.track.lyrics = None
        return


def lyrics_embed(player):
    limit = 500
    embed = Embed(title=player.track.title, color=Colour.blurple())
    embed.set_author(name=f'{player.lyrics_lang.upper()} lyrics',
                     icon_url="https://cdn.discordapp.com/emojis/941343150595772467.webp")
    fields = []
    if player is not None and player.track is not None:
        lyrics = player.track.lyrics
        time = player.position
        ratio = time / player.track.length * 0.3
        strings = []
        if lyrics is not None:
            for i in range(len(lyrics)):
                fields.append(deque())
                strings.append("")
                sz = 0
                pos = None
                for line in lyrics[i]:
                    if time < line.time and pos is None:
                        pos = len(fields[i]) - 1
                    fields[i].append(line.text)
                if pos is None:
                    pos = len(fields[i]) - 1
                for j in range(len(fields[i])):
                    if lyrics[i][j].time <= time <= lyrics[i][j].time + lyrics[i][j].duration:
                        fields[i][j] = '__**' + fields[i][j] + '**__\n\n'
                    elif j == pos:
                        fields[i][j] = '**' + fields[i][j] + '**\n\n'
                    else:
                        fields[i][j] = '*' + fields[i][j] + '*\n\n'
                    sz += len(fields[i][j])
                if pos < 0:
                    pos = 0
                while sz > limit or len(fields[i]) > 12:
                    rate = pos / len(fields[i])
                    if rate < 0.3 + ratio:
                        sz -= len(fields[i].pop())
                    else:
                        sz -= len(fields[i].popleft())
                        pos -= 1
                fields[i] = ''.join(fields[i])
    if len(fields) == 0:
        embed.description = "*No lyrics for this song*"
    for i in range(len(fields)):
        fields[i] = ('-+'*(17 if len(fields) == 2 else 25)) + '-\n' + fields[i] + \
                    ('-+'*(17 if len(fields) == 2 else 25)) + '-'
    for idx, field in enumerate(fields):
        embed.add_field(name=f'Type {chr(ord("A") + idx)}', value=field, inline=True)
    return embed


async def lyrics_auto_update(player):
    while player.lyrics_message is not None:
        with contextlib.suppress(Exception):
            await player.lyrics_message.edit(embed=lyrics_embed(player))
        await asyncio.sleep(1.5)


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
        self.add_item(Button(custom_id="pause",
                             style=(ButtonStyle.red if self.player.is_paused() else ButtonStyle.green),
                             emoji=emoji.emojize(':pause_button:'), row=0))
        self.add_item(Button(custom_id="forw", style=ButtonStyle.green,
                             emoji=emoji.emojize(':play_button:'), row=0))
        self.add_item(Button(custom_id="next", style=ButtonStyle.blurple,
                             emoji=emoji.emojize(':next_track_button:'), row=0))
        # if VOLUME_LOCK:
        #     self.add_item(Button(label="Mute", custom_id="mute", disabled=True,
        #                          emoji=emoji.emojize(':muted_speaker:'), row=1))
        # elif self.player.volume > 0:
        #     self.add_item(Button(label="Mute", custom_id="mute",
        #                          emoji=emoji.emojize(':muted_speaker:'), row=1))
        # else:
        #     self.add_item(Button(label="Unmute", custom_id="mute",
        #                          emoji=emoji.emojize(':speaker_high_volume:'), row=1))
        self.add_item(Button(label="Auto", custom_id="related",
                             style=(ButtonStyle.green if self.player.related else ButtonStyle.gray),
                             emoji=emoji.emojize(':seedling:'), row=1))
        self.add_item(Button(label="Loop", custom_id="repeat",
                             style=(ButtonStyle.green if self.player.loop else ButtonStyle.gray),
                             emoji=emoji.emojize(':repeat_button:'), row=1))
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
                self.player.related = False
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
        elif custom_id == 'related':
            self.player.related ^= True
        elif custom_id == 'repeat':
            self.player.loop ^= True
        elif custom_id == 'stop':
            self.player.loop = False
            self.player.related = False
            self.player.queue.clear()
            await self.player.stop()
        elif custom_id == 'history':
            await interaction.response.send_message(
                embed=build_history_embed(self.player, "History:"), ephemeral=True
            )
            return True
        elif custom_id == 'queue_list':
            value = interaction.data['values'][0]
            for i in range(int(value)):
                await get_track(self.player.queue, parse=False)
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
                                            host=WAVELINK_HOST,
                                            port=WAVELINK_PORT,
                                            password=WAVELINK_PASSWORD,
                                            spotify_client=spotify.SpotifyClient(
                                                client_id=SPOTIFY_CLIENT_ID,
                                                client_secret=SPOTIFY_CLIENT_SECRET))

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        print("Connected to lavalink!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: ExtPlayer, track: Track):
        player.hash = random.random()
        if player.message is None:
            await self.player_message(player)

    async def soft_destroy(self, player):
        h = player.hash
        await asyncio.sleep(10)
        if h != player.hash:
            return
        if not player.is_playing():
            await player_terminate(player, self.players, history=True)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: ExtPlayer, track: Track, reason):
        if player.history and player.history[-1]['track'].title == track.title:
            player.history[-1]['cnt'] += 1
        else:
            player.history.append({'track': track, 'cnt': 1})

        if not player.is_playing():
            self.bot.loop.create_task(self.soft_destroy(player))
        await play_next(player, track)

    async def player_message(self, player: ExtPlayer):
        ctx = player.ctx
        view = PlayerView(player)
        msg = await ctx.send(embed=player_embed(player),
                             view=view)
        player.message = msg
        self.bot.loop.create_task(message_auto_update(player))

    async def update_server_player(self, ctx, vc):
        if not wavelink.NodePool.get_node().is_connected():
            await ctx.send(embed=Embed(title="No lavalink connection, trying to reconnect\n"
                                             "Please, retry in a few seconds", color=Colour.gold()),
                           delete_after=10.0)
            await (wavelink.NodePool.get_node())._connect()
            return 0
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
            self.players[server_id].ctx = ctx
        return 1

    @slash_command(name='spotify', description="Add playlist from Spotify")
    async def spotify(self, ctx,
                      url: str = SlashOption(description="Album URL or ID", required=True),
                      vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False),
                      top: bool = SlashOption(description="Add song at the top of the queue", required=False)):
        await ctx.response.defer()
        if not await self.update_server_player(ctx, vc):
            return
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = player.queue
        try:
            playlist, node = spotify.SpotifyTrack.iterator(query=url)
            await playlist.fill_queue(node)
        except Exception:
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.dark_red()),
                           delete_after=10.0)
            return
        if top:
            queue.appendleft(playlist)
        else:
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
                   vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False),
                   top: bool = SlashOption(description="Add song at the top of the queue", required=False)):
        await ctx.response.defer()
        if not await self.update_server_player(ctx, vc):
            return
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = player.queue
        try:
            track = await wavelink.YouTubeTrack.search(query=track, return_first=True)
        except Exception:
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.dark_red()),
                           delete_after=10.0)
            return
        if top:
            queue.appendleft(track)
        else:
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

    @slash_command(name='playlist', description='Add playlist from Youtube')
    async def playlist(self, ctx,
                       url: str = SlashOption(description="Playlist URL", required=True),
                       offset: int = SlashOption(description="Track index from which to start playing songs",
                                                 default=0,
                                                 required=False),
                       vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False),
                       top: bool = SlashOption(description="Add song at the top of the queue", required=False)):
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
            await ctx.send(embed=Embed(title="Nothing found :(", color=Colour.dark_red()),
                           delete_after=10.0)
            return
        if top:
            queue.appendleft(playlist)
        else:
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
            with contextlib.suppress(errors.NotFound, AttributeError):
                await player.message.delete()
            player.message = None
            await self.player_message(player)
            if player.lyrics_message is not None:
                with contextlib.suppress(errors.NotFound, AttributeError):
                    old_msg = player.lyrics_message
                    new_msg = await ctx.send(embed=Embed(title="Lyrics loading", color=Colour.green()))
                    player.lyrics_message = new_msg
                    await old_msg.delete()

    @slash_command(name='save', description='Save (serialize) music player state in chat message')
    async def save(self, ctx,
                   name: str = SlashOption(description="Dump name (optional)", required=False)):
        await ctx.response.defer()
        try:
            data = io.BytesIO(serialize_music(self.players[ctx.guild.id]))
            embed = Embed(description='Use ***floppy disk*** react on this message to restore the dump\n'
                                      '**This action will overwrite all current music state**\n '
                                      'If nothing is playing now, you should be in the voice channel',
                          color=Colour.blurple())
            if name is None:
                name = ""
            else:
                name = '"' + name[:128] + '" '
            embed.set_author(name='Dump ' + name + 'saved',
                             icon_url="https://cdn.discordapp.com/emojis/884559976016805888.webp")
            message = await ctx.send(embed=embed, file=File(data, "dump"))
            await message.add_reaction('💾')
        except:
            embed = Embed(description='Something went wrong...',
                          color=Colour.blurple())
            await ctx.send(embed=embed, delete_after=5.0)

    async def load(self, message, user):
        try:
            server_id = message.guild.id
            file_url = message.attachments[0].url
            request = Request(
                file_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            binary = urlopen(request).read()
            obj = deserialize_music(binary)
            obj['queue'].appendleft(obj['track'])
            if server_id not in self.players:
                if user.voice is None:
                    await message.channel.send(embed=Embed(title="Which voice channel?", color=Colour.green()),
                                               delete_after=10.0)
                    raise Exception('No voice chat')
                await self.update_server_player(message.channel, user.voice.channel)
            self.players[server_id].queue = obj['queue']
            self.players[server_id].history = obj['history']
            if self.players[server_id].is_playing():
                await self.players[server_id].stop()
            else:
                await play_next(self.players[server_id])
        except Exception as e:
            return False
        return True

    @slash_command(name='shuffle', description='Queue random shuffle')
    async def shuffle(self, ctx):
        await ctx.response.defer()
        if ctx.guild.id in self.players:
            player = self.players[ctx.guild.id]
            for item in player.queue:
                if isinstance(item, wavelink.tracks.YouTubePlaylist):
                    my_shuffle(item.tracks, item.selected_track)
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

    @slash_command(name='stfu', description='Stop current song and clear song queue '
                                            '(immediately destroys music player session)')
    async def disconnect(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.players:
            player = self.players[server_id]
            player.queue.clear()
            player.loop = False
            player.related = False
            await self.players[server_id].stop()
            embed = Embed(color=Colour.blurple())
            embed.set_author(name='Ok', icon_url="https://cdn.discordapp.com/emojis/807417229976272896.webp")
            await player_terminate(player, self.players)
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
            await ctx.response.send_message(embed=build_history_embed(self.players[server_id], "History:"),
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
        if VOLUME_LOCK:
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

    @slash_command(name='loop', description='Repeat song infinitely (turns off when skipped, stopped, plays previous)')
    async def loop(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            player = self.players[server_id]
            if player.loop:
                embed = Embed(title="Replay disabled", color=Colour.blurple())
            else:
                embed = Embed(title="On replay", color=Colour.blurple())
            player.loop ^= True
        else:
            embed = Embed(title="Nothing to loop", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='related', description='Play related songs (turns off when stopped, plays previous)')
    async def related(self, ctx):
        await ctx.response.defer()
        if not YOUTUBE_API_TOKEN:
            embed = Embed(title="Youtube token not specified, but required for this command", color=Colour.dark_red())
            await ctx.send(embed=embed, delete_after=5.0)
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            player = self.players[server_id]
            if player.related:
                embed = Embed(title="Auto-select disabled", color=Colour.blurple())
            else:
                embed = Embed(title="Related mode turned on", color=Colour.blurple())
            player.related ^= True
        else:
            embed = Embed(title="Nothing is playing", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='lyrics', description='Show lyrics of the song')
    async def lyrics(self, ctx, lang: str = SlashOption(description='Lyrics language', default='en',
                                                        choices={
                                                            "English": "en",
                                                            "Japanese": "ja",
                                                            "Russian": "ru"
                                                        },
                                                        required=False)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            player = self.players[server_id]
            if player.lyrics_message is None:
                player.lyrics_lang = lang
                load_lyrics(player)
                player.lyrics_message = await ctx.send(embed=lyrics_embed(player))
                self.bot.loop.create_task(lyrics_auto_update(player))
            else:
                await player.lyrics_message.delete()
                player.lyrics_message = None
                embed = Embed(title="Lyrics disabled", color=Colour.gold())
                await ctx.send(embed=embed, delete_after=5.0)
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
            await ctx.send(embed=embed, delete_after=5.0)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        server_id = payload.guild_id
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        user = self.bot.get_user(payload.user_id)
        if payload.user_id != self.bot.user.id and len(message.reactions) > 0 and \
                message.reactions[0].emoji == '💾':
            await message.remove_reaction(payload.emoji, user)
            res = await self.load(message, payload.member)
            if res:
                await message.add_reaction('👍')
            else:
                await message.add_reaction('👎')
            return

        if server_id not in self.players or \
                (self.players[server_id].message is not None and self.players[server_id].message.id != message.id):
            with contextlib.suppress(Exception):
                text = message.embeds[0].description
                if 'Length' in text and 'Volume' in text and 'Timeline' in text:
                    await message.delete()
            return

        if payload.user_id != self.bot.user.id:
            await message.add_reaction(emoji.emojize(':angry_face:'))
            await message.remove_reaction(payload.emoji, user)
        else:
            await asyncio.sleep(2)
            with contextlib.suppress(errors.NotFound):
                await message.remove_reaction(payload.emoji, user)


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
