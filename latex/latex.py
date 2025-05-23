import aiohttp
import discord
import io
import logging
import re
from typing import Optional
from PIL import Image, ImageOps
import urllib.parse as parse
from redbot.core import commands, app_commands
from redbot.core.bot import Red

try:
    from discord.app_commands import installs as app_installs
except ImportError:
    app_installs = None

log = logging.getLogger("red.latex")

START_CODE_BLOCK_RE = re.compile(r"^((```(la)?tex)(?=\s)|(```))")


class Latex(commands.Cog):
    """LaTeX expressions via an image"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.latex_context = app_commands.ContextMenu(name="Render as LaTeX", callback=self._latex_context_callback)
        if app_installs is not None:
            try:
                for cmd in [self.latex_slash, self.latex_help_slash]:
                    cmd.allowed_contexts = app_installs.AppCommandContext(
                        guild=True, dm_channel=True, private_channel=True
                    )
                    cmd.allowed_installs = app_installs.AppInstallationType(guild=True, user=True)
                self.latex_context.allowed_contexts = app_installs.AppCommandContext(
                    guild=True, dm_channel=True, private_channel=True
                )
                self.latex_context.allowed_installs = app_installs.AppInstallationType(guild=True, user=True)
                log.info("Successfully configured app commands for user installation")
            except Exception as exc:
                log.exception("Failed to set allowed_contexts/installs for latex commands", exc_info=exc)

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        self.bot.tree.add_command(self.latex_context)

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()
        self.bot.tree.remove_command(self.latex_context.name, type=self.latex_context.type)

    async def red_delete_data_for_user(self):
        return

    @staticmethod
    def cleanup_code_block(content: str) -> str:
        """Remove code block formatting from the input."""
        # remove ```latex\n```/```tex\n```/``````
        if content.startswith("```") and content.endswith("```"):
            return START_CODE_BLOCK_RE.sub("", content)[:-3]
        return content.strip("` \n")

    async def generate_latex_image(self, equation: str) -> Optional[discord.File]:
        """Generate a LaTeX image from the given equation."""
        base_url = "https://latex.codecogs.com/png.image?%5Cdpi%7B200%7D%5Cbg%7Bwhite%7D%20"
        equation_encoded = parse.quote(equation)
        url = f"{base_url}{equation_encoded}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    log.error(f"Failed to get LaTeX image: HTTP {response.status}")
                    return None
                image_data = await response.read()
            image = Image.open(io.BytesIO(image_data)).convert("RGBA")
            image = ImageOps.expand(image, border=10, fill="white")
            image_file_object = io.BytesIO()
            image.save(image_file_object, format="PNG")
            image_file_object.seek(0)
            return discord.File(fp=image_file_object, filename="latex.png")
        except aiohttp.ClientError as e:
            log.exception(f"Network error while fetching LaTeX image: {e}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error while processing LaTeX image: {e}")
            return None

    @app_commands.command(name="latex", description="Render a LaTeX expression as an image")
    @app_commands.describe(equation="The LaTeX expression to render (e.g., \\frac{a}{b})")
    async def latex_slash(self, interaction: discord.Interaction, equation: str):
        equation = self.cleanup_code_block(equation)
        await interaction.response.defer()
        image_file = await self.generate_latex_image(equation)
        if image_file:
            embed = discord.Embed(title="LaTeX Render", color=discord.Color.blue())
            embed.set_image(url="attachment://latex.png")
            embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(file=image_file, embed=embed)
        else:
            await interaction.followup.send(
                "❌ I couldn't render that LaTeX expression. Please check your syntax and try again.", ephemeral=True
            )

    @app_commands.command(name="latexhelp", description="Show helpful LaTeX syntax examples")
    async def latex_help_slash(self, interaction: discord.Interaction):
        """Slash command to show LaTeX help."""
        embed = discord.Embed(
            title="LaTeX Help",
            description="Here are some common LaTeX expressions you can use:",
            color=discord.Color.blue(),
        )
        examples = [
            ("Fractions", "`\\frac{a}{b}`", "\\frac{a}{b}"),
            ("Superscript", "`x^2`", "x²"),
            ("Subscript", "`x_1`", "x₁"),
            ("Greek letters", "`\\alpha, \\beta, \\gamma`", "α, β, γ"),
            ("Sum", "`\\sum_{i=1}^{n} x_i`", "Σ from i=1 to n of xᵢ"),
            ("Integral", "`\\int_{a}^{b} f(x) dx`", "∫ from a to b of f(x)dx"),
            ("Square root", "`\\sqrt{x}`", "√x"),
            ("Matrices", "`\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}`", "Matrix [[a,b],[c,d]]"),
        ]
        for name, syntax, rendered in examples:
            embed.add_field(name=name, value=f"Syntax: {syntax}\nRenders as: {rendered}", inline=False)
        embed.set_footer(text="Use /latex to render these expressions!")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _latex_context_callback(self, interaction: discord.Interaction, message: discord.Message):
        """Right-click context menu to render a message's content as LaTeX."""
        if not message.content:
            await interaction.response.send_message("This message has no content to render.", ephemeral=True)
            return
        equation = self.cleanup_code_block(message.content)
        await interaction.response.defer(ephemeral=True)
        image_file = await self.generate_latex_image(equation)
        if image_file:
            embed = discord.Embed(
                title="LaTeX Render", description=f"From: {message.author.mention}", color=discord.Color.blue()
            )
            embed.set_image(url="attachment://latex.png")
            await interaction.followup.send(file=image_file, embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ I couldn't render that as a LaTeX expression.", ephemeral=True)

    @commands.guild_only()
    @commands.command(aliases=["tex"], hidden=True)
    async def latex(self, ctx: commands.Context, *, equation: str):
        """
        [Legacy] Takes a LaTeX expression and renders it as an image.
        **Note: Please use `/latex` instead!**
        You can use code blocks or inline code formatting:
        - `$\\alpha + \\beta$`
        - ```latex
          \\frac{a}{b}
          ```
        """
        equation = self.cleanup_code_block(equation)
        async with ctx.typing():
            image_file = await self.generate_latex_image(equation)
        if image_file:
            embed = discord.Embed(
                title="LaTeX Render",
                color=await ctx.embed_color(),
                description="💡 **Tip:** Use `/latex` for a better experience!",
            )
            embed.set_image(url="attachment://latex.png")
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(file=image_file, embed=embed)
        else:
            await ctx.send(
                "❌ I couldn't render that LaTeX expression. "
                "Please check your syntax and try again.\n"
                "💡 **Tip:** Try using `/latex` instead!"
            )

    @commands.guild_only()
    @commands.command(name="latexhelp", hidden=True)
    async def latex_help(self, ctx: commands.Context):
        """[Legacy] Show helpful LaTeX syntax examples. Use /latexhelp instead!"""
        embed = discord.Embed(
            title="LaTeX Help",
            description="**Note:** Please use `/latexhelp` for a better experience!\n\n"
            "Here are some common LaTeX expressions you can use:",
            color=await ctx.embed_color(),
        )
        examples = [
            ("Fractions", "`\\frac{a}{b}`", "\\frac{a}{b}"),
            ("Superscript", "`x^2`", "x²"),
            ("Subscript", "`x_1`", "x₁"),
            ("Greek letters", "`\\alpha, \\beta, \\gamma`", "α, β, γ"),
            ("Sum", "`\\sum_{i=1}^{n} x_i`", "Σ from i=1 to n of xᵢ"),
            ("Integral", "`\\int_{a}^{b} f(x) dx`", "∫ from a to b of f(x)dx"),
            ("Square root", "`\\sqrt{x}`", "√x"),
            ("Matrices", "`\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}`", "Matrix [[a,b],[c,d]]"),
        ]
        for name, syntax, rendered in examples:
            embed.add_field(name=name, value=f"Syntax: {syntax}\nRenders as: {rendered}", inline=False)
        embed.set_footer(text="Use /latex to render these expressions!")
        await ctx.send(embed=embed)
