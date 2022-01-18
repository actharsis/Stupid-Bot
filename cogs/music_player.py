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


def time_to_str(time):
    return str(time // 60) + ' min ' + str(time % 60) + ' secs'


def get_song_path(song):
    return str(song['title']) + " [" + str(song['id'] + "].mp3")


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guilds = {}
        self.voice_clients = {}

    async def join_vc(self, server_id, channel):
        if server_id not in self.voice_clients.keys():
            self.voice_clients[server_id] = await channel.connect()
        elif self.voice_clients[server_id].channel != channel:
            await self.voice_clients[server_id].disconnect()
            self.voice_clients.pop(server_id)
            self.voice_clients[server_id] = await channel.connect()

    async def is_ready(self, server_id):
        if server_id not in self.voice_clients.keys() \
                or not self.voice_clients[server_id].is_playing() and len(self.guilds[server_id]) > 0:
            await self.join_vc(server_id, self.guilds[server_id][0]['channel'])
            return True
        if len(self.guilds[server_id]) == 0 and server_id in self.voice_clients.keys():
            await self.voice_clients[server_id].disconnect()
            self.voice_clients.pop(server_id)
        return False

    async def play(self, server_id):
        if not await self.is_ready(server_id):
            return

        item = self.guilds[server_id].pop(0)
        song = item['song']
        ctx = item['ctx']

        await ctx.send(embed=Embed(title="Currently playing: " + song['title'],
                                   description='Duration: ' + time_to_str(song['duration']),
                                   color=Colour.dark_red()),
                       delete_after=int(song['duration']))

        options = ydl_opts
        path = 'temp/' + str(server_id) + '.mp3'
        options['outtmpl'] = path
        if os.path.isfile(path):
            os.remove(path)
        yt_dlp.YoutubeDL(options).extract_info(song['url'], download=True)

        self.voice_clients[server_id].play(discord.FFmpegPCMAudio(path))
        self.voice_clients[server_id].source = \
            discord.PCMVolumeTransformer(self.voice_clients[server_id].source, 1)

        while self.voice_clients[server_id].is_playing() or self.voice_clients[server_id].is_paused():
            await asyncio.sleep(1)
        await self.play(server_id)

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
            server_id = ctx.guild.id
            song = yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
            channel = ctx.author.voice.channel
            await ctx.send(embed=Embed(title="Song '" + song['title'] + "' added to queue", color=Colour.green()),
                           delete_after=5.0)
            if server_id not in self.guilds.keys():
                self.guilds[server_id] = []
            self.guilds[server_id].append({
                'song': {'title': song['title'], 'id': song['id'], 'duration': song['duration'], 'url': url},
                'channel': channel,
                'ctx': ctx
            })
            await self.play(server_id)
        except:
            await ctx.send(embed=Embed(title="YT DL error", color=Colour.red()), delete_after=5.0)

    @cog_ext.cog_slash(name='queue', description='Show current song queue')
    async def show_queue(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        text = ""
        for i, item in enumerate(self.guilds[server_id]):
            text += str(i) + '. ' + item['song']['title'] + '\n'
        if len(self.guilds[server_id]) == 0:
            text = "Empty"
        await ctx.send(embed=Embed(title="Queue:", description=text, color=Colour.blurple()),
                       delete_after=30.0)

    @cog_ext.cog_slash(name='clear', description='Clear song queue')
    async def clear_queue(self, ctx):
        server_id = ctx.guild.id
        self.guilds[server_id].clear()
        await ctx.send(embed=Embed(title="Queue cleared", color=Colour.blurple()),
                       delete_after=5.0)

    @cog_ext.cog_slash(name='stfu', description='Stop current song and clear song queue')
    async def disconnect(self, ctx):
        server_id = ctx.guild.id
        if server_id in self.voice_clients.keys():
            self.guilds[server_id].clear()
            self.voice_clients[server_id].stop()
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
        server_id = ctx.guild.id
        if idx >= 0 or idx < len(self.guilds[server_id]):
            title = self.guilds[server_id].pop(idx)['song']['title']
            embed = Embed(title="Song: " + title + " was deleted", color=Colour.blurple())
        else:
            embed = Embed(title="Wrong index given", color=Colour.red())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='skip', description='Skip current song')
    async def skip(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.voice_clients.keys():
            self.voice_clients[server_id].stop()
            embed = Embed(title="Current track skipped", color=Colour.gold())
        else:
            embed = Embed(title="Nothing playing at this moment", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='pause', description='Pause current song')
    async def pause(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.voice_clients.keys() and self.voice_clients[server_id].is_playing():
            self.voice_clients[server_id].pause()
            embed = Embed(title="Song paused", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to pause", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)

    @cog_ext.cog_slash(name='resume', description='Resume current song')
    async def resume(self, ctx):
        await ctx.defer()
        server_id = ctx.guild.id
        if server_id in self.voice_clients.keys() and self.voice_clients[server_id].is_paused():
            self.voice_clients[server_id].resume()
            embed = Embed(title="Playing again", color=Colour.gold())
        else:
            embed = Embed(title="Nothing to resume", color=Colour.gold())
        await ctx.send(embed=embed, delete_after=5.0)


def setup(bot):
    bot.add_cog(MusicPlayerCog(bot))
