import json
import logging
from typing import Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from redbot.core import Config, checks, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify

from .api import run_workflow

log = logging.getLogger("red.Comfy")


def validate_workflow(workflow: dict) -> Tuple[bool, str]:
    """
    Validate the structure of a ComfyUI workflow.
    Returns (is_valid, error_message).
    """
    if not isinstance(workflow, dict):
        return False, "Workflow must be a dictionary"

    if "nodes" not in workflow:
        return False, "Workflow must contain a 'nodes' key"

    if not isinstance(workflow["nodes"], list):
        return False, "Workflow 'nodes' must be a list"

    for i, node in enumerate(workflow["nodes"]):
        if not isinstance(node, dict):
            return False, f"Node {i} must be a dictionary"

        if "id" not in node:
            return False, f"Node {i} missing required 'id' field"

        if "type" not in node:
            return False, f"Node {i} missing required 'type' field"

    return True, ""


class Comfy(commands.Cog):
    """
    A Red cog for interfacing with ComfyUI's workflow API.
    Allows caching workflows and sending them to ComfyUI.
    """

    __author__ = "Cobray"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=818825515, force_registration=True
        )
        default_global = {
            "workflows": {},
            "cooldown_seconds": 30,
            "default_url": "http://localhost:8188",
        }
        self.config.register_global(**default_global)

        self.slash_group = app_commands.Group(
            name="comfy", description="ComfyUI workflow commands"
        )
        self.setup_slash_commands()

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        self.bot.tree.add_command(self.slash_group)

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        self.bot.tree.remove_command(self.slash_group.name)

    def setup_slash_commands(self):
        """Set up all slash commands."""

        @self.slash_group.command(name="list")
        async def slash_list(interaction: discord.Interaction):
            """List all cached workflows."""
            await interaction.response.defer()

            workflows = await self.config.workflows()
            if not workflows:
                await interaction.followup.send("No workflows are currently stored.")
                return

            workflow_list = []
            for name, workflow in workflows.items():
                node_count = len(workflow.get("nodes", []))
                workflow_list.append(f"• {name} ({node_count} nodes)")

            message = "**Cached Workflows:**\n" + "\n".join(workflow_list)

            for page in pagify(message):
                await interaction.followup.send(page)

        @self.slash_group.command(name="run")
        @app_commands.describe(
            workflow_name="Name of the workflow to run",
            base_url="Optional custom ComfyUI server URL",
        )
        async def slash_run(
            interaction: discord.Interaction,
            workflow_name: str,
            base_url: Optional[str] = None,
        ):
            """Run a cached workflow."""
            await interaction.response.defer()

            try:
                workflows = await self.config.workflows()
                workflow = workflows.get(workflow_name)
                if not workflow:
                    await interaction.followup.send(
                        f"No workflow with the name '{workflow_name}' found."
                    )
                    return

                url = base_url or await self.get_base_url()

                ctx = (
                    await self.bot.get_context(interaction.message)
                    if interaction.message
                    else None
                )
                if ctx is None:

                    class MinimalContext:
                        async def send(self, *args, **kwargs):
                            return await interaction.followup.send(*args, **kwargs)

                    ctx = MinimalContext()

                await run_workflow(ctx, workflow, base_url=url)

            except Exception as e:
                await interaction.followup.send(f"An error occurred: {str(e)}")
                log.error("Error running workflow", exc_info=True)

        @self.slash_group.command(name="info")
        @app_commands.describe(workflow_name="Name of the workflow to get info about")
        async def slash_info(interaction: discord.Interaction, workflow_name: str):
            """Show detailed information about a specific workflow."""
            await interaction.response.defer()

            workflows = await self.config.workflows()
            workflow = workflows.get(workflow_name)

            if not workflow:
                await interaction.followup.send(
                    f"No workflow found with the name '{workflow_name}'."
                )
                return

            nodes = workflow.get("nodes", [])
            node_types = {}
            for node in nodes:
                node_type = node.get("type", "Unknown")
                node_types[node_type] = node_types.get(node_type, 0) + 1

            info = [
                f"**Workflow: {workflow_name}**",
                f"Total Nodes: {len(nodes)}",
                "\nNode Types:",
            ]
            for node_type, count in node_types.items():
                info.append(f"• {node_type}: {count}")

            for page in pagify("\n".join(info)):
                await interaction.followup.send(page)

        @self.slash_group.command(name="add")
        @app_commands.describe(
            workflow_name="Name to give the workflow",
            workflow_json="JSON content of the workflow",
        )
        async def slash_add(
            interaction: discord.Interaction,
            workflow_name: str,
            workflow_json: Optional[str] = None,
        ):
            """Add a workflow to the cache from JSON or an attached file."""
            await interaction.response.defer()

            if workflow_json:
                try:
                    parsed_workflow = json.loads(workflow_json)
                except json.JSONDecodeError:
                    await interaction.followup.send(
                        "Invalid JSON provided. Please check your workflow definition."
                    )
                    return
            elif interaction.message and interaction.message.attachments:
                attachment = interaction.message.attachments[0]
                if not attachment.filename.lower().endswith(".json"):
                    await interaction.followup.send(
                        "This file does not appear to be JSON. Please attach a .json file."
                    )
                    return

                try:
                    content = await attachment.read()
                    parsed_workflow = json.loads(content)
                except Exception as e:
                    await interaction.followup.send(
                        f"Error reading or parsing the file: {e}"
                    )
                    return
            else:
                await interaction.followup.send(
                    "Please provide either JSON inline or attach a JSON file."
                )
                return

            is_valid, error = validate_workflow(parsed_workflow)
            if not is_valid:
                await interaction.followup.send(f"Invalid workflow format: {error}")
                return

            async with self.config.workflows() as workflows:
                workflows[workflow_name] = parsed_workflow
            await interaction.followup.send(
                f"Workflow '{workflow_name}' has been added to the cache."
            )

        @self.slash_group.command(name="remove")
        @app_commands.describe(workflow_name="Name of the workflow to remove")
        async def slash_remove(interaction: discord.Interaction, workflow_name: str):
            """Remove a workflow from the cache."""
            await interaction.response.defer()

            async with self.config.workflows() as workflows:
                if workflow_name in workflows:
                    del workflows[workflow_name]
                    await interaction.followup.send(
                        f"Removed workflow '{workflow_name}' from the cache."
                    )
                else:
                    await interaction.followup.send(
                        f"No workflow found with the name '{workflow_name}'."
                    )

    async def get_base_url(self) -> str:
        """Get the configured base URL for ComfyUI."""
        return await self.config.default_url()

    @commands.group(name="comfy")
    async def comfy_main(self, ctx: commands.Context):
        """Commands for managing and running ComfyUI workflows."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @comfy_main.command(name="add")
    async def comfy_add(
        self, ctx: commands.Context, workflow_name: str, *, workflow_json: str = None
    ):
        """
        Add a workflow to the local cache either by inline JSON or file attachment.

        Methods:
        1. Inline JSON: [p]comfy add myWorkflow {"nodes": [...]}
        2. File attachment: Upload .json file and use [p]comfy add myWorkflow
        """
        if workflow_json:
            try:
                parsed_workflow = json.loads(workflow_json)
            except json.JSONDecodeError:
                await ctx.send(
                    "Invalid JSON provided. Please check your workflow definition."
                )
                return
        elif ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.lower().endswith(".json"):
                await ctx.send(
                    "This file does not appear to be JSON. Please attach a .json file."
                )
                return

            try:
                content = await attachment.read()
                parsed_workflow = json.loads(content)
            except Exception as e:
                await ctx.send(f"Error reading or parsing the file: {e}")
                return
        else:
            await ctx.send("Please provide either JSON inline or attach a JSON file.")
            return

        is_valid, error = validate_workflow(parsed_workflow)
        if not is_valid:
            await ctx.send(f"Invalid workflow format: {error}")
            return

        async with self.config.workflows() as workflows:
            workflows[workflow_name] = parsed_workflow
        await ctx.send(f"Workflow '{workflow_name}' has been added to the cache.")

    @comfy_main.command(name="list")
    async def comfy_list(self, ctx: commands.Context):
        """List the names of all cached workflows."""
        workflows = await self.config.workflows()
        if not workflows:
            await ctx.send("No workflows are currently stored.")
            return

        workflow_list = []
        for name, workflow in workflows.items():
            node_count = len(workflow.get("nodes", []))
            workflow_list.append(f"• {name} ({node_count} nodes)")

        message = "**Cached Workflows:**\n" + "\n".join(workflow_list)

        for page in pagify(message):
            await ctx.send(page)

    @comfy_main.command(name="info")
    async def comfy_info(self, ctx: commands.Context, workflow_name: str):
        """Show detailed information about a specific workflow."""
        workflows = await self.config.workflows()
        workflow = workflows.get(workflow_name)

        if not workflow:
            await ctx.send(f"No workflow found with the name '{workflow_name}'.")
            return

        nodes = workflow.get("nodes", [])
        node_types = {}
        for node in nodes:
            node_type = node.get("type", "Unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1

        info = [
            f"**Workflow: {workflow_name}**",
            f"Total Nodes: {len(nodes)}",
            "\nNode Types:",
        ]
        for node_type, count in node_types.items():
            info.append(f"• {node_type}: {count}")

        for page in pagify("\n".join(info)):
            await ctx.send(page)

    @comfy_main.command(name="remove")
    async def comfy_remove(self, ctx: commands.Context, workflow_name: str):
        """Remove a workflow from the local cache by name."""
        async with self.config.workflows() as workflows:
            if workflow_name in workflows:
                del workflows[workflow_name]
                await ctx.send(f"Removed workflow '{workflow_name}' from the cache.")
            else:
                await ctx.send(f"No workflow found with the name '{workflow_name}'.")

    @commands.cooldown(1, 30, commands.BucketType.user)
    @comfy_main.command(name="run")
    async def comfy_run(
        self,
        ctx: commands.Context,
        workflow_name: str,
        base_url: Optional[str] = None,
    ):
        """
        Run a cached workflow by name.

        Args:
            workflow_name: Name of the cached workflow to run
            base_url: Optional custom ComfyUI server URL
        """
        try:
            workflows = await self.config.workflows()
            workflow = workflows.get(workflow_name)
            if not workflow:
                await ctx.send(f"No workflow with the name '{workflow_name}' found.")
                return

            # Use provided URL or fall back to default
            url = base_url or await self.get_base_url()

            # Run the workflow
            await run_workflow(ctx, workflow, base_url=url)

        except commands.CommandOnCooldown as e:
            await ctx.send(
                f"Please wait {e.retry_after:.1f}s before running another workflow."
            )
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            log.error("Error running workflow", exc_info=True)

    @checks.is_owner()
    @comfy_main.command(name="seturl")
    async def comfy_seturl(self, ctx: commands.Context, url: str):
        """
        Set the default ComfyUI server URL.

        This command is restricted to bot owners.
        Default is http://localhost:8188
        """
        await self.config.default_url.set(url)
        await ctx.send(f"Default ComfyUI server URL has been set to: {url}")

    @checks.is_owner()
    @comfy_main.command(name="setcooldown")
    async def comfy_setcooldown(self, ctx: commands.Context, seconds: int):
        """
        Set the cooldown period between workflow runs (in seconds).

        This command is restricted to bot owners.
        Default is 30 seconds.
        """
        if seconds < 0:
            await ctx.send("Cooldown must be a positive number.")
            return

        await self.config.cooldown_seconds.set(seconds)
        await ctx.send(f"Workflow cooldown period has been set to {seconds} seconds.")
