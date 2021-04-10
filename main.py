import os, random
import discord
from discord.ext import commands
from config import settings
from datetime import datetime

client = discord.Client()

start_time = datetime.now()
start_time.isoformat(sep='T')
memory = ''
count = 0
cache_users = []

@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    await check_cmd(message)
    await message_repeating(message)
    return

async def message_repeating(message):
    global count
    global memory
    if count == 0:
        cache_users.append(message.author.id)
        memory = message.content
        count += 1
    elif message.content == memory:
        if count == 2:
            await message.channel.send(memory)
            memory = ""
        elif not message.author.id in cache_users:
            cache_users.append(message.author.id)
            count += 1
    else:
        memory = ""
        memory = message.content
        count = 0

async def check_cmd(message):
    if message.content.startswith("$Homoquote"):
        random_file_name = random.choice(os.listdir(os.getcwd() + "/img/homoquotes"))
        await message.channel.send(file=discord.File("img/homoquotes/" + random_file_name))
    elif message.content.startswith("$StartTime"):
        await message.channel.send('Bot working since ' + str(start_time.strftime("%b %d %Y %H:%M:%S")))
    elif message.content.startswith("$RenaStare"):
        await message.channel.send(file=discord.File("content/post_this_rena.gif"))
    elif message.content.startswith("$Help"):
        help_file = open('help.txt')
        await message.channel.send("User commands:\n" + help_file.read())
        help_file.close

client.run(settings['token'])