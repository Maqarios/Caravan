"""
Caravan Discord Bot - Main Entry Point

A Discord bot for Silkroad server management with MSSQL integration.
"""

import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils import get_logger, setup_discord_logging

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("bot")

# Configure discord.py library logging
setup_discord_logging()


class CaravanBot(commands.Bot):
    """Main bot class for Caravan"""

    def __init__(self):
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(
            command_prefix=os.getenv("BOT_PREFIX", "/"),
            intents=intents,
            help_command=None,  # TODO: add help command
        )

        # Database connection string
        self.db_connection_string = os.getenv("MSSQL_CONNECTION_STRING")
        logger.info("Bot instance created")

    async def setup_hook(self):
        """Called before bot starts - load cogs and sync commands"""
        logger.info("Running setup hook...")

        # Load cogs
        # TODO: add cogs

        # Sync commands
        await self.tree.sync()
        logger.info("Commands synced globally")

    async def on_ready(self):
        """Called when bot is ready and connected"""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info(f"Bot is ready! Latency: {round(self.latency * 1000)}ms")

        # Set bot activity status
        activity = discord.Activity(type=discord.ActivityType.watching, name="Silkroad")
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for prefix commands"""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                "❌ You don't have permission to use this command.", ephemeral=True
            )
            logger.warning(f"{ctx.author} lacks permissions for {ctx.command}")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
            return

        # Log unexpected errors
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=error)
        await ctx.send("❌ An error occurred while processing your command.")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        """Global error handler for slash commands"""
        if isinstance(error, discord.app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", ephemeral=True
            )
            logger.warning(
                f"{interaction.user} lacks permissions for /{interaction.command.name}"
            )
            return

        # Log unexpected errors
        logger.error(
            f"App command error in /{interaction.command.name}: {error}", exc_info=error
        )

        # Send error message
        error_msg = "❌ An error occurred while processing your command."
        if interaction.response.is_done():
            await interaction.followup.send(error_msg, ephemeral=True)
        else:
            await interaction.response.send_message(error_msg, ephemeral=True)


async def main():
    """Main entry point"""
    # Check for required environment variables
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN not found in environment variables!")
        return

    # Create and run bot
    bot = CaravanBot()

    try:
        logger.info("Starting Caravan Bot...")
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        await bot.close()
        logger.info("Bot closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user")
