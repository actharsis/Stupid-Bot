import os, random
import discord
from discord.ext import commands
import Constants
import commands as cmd
from config import settings
from datetime import datetime

client = discord.Client()
history = { }

commands_dict = cmd.commands_init(client)

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    command = message.content.split(' ', maxsplit = 1)[0]
    if command in commands_dict:
        await commands_dict[command](message)

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

client.run(settings['token'])