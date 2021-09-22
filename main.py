import discord
import constants
import modules.commands as cmd
from modules.message_analysis import Analysis_module
from config import settings

client = discord.Client()
analyzer = Analysis_module(client)
commands_module = cmd.Commands_module(analyzer)
history = { }


@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    await commands_module.execute_command(message)
    await message_repeating(message)
    analyzer.save_message(message)

    return


async def message_repeating(message):
    if message.channel.id in history and not message.content == '':
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

client.run(settings['token'])