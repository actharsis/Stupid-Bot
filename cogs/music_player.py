import math

import wavelink
import asyncio
import emoji
import discord

from discord import Embed
from discord.colour import Colour
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option
from wavelink import Track, Node, player
from config import volume_lock


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


def player_embed(player):
    track = player.track
    embed = Embed(title="🎧 Currently playing:",
                  description=f"[**{track.title}**]({track.uri})\n"
                              f"**Length**: *{time_to_str(track.length)}*; **Volume**: *{int(player.volume)}*\n"
                              f"**{' ' * 40}Timeline**: *{short_time(player.position)}/{short_time(track.length)}*\n"
                              f"```{render_bar(36, player.position, track.length)}```",
                  color=Colour.red())
    embed.set_image(url=f'https://img.youtube.com/vi/{track.uri[32:]}/mqdefault.jpg')
    return embed


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.connect_nodes())
        self.players = {}
        self.queues = {}
        self.server_ctx = {}
        self.messages = {}

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=2333,
                                            password='youwillpass')

    async def soft_leave_vc(self, player: player):
        await asyncio.sleep(20)
        if self.queues[player.guild.id].is_empty and not self.players[player.guild.id].is_playing():
            await player.disconnect()

    async def soft_message_delete(self, server_id):
        await asyncio.sleep(20)
        if server_id in self.queues and self.queues[server_id].is_empty and not self.players[server_id].is_playing():
            await self.messages[server_id].delete()
            self.messages.pop(server_id)

    async def message_auto_update(self, server_id):
        while server_id in self.messages:
            try:
                await self.messages[server_id].edit(embed=player_embed(self.players[server_id]))
            except AttributeError:
                return
            await asyncio.sleep(3)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: Node):
        print(f"Connected to lavalink!")

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
                  ':next_track_button:', ':red_square:'}
        if not volume_lock:
            emojis.add(':muted_speaker:')
            emojis.add(':speaker_high_volume:')
        try:
            demojized = emoji.demojize(payload.emoji.name)
        except TypeError:
            return
        if self.messages[server_id].id != message.id:
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
                        await player.stop()
                    elif demojized == ':red_square:':
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

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: player, track: Track):
        server_id = player.guild.id
        if server_id in self.server_ctx:
            ctx = self.server_ctx[server_id]
            if server_id not in self.messages:
                msg = await ctx.send(embed=player_embed(player))
                self.messages[server_id] = msg
                self.bot.loop.create_task(self.message_auto_update(server_id))
                emojis = [':last_track_button:', ':reverse_button:', ':pause_button:', ':play_button:',
                          ':next_track_button:', ':red_square:']
                if not volume_lock:
                    emojis.append(':muted_speaker:')
                for e in emojis:
                    await msg.add_reaction(emoji.emojize(e))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: player, track: Track, reason):
        server_id = player.guild.id
        if self.queues[server_id].is_empty:
            await self.soft_message_delete(server_id)
            await self.soft_leave_vc(player)
        await self.play_next(player, server_id)

    async def play_next(self, player: player, server_id):
        queue = self.queues[server_id]
        if not queue.is_empty:
            track = queue.pop()
            await player.play(track)

    def update_server_ctx(self, ctx):
        server_id = ctx.guild.id
        self.server_ctx[server_id] = ctx

    @cog_ext.cog_slash(name='play', description='Play a song from Youtube',
                       options=[
                           create_option(
                               name="track",
                               description="Track name",
                               option_type=SlashCommandOptionType.STRING,
                               required=True
                           )
                       ])
    async def play(self, ctx, track):
        await ctx.defer()
        self.update_server_ctx(ctx)
        server_id = ctx.guild.id
        channel = ctx.author.voice.channel
        if server_id not in self.players or not self.players[server_id].is_connected():
            self.players[server_id] = await channel.connect(cls=wavelink.Player)
        if server_id not in self.queues:
            self.queues[server_id] = wavelink.Queue()
        player = self.players[server_id]
        queue = self.queues[server_id]
        track = await wavelink.YouTubeTrack.search(query=track, return_first=True)

        if player.is_playing():
            queue.put(track)
            await ctx.send(embed=Embed(title="Song '" + track.title + "' added to queue", color=Colour.green()),
                           delete_after=10.0)
            return
        else:
            if server_id in self.messages:
                await self.messages[server_id].delete()
                self.messages.pop(server_id)
            await player.play(track)

    @cog_ext.cog_slash(name='pop_song', description='Delete specific song from queue by index',
                       options=[
                           create_option(
                               name="idx",
                               description="ID of the song from the queue",
                               option_type=SlashCommandOptionType.INTEGER,
                               required=True
                           )
                       ])
    async def pop_song(self, ctx, idx):
        server_id = ctx.guild.id
        queue = self.queues[server_id]
        if idx >= 0 or idx < len(queue):
            title = queue.pop(idx)
            embed = Embed(title="Song: " + title + " was deleted", color=Colour.blurple())
        else:
            embed = Embed(title="Wrong index given", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.players and self.players[server_id].is_playing():
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
            await self.players[server_id].stop()
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="I've been quiet enough", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=10.0)

    @cog_ext.cog_slash(name='queue', description='Show current song queue')
    async def queue(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        text = ""
        for i, item in enumerate(self.queues[server_id]):
            text += f"*{i}*. [**{item.title}**]({item.uri}), length: {int(item.length)} sec.\n"
        if server_id not in self.queues or len(self.queues[server_id]) == 0:
            text = "*Empty*"
        await ctx.send(embed=Embed(title="Queue:", description=text, color=Colour.blurple()),
                       delete_after=30.0)

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


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
