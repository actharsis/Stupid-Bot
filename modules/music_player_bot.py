import asyncio
import discord
import os
import yt_dlp

from config import ydl_opts
from discord import Embed
from discord.colour import Colour
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType
from discord_slash.utils.manage_commands import create_option


def delete_song(path):
    os.remove(path)


def time_to_str(time):
    return str(time // 60) + ' min ' + str(time % 60) + ' secs'


def get_song_path(song):
    return str(song['title']) + " [" + str(song['id'] + "].mp3")


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.voice = None
        self.voice_client = None

    async def join_vc(self, channel):
        if self.voice_client is None:
            self.voice_client = await channel.connect()
        elif self.voice_client.channel != channel:
            self.voice_client = await self.voice_client.disconnect()
            self.voice_client = await channel.connect()

    async def is_ready(self):
        if self.voice_client is None or not self.voice_client.is_playing() and len(self.queue) > 0:
            await self.join_vc(self.queue[0]['channel'])
            return True
        if len(self.queue) == 0 and self.voice_client is not None:
            self.voice_client = await self.voice_client.disconnect()
        return False

    async def play(self):
        if not await self.is_ready():
            return

        item = self.queue.pop(0)
        song = item['song']
        ctx = item['ctx']

        await ctx.send(embed=Embed(title="Currently playing: " + song['title'],
                                   description='Duration: ' + time_to_str(song['duration']),
                                   color=Colour.dark_red()),
                       delete_after=int(song['duration']))

        path = get_song_path(song)
        if not os.path.isfile(path):
            yt_dlp.YoutubeDL(ydl_opts).extract_info(song['url'], download=True)

        self.voice_client.play(discord.FFmpegPCMAudio(get_song_path(song)))
        self.voice_client.source = discord.PCMVolumeTransformer(self.voice_client.source, 1)

        while self.voice_client.is_playing() or self.voice_client.is_paused():
            await asyncio.sleep(1)
        await self.play()

    @cog_ext.cog_slash(name='play', description='Play a song from Youtube URL',
                       options=[
                           create_option(
                               name="url",
                               description="URL of the song",
                               option_type=SlashCommandOptionType.STRING,
                               required=True
                           )
                       ])
    async def add_song(self, ctx, url):
        await ctx.defer()
        if not ctx.author.voice:
            await ctx.send('you are not connected to a voice channel')
            return
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                song = ydl.extract_info(url, download=False)
                if not os.path.isfile(get_song_path(song)):
                    ydl.extract_info(url, download=True)
            channel = ctx.author.voice.channel
            await ctx.send(embed=Embed(title="Song '" + song['title'] + "' added to queue", color=Colour.green()),
                           delete_after=5.0)
            self.queue.append({
                'song': {'title': song['title'], 'id': song['id'], 'duration': song['duration'], 'url': song['url']},
                'channel': channel,
                'ctx': ctx
            })
            await self.play()
        except:
            await ctx.send(embed=Embed(title="YT DL error", color=Colour.red()), delete_after=5.0)

    @cog_ext.cog_slash(name='queue', description='Show current song queue')
    async def show_queue(self, ctx):
        await ctx.defer()
        text = ""
        for i, item in enumerate(self.queue):
            text += str(i) + '. ' + item['song']['title'] + '\n'
        if len(self.queue) == 0:
            text = "Empty"
        await ctx.send(embed=Embed(title="Queue:", description=text, color=Colour.blurple()),
                       delete_after=30.0)

    @cog_ext.cog_slash(name='clear', description='Clear song queue')
    async def show_queue(self, ctx):
        self.queue.clear()
        await ctx.send(embed=Embed(title="Queue cleared", color=Colour.blurple()),
                       delete_after=5.0)

    @cog_ext.cog_slash(name='stfu', description='Stop current song and clear song queue')
    async def show_queue(self, ctx):
        if self.voice_client is not None:
            self.queue.clear()
            self.voice_client.stop()
            embed = Embed(title="Ok", color=Colour.blurple())
        else:
            embed = Embed(title="I've been quiet enough", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5.0)

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
        if idx < 0 or idx > len(self.queue):
            title = self.queue.pop(idx)['song']['title']
            embed = Embed(title="Song with name: " + title + " was deleted", color=Colour.blurple())
        else:
            embed = Embed(title="Wrong index given", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.defer()
        if self.voice_client is not None:
            self.voice_client.stop()
            embed = Embed(title="Current track skipped", color=Colour.gold())
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='pause', description='Pause current song')
    async def pause(self, ctx):
        await ctx.defer()
        if self.voice_client is not None and self.voice_client.is_playing():
            self.voice_client.pause()
            embed = Embed(title="Song paused", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to pause", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='resume', description='Resume current song')
    async def resume(self, ctx):
        await ctx.defer()
        if self.voice_client is not None and self.voice_client.is_paused():
            self.voice_client.resume()
            embed = Embed(title="Playing again", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to resume", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
