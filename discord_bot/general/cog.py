"""Cog de comandos generales."""

import logging

from discord.ext import commands

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import get_config_schema_service

logger = logging.getLogger(__name__)

GENERAL_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="general",
    display_name="General",
    description="Configuración general del bot",
    icon="⚙️",
    options=[
        ConfigOption(
            key="prefix",
            name="Prefijo de comandos",
            description="Prefijo para comandos de texto (ej: !, ?, $)",
            option_type=ConfigOptionType.STRING,
            default="!",
            max_length=5,
        ),
        ConfigOption(
            key="welcome_channel",
            name="Canal de bienvenida",
            description="Canal donde se envían los mensajes de bienvenida",
            option_type=ConfigOptionType.CHANNEL,
        ),
        ConfigOption(
            key="welcome_enabled",
            name="Bienvenidas habilitadas",
            description="Habilitar/deshabilitar mensajes de bienvenida",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
        ),
        ConfigOption(
            key="log_channel",
            name="Canal de logs",
            description="Canal donde se envían los logs del bot",
            option_type=ConfigOptionType.CHANNEL,
        ),
        ConfigOption(
            key="mod_roles",
            name="Roles de moderación",
            description="Roles con permisos de moderación",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
        ),
        ConfigOption(
            key="language",
            name="Idioma",
            description="Idioma del bot para este servidor",
            option_type=ConfigOptionType.TEXT_CHOICE,
            default="es",
            choices=[
                ("Español", "es"),
                ("English", "en"),
                ("Português", "pt"),
            ],
        ),
    ],
)


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
        bot (commands.Bot): La instancia del bot de Discord
    """
    get_config_schema_service().register_schema(GENERAL_CONFIG_SCHEMA)
    await bot.add_cog(GeneralCog(bot))


async def teardown(bot: commands.Bot) -> None:
    """Descarga el cog general.

    Args:
        bot (commands.Bot): La instancia del bot de Discord
    """
    get_config_schema_service().unregister_schema("general")
