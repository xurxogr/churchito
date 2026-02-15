"""Esquema de opción de configuración para cogs."""

from typing import Any

from pydantic import BaseModel, Field

from discord_bot.common.enums.config_option_type import ConfigOptionType


class ConfigOption(BaseModel):
    """Definición de una opción de configuración para un cog.

    Este modelo representa los metadatos de una opción de configuración,
    incluyendo su tipo, valor por defecto, validaciones y restricciones.
    """

    key: str = Field(description="Identificador único de la opción dentro del cog")
    name: str = Field(description="Nombre legible para mostrar en la UI")
    description: str = Field(default="", description="Descripción de la opción")
    option_type: ConfigOptionType = Field(description="Tipo de dato de la opción")
    default: Any = Field(default=None, description="Valor por defecto si no se configura")
    required: bool = Field(default=False, description="Si la opción es obligatoria")
    group: str | None = Field(
        default=None,
        description="Grupo para organizar opciones relacionadas en la UI",
    )
    choices: list[tuple[str, Any]] | None = Field(
        default=None,
        description="Lista de opciones válidas (label, value) para TEXT_CHOICE",
    )
    min_value: int | None = Field(default=None, description="Valor mínimo para INTEGER")
    max_value: int | None = Field(default=None, description="Valor máximo para INTEGER")
    max_length: int | None = Field(default=None, description="Longitud máxima para STRING")
    placeholders: list[str] | None = Field(
        default=None,
        description="Lista de placeholders disponibles para TEXTAREA",
    )

    def validate_value(self, value: Any) -> tuple[bool, str | None]:
        """Validar un valor contra las restricciones de esta opción.

        Args:
            value (Any): Valor a validar

        Returns:
            tuple[bool, str | None]: (es_valido, mensaje_error)
        """
        if value is None:
            if self.required:
                return False, f"La opción '{self.name}' es obligatoria"
            return True, None

        match self.option_type:
            case ConfigOptionType.STRING | ConfigOptionType.TEXTAREA:
                if not isinstance(value, str):
                    return False, f"'{self.name}' debe ser texto"
                if self.max_length and len(value) > self.max_length:
                    return False, f"'{self.name}' no puede exceder {self.max_length} caracteres"

            case ConfigOptionType.INTEGER:
                if not isinstance(value, int):
                    return False, f"'{self.name}' debe ser un número entero"
                if self.min_value is not None and value < self.min_value:
                    return False, f"'{self.name}' debe ser al menos {self.min_value}"
                if self.max_value is not None and value > self.max_value:
                    return False, f"'{self.name}' no puede exceder {self.max_value}"

            case ConfigOptionType.BOOLEAN:
                if not isinstance(value, bool):
                    return False, f"'{self.name}' debe ser verdadero o falso"

            case ConfigOptionType.CHANNEL | ConfigOptionType.ROLE:
                if not isinstance(value, int):
                    return False, f"'{self.name}' debe ser un ID válido"

            case ConfigOptionType.CHANNEL_LIST | ConfigOptionType.ROLE_LIST:
                if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
                    return False, f"'{self.name}' debe ser una lista de IDs"

            case ConfigOptionType.TEXT_CHOICE:
                if self.choices:
                    valid_values = [choice[1] for choice in self.choices]
                    if value not in valid_values:
                        return False, f"'{self.name}' debe ser una de las opciones válidas"

        return True, None
