import nextcord
import io
import contextlib
from nextcord.ext import commands
from nextcord.ui import Modal, TextInput


class ExecModal(Modal):
    def __init__(self) -> None:
        super().__init__(title="Execute Your Code", custom_id="execute_code")

        self.add_item(
            TextInput(
                label="Input code",
                placeholder="print('Hello World')",
                custom_id="exec",
                style=nextcord.TextInputStyle.paragraph,
            )
        )

    async def callback(self, inter: nextcord.Interaction) -> None:
        embed = nextcord.Embed(title=":white_check_mark: Your code has been successfully executed",
                               color=0x00FF00)
        code = self.children[0].value

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exec(code)

        res = stdout.getvalue()
        embed.add_field(name="Code", value=f"```py\n{code}\n```", inline=False)
        embed.add_field(name="Output:", value=res, inline=False)
        await inter.response.send_message(embed=embed)

    async def on_error(self, error, interaction: nextcord.Interaction):
        embed = nextcord.Embed(title=":warning: Error", color=0xFF0000)
        embed.add_field(name="Message:", value=f"```{error}```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Exec(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(name="exec", description="Execute given python code")
    async def exec(self, interaction: nextcord.Interaction):
        await interaction.response.send_modal(modal=ExecModal())


def setup(bot):
    bot.add_cog(Exec(bot))
