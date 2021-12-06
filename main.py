import discord
import constants
import os, random
from modules.message_analysis import Analysis_module
from discord.ext import commands
from config import settings
from datetime import datetime

client = commands.Bot(command_prefix=settings['prefix'], case_insensitive=True, help_command=None)
analyzer = Analysis_module(client)
start_time = datetime.now()
start_time.isoformat(sep='T')
history = { }

@client.event
async def on_message(ctx):
    if ctx.author.id == client.user.id:
        return

    await message_repeating(ctx)
    analyzer.save_message(ctx)

    await client.process_commands(ctx)


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
