import nextcord
import emoji
from nextcord.ext import commands
from nextcord import slash_command, SelectOption, Interaction
from nextcord.ui import View, Select


class SelectView(View):
    def __init__(self, cogs):
        super().__init__(timeout=None)
        self.cogs = cogs
        self.hidden_cogs = {'Help', 'MiscCog'}
        self.load_cogs()

    def load_cogs(self):
        options = []
        counter = 1
        for i, item in enumerate(self.cogs.items()):
            value = item[0]
            cog = item[1]
            if value in self.hidden_cogs:
                continue
            options.append(SelectOption(label=cog.qualified_name, value=value,
                                        emoji=emoji.emojize(f':keycap_{counter}:')))
            counter += 1
        self.add_item(Select(placeholder="Cogs", options=options, custom_id="cog"))

    async def interaction_check(self, interaction: Interaction) -> bool:
        value = interaction.data['values'][0]
        cog = self.cogs[value]
        embed = nextcord.Embed(colour=nextcord.Colour.gold())
        embed.set_author(
            name="Help page",
            icon_url="https://cdn.discordapp.com/emojis/695126170508984351.gif?&quality=lossless")
        embed.title = (
            f'Cog {cog.qualified_name}'
        )
        if cog and cog.description:
            embed.description = f"{cog.description}"
        await interaction.response.edit_message(embed=embed)
        return True


class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @slash_command(name='help', description="Show help message")
    async def help(self, ctx):
        embed = nextcord.Embed(colour=nextcord.Colour.gold())
        embed.set_author(
            name="Help page",
            icon_url="https://cdn.discordapp.com/emojis/695126170508984351.gif?&quality=lossless")
        embed.description = (
            f'All features are divided into the categories below.\n'
            f'This message *will be deleted* after **5** minutes.'
        )
        await ctx.response.send_message(embed=embed, view=SelectView(self.bot.cogs), delete_after=300)


def setup(bot):
    bot.add_cog(HelpCog(bot))
