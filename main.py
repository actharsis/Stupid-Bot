import constants
import discord
import os, random
from modules.message_analysis import Analysis_module
from discord.ext import commands
from config import settings
from config import ydl_opts
from datetime import datetime
import yt_dlp
import asyncio

# misc init
start_time = datetime.now()
start_time.isoformat(sep='T')
true_random = random.SystemRandom()
history = { }

very_clever_quotes = []
with open(constants.CLEVER_QUOTES_DIR, encoding='utf-8') as file:
        very_clever_quotes = file.read().split(";")

replies = None
with open('replies.txt', encoding="utf-8") as f:
    lines = f.read().splitlines()
if len(lines) > 0:
    pairs = [l.split('//')[0].split('->') for l in lines]
    for p in pairs:
        p[1] = p[1].split(";")
    replies = {int(p[0]):p[1] for p in pairs}

# functions
def endSong(guild, path):
    os.remove(path)


def get_special_replies(author_id):
    if author_id in replies:
        return replies[author_id]
    else:
        return []


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

async def reference_reaction(ctx):
    if ctx.reference and ctx.reference.resolved.author.id == client.user.id and ctx.author.id != client.user.id:

        if replies:
            special_replies = get_special_replies(ctx.author.id)
            if special_replies:
                special_reply = true_random.choice(special_replies)
                reply = f"{ctx.author.mention}, {special_reply}"
            else:
                reply = ctx.channel.send(f"{ctx.author.mention}, вы кто?")
        await ctx.channel.send(reply)

# client init
client = commands.Bot(command_prefix=settings['prefix'], case_insensitive=True, help_command=None)
analyzer = Analysis_module(client)

# commands
@client.event
async def on_message(ctx):
    if ctx.author.id == client.user.id:
        return

    await random_vot_da(ctx)
    await message_repeating(ctx)
    await reference_reaction(ctx)
    analyzer.save_message(ctx)

    await client.process_commands(ctx)


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

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        file = ydl.extract_info(url, download=True)
        path = str(file['title']) + " [" + str(file['id'] + "].mp3")

    voice_client.play(discord.FFmpegPCMAudio(path), after=lambda x: endSong(ctx.message.guild, path))
    voice_client.source = discord.PCMVolumeTransformer(voice_client.source, 1)

    await ctx.send(f'**Music: **{url}')

    while voice_client.is_playing():
        await asyncio.sleep(1)
    else:
        await voice_client.disconnect()
        print("Disconnected")


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


# exec
client.run(settings['token'], bot = True)