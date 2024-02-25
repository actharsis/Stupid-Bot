import logging
import nextcord
from nextcord import Colour, Embed, SlashOption, ChannelType, slash_command
from nextcord.ext import commands
from modules.webchatgpt import ChatGPT

from config import PATH_TO_GPT_COOKIES

logger = logging.getLogger(__name__)


class ChatGPTCog(commands.Cog, name="Chat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gpt = ChatGPT(PATH_TO_GPT_COOKIES)
        logger.info('GPT api is fine')

    def pick_last_markdown_type(self, text):
        pos = text.rfind('```')
        return text[pos:].split()[0] + '\n'

    def nice_cut(self, chunk: str) -> [str, bool]:
        markdown = ""
        last_line_pos = chunk.rfind('\n')
        last_word_pos = chunk.rfind(' ')
        if len(chunk) - last_line_pos < 200:
            chunk = chunk[:last_line_pos]
        elif len(chunk) - last_word_pos < 200:
            chunk = chunk[:last_word_pos]
        if chunk.count('```') % 2 == 1:
            markdown = self.pick_last_markdown_type(chunk)
            chunk += '```'
        return chunk, markdown

    def pagify(self, message: str) -> list:
        pages = []
        while len(message) >= 2000:
            page, markdown = self.nice_cut(message[:1990])
            pages.append(page)
            message = f"{markdown}{message[len(page):]}"
        pages.append(message)
        return pages

    async def gpt_request(self, thread, prompt):
        await thread.trigger_typing()

        message = None
        current_page_index = -1
        async for response in self.gpt.ask(prompt):
            if response["error"] is None:
                content = response["message"]["content"]["parts"][0]
                pages = self.pagify(content)
                if message:
                    await message.edit(content=pages[current_page_index])
                if current_page_index < len(pages) - 1:
                    current_page_index += 1
                    message = await thread.send(pages[current_page_index])
            else:
                logger.error(response["error"])

    @slash_command(name='gpt', description="Create ChatGPT thread")
    async def gpt(self,
                  interaction: nextcord.Interaction,
                  message: str = SlashOption(description="Message", required=False)):
        thread = await interaction.channel.create_thread(
            name=f'{interaction.user.name}\'s thread',
            type=ChannelType.public_thread,
            auto_archive_duration=60
        )
        await interaction.response.send_message(
            embed=Embed(
                colour=Colour.dark_teal(),
                title='Thread created',
                description="Use this thread to chat with gpt"
            ),
            delete_after=5,
            ephemeral=True
        )
        if message:
            embed = Embed(
                colour=Colour.blurple(),
                title='Starting message',
                description=message
            )
        else:
            embed = Embed(
                colour=Colour.gold(),
                title='GPT Thread',
                description='Gpt blank thread created'
            )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
        await thread.send(embed=embed)
        logger.info('GPT Thread created')
        if message:
            await self.gpt_request(thread, message)

    @commands.Cog.listener()
    async def on_message(self, ctx: nextcord.Message):
        if ((ctx.channel.type == ChannelType.public_thread or ctx.channel.type == ChannelType.private_thread)
                and ctx.channel.owner_id == self.bot.application_id and ctx.author != self.bot.user):
            await self.gpt_request(ctx.channel, ctx.content)


def setup(bot):
    bot.add_cog(ChatGPTCog(bot))
