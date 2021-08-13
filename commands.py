import discord
import os, random
import Constants
from datetime import datetime

global client
start_time = datetime.now()
start_time.isoformat(sep='T')

def commands_init(clnt):
    client = clnt

    return {'$RenaStare': rena_stare,
            '$StartTime': send_start_time,
            '$Homoquote': homoquote,
            '$Help': help
            }


async def rena_stare(message):
    await message.channel.send(file=discord.File(Constants.GIF_DIRECTORY))


async def send_start_time(message):
    await message.channel.send('Bot working since ' + str(start_time.strftime('%b %d %Y %H:%M:%S')))


async def homoquote(message):
    random_file_name = random.choice(os.listdir(os.getcwd() + '/' + Constants.HOMOQUOTES_IMG_DIRECTORY))
    await message.channel.send(file=discord.File(Constants.HOMOQUOTES_IMG_DIRECTORY + '/' + random_file_name))


async def help(message):
    help_file = open('help.txt')
    await message.channel.send('User commands:\n' + help_file.read())
    help_file.close