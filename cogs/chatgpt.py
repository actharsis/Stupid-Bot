import logging
import nextcord
from nextcord import Interaction, SelectOption, slash_command
from nextcord.ext import commands
from nextcord import Thread

logger = logging.getLogger(__name__)

class ChatGPTCog(commands.Cog, name="Chat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.threads = []

    @slash_command(name='chatgpt', description="Create ChatGPT thread")
    async def chatgpt(self, interaction: nextcord.Interaction, arg: str):
        thread = await interaction.channel.create_thread(name=f'{arg}', auto_archive_duration=60)
        await thread.add_user(interaction.user)
        self.threads.append(thread)
        embed = nextcord.Embed(colour=nextcord.Colour.gold())
        embed.description = 'Thread created.'
        await interaction.response.send_message(embed=embed, delete_after=300, ephemeral=True)
        logger.info('Thread created')

    @commands.Cog.listener()
    async def on_message(self, ctx: nextcord.Message):
        if ctx.channel.type == "public_thread" or "private_thread":
            if ctx.channel in self.threads:
                answer = self.get_chatgpt_answer(ctx)
                await ctx.response.send_message(answer)

    async def get_chatgpt_answer(self, ctx):
        logger.info('Not implemented')


def setup(bot):
    bot.add_cog(ChatGPTCog(bot))
