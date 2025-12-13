"""Cog de comandos generales."""

import logging

from discord.ext import commands

logger = logging.getLogger(__name__)


class GeneralCog(commands.Cog):
    """Comandos generales para el bot."""

    def __init__(self, bot: commands.Bot) -> None:
        """Inicializa el cog general.

        Args:
            bot (commands.Bot): La instancia del bot de Discord
        """
        self.bot = bot

    @commands.command()
    async def ping(self, ctx: commands.Context[commands.Bot]) -> None:
        """Verifica si el bot está respondiendo.

        Args:
            ctx (commands.Context[commands.Bot]): El contexto del comando
        """
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! Latencia: {latency}ms")
        logger.info(f"Comando ping ejecutado por {ctx.author} (latencia: {latency}ms)")

    @commands.command()
    async def info(self, ctx: commands.Context[commands.Bot]) -> None:
        """Muestra información del bot.

        Args:
            ctx (commands.Context[commands.Bot]): El contexto del comando
        """
        guild_count = len(self.bot.guilds)
        await ctx.send(
            f"**Información del Bot**\n"
            f"Nombre: {self.bot.user.name if self.bot.user else 'Desconocido'}\n"
            f"Servidores: {guild_count}\n"
            f"Prefijo: `{self.bot.command_prefix}`"
        )
        logger.info(f"Comando info ejecutado por {ctx.author}")


async def setup(bot: commands.Bot) -> None:
    """Carga el cog general.

    Args:
        bot: La instancia del bot de Discord
    """
    await bot.add_cog(GeneralCog(bot))
