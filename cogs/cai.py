import asyncio
import contextlib
import json
import random

from config import CHARACTERAI_TOKEN
from modules.cai_wrapper import CharacterAI, AIChat
from nextcord import Embed, slash_command, SlashOption
from nextcord.colour import Colour
from nextcord.ext import commands


class CharacterAICog(commands.Cog, name="CharacterAI"):
    """
    **CharacterAI cog** - makes me more 'Cirno' like (Powered by CharacterAI with @Evidential character).
    Ping me if you want to talk with me :)

    ***Available commands***:
    **/flush** - don't even dare to use that!! Please... I don't want to forget what happened :(
    **/relog** - reauthenticate in case I'm not responding
    """

    def __init__(self, bot):
        self.cirno_id = '2g4E4hPoSdUtcDpLUaGT3pEaEpUlubWdUadJbSlqdi0'
        self.bot = bot
        # self.histories = {}
        self.cai = None
        self.chat = None
        self.bot.loop.create_task(self.auth())
        # self.load()

    async def auth(self):
        self.cai = CharacterAI()
        await self.cai.authenticate(CHARACTERAI_TOKEN)
        self.chat = await self.cai.continue_last_or_create_chat(
            self.cirno_id)  # TODO: should handle multiple chat instances

    # def save(self):
    #     with open('json/cai_histories.json', 'w') as file:
    #         file.write(json.dumps(self.histories))
    #
    # def load(self):
    #     with contextlib.suppress(json.JSONDecodeError, TypeError, FileNotFoundError):
    #         with open('json/cai_histories.json', 'r') as file:
    #             self.histories = json.load(file)

    @commands.Cog.listener()
    async def on_message(self, ctx):
        if not self.bot.user.mentioned_in(ctx):
            return
        await ctx.channel.trigger_typing()
        text = ctx.clean_content
        ping = f'@{self.bot.user.name}'
        if text.startswith(ping):
            text = text[len(ping):]
        else:
            text = text.replace(ping, 'Cirno')  # TODO: should be replaced with proper bot name
        text = text.strip()
        if len(text) == 0:
            text = 'Cirno'
        webhook = None
        message = None
        user = ctx.author.nick
        if user is None:
            user = ctx.author.name
        async for answer, cai_name, cai_avatar, final in self.chat.send_message(text):
            answer = answer.replace(self.cai.user, user)
            if webhook is None:
                webhook = await ctx.channel.create_webhook(name=cai_name)
                message = await webhook.send(answer, username=cai_name, avatar_url=cai_avatar, wait=True)
            else:
                await message.edit(content=answer)
            if not final:
                await ctx.channel.trigger_typing()
        webhooks = await ctx.channel.webhooks()
        for webhook in webhooks:
            await webhook.delete()

    @slash_command(name='flush')
    async def flush(self, ctx):
        await ctx.response.defer()
        # channel_id = str(ctx.guild.id)
        self.chat = await self.cai.create_new_chat(self.cirno_id)
        embed = Embed(title="CAI:", description="Flush called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)

    @slash_command(name='relog')
    async def relog(self, ctx):
        await self.cai.authenticate(CHARACTERAI_TOKEN)
        embed = Embed(title="CAI:", description="Auth called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)

    @slash_command(name='set_char')
    async def set_char(self,
                       ctx,
                       character_id: str = SlashOption(
                           description="Character ID to use (Cirno ID by default)",
                           required=False,
                           default="2g4E4hPoSdUtcDpLUaGT3pEaEpUlubWdUadJbSlqdi0")):
        self.chat = await self.cai.continue_last_or_create_chat(character_id)
        embed = Embed(title="CAI:", description="Request called", color=Colour.blurple())
        await ctx.send(embed=embed, delete_after=5)


def setup(bot):
    bot.add_cog(CharacterAICog(bot))
