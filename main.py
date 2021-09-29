import discord
import constants
import os, random
from modules.message_analysis import Analysis_module
from discord.ext import commands
from config import settings
from datetime import datetime

client = commands.Bot(command_prefix=settings['prefix'], case_insensitive=True)
analyzer = Analysis_module(client)
start_time = datetime.now()
start_time.isoformat(sep='T')
history = { }

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    await message_repeating(message)
    analyzer.save_message(message)

    await client.process_commands(message)


@client.command(name='RenaStare')
async def rena_stare(message):
    await message.channel.send(file=discord.File(constants.GIF_DIRECTORY))


@client.command(name='StartTime')
async def send_start_time(message):
    await message.channel.send('Bot working since ' + str(start_time.strftime('%b %d %Y %H:%M:%S'), 'UTC+03:00'))


@client.command(name='HomoQuote')
async def homoquote(message):
    random_file_name = random.choice(os.listdir(os.getcwd() + '/' + constants.HOMOQUOTES_IMG_DIRECTORY))
    await message.channel.send(file=discord.File(constants.HOMOQUOTES_IMG_DIRECTORY + '/' + random_file_name))


@client.command(name='Commands')
async def help(message):
    with open('help.txt') as help_file:
        await message.channel.send('User commands:\n' + help_file.read())


@client.command(name='Top')
async def top(message):
        await analyzer.get_top(message)


async def message_repeating(message):
    if message.channel.id in history and message.content != '':
        if history[message.channel.id]['text'] == message.content:
            history[message.channel.id]['count'] += 1
            if(history[message.channel.id]['count'] == constants.MESSAGES_TO_REPEAT):
                await message.channel.send(history[message.channel.id]['text'])
                history[message.channel.id]['text'] = ''
                history[message.channel.id]['count'] = 0
        else:
            history[message.channel.id]['text'] = message.content
            history[message.channel.id]['count'] = 1
    else:
        history[message.channel.id] = {'text': message.content, 'count': 1}

client.run(settings['token'], bot = True)
