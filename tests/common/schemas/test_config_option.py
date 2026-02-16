"""Tests para ConfigOption."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.config_option import ConfigOption


class TestConfigOptionValidation:
    """Tests para la validación de ConfigOption."""

    def test_validate_none_value_required(self) -> None:
        """Probar validación de None cuando es requerido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            required=True,
        )
        is_valid, error = option.validate_value(None)
        assert is_valid is False
        assert error is not None and "obligatoria" in error

    def test_validate_none_value_not_required(self) -> None:
        """Probar validación de None cuando no es requerido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            required=False,
        )
        is_valid, error = option.validate_value(None)
        assert is_valid is True
        assert error is None

    def test_validate_string_valid(self) -> None:
        """Probar validación de string válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            max_length=10,
        )
        is_valid, error = option.validate_value("hello")
        assert is_valid is True
        assert error is None

    def test_validate_string_invalid_type(self) -> None:
        """Probar validación de string con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
        )
        is_valid, error = option.validate_value(123)
        assert is_valid is False
        assert error is not None and "debe ser texto" in error

    def test_validate_string_too_long(self) -> None:
        """Probar validación de string demasiado largo."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.STRING,
            max_length=5,
        )
        is_valid, error = option.validate_value("hello world")
        assert is_valid is False
        assert error is not None and "no puede exceder" in error

    def test_validate_integer_valid(self) -> None:
        """Probar validación de entero válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            min_value=0,
            max_value=100,
        )
        is_valid, error = option.validate_value(50)
        assert is_valid is True
        assert error is None

    def test_validate_integer_invalid_type(self) -> None:
        """Probar validación de entero con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
        )
        is_valid, error = option.validate_value("not a number")
        assert is_valid is False
        assert error is not None and "debe ser un número entero" in error

    def test_validate_integer_below_min(self) -> None:
        """Probar validación de entero por debajo del mínimo."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            min_value=10,
        )
        is_valid, error = option.validate_value(5)
        assert is_valid is False
        assert error is not None and "debe ser al menos" in error

    def test_validate_integer_above_max(self) -> None:
        """Probar validación de entero por encima del máximo."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.INTEGER,
            max_value=10,
        )
        is_valid, error = option.validate_value(15)
        assert is_valid is False
        assert error is not None and "no puede exceder" in error

    def test_validate_boolean_valid(self) -> None:
        """Probar validación de booleano válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.BOOLEAN,
        )
        is_valid, error = option.validate_value(True)
        assert is_valid is True
        assert error is None

    def test_validate_boolean_invalid_type(self) -> None:
        """Probar validación de booleano con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.BOOLEAN,
        )
        is_valid, error = option.validate_value("true")
        assert is_valid is False
        assert error is not None and "debe ser verdadero o falso" in error

    def test_validate_channel_valid(self) -> None:
        """Probar validación de canal válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL,
        )
        is_valid, error = option.validate_value(123456789)
        assert is_valid is True
        assert error is None

    def test_validate_channel_invalid_type(self) -> None:
        """Probar validación de canal con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL,
        )
        is_valid, error = option.validate_value("not an id")
        assert is_valid is False
        assert error is not None and "debe ser un ID válido" in error

    def test_validate_role_valid(self) -> None:
        """Probar validación de rol válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE,
        )
        is_valid, error = option.validate_value(123456789)
        assert is_valid is True
        assert error is None

    def test_validate_role_invalid_type(self) -> None:
        """Probar validación de rol con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE,
        )
        is_valid, error = option.validate_value("not an id")
        assert is_valid is False
        assert error is not None and "debe ser un ID válido" in error

    def test_validate_channel_list_valid(self) -> None:
        """Probar validación de lista de canales válida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL_LIST,
        )
        is_valid, error = option.validate_value([123, 456, 789])
        assert is_valid is True
        assert error is None

    def test_validate_channel_list_invalid(self) -> None:
        """Probar validación de lista de canales inválida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.CHANNEL_LIST,
        )
        is_valid, error = option.validate_value(["not", "ids"])
        assert is_valid is False
        assert error is not None and "debe ser una lista de IDs" in error

    def test_validate_role_list_valid(self) -> None:
        """Probar validación de lista de roles válida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE_LIST,
        )
        is_valid, error = option.validate_value([123, 456, 789])
        assert is_valid is True
        assert error is None

    def test_validate_role_list_invalid(self) -> None:
        """Probar validación de lista de roles inválida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.ROLE_LIST,
        )
        is_valid, error = option.validate_value("not a list")
        assert is_valid is False
        assert error is not None and "debe ser una lista de IDs" in error

    def test_validate_text_choice_valid(self) -> None:
        """Probar validación de opción de texto válida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[("Option A", "a"), ("Option B", "b")],
        )
        is_valid, error = option.validate_value("a")
        assert is_valid is True
        assert error is None

    def test_validate_text_choice_invalid(self) -> None:
        """Probar validación de opción de texto inválida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[("Option A", "a"), ("Option B", "b")],
        )
        is_valid, error = option.validate_value("c")
        assert is_valid is False
        assert error is not None and "debe ser una de las opciones válidas" in error

    def test_validate_text_choice_no_choices(self) -> None:
        """Probar validación de opción de texto sin choices definidas."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXT_CHOICE,
        )
        is_valid, error = option.validate_value("anything")
        assert is_valid is True
        assert error is None

    def test_validate_textarea_valid(self) -> None:
        """Probar validación de textarea válido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=2000,
        )
        multiline_text = "Linea 1\nLinea 2\nLinea 3"
        is_valid, error = option.validate_value(multiline_text)
        assert is_valid is True
        assert error is None

    def test_validate_textarea_with_markdown(self) -> None:
        """Probar validación de textarea con markdown de Discord."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=2000,
        )
        markdown_text = (
            "**Bienvenido**\n\n"
            "Por favor sube capturas de:\n"
            "- :flag_es: Perfil\n"
            "- <#123456789> Canal\n"
            "~~tachado~~ __subrayado__"
        )
        is_valid, error = option.validate_value(markdown_text)
        assert is_valid is True
        assert error is None

    def test_validate_textarea_invalid_type(self) -> None:
        """Probar validación de textarea con tipo inválido."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
        )
        is_valid, error = option.validate_value(123)
        assert is_valid is False
        assert error is not None and "debe ser texto" in error

    def test_validate_textarea_too_long(self) -> None:
        """Probar validación de textarea demasiado largo."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TEXTAREA,
            max_length=100,
        )
        long_text = "a" * 150
        is_valid, error = option.validate_value(long_text)
        assert is_valid is False
        assert error is not None and "no puede exceder" in error

    def test_validate_table_valid(self) -> None:
        """Probar validación de tabla válida."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Rol", "type": "role", "required": True},
                {"key": "tag", "name": "Etiqueta", "type": "string", "required": True},
            ],
        )
        table_value = [
            {"role_id": 123, "tag": "CAP"},
            {"role_id": 456, "tag": "SGT"},
        ]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is True
        assert error is None

    def test_validate_table_not_list(self) -> None:
        """Probar validación de tabla con tipo no lista."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        is_valid, error = option.validate_value("not a list")
        assert is_valid is False
        assert error is not None and "debe ser una lista" in error

    def test_validate_table_row_not_dict(self) -> None:
        """Probar validación de tabla con fila que no es dict."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        is_valid, error = option.validate_value(["not", "dicts"])
        assert is_valid is False
        assert error is not None and "debe ser un objeto" in error

    def test_validate_table_missing_required_column(self) -> None:
        """Probar validación de tabla con columna requerida faltante."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Rol", "type": "role", "required": True},
                {"key": "tag", "name": "Etiqueta", "type": "string", "required": True},
            ],
        )
        table_value = [
            {"role_id": 123},  # Falta "tag"
        ]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is False
        assert error is not None and "es obligatorio" in error

    def test_validate_table_empty_list(self) -> None:
        """Probar validación de tabla vacía (válido)."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
            columns=[
                {"key": "role_id", "name": "Rol", "type": "role", "required": True},
            ],
        )
        is_valid, error = option.validate_value([])
        assert is_valid is True
        assert error is None

    def test_validate_table_no_columns(self) -> None:
        """Probar validación de tabla sin columnas definidas."""
        option = ConfigOption(
            key="test",
            name="Test",
            option_type=ConfigOptionType.TABLE,
        )
        table_value = [{"any": "data"}]
        is_valid, error = option.validate_value(table_value)
        assert is_valid is True
        assert error is None
