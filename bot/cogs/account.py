"""
Account Management Cog

This cog provides Discord commands for user account creation and management
using the usp_AddUser stored procedure.
"""

import hashlib
import json
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
            fullname: Full name (optional, max 30 chars, default: "Player")
            sex: Sex/Gender (optional, M or F, default: M)
            email: Email address (optional, max 50 chars)

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
        hashed_password = hashlib.md5(
            password.encode()
        ).hexdigest()  # Password is md5 in db

        try:
            # Prepare parameters for usp_AddUser stored procedure
            parameters = {
                "StrUserID": username,
                "Password": hashed_password,
                "SecPassword": hashed_password,  # Using same password for secondary (can be modified)
                "FullName": None,
                "Question": None,
                "Answer": None,
                "Sex": None,
                "BirthDay": None,
                "Province": None,
                "Address": f"Discord User: {interaction.user.name}#{interaction.user.discriminator}",  # Store Discord tag
                "Phone": None,
                "Mobile": None,
                "Email": f"{interaction.user.id}@discord.user",  # Discord ID as email fallback
                "cid": discord_user_id,  # Certificate ID - Discord User ID
                "RegIP": None,
                "JID": 0,
            }

            # Execute stored procedure
            result = await self.db_client.async_execute_procedure(
                database="SRO_VT_ACCOUNT",
                procedure_name="usp_AddUser",
                parameters=parameters,
            )

            if result["success"] and result["affected_rows"] == 1:
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
                error_msg = result.get("error", "Unknown error")

                await interaction.followup.send(
                    f"❌ Failed to create account: {error_msg}", ephemeral=True
                )

                logger.error(f"Failed to register user '{username}': {error_msg}")

        except Exception as e:
            logger.error(f"Error in register_user command: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An unexpected error occurred while creating your account. Please try again later.",
                ephemeral=True,
            )


async def setup(bot):
    """
    Setup function for loading the cog

    This function is called by Discord.py when loading the extension.
    """
    await bot.add_cog(AccountCog(bot))
