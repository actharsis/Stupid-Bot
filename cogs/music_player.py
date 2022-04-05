import asyncio
import discord
import emoji
import math
import wavelink

from collections import deque
from config import volume_lock, safety
from discord import Embed
from discord.colour import Colour
from discord.ext import commands
from discord_components import Select, SelectOption, Button, ButtonStyle
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option
from wavelink import Track, Node
if safety:
    from modules.predict import is_nsfw


def time_to_str(time):
    return f"{int(time // 60)} minutes, {int(time % int(60))} seconds"


def short_time(time):
    return f"{int(time // 60)}:{int(time % int(60))}"


def render_bar(cells, time, duration):
    filled = max(1, math.floor(cells * (time / duration)))
    empty = cells - filled
    filled -= 1
    bar = f"[{('=' * filled)}O{('-' * empty)}]"
    return bar


def cut_text(text, limit):
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def get_track(queue):
    if isinstance(queue[0], wavelink.tracks.YouTubePlaylist):
        playlist = queue[0]
        if playlist.selected_track >= len(playlist.tracks):
            queue.popleft()
            return
        track = playlist.tracks[playlist.selected_track]
        playlist.selected_track += 1
        if playlist.selected_track == len(playlist.tracks):
            queue.popleft()
    else:
        track = queue.popleft()
    return track


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.connect_nodes())
        self.players = {}
        self.queues = {}
        self.server_ctx = {}
        self.messages = {}
        self.loops = set()

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=2333,
                                            password='youwillpass')

    async def soft_leave_vc(self, server_id):
        await asyncio.sleep(5)
        if not self.players[server_id].is_playing():
            await self.players[server_id].disconnect()

    async def soft_message_delete(self, server_id):
        await asyncio.sleep(5)
        if not self.players[server_id].is_playing():
            await self.messages[server_id].delete()
            self.messages.pop(server_id)

    async def message_auto_update(self, server_id):
        while server_id in self.messages:
            try:
                await self.messages[server_id].edit(
                    embed=self.player_embed(self.players[server_id]),
                    components=self.player_components(server_id)
                )
            except AttributeError:
                return
            await asyncio.sleep(3)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        print(f"Connected to lavalink!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: wavelink.player, track: Track):
        server_id = player.guild.id
        if server_id in self.server_ctx and server_id not in self.messages:
            await self.player(server_id)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.player, track: Track, reason):
        server_id = player.guild.id
        if not player.is_playing():
            self.bot.loop.create_task(self.soft_message_delete(server_id))
            self.bot.loop.create_task(self.soft_leave_vc(server_id))
        if server_id in self.loops:
            await player.play(track)
        else:
            await self.play_next(player, server_id)

    @commands.Cog.listener()
    async def on_select_option(self, interaction):
        await interaction.respond(type=7)
        server_id = interaction.guild_id
        for i in range(int(interaction.values[0])):
            get_track(self.queues[server_id])
        if server_id in self.loops:
            self.loops.remove(server_id)
        await self.players[server_id].stop()

    @commands.Cog.listener()
    async def on_button_click(self, interaction):
        server_id = interaction.guild_id
        player = self.players[server_id]
        custom_id = interaction.custom_id
        if custom_id == 'prev':
            await player.seek(0)
        elif custom_id == 'back':
            cur = self.players[server_id].position
            await player.seek(1000 * (cur - 30))
        elif custom_id == 'pause':
            if player.is_playing():
                if player.is_paused():
                    await player.resume()
                else:
                    await player.pause()
        elif custom_id == 'forw':
            cur = self.players[server_id].position
            await player.seek(1000 * (cur + 30))
        elif custom_id == 'next':
            if server_id in self.loops:
                self.loops.remove(server_id)
            await player.stop()
        elif custom_id == 'mute':
            if player.volume > 0:
                await player.set_volume(0)
            else:
                await player.set_volume(100)
        elif custom_id == 'repeat':
            if server_id in self.loops:
                self.loops.remove(server_id)
            else:
                self.loops.add(server_id)
        elif custom_id == 'stop':
            if server_id in self.loops:
                self.loops.remove(server_id)
            self.queues[server_id].clear()
            await player.stop()
        elif custom_id == 'queue':
            await interaction.respond(embed=self.build_queue_embed(server_id))
            return
        await interaction.respond(type=7)

    async def player(self, server_id):
        player = self.players[server_id]
        ctx = self.server_ctx[server_id]
        msg = await ctx.send(embed=self.player_embed(player),
                             components=self.player_components(server_id))
        self.messages[server_id] = msg
        self.bot.loop.create_task(self.message_auto_update(server_id))

    def player_embed(self, player):
        track = player.track
        embed = Embed(title="🎧 Currently playing:",
                      description=f"[**{track.title}**]({track.uri})\n"
                                  f"**Length**: *{time_to_str(track.length)}*; **Volume**: *{int(player.volume)}*\n"
                                  f"**{' ' * 40}Timeline**: *{short_time(player.position)}/{short_time(track.length)}*\n"
                                  f"```{render_bar(36, player.position, track.length)}```"
                                  f"{'*On repeat*' if player.guild.id in self.loops else ''}",
                      color=Colour.red())
        url = f'https://img.youtube.com/vi/{track.uri[32:]}/mqdefault.jpg'
        if safety and is_nsfw(url):
            url = f'https://img.youtube.com/vi/nter2axWgoA/mqdefault.jpg'
        embed.set_image(url=url)
        return embed

    def player_components(self, server_id):
        first_line = [
            Button(custom_id="prev", style=ButtonStyle.blue, emoji=emoji.emojize(':last_track_button:')),
            Button(custom_id="back", style=ButtonStyle.green, emoji=emoji.emojize(':reverse_button:')),
            Button(custom_id="pause", style=ButtonStyle.green, emoji=emoji.emojize(':pause_button:')),
            Button(custom_id="forw", style=ButtonStyle.green, emoji=emoji.emojize(':play_button:')),
            Button(custom_id="next", style=ButtonStyle.blue, emoji=emoji.emojize(':next_track_button:'))
        ]
        volume = []
        if not volume_lock:
            if self.players[server_id].volume > 0:
                volume = [Button(label="Mute", custom_id="mute", emoji=emoji.emojize(':muted_speaker:'))]
            else:
                volume = [Button(label="Unmute", custom_id="mute", emoji=emoji.emojize(':speaker_high_volume:'))]
        else:
            volume = [Button(label="Mute", custom_id="mute", disabled=True, emoji=emoji.emojize(':muted_speaker:'))]
        second_line = volume + [Button(label="Loop", custom_id="repeat", emoji=emoji.emojize(':repeat_button:')),
                                Button(label="List", custom_id="queue", emoji=emoji.emojize(':scroll:')),
                                Button(label="Quit", custom_id="stop", style=ButtonStyle.red,
                                       emoji=emoji.emojize(':black_large_square:'))]

        options = []
        for i, item in enumerate(self.queues[server_id]):
            if isinstance(item, wavelink.tracks.YouTubePlaylist):
                j = 0
                while j + item.selected_track < len(item.tracks) and len(options) < 10:
                    idx = item.selected_track + j
                    track = item.tracks[idx]
                    word = f"{cut_text(track.title, 48)}, {short_time(track.length)}"
                    num = str(len(options))
                    options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
                    j += 1
            else:
                word = f"{cut_text(item.title, 48)}, {short_time(item.length)}"
                num = str(len(options))
                options.append(SelectOption(label=word, value=num, emoji=emoji.emojize(f':keycap_{num}:')))
            if len(options) == 10:
                break
        if len(options) > 0:
            queue = [Select(placeholder="Queue", options=options, custom_id="queue_list")]
            return [first_line, second_line, queue]
        return [first_line, second_line]

    async def play_next(self, player: wavelink.player, server_id):
        queue = self.queues[server_id]
        if queue:
            track = get_track(queue)
            await player.play(track)

    async def update_server_player(self, ctx, vc):
        server_id = ctx.guild.id
        self.server_ctx[server_id] = ctx.channel
        try:
            if vc is None:
                if server_id not in self.players or not self.players[server_id].is_connected():
                    self.players[server_id] = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            else:
                if server_id not in self.players or not self.players[server_id].is_connected():
                    self.players[server_id] = await vc.connect(cls=wavelink.Player)
                else:
                    self.players[server_id].move_to(vc)
        except:
            await ctx.send(embed=Embed(title="Which voice channel?", color=Colour.green()), delete_after=10.0)
        if server_id not in self.queues:
            self.queues[server_id] = deque()

    @cog_ext.cog_slash(name='play', description='Play a song from Youtube',
                       options=[
                           create_option(
                               name="track",
                               description="Track name",
                               option_type=SlashCommandOptionType.STRING,
                               required=True
                           ),
                           create_option(
                               name="vc",
                               description="Voice channel",
                               option_type=SlashCommandOptionType.CHANNEL,
                               required=False
                           )
                       ])
    async def play(self, ctx, track, vc=None):
        await ctx.defer()
        await self.update_server_player(ctx, vc)
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = self.queues[server_id]
        try:
            track = await wavelink.YouTubeTrack.search(query=track, return_first=True)
        except:
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
        if server_id in self.messages:
            await self.messages[server_id].delete()
            self.messages.pop(server_id)
        await self.play_next(player, server_id)

    @cog_ext.cog_slash(name='playlist', description='Add playlist',
                       options=[
                           create_option(
                               name="uri",
                               description="Playlist URI",
                               option_type=SlashCommandOptionType.STRING,
                               required=True
                           ),
                           create_option(
                               name="offset",
                               description="Track index from which to start playing songs",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=False
                           ),
                           create_option(
                               name="vc",
                               description="Voice channel",
                               option_type=SlashCommandOptionType.CHANNEL,
                               required=False
                           )
                       ])
    async def playlist(self, ctx, uri, offset=0, vc=None):
        await ctx.defer()
        await self.update_server_player(ctx, vc)
        server_id = ctx.guild.id
        player = self.players[server_id]
        queue = self.queues[server_id]
        try:
            playlist = await wavelink.YouTubePlaylist.search(query=uri)
            playlist.selected_track = max(0, offset)
        except:
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
        if server_id in self.messages:
            await self.messages[server_id].delete()
            self.messages.pop(server_id)
        await self.play_next(player, server_id)

    @cog_ext.cog_slash(name='spawn_player', description='Resend player body')
    async def spawn_player(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id not in self.players or not self.players[server_id].is_playing():
            await ctx.send(embed=Embed(title=f"Nothing is playing", color=Colour.red()), delete_after=5)
        else:
            await ctx.send(embed=Embed(title=f"Player respawned", color=Colour.green()), delete_after=5)
            if server_id in self.messages:
                self.server_ctx[server_id] = ctx.channel
                await self.messages[server_id].delete()
                self.messages.pop(server_id)
            await self.player(server_id)

    @cog_ext.cog_slash(name='move', description='Move to specified voice channel (default=<user voice channel>)',
                       options=[
                           create_option(
                               name="vc",
                               description="Voice channel",
                               option_type=SlashCommandOptionType.CHANNEL,
                               required=False
                           )
                       ])
    async def move(self, ctx, vc=None):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.players:
            try:
                player = self.players[server_id]
                if vc is None:
                    await player.move_to(ctx.author.voice.channel)
                else:
                    await player.move_to(vc)
                embed = Embed(title=f"Ok", color=Colour.green())
            except:
                embed = Embed(title=f"Can't move in this channel", color=Colour.red())
        else:
            embed = Embed(title=f"Player not initialized", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='pop', description='Delete specific song/playlist from queue by index',
                       options=[
                           create_option(
                               name="idx",
                               description="ID of the song/playlist from the queue",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=True
                           )
                       ])
    async def pop(self, ctx, idx):
        server_id = ctx.guild.id
        if server_id in self.queues:
            queue = self.queues[server_id]
            if idx >= 0 or idx < len(queue):
                item = queue[idx]
                del queue[idx]
                if isinstance(item, wavelink.tracks.YouTubePlaylist):
                    embed = Embed(title=f"Playlist: '**{item.name}**' was deleted", color=Colour.blurple())
                else:
                    embed = Embed(title=f"Song: '**{item.title}**' was deleted", color=Colour.blurple())
            else:
                embed = Embed(title="Wrong index given", color=Colour.red())
        else:
            embed = Embed(title="Player not initialized", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            if server_id in self.loops:
                self.loops.remove(server_id)
            await self.players[server_id].stop()
            embed = Embed(title="Current track skipped", color=Colour.gold())
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='pause', description='Pause/resume current song')
    async def pause(self, ctx):
        await ctx.defer()
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

    @cog_ext.cog_slash(name='stfu', description='Stop current song and clear song queue')
    async def disconnect(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.players:
            self.queues[server_id].clear()
            if server_id in self.loops:
                self.loops.remove(server_id)
            await self.players[server_id].stop()
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="I've been quiet enough", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    def build_queue_embed(self, server_id):
        if server_id not in self.queues or len(self.queues[server_id]) == 0:
            text = "*Empty*"
        else:
            text = ""
            for i, item in enumerate(self.queues[server_id]):
                if isinstance(item, wavelink.tracks.YouTubePlaylist):
                    text += f"*{i}*. Playlist '**{item.name}**'\n"
                    j = 0
                    while j + item.selected_track < len(item.tracks) and j < 3:
                        idx = item.selected_track + j
                        track = item.tracks[idx]
                        text += f"--->{i}.{idx}. [**{track.title}**]({track.uri}), length: {int(track.length)} sec.\n"
                        j += 1
                    if j + item.selected_track < len(item.tracks):
                        text += "...\n"
                else:
                    text += f"*{i}*. [**{item.title}**]({item.uri}), length: {int(item.length)} sec.\n"
                text += '\n'
        return Embed(title="Queue:", description=text, color=Colour.blurple())

    @cog_ext.cog_slash(name='queue', description='Show current song queue')
    async def queue(self, ctx):
        await ctx.defer()
        await ctx.send(embed=self.build_queue_embed(ctx.guild.id), delete_after=30.0)

    @cog_ext.cog_slash(name='seek', description='Move timeline to specific time in seconds',
                       options=[
                           create_option(
                               name="time",
                               description="Time to seek in seconds",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=True
                           )
                       ])
    async def seek(self, ctx, time):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            await self.players[server_id].seek(1000 * time)
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="Nothing to move", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='volume', description='Change volume to specific value',
                       options=[
                           create_option(
                               name="value",
                               description="Volume value",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=True
                           )
                       ])
    async def volume(self, ctx, value):
        await ctx.defer()
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

    @cog_ext.cog_slash(name='loop', description='Repeat song infinitely (disables on skip/stop)')
    async def loop(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
            if server_id in self.loops:
                self.loops.remove(server_id)
                embed = Embed(title="Replay disabled", color=Colour.blurple())
            else:
                self.loops.add(server_id)
                embed = Embed(title="On replay", color=Colour.blurple())
        else:
            embed = Embed(title="Nothing to loop", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        server_id = payload.guild_id
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except:
            return

        user = self.bot.get_user(payload.user_id)
        emojis = {':last_track_button:', ':reverse_button:', ':pause_button:', ':play_button:',
                  ':next_track_button:', ':red_square:', ':repeat_button:'}
        if not volume_lock:
            emojis.add(':muted_speaker:')
            emojis.add(':speaker_high_volume:')
        try:
            demojized = emoji.demojize(payload.emoji.name)
        except TypeError:
            return
        if server_id not in self.messages or self.messages[server_id].id != message.id:
            return
        if payload.user_id != self.bot.user.id:
            if demojized in emojis:
                try:
                    player = self.players[server_id]
                    if demojized == ':last_track_button:':
                        await player.seek(0)
                    elif demojized == ':reverse_button:':
                        cur = self.players[server_id].position
                        await player.seek(1000 * (cur - 30))
                    elif demojized == ':pause_button:':
                        if player.is_playing():
                            if player.is_paused():
                                await player.resume()
                            else:
                                await player.pause()
                    elif demojized == ':play_button:':
                        cur = self.players[server_id].position
                        await player.seek(1000 * (cur + 30))
                    elif demojized == ':next_track_button:':
                        if server_id in self.loops:
                            self.loops.remove(server_id)
                        await player.stop()
                    elif demojized == ':red_square:':
                        if server_id in self.loops:
                            self.loops.remove(server_id)
                        self.queues[server_id].clear()
                        await player.stop()
                    elif demojized == ':muted_speaker:':
                        await message.remove_reaction(emoji.emojize(':muted_speaker:'), self.bot.user)
                        await message.add_reaction(emoji.emojize(':speaker_high_volume:'))
                        await player.set_volume(0)
                    elif demojized == ':speaker_high_volume:':
                        await message.remove_reaction(emoji.emojize(':speaker_high_volume:'), self.bot.user)
                        await message.add_reaction(emoji.emojize(':muted_speaker:'))
                        await player.set_volume(100)
                    elif demojized == ':repeat_button:':
                        if server_id in self.loops:
                            self.loops.remove(server_id)
                        else:
                            self.loops.add(server_id)
                    await message.add_reaction(emoji.emojize(':thumbs_up:'))
                except:
                    await message.add_reaction(emoji.emojize(':thumbs_down:'))
            else:
                await message.add_reaction(emoji.emojize(':angry_face:'))
            await message.remove_reaction(payload.emoji, user)
        elif demojized not in emojis:
            await asyncio.sleep(2)
            try:
                await message.remove_reaction(payload.emoji, user)
            except discord.errors.NotFound:
                pass


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
