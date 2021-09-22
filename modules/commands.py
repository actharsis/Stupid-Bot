from modules.message_analysis import Analysis_module
import discord
import os, random
import constants
from datetime import datetime

class Commands_module:
    global analysis_module
    global commands_dict
    start_time = datetime.now()
    start_time.isoformat(sep='T')

    def __init__(self, analyzer):
        self.analysis_module = analyzer

        self.commands_dict = {'$renastare': self.rena_stare,
                '$startTime': self.send_start_time,
                '$homoquote': self.homoquote,
                '$help': self.help,
                '$top': self.top
                }


    async def execute_command(self, message):
        command = message.content.split(' ', maxsplit = 1)[0].lower()
        if command in self.commands_dict:
            await self.commands_dict[command](message)


    async def rena_stare(self, message):
        await message.channel.send(file=discord.File(constants.GIF_DIRECTORY))


    async def send_start_time(self, message):
        await message.channel.send('Bot working since ' + str(self.start_time.strftime('%b %d %Y %H:%M:%S')))


    async def homoquote(self, message):
        random_file_name = random.choice(os.listdir(os.getcwd() + '/' + constants.HOMOQUOTES_IMG_DIRECTORY))
        await message.channel.send(file=discord.File(constants.HOMOQUOTES_IMG_DIRECTORY + '/' + random_file_name))


    async def help(self, message):
        help_file = open('help.txt')
        await message.channel.send('User commands:\n' + help_file.read())
        help_file.close


    async def top(self, message):
        await self.analysis_module.get_top(message)
        print('hello')