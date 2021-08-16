import discord
import constants
import commands as cmd
from modules.message_analysis import Analysis_module
from config import settings

client = discord.Client()
commands_dict = cmd.commands_init(client)
analyzer = Analysis_module()
history = { }


@client.event
async def on_message(message):
    if message.author.id == client.user.id:
        return

    command = message.content.split(' ', maxsplit = 1)[0]
    if command in commands_dict:
        await commands_dict[command](message)
        
    await message_repeating(message)
    analyzer.save_message(message)

    return


async def message_repeating(message):
    if message.channel.id in history:
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