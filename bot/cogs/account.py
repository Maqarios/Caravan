"""
Account Management Cog

This cog provides Discord commands for user account creation and management
using the usp_AddUser stored procedure.
"""

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils import DatabaseClient, get_logger

logger = get_logger("bot")


class AccountCog(commands.Cog):
    """Account management commands"""

    def __init__(self, bot):
        self.bot = bot
        self.db_client = DatabaseClient()
        logger.info("AccountCog initialized")

    # TODO: Add filter by role to a config file
    @app_commands.command(
        name="register",
        description="Register a new user account (automatically links to your Discord account)",
    )
    async def register_user(
        self,
        interaction: discord.Interaction,
        username: str,
        password: str,
    ):
        """
        Register a new user account (automatically links to your Discord account)

        Args:
            username: Account username (max 25 chars)
            password: Account password (max 50 chars)

        Note: Your Discord User ID is automatically stored for account verification.
        """
        await interaction.response.defer(ephemeral=True)

        # Validate inputs
        if len(username) > 25:
            await interaction.followup.send(
                "❌ Username must be 25 characters or less.", ephemeral=True
            )
            return

        if len(password) > 50:
            await interaction.followup.send(
                "❌ Password must be 50 characters or less.", ephemeral=True
            )
            return

        # Get Discord user ID and use it as certificate ID
        discord_user_id = str(interaction.user.id)
        result = await self.db_client.async_add_user(
            username, password, discord_user_id
        )

        logger.debug(f"Registering user: {result}")

        if result["success"]:
            if result["jid"]:
                # Create success embed
                embed = discord.Embed(
                    title="✅ Account Created Successfully",
                    description=f"Welcome, {username}!",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Username", value=username, inline=True)
                embed.add_field(name="Discord ID", value=discord_user_id, inline=True)
                embed.add_field(
                    name="Linked Account",
                    value=f"{interaction.user.mention}",
                    inline=False,
                )
                embed.set_footer(
                    text=f"Registered via Discord • Your Discord ID is stored for account verification"
                )
                embed.timestamp = datetime.utcnow()

                await interaction.followup.send(embed=embed, ephemeral=True)
                logger.info(
                    f"User '{username}' registered successfully and linked to Discord user {interaction.user.name} (ID: {interaction.user.id})"
                )
            else:
                # Create fail embed
                embed = discord.Embed(
                    title="❌ Account Creation failed",
                    description=f"Username **{username}** is 'likely' taken",
                    color=discord.Color.red(),
                )
                embed.timestamp = datetime.utcnow()

                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Account Creation failed",
                description=f"Internal server error. Contact an admin!",
                color=discord.Color.red(),
            )
            embed.timestamp = datetime.utcnow()

            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    """
    Setup function for loading the cog

    This function is called by Discord.py when loading the extension.
    """
    await bot.add_cog(AccountCog(bot))
