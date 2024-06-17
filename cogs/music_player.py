import asyncio
import contextlib
from enum import Enum

import emoji
import io
import logging
import math
import pickle
import random
import re
import string

from collections import deque
from config import *
from cryptography.fernet import Fernet
from os.path import exists
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from youtube_transcript_api import YouTubeTranscriptApi

import nextcord
from nextcord import (ButtonStyle, ChannelType, Client, Embed, Interaction, File,
                      SelectOption, SlashOption, errors, slash_command)
from nextcord.abc import GuildChannel
from nextcord.channel import VoiceChannel
from nextcord.colour import Colour
from nextcord.ext import commands
from nextcord.ui import Button, Select, View

import lavalink
from lavalink import Node
from lavalink.errors import ClientError
from lavalink.events import TrackStartEvent, TrackEndEvent, NodeConnectedEvent
from lavalink.filters import LowPass
from lavalink.server import LoadType

if SAFETY:
    from modules.predict import is_nsfw

log = logging.getLogger(__name__)

def time_to_str(time_ms):
    time = round(time_ms / 1000)
    return f"{int(time // 60)} minutes, {int(time % 60)} seconds"


def short_time(time_ms):
    time = round(time_ms / 1000)
    return f"{int(time // 60):02d}:{int(time % 60):02d}"


def render_bar(cells, time, duration):
    filled = max(1, math.floor(cells * (time / duration)))
    empty = cells - filled
    filled -= 1
    return f"[{('=' * filled)}O{('-' * empty)}]"


def cut_text(text, limit):
    return f"{text[:limit]}..." if len(text) > limit else text


class ExtPlayer(lavalink.DefaultPlayer):
    history: deque
    message: nextcord.Message | None
    lyrics_message: nextcord.Message | None
    lyrics_lang: str | None

    def __init__(self, guild_id: int, node: 'Node'):
        super().__init__(guild_id, node)
        self.bot = None
        self.message = None
        self.ctx = None
        self.history = deque()
        self.moving_backwards = False

        self.lyrics = None
        self.lyrics_message = None
        self.lyrics_lang = None

    async def destroy(self):
        with contextlib.suppress(Exception):
            await self.lyrics_message.delete()
        with contextlib.suppress(Exception):
            await self.message.delete()
        with contextlib.suppress(Exception):
            embed = build_history_embed(self, "Songs played during the session:")
            if HISTORY_DUMP:
                data = io.BytesIO(serialize_music(self, SerializeType.HISTORY))
            await self.ctx.send(embed=embed, file=File(data, "history_dump") if HISTORY_DUMP else None)
        with contextlib.suppress(Exception):
            guild = self.bot.get_guild(self.guild_id)
            await guild.voice_client.disconnect(force=True)
        await self.client.player_manager.destroy(self.guild_id)


class LavalinkVoice(nextcord.VoiceProtocol):
    def __init__(self, client: Client, channel: VoiceChannel):
        super().__init__(client, channel)
        self.client = client
        self.channel = channel
        self.guild_id = channel.guild.id
        self._destroyed = False

        if not hasattr(self.client, 'lavalink'):
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(host=LAVALINK_HOST, port=LAVALINK_PORT, password=LAVALINK_PASSWORD,
                                          region='eu', name='local-node')

        self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            't': 'VOICE_SERVER_UPDATE',
            'd': data
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        channel_id = data['channel_id']

        if not channel_id:
            await self._destroy()
            return

        self.channel = self.client.get_channel(int(channel_id))

        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
            't': 'VOICE_STATE_UPDATE',
            'd': data
        }

        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False,
                      self_mute: bool = False) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that would set channel_id
        # to None doesn't get dispatched after the disconnect
        player.channel_id = None
        await self._destroy()

    async def _destroy(self):
        self.cleanup()

        if self._destroyed:
            # Idempotency handling, if `disconnect()` is called, the changed voice state
            # could cause this to run a second time.
            return

        self._destroyed = True

        try:
            await self.lavalink.player_manager.destroy(self.guild_id)
        except ClientError:
            pass


async def get_track(player: ExtPlayer):
    while player.queue:
        track = player.queue.pop(0)
        if player.history and len(player.history) > 0 and player.history[-1]['track'].title == track.title:
            player.history[-1]['cnt'] += 1
        else:
            player.history.append({'track': track, 'cnt': 1})
        return track
    return None


def build_queue_embed(player: ExtPlayer):
    if not player.queue:
        text = "*Empty*"
    else:
        text = ""
        for i, item in enumerate(player.queue):
            text += f"*{i}*. [**{item.title}**]({item.uri}), length: {round(item.duration / 1000)} sec.\n"
            text += '\n'
            if len(text) > 3000:
                break
    embed = Embed(description=text, color=Colour.blurple())
    embed.set_author(name="Queue", icon_url="https://cdn.discordapp.com/emojis/695126168680005662.webp")
    return embed


def build_history_embed(player: ExtPlayer, title: str):
    text = ""
    if not player.history:
        text = "*Empty*"
    else:
        for i, item in enumerate(player.history):
            text += f"*{i}*. [**{item['track'].title}**]({item['track'].uri}), " \
                    f"length: *{short_time(item['track'].duration)}*"
            if item['cnt'] > 1:
                text += f", **{item['cnt']}**x"
            text += '\n\n'
            if len(text) > 3000:
                text += 'and more...'
                break
    embed = Embed(description=text)
    embed.set_author(name=title, icon_url="https://cdn.discordapp.com/emojis/695126168680005662.webp")
    return embed


def player_embed(player: ExtPlayer):
    track = player.current
    options = []
    if player.loop == player.LOOP_SINGLE:
        options.append('*On song repeat*')
    if player.loop == player.LOOP_QUEUE:
        options.append('*On queue repeat*')
    if player.shuffle:
        options.append('*On shuffle*')
    if track is not None:
        embed = Embed(description=f"[**{track.title}**]({track.uri})\n"
                                  f"**Length**: *{time_to_str(track.duration)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**Timeline**: *{short_time(player.position)}/{short_time(track.duration)}*\n"
                                  f"```{render_bar(30, player.position, track.duration)}```"
                                  f"{', '.join(options)}",
                      color=Colour.blurple())
        if player.paused:
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
                                  f"```{render_bar(30, 1, 1)}```"
                                  f"{','.join(options)}",
                      color=Colour.blurple())
        embed.set_author(name='Stopped.',
                         icon_url='https://cdn.discordapp.com/emojis/884559976016805888.webp')
        embed.set_image(url='https://s9.gifyu.com/images/SV5g5.gif')
    return embed


async def play_next(player: ExtPlayer):
    try:
        await player.play()
        return True
    except Exception:
        return False
    finally:
        if player.lyrics_message is not None:
            load_lyrics(player)


async def player_message(player: ExtPlayer, bot):
    ctx = player.ctx
    view = PlayerView(player)
    msg = await ctx.send(embed=player_embed(player),
                         view=view)
    player.message = msg
    bot.loop.create_task(message_auto_update(player, bot))


async def respawn_player_body(player, ctx, bot):
    player.ctx = ctx.channel
    with contextlib.suppress(errors.NotFound, AttributeError, HTTPError):
        await player.message.delete()
    player.message = None
    await player_message(player, bot)
    if player.lyrics_message is not None:
        with contextlib.suppress(errors.NotFound, AttributeError, HTTPError):
            await player.lyrics_message.delete()
        await init_lyrics(player, player.lyrics_lang, ctx, bot)


async def message_auto_update(player, bot):
    try:
        idx = player.message.id
        bad_req = 0
        prev = None
        while player.message is not None and idx == player.message.id:
            try:
                view = PlayerView(player)
                embed = player_embed(player)
                v_cmp = view.to_components()
                e_cmp = embed.to_dict()
                if prev != [v_cmp, e_cmp]:
                    await player.message.edit(
                        embed=embed,
                        view=view
                    )
                bad_req = 0
            except errors.HTTPException:
                if bad_req >= 5:
                    await respawn_player_body(player, player.ctx, bot)
                    return
                bad_req += 1
            except Exception:
                return
            await asyncio.sleep(1)
    finally:
        log.info('music_player message auto update stopped')


class SerializeType(Enum):
    NORMAL = 0
    HISTORY = 1


def serialize_music(player: ExtPlayer, serialize_type: SerializeType = SerializeType.NORMAL):
    if not exists('secret.key'):
        key = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(key)
    key = open("secret.key", "rb").read()
    if serialize_type == serialize_type.NORMAL:
        dump = pickle.dumps({'queue': player.queue, 'history': player.history, 'track': player.current})
    elif serialize_type == serialize_type.HISTORY:
        dump = pickle.dumps({'queue': [item['track'] for item in player.history], 'history': deque()})
    else:
        return None
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
        transcript_list = YouTubeTranscriptApi.list_transcripts(player.current.identifier)
        transcript = transcript_list.find_manually_created_transcript([player.lyrics_lang])
        if transcript is not None:
            transcript = transcript.fetch()
            player.lyrics = beautify_lyrics(transcript)
            return
    except Exception as e:
        with contextlib.suppress(AttributeError):
            player.lyrics = None
        return


async def init_lyrics(player: ExtPlayer, lang: str, ctx, bot):
    player.lyrics_lang = lang
    load_lyrics(player)
    player.lyrics_message = await ctx.send(embed=lyrics_embed(player))
    bot.loop.create_task(lyrics_auto_update(player, bot))


def lyrics_embed(player: ExtPlayer):
    limit = 500
    embed = Embed(title=player.current.title, color=Colour.blurple())
    embed.set_author(name=f'{player.lyrics_lang.upper()} lyrics',
                     icon_url="https://cdn.discordapp.com/emojis/941343150595772467.webp")
    fields = []
    if player is not None and player.current is not None:
        lyrics = player.lyrics
        time = round(player.position / 1000)
        ratio = time / player.current.duration * 0.3
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
        fields[i] = ('-+' * (17 if len(fields) == 2 else 25)) + '-\n' + fields[i] + \
                    ('-+' * (17 if len(fields) == 2 else 25)) + '-'
    for idx, field in enumerate(fields):
        embed.add_field(name=f'Type {chr(ord("A") + idx)}', value=field, inline=True)
    return embed


async def lyrics_auto_update(player: ExtPlayer, bot):
    idx = player.lyrics_message.id
    bad_req = 0
    while player.lyrics_message is not None and idx == player.lyrics_message.id:
        try:
            await player.lyrics_message.edit(embed=lyrics_embed(player))
            bad_req = 0
        except (errors.NotFound, AttributeError):
            with contextlib.suppress(Exception):
                await player.lyrics_message.delete()
            player.lyrics_message = None
            return
        except errors.HTTPException:
            if bad_req >= 5:
                await init_lyrics(player, player.lyrics_lang, player.ctx, bot)
                return
            bad_req += 1
        except Exception:
            return
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
    player: ExtPlayer

    def __init__(self, player: ExtPlayer):
        super().__init__(timeout=None)
        self.player = player
        self.player_components()

    def loop_button(self):
        button = Button(label="Loop", custom_id="repeat", row=1)
        if self.player.loop == self.player.LOOP_NONE:
            button.emoji = emoji.emojize(':repeat_button:')
            button.style = ButtonStyle.gray
        if self.player.loop == self.player.LOOP_SINGLE:
            button.emoji = emoji.emojize(':repeat_single_button:')
            button.style = ButtonStyle.blurple
        if self.player.loop == self.player.LOOP_QUEUE:
            button.emoji = emoji.emojize(':repeat_button:')
            button.style = ButtonStyle.green
        return button

    def stop_button(self):
        button = Button(custom_id="stop", style=ButtonStyle.red, emoji=emoji.emojize(':black_large_square:'), row=1)
        if self.player.is_playing:
            button.label = "Exit"
        else:
            button.label = "Quit"
        return button

    def player_components(self):
        self.add_item(Button(custom_id="prev", style=ButtonStyle.blurple,
                             emoji=emoji.emojize(':last_track_button:'), row=0))
        self.add_item(Button(custom_id="back", style=ButtonStyle.green,
                             emoji=emoji.emojize(':reverse_button:'), row=0))
        self.add_item(Button(custom_id="pause",
                             style=(ButtonStyle.red if self.player.paused else ButtonStyle.green),
                             emoji=emoji.emojize(':play_or_pause_button:'), row=0))
        self.add_item(Button(custom_id="forw", style=ButtonStyle.green,
                             emoji=emoji.emojize(':play_button:'), row=0))
        self.add_item(Button(custom_id="next", style=ButtonStyle.blurple,
                             emoji=emoji.emojize(':next_track_button:'), row=0))
        self.add_item(Button(label="Rand", custom_id="shuffle",
                             style=(ButtonStyle.green if self.player.shuffle else ButtonStyle.gray),
                             emoji=emoji.emojize(':seedling:'), row=1))
        self.add_item(self.loop_button())
        self.add_item(Button(label="Log", custom_id="history", emoji=emoji.emojize(':scroll:'), row=1))
        self.add_item(self.stop_button())

        options = []
        for item in self.player.queue:
            word = f"{cut_text(item.title, 48)}, {short_time(item.duration)}"
            num = str(len(options))
            options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
            if len(options) == 10:
                break
        if len(options) == 0:
            options.append(SelectOption(label="empty", value="cricket", emoji=emoji.emojize(':cricket:')))
        if options:
            self.add_item(
                Select(placeholder=f"Queue: {options[0].label}", options=options, custom_id="queue_list", row=2))

    async def interaction_check(self, interaction: Interaction) -> bool:
        custom_id = interaction.data['custom_id']
        if custom_id == 'prev':
            if self.player.history:
                prev = self.player.history.pop()['track']
                self.player.loop = self.player.LOOP_NONE
                self.player.moving_backwards = True
                await self.player.play(prev)
            else:
                await self.player.seek(0)
        elif custom_id == 'back':
            cur = self.player.position
            await self.player.seek(cur - 30 * 1000)
        elif custom_id == 'pause':
            if self.player.is_playing:
                if self.player.paused:
                    await self.player.set_pause(False)
                else:
                    await self.player.set_pause(True)
        elif custom_id == 'forw':
            cur = self.player.position
            await self.player.seek(cur + 30 * 1000)
        elif custom_id == 'next':
            if self.player.loop == self.player.LOOP_SINGLE:
                self.player.loop = self.player.LOOP_NONE
            await self.player.play()
        elif custom_id == 'mute':
            if self.player.volume > 0:
                await self.player.set_volume(0)
            else:
                await self.player.set_volume(100)
        elif custom_id == 'shuffle':
            self.player.set_shuffle(self.player.shuffle ^ True)
        elif custom_id == 'repeat':
            self.player.loop = (self.player.loop + 1) % 3
        elif custom_id == 'stop':
            if self.player.is_playing:
                self.player.loop = self.player.LOOP_NONE
                self.player.queue.clear()
                await self.player.stop()
                return True
            else:
                await self.player.destroy()
                return True
        elif custom_id == 'history':
            await interaction.response.send_message(
                embed=build_history_embed(self.player, "History:"), ephemeral=True
            )
            return True
        elif custom_id == 'queue_list':
            value = interaction.data['values'][0]
            if not value.isnumeric():
                return True
            for i in range(int(value)):
                await get_track(self.player)
            self.player.loop = self.player.LOOP_NONE
            await self.player.play()
        await interaction.response.edit_message()
        return True


async def search_query(node: lavalink.Node, text: str, source: str='ytsearch'):
    url_rx = re.compile(r'https?://(?:www\.)?.+')
    query = text.strip('<>')

    if not url_rx.match(query):
        query = f'{source}:{query}'

    results = await node.get_tracks(query)
    return results


class MusicPlayerCog(commands.Cog, name="Music player"):
    """
    **Music cog** - music player. Designed for control via buttons.

    ***Available commands:***

    **/play** - play songs from query (may be link or text query)

    **/seek** - play from the specified second
    **/skip** - skip current song
    **/pause** - pause/continue
    **/stfu** - clear queue and stop playing

    **/respawn** - start rendering the player body in the last message

    **/queue** - song queue
    **/history** - song history
    """

    def __init__(self, bot):
        self.bot = bot
        self.lavalink = None
        self.bot.loop.create_task(self.setup_hook())

    async def setup_hook(self) -> None:
        await self.bot.wait_until_ready()
        if not hasattr(self.bot, 'lavalink'):
            self.bot.lavalink = lavalink.Client(self.bot.user.id)
            self.bot.lavalink.add_node(host=LAVALINK_HOST, port=LAVALINK_PORT, password=LAVALINK_PASSWORD,
                                       region='eu', name='local-node')
        self.lavalink: lavalink.Client = self.bot.lavalink
        self.lavalink.add_event_hooks(self)

    def cog_unload(self):
        self.lavalink._event_hooks.clear()

    @lavalink.listener(NodeConnectedEvent)
    async def on_node_ready(self, event: NodeConnectedEvent):
        log.info("Connected to lavalink! Music Player api is fine")

    @lavalink.listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        player: ExtPlayer = event.player
        if player.message is None:
            await player_message(player, self.bot)

    @lavalink.listener(TrackEndEvent)
    async def on_track_end(self, event: TrackEndEvent):
        player: ExtPlayer = event.player
        if player.moving_backwards:
            player.queue.insert(0, event.track)
            player.moving_backwards = False
        else:
            if player.history and len(player.history) > 0 and player.history[-1]['track'].title == event.track.title:
                player.history[-1]['cnt'] += 1
            else:
                player.history.append({'track': event.track, 'cnt': 1})

    async def update_server_player(self, ctx, voice_client):
        server_id = ctx.guild.id
        player = self.bot.lavalink.player_manager.create(server_id, cls=ExtPlayer)

        if not player.is_connected:
            try:
                if voice_client is None:
                    await ctx.user.voice.channel.connect(cls=LavalinkVoice)
                else:
                    await voice_client.connect(cls=LavalinkVoice)
                player.bot = self.bot
            except Exception:
                await ctx.send(embed=Embed(title="Which voice channel?", color=Colour.green()), delete_after=10.0)
                return False

        channel = ctx.channel
        if player.ctx is None:
            player.ctx = channel
        return True

    @slash_command(name='play', description='Play songs from query (may be link or text query)')
    async def play(self,
                   interaction: Interaction,
                   query: str = SlashOption(description="Song name or link", required=True),
                   vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=False),
                   top: bool = SlashOption(description="Add songs at the top of the queue", required=False)):
        if not await self.update_server_player(interaction, vc):
            return
        server_id = interaction.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)

        search_result = await search_query(player.node, query)
        if len(search_result.tracks) == 0:
            raise Exception

        embed = Embed(color=Colour.green())
        name = interaction.user.nick if interaction.user.nick else interaction.user.global_name
        embed.set_author(name=name, icon_url=interaction.user.avatar.url)

        if search_result.load_type == LoadType.EMPTY:
            await interaction.send(embed=Embed(title="Nothing found :(", color=Colour.dark_red()), delete_after=10.0)
            return
        elif search_result.load_type == LoadType.PLAYLIST:
            tracks = search_result.tracks
            if top:
                for track in reversed(tracks):
                    player.add(track=track, requester=interaction.user.id, index=0)
            else:
                for track in tracks:
                    player.add(track=track, requester=interaction.user.id)
            embed.title = 'Playlist added'
            embed.description = f'**{search_result.playlist_info.name}** - *{len(tracks)}* tracks'
        else:
            track = search_result.tracks[0]
            embed.title = 'Track added'
            embed.description = f'[{track.title}]({track.uri})'
            if top:
                player.add(track=track, requester=interaction.user.id, index=0)
            else:
                player.add(track=track, requester=interaction.user.id)

        await interaction.response.send_message(embed=embed, delete_after=10.0)
        if not player.is_playing:
            await play_next(player)

    @play.on_autocomplete("query")
    async def load_tracklist(self, interaction: Interaction, query: str):
        if not query:
            await interaction.response.send_autocomplete([])
            return
        node = random.choice(self.lavalink.nodes)
        search_result = await search_query(node, query)
        titles = list(map(lambda track: track.title, search_result.tracks))[:5]
        await interaction.response.send_autocomplete(titles)

    @slash_command(name='respawn', description='Resend player body')
    async def respawn(self, ctx):
        await ctx.response.defer()
        player: ExtPlayer = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player or not player.ctx:
            await ctx.send(embed=Embed(title="Nothing is playing", color=Colour.red()), delete_after=5)
        else:
            await ctx.send(embed=Embed(title="Player respawned", color=Colour.green()), delete_after=5)
            await respawn_player_body(player, ctx, self.bot)

    @slash_command(name='save', description='Save (serialize) music player state in chat message')
    async def save(self, ctx,
                   name: str = SlashOption(description="Dump name (optional)", required=False)):
        await ctx.response.defer()
        try:
            player: ExtPlayer = self.bot.lavalink.player_manager.get(ctx.guild.id)
            data = io.BytesIO(serialize_music(player))
            embed = Embed(description='Use ***any*** react on this message to restore the dump\n'
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
        except Exception as e:
            embed = Embed(description='Something went wrong...',
                          color=Colour.blurple())
            await ctx.send(embed=embed, delete_after=5.0)

    async def load(self, message, user):
        await self.update_server_player(message, user.voice.channel)
        try:
            file_url = message.attachments[0].url
            request = Request(
                file_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            binary = urlopen(request).read()
            obj = deserialize_music(binary)
            player: ExtPlayer = self.bot.lavalink.player_manager.get(message.guild.id)
            if not player or not player.is_connected:
                if user.voice is None:
                    await message.channel.send(embed=Embed(title="Which voice channel?", color=Colour.green()),
                                               delete_after=10.0)
                    raise Exception('No voice chat')
            player.queue = obj['queue']
            player.history = obj['history']
            if 'track' in obj:
                await player.play(obj['track'])
            else:
                await player.play()
        except Exception as e:
            return False
        return True

    @slash_command(name='shuffle', description='Queue random playback')
    async def shuffle(self, ctx):
        await ctx.response.defer()
        player: ExtPlayer = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player.shuffle:
            player.set_shuffle(False)
            await ctx.send(embed=Embed(title="Shuffle turned off", color=Colour.green()), delete_after=5)
        else:
            player.set_shuffle(True)
            await ctx.send(embed=Embed(title="Shuffle turned on", color=Colour.green()), delete_after=5)

    # @slash_command(name='move', description='Move to specified voice channel (default=<user voice channel>)')
    # async def move(self, ctx,
    #                vc: GuildChannel = SlashOption(channel_types=[ChannelType.voice], default=None, required=True)):
    #     await ctx.response.defer()
    #     server_id = ctx.guild.id
    #     if server_id in self.players and self.players[server_id].is_playing():
    #         try:
    #             player = self.players[server_id]
    #             if vc is None:
    #                 await player.move_to(ctx.author.voice.channel)
    #             else:
    #                 await player.move_to(vc)
    #             embed = Embed(title="Ok", color=Colour.green())
    #         except Exception:
    #             embed = Embed(title="Can't move in this channel", color=Colour.red())
    #     else:
    #         embed = Embed(title="Player not initialized", color=Colour.red())
    #     await ctx.send(embed=embed, delete_after=5.0)

    @slash_command(name='pop', description='Delete specific song/playlist from queue by index')
    async def pop(self, ctx,
                  idx: int = SlashOption(description="ID of the song/playlist from the queue", required=True)):
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        queue = player.queue
        if idx >= 0 or idx < len(queue):
            item = queue[idx]
            del queue[idx]
            embed = Embed(title=f"Song: '**{item.title}**' was deleted", color=Colour.blurple())
        else:
            embed = Embed(title="Wrong index given", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player.is_playing:
            if player.loop == player.LOOP_SINGLE:
                player.loop = player.LOOP_NONE
            await player.play()
            embed = Embed(title="Current track skipped", color=Colour.gold())
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='pause', description='Pause/resume current song')
    async def pause(self, ctx):
        await ctx.response.defer()
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_connected:
            if player.paused:
                await player.set_pause(False)
                embed = Embed(title="Playing again", color=Colour.gold())
            else:
                await player.set_pause(True)
                embed = Embed(title="Song paused", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to pause", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='stfu', description='Stop current song and clear song queue '
                                            '(immediately destroys music player session)')
    async def disconnect(self, ctx):
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_connected:
            embed = Embed(color=Colour.blurple())
            embed.set_author(name='Ok', icon_url="https://cdn.discordapp.com/emojis/807417229976272896.webp")

            await player.destroy()
        else:
            embed = Embed(color=Colour.blurple())
            embed.set_author(name="I've been quiet enough",
                             icon_url="https://cdn.discordapp.com/emojis/807417229976272896.webp")
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='queue', description='Show current song queue')
    async def queue(self, ctx):
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_connected:
            await ctx.response.send_message(embed=build_queue_embed(player),
                                            delete_after=60.0, ephemeral=True)
        else:
            await ctx.response.send_message(embed=Embed(title="Player not initialized", color=Colour.red()),
                                            delete_after=5.0, ephemeral=True)

    @slash_command(name='history', description='Show song history')
    async def history(self, ctx):
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_connected:
            await ctx.response.send_message(embed=build_history_embed(player, "History:"),
                                            delete_after=60.0, ephemeral=True)
        else:
            await ctx.response.send_message(Embed(title="Player not connected", color=Colour.red()),
                                            delete_after=5.0, ephemeral=True)

    @slash_command(name='seek', description='Move timeline to specific time in seconds')
    async def seek(self, ctx, time: int = SlashOption(description="Time to seek in seconds", required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_playing:
            await player.seek(1000 * time)
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="Nothing to move", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='volume', description='Change volume to specific value')
    async def volume(self, ctx, value: int = SlashOption(description="Volume value", required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if player and player.is_connected:
            await player.set_volume(value)
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="Player not connected", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='loop', description='Repeat song infinitely (turns off when skipped, stopped, plays previous)')
    async def loop(self, ctx, type: int = SlashOption(description="Loop type",
                                                      choices={"Disabled": 0, "Single": 1, "Queue": 2},
                                                      required=True)):
        await ctx.response.defer()
        server_id = ctx.guild.id
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)

        embed = Embed(title="Nothing to loop", color=Colour.blurple())
        if player and player.is_playing:
            if type == player.LOOP_NONE:
                embed = Embed(title="Replay disabled", color=Colour.blurple())
            elif type == player.LOOP_SINGLE:
                embed = Embed(title="On song repeat", color=Colour.blurple())
            elif type == player.LOOP_QUEUE:
                embed = Embed(title="On queue repeat", color=Colour.blurple())
            player.loop = type

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
        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)

        if player and player.is_playing:
            if player.lyrics_message is None:
                await init_lyrics(player, lang, ctx, self.bot)
            else:
                try:
                    await player.lyrics_message.delete()
                except errors.HTTPException:
                    await init_lyrics(player, lang, ctx, self.bot)
                    return
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
        message = await channel.fetch_message(payload.message_id)

        def has_dump():
            for attachment in message.attachments:
                if 'dump' in attachment.filename:
                    return True
            return False

        if payload.user_id != self.bot.user.id and has_dump():
            await self.load(message, payload.member)
            await message.remove_reaction(payload.emoji, payload.member)
            return

        player: ExtPlayer = self.bot.lavalink.player_manager.get(server_id)
        if not player or player.message is not None and player.message.id != message.id:
            with contextlib.suppress(Exception):
                text = message.embeds[0].description
                if 'Length' in text and 'Volume' in text and 'Timeline' in text:
                    await message.delete()
            return


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
