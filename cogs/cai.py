import contextlib
import json
import re

import nextcord

from config import CHARACTERAI_TOKEN, CAI_NO_MESSAGE_EDIT
from modules.cai_wrapper import CharacterAI
from nextcord import Embed, Message, MessageType, slash_command, SlashOption
from nextcord.colour import Colour
from nextcord.ext import commands

DEFAULT_CHAR_ID = '2g4E4hPoSdUtcDpLUaGT3pEaEpUlubWdUadJbSlqdi0'


class CharacterAICog(commands.Cog, name="CharacterAI"):
    """
    **CharacterAI cog** - makes me more 'Cirno' like (Powered by CharacterAI with @Evidential character).
    Ping me if you want to talk with me :)

    ***Available commands***:
    **/flush** - don't even dare to use that!! Please... I don't want to forget what happened :(
    **/relog** - re-authenticate in case I'm not responding
    **/set_char** - give a character id to change character (Cirno if no argument given)
    """

    def __init__(self, bot):
        self.bot = bot
        self.cai_data = {}
        self.chats = {}
        self.webhooks = {}
        self.cai = None
        self.bot.loop.create_task(self.auth())
        self.load()

    async def auth(self):
        self.cai = CharacterAI(CHARACTERAI_TOKEN)
        await self.cai.start()

    def save(self):
        with open('json/cai_data.json', 'w') as file:
            file.write(json.dumps(self.cai_data))

    def load(self):
        with contextlib.suppress(json.JSONDecodeError, TypeError, FileNotFoundError):
            with open('json/cai_data.json', 'r') as file:
                self.cai_data = json.load(file)

    async def call_create_new_chat(self, ctx, character_id):
        chat = await self.cai.create_new_chat(character_id)
        await ctx.channel.send(f'New chat created\nChar_id: {chat.character_id}\nHistory_id: {chat.external_id}')
        return chat

    async def get_chat_and_webhook(self, ctx):
        server_id = str(ctx.guild.id)
        if server_id not in self.cai_data:
            self.cai_data[server_id] = {}
        data = self.cai_data[server_id]

        if server_id in self.chats:
            chat = self.chats[server_id]
        elif data.get('chat') is not None:
            chat = await self.cai.continue_chat(data['chat']['char_id'], data['chat']['hist_id'])
        else:
            chat = await self.call_create_new_chat(ctx, DEFAULT_CHAR_ID)

        webhook = None
        if server_id in self.webhooks:
            webhook = self.webhooks[server_id]
        elif data.get('webhook') is not None:
            webhook = await self.bot.fetch_webhook(int(data['webhook']))
        if webhook is None:
            webhook = await ctx.channel.create_webhook(name='CAI webhook')

        if webhook.channel != ctx.channel:
            webhook = await webhook.edit(channel=ctx.channel)

        self.chats[server_id] = chat
        self.webhooks[server_id] = webhook
        self.cai_data[server_id] = {'webhook': str(webhook.id),
                                    'chat': {'char_id': chat.character_id, 'hist_id': chat.external_id}}
        self.save()

        return chat, webhook

    @commands.Cog.listener()
    async def on_message(self, ctx: nextcord.Message):
        server_id = str(ctx.guild.id)
        if self.bot.user.mentioned_in(ctx) and \
                not ctx.mention_everyone or \
                ctx.type == MessageType.reply and \
                server_id in self.chats and \
                ctx.reference.resolved.author.bot and \
                ctx.reference.resolved.author.name == self.chats[server_id].character_data['name'] and \
                ctx.reference.resolved.author.discriminator == '0000':
            await ctx.channel.trigger_typing()

            chat, webhook = await self.get_chat_and_webhook(ctx)

            text = ctx.clean_content
            bot = ctx.guild.get_member(self.bot.user.id)
            ping = f'@{bot.nick if bot.nick else bot.name}'
            cai_name = chat.character_data.get('name')
            if cai_name is None:
                cai_name = 'Cirno'
            if text.startswith(ping):
                text = text[len(ping):]
            else:
                text = text.replace(ping, cai_name)
            text = text.strip()
            if len(text) == 0:
                text = cai_name

            message = None
            user = ctx.author.nick if ctx.author.nick else ctx.author.name

            async for answer, cai_name, cai_avatar, final in chat.send_message(text):
                if CAI_NO_MESSAGE_EDIT and not final:
                    continue
                answer = re.sub(self.cai.user, user, answer, flags=re.IGNORECASE)
                if message is None:
                    message = await webhook.send(answer, username=cai_name, avatar_url=cai_avatar, wait=True)
                else:
                    await message.edit(content=answer)
                # if not final:
                #     await ctx.channel.trigger_typing()

    # @slash_command(name='relog')
    # async def relog(self, ctx):
    #     await self.cai.authenticate(CHARACTERAI_TOKEN)
    #     embed = Embed(title="CAI:", description="Auth called", color=Colour.blurple())
    #     await ctx.send(embed=embed, delete_after=5)

    async def update_chat(self, ctx, character_id=None, history_id=None):
        server_id = str(ctx.guild.id)
        if server_id not in self.cai_data:
            self.cai_data[server_id] = {}

        if character_id is None:
            chat = await self.call_create_new_chat(ctx, DEFAULT_CHAR_ID)
        else:
            if history_id is None:
                chat = await self.call_create_new_chat(ctx, character_id)
            else:
                chat = await self.cai.continue_chat(character_id, history_id)

        self.cai_data[server_id]['chat'] = {'char_id': chat.character_id, 'hist_id': chat.external_id}
        self.chats[server_id] = chat
        self.save()

    @slash_command(name='flush_char')
    async def flush_char(self, ctx):
        embed = Embed(title="CAI:", description="Flush called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)
        await self.update_chat(ctx)

    @slash_command(name='set_char')
    async def set_char(self,
                       ctx,
                       character_id: str = SlashOption(
                           description="Character ID to use (Cirno ID by default)",
                           required=False,
                           default="2g4E4hPoSdUtcDpLUaGT3pEaEpUlubWdUadJbSlqdi0")):
        embed = Embed(title="CAI:", description="Request called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)
        await self.update_chat(ctx, character_id)

    @slash_command(name='load_char')
    async def load_char(self,
                        ctx,
                        character_id: str = SlashOption(description="Character ID"),
                        history_id: str = SlashOption(description="History ID")):
        embed = Embed(title="CAI:", description="Request called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)
        await self.update_chat(ctx, character_id, history_id)


def setup(bot):
    bot.add_cog(CharacterAICog(bot))
