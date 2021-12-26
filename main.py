import discord
import constants
import os, random
from modules.message_analysis import Analysis_module
from discord.ext import commands
from config import settings
from datetime import datetime
import yt_dlp
import sys

client = commands.Bot(command_prefix=settings['prefix'], case_insensitive=True, help_command=None)
analyzer = Analysis_module(client)
start_time = datetime.now()
start_time.isoformat(sep='T')
history = { }
very_clever_quotes = []

with open('clever_quotes.txt', encoding='utf-8') as file:
        very_clever_quotes = file.read().split(";")

@client.event
async def on_message(ctx):
    if ctx.author.id == client.user.id:
        return

    await random_vot_da(ctx)
    await message_repeating(ctx)
    analyzer.save_message(ctx)

    await client.process_commands(ctx)


ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}   

def endSong(guild, path):
    os.remove(path)


@client.command(name='disconnect', pass_ctx=True)
async def disconnect(ctx):
    vc = ctx.message.guild.voice_client
    await vc.disconnect()


@client.command(pass_context=True)
async def play(ctx, url):
    if not ctx.message.author.voice:
        await ctx.send('you are not connected to a voice channel')
        return

    else:
        channel = ctx.message.author.voice.channel

    voice = discord.utils.get(client.voice_clients, guild=ctx.guild)

    if voice is None:
        voice_client = await channel.connect()

    guild = ctx.message.guild

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        file = ydl.extract_info(url, download=True)
        path = str(file['title']) + " [" + str(file['id'] + "].mp3")

    voice_client.play(discord.FFmpegPCMAudio(path), after=lambda x: endSong(guild, path))
    voice_client.source = discord.PCMVolumeTransformer(voice_client.source, 1)

    await ctx.send(f'**Music: **{url}')

    #while voice_client.is_playing():
    #    await asyncio.sleep(1)
    #else:
    #    await voice_client.disconnect()
    #    print("Disconnected")


@client.command(name='RenaStare')
async def rena_stare(ctx):
    await ctx.channel.send(file=discord.File(constants.GIF_DIRECTORY))


@client.command(name='StartTime')
async def send_start_time(ctx):
    await ctx.channel.send('Bot working since ' + str(start_time.strftime('%b %d %Y %H:%M:%S') + ' UTC+03:00'))


@client.command(name='HomoQuote')
async def homoquote(ctx):
    random_file_name = random.choice(os.listdir(os.getcwd() + '/' + constants.HOMOQUOTES_IMG_DIRECTORY))
    await ctx.channel.send(file=discord.File(constants.HOMOQUOTES_IMG_DIRECTORY + '/' + random_file_name))


@client.command()
async def help(ctx):
    with open('help.txt') as help_file:
        await ctx.channel.send('User commands:\n' + help_file.read())


@client.command(name='Top')
async def top(ctx):
        await analyzer.get_top(ctx)


@client.command(name='Voice')
async def top(ctx):
        await analyzer.get_voice_activity(ctx)


async def random_vot_da(ctx):
    if ctx.author.id == client.user.id:
        return
    if random.random() < 0.01:
        await ctx.channel.send('вот да')
    elif random.random() < 0.005:
        await ctx.channel.send(random.choice(very_clever_quotes))


async def message_repeating(ctx):
    if ctx.channel.id in history and ctx.content != '':
        if history[ctx.channel.id]['text'] == ctx.content:
            history[ctx.channel.id]['count'] += 1
            if(history[ctx.channel.id]['count'] == constants.MESSAGES_TO_REPEAT):
                await ctx.channel.send(history[ctx.channel.id]['text'])
                history[ctx.channel.id]['text'] = ''
                history[ctx.channel.id]['count'] = 0
        else:
            history[ctx.channel.id]['text'] = ctx.content
            history[ctx.channel.id]['count'] = 1
    else:
        history[ctx.channel.id] = {'text': ctx.content, 'count': 1}

client.run(settings['token'], bot = True)
