import os, random
import discord
from discord.ext import commands
import Constants
import commands as cmd
from config import settings
from datetime import datetime

client = discord.Client()

start_time = datetime.now()
start_time.isoformat(sep='T')
history = { }

commands_dict = cmd.commands_init(client)

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    command = message.content.split(' ', maxsplit = 1)[0]
    if command in commands_dict:
        await commands_dict[command](message)

    #await check_cmd(message)
    await message_repeating(message)
    return

async def message_repeating(message):
    if message.channel.id in history:
        if history[message.channel.id]['text'] == message.content:
            history[message.channel.id]['count'] += 1
            if(history[message.channel.id]['count'] == Constants.MESSAGES_TO_REPEAT):
                await message.channel.send(history[message.channel.id]['text'])
                history[message.channel.id]['text'] = ''
                history[message.channel.id]['count'] = 0
        else:
            history[message.channel.id]['text'] = message.content
            history[message.channel.id]['count'] = 1
    else:
        history[message.channel.id] = {'text': message.content, 'count': 1}


async def check_cmd(message):
    if message.content.startswith('$Homoquote'):
        random_file_name = random.choice(os.listdir(os.getcwd() + Constants.HOMOQUOTES_IMG_DIRECTORY))
        await message.channel.send(file=discord.File(Constants.HOMOQUOTES_IMG_DIRECTORY + random_file_name))
    elif message.content.startswith('$StartTime'):
        await message.channel.send('Bot working since ' + str(start_time.strftime('%b %d %Y %H:%M:%S')))
    elif message.content.startswith('$RenaStare'):
        await message.channel.send(file=discord.File(Constants.GIF_DIRECTORY))
    elif message.content.startswith('$Help'):
        help_file = open('help.txt')
        await message.channel.send('User commands:\n' + help_file.read())
        help_file.close

client.run(settings['token'])