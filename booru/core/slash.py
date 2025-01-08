import logging
from typing import List, Optional

import discord
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru.slash")


class BooruSlash(commands.Cog):
    """Slash command implementation of booru search commands"""

    def __init__(self, bot):
        self.bot = bot
        self.tag_handler = TagHandler()
        super().__init__()

    @commands.hybrid_group(name="booru", invoke_without_command=True)
    @commands.guild_only()
    async def booru(
        self, ctx: commands.Context, *, tags: str = "", source: Optional[str] = None
    ):
        """Search booru sites for images"""
        if not ctx.interaction:
            await ctx.send_help()
            return

        is_nsfw = False
        if isinstance(ctx.channel, discord.TextChannel):
            is_nsfw = ctx.channel.is_nsfw()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await ctx.send("Booru cog is not loaded.")
            return

        if source:
            source = source.lower()
            if source not in booru_cog.sources:
                await ctx.send(f"Invalid source: {source}")
                return

            post = await booru_cog._get_post_from_source(source, tags, is_nsfw)
            if not post:
                await ctx.send(f"No results found on {source.title()}")
                return

            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From {source.title()} • ID: {post['id']}")

            await ctx.send(embed=embed)
            return

        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await ctx.send("No sources configured.")
            return

        posts = []
        used_source = None

        for source_name in source_order:
            try:
                posts = await booru_cog._get_multiple_posts_from_source(
                    source_name, tags, is_nsfw, limit=100
                )
                if posts:
                    used_source = source_name
                    break
            except Exception as e:
                log.error(f"Error with {source_name}: {e}")
                continue

        if not posts:
            await ctx.send("No results found in any source.")
            return

        current_index = 0
        embed = booru_cog._build_embed(posts[current_index], current_index, len(posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {used_source.title()}")

        message = await ctx.send(embed=embed)
        if len(posts) > 1:
            view = BooruPaginationView(ctx.author, posts, used_source)
            await message.edit(view=view)

    @booru.command(name="source")
    @commands.guild_only()
    async def booru_source(self, ctx: commands.Context, source: str, *, tags: str):
        """Search a specific booru source"""
        is_nsfw = False
        if isinstance(ctx.channel, discord.TextChannel):
            is_nsfw = ctx.channel.is_nsfw()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await ctx.send("Booru cog is not loaded.")
            return

        source = source.lower()
        if source not in booru_cog.sources:
            await ctx.send(f"Invalid source: {source}")
            return

        post = await booru_cog._get_post_from_source(source, tags, is_nsfw)
        if not post:
            await ctx.send(f"No results found on {source.title()}")
            return

        embed = booru_cog._build_embed(post, 0, 1)
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {source.title()}")

        await ctx.send(embed=embed)


class BooruPaginationView(discord.ui.View):
    """View for handling pagination of booru search results"""

    def __init__(self, author: discord.User, posts: List[dict], source: str):
        super().__init__(timeout=60)
        self.author = author
        self.posts = posts
        self.current_index = 0
        self.source = source

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can use the buttons"""
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None)
        self.stop()

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the next/previous post"""
        post = self.posts[self.current_index]

        booru_cog = interaction.client.get_cog("Booru")
        embed = booru_cog._build_embed(post, self.current_index, len(self.posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {self.source.title()}")

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Remove buttons when the view times out"""
        try:
            await self.message.edit(view=None)
        except (discord.NotFound, discord.HTTPException):
            pass
