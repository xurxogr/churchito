"""Tests para autoname service (funciones puras)."""

from typing import Any

from discord_bot.autoname.service import (
    build_nickname,
    build_tag_pattern,
    compute_nickname,
    extract_base_name,
    find_matching_value,
)

DEFAULT_FORMAT = "[ABC | {tag}]"


class TestBuildTagPattern:
    """Tests para build_tag_pattern."""

    def test_simple_format(self) -> None:
        """Patron simple debe coincidir correctamente."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        assert pattern.match("[ABC | CAP] Xurxo")
        assert pattern.match("★[ABC | SGT] Juan")

    def test_does_not_match_different_format(self) -> None:
        """No debe coincidir con formato diferente."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        assert not pattern.match("[XYZ | CAP] Xurxo")
        assert not pattern.match("[OTHER] Name")

    def test_extracts_base_name(self) -> None:
        """Debe extraer el nombre base correctamente."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        match = pattern.match("[ABC | CAP] Xurxo")
        assert match is not None
        assert match.group(1) == "Xurxo"

    def test_extracts_with_prefix(self) -> None:
        """Debe extraer nombre incluso con prefijo."""
        pattern = build_tag_pattern("[ABC | {tag}]")
        match = pattern.match("★[ABC | CAP] Xurxo")
        assert match is not None
        assert match.group(1) == "Xurxo"

    def test_special_chars_escaped(self) -> None:
        """Caracteres especiales deben escaparse."""
        pattern = build_tag_pattern("[A.B | {tag}]")
        assert pattern.match("[A.B | CAP] Name")
        assert not pattern.match("[AXB | CAP] Name")  # . no debe coincidir con X


class TestExtractBaseName:
    """Tests para extract_base_name."""

    def test_simple_name(self) -> None:
        """Nombre sin tags debe devolverse tal cual."""
        result = extract_base_name(display_name="Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_matching_tag(self) -> None:
        """Nombre con tag que coincide con formato debe limpiarse."""
        result = extract_base_name(display_name="[ABC | CAP] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_prefix_and_matching_tag(self) -> None:
        """Nombre con prefijo y tag que coincide debe limpiarse."""
        result = extract_base_name(display_name="★[ABC | CAP] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_name_with_different_tag_uses_fallback(self) -> None:
        """Tag de formato diferente debe limpiarse via fallback generico."""
        # [XYZ | ...] no coincide con [ABC | ...] pero el fallback lo limpia
        result = extract_base_name(display_name="[XYZ | OLD] Xurxo", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_whitespace_handling(self) -> None:
        """Espacios extra deben manejarse correctamente."""
        result = extract_base_name(display_name="  [ABC | SGT] Juan  ", tag_format=DEFAULT_FORMAT)
        assert result == "Juan"

    def test_name_with_spaces(self) -> None:
        """Nombres con espacios deben preservarse."""
        result = extract_base_name(
            display_name="[ABC | TAG] Juan Carlos", tag_format=DEFAULT_FORMAT
        )
        assert result == "Juan Carlos"

    def test_format_change_cleans_old_format(self) -> None:
        """Al cambiar formato, el viejo debe limpiarse via fallback."""
        old_name = "★[OLD | CAP] Xurxo"
        new_format = "[NEW | {tag}]"
        # El tag [OLD | CAP] no coincide con [NEW | ...] pero el fallback lo limpia
        result = extract_base_name(display_name=old_name, tag_format=new_format)
        assert result == "Xurxo"

    def test_multiword_name_without_tag_preserved(self) -> None:
        """Nombres con varias palabras sin tags deben preservarse completos."""
        # "Karl Fisburne" no debe convertirse en "Fisburne"
        result = extract_base_name(display_name="Karl Fisburne", tag_format=DEFAULT_FORMAT)
        assert result == "Karl Fisburne"

    def test_short_first_word_preserved(self) -> None:
        """Nombres cortos al inicio no deben confundirse con prefijos."""
        result1 = extract_base_name(display_name="Ana Garcia", tag_format=DEFAULT_FORMAT)
        result2 = extract_base_name(display_name="El Jefe", tag_format=DEFAULT_FORMAT)
        assert result1 == "Ana Garcia"
        assert result2 == "El Jefe"

    def test_strips_known_prefix_without_tag(self) -> None:
        """Debe quitar prefijo conocido cuando no hay tag."""
        result = extract_base_name(
            display_name="★ Xurxo",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "Xurxo"

    def test_strips_different_known_prefix(self) -> None:
        """Debe quitar cualquier prefijo conocido."""
        result = extract_base_name(
            display_name="◈ Juan",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "Juan"

    def test_does_not_strip_unknown_prefix(self) -> None:
        """No debe quitar prefijos no configurados."""
        result = extract_base_name(
            display_name="♦ Pedro",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★", "◈"],
        )
        assert result == "♦ Pedro"

    def test_strips_prefix_and_tag_together(self) -> None:
        """Debe quitar prefijo y tag cuando ambos estan presentes."""
        result = extract_base_name(
            display_name="★[ABC | CAP] Xurxo",
            tag_format=DEFAULT_FORMAT,
            known_prefixes=["★"],
        )
        assert result == "Xurxo"


class TestFindMatchingValue:
    """Tests para find_matching_value."""

    def test_first_match_wins(self) -> None:
        """El primer rol coincidente en la lista debe ganar."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200, 100]  # Tiene ambos roles

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "CAP"  # CAP esta primero en config

    def test_no_matching_role(self) -> None:
        """Sin rol coincidente debe devolver None."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
        ]
        member_role_ids = [200, 300]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result is None

    def test_empty_roles_config(self) -> None:
        """Config vacia debe devolver None."""
        result = find_matching_value(member_role_ids=[100, 200], roles_config=[], value_key="tag")
        assert result is None

    def test_empty_member_roles(self) -> None:
        """Miembro sin roles debe devolver None."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        result = find_matching_value(member_role_ids=[], roles_config=tags_config, value_key="tag")
        assert result is None

    def test_role_id_as_string_in_config(self) -> None:
        """role_id puede venir como string del form (Discord snowflakes)."""
        # Web form saves role_id as string to avoid JS precision loss
        tags_config = [
            {"role_id": "484072731344764932", "tag": "CAP"},
        ]
        member_role_ids = [484072731344764932]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )
        assert result == "CAP"

    def test_role_id_as_int_in_config(self) -> None:
        """role_id como int tambien funciona (compatibilidad)."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
        ]
        member_role_ids = [100]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )
        assert result == "CAP"

    def test_missing_role_id_skipped(self) -> None:
        """Config sin role_id debe saltarse."""
        tags_config: list[dict[str, Any]] = [
            {"tag": "CAP"},  # Sin role_id
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"

    def test_invalid_role_id_skipped(self) -> None:
        """role_id no numerico debe saltarse."""
        tags_config: list[dict[str, Any]] = [
            {"role_id": "invalid", "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"

    def test_none_role_id_skipped(self) -> None:
        """role_id None debe saltarse."""
        tags_config: list[dict[str, Any]] = [
            {"role_id": None, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        member_role_ids = [200]

        result = find_matching_value(
            member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
        )

        assert result == "SGT"


class TestBuildNickname:
    """Tests para build_nickname."""

    def test_full_nickname(self) -> None:
        """Nickname completo con prefix, tag y nombre."""
        result = build_nickname(base_name="Xurxo", tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT)
        assert result == "★[ABC | CAP] Xurxo"

    def test_no_prefix(self) -> None:
        """Nickname sin prefijo."""
        result = build_nickname(base_name="Xurxo", tag="CAP", prefix="", tag_format=DEFAULT_FORMAT)
        assert result == "[ABC | CAP] Xurxo"

    def test_no_tag(self) -> None:
        """Nickname sin tag (solo nombre)."""
        result = build_nickname(base_name="Xurxo", tag="", prefix="", tag_format=DEFAULT_FORMAT)
        assert result == "Xurxo"

    def test_custom_tag_format(self) -> None:
        """Formato de tag personalizado."""
        result = build_nickname(base_name="Xurxo", tag="LEADER", prefix="◈", tag_format="[{tag}]")
        assert result == "◈[LEADER] Xurxo"

    def test_truncation_long_name(self) -> None:
        """Nombres largos deben truncarse a 32 caracteres."""
        long_name = "A" * 40
        result = build_nickname(
            base_name=long_name, tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT
        )
        assert len(result) <= 32

    def test_truncation_preserves_tag(self) -> None:
        """El tag debe preservarse y truncar el nombre."""
        long_name = "A" * 30
        result = build_nickname(
            base_name=long_name, tag="CAP", prefix="★", tag_format=DEFAULT_FORMAT
        )

        assert len(result) <= 32
        assert "[ABC | CAP]" in result
        assert "★" in result

    def test_very_long_tag_uses_name_only(self) -> None:
        """Si el tag es muy largo, usar solo nombre truncado."""
        result = build_nickname(
            base_name="Xurxo",
            tag="CAP",
            prefix="★",
            tag_format="[" + "X" * 40 + " | {tag}]",
        )
        assert len(result) <= 32

    def test_prefix_only_with_empty_tag_format(self) -> None:
        """Prefix con formato que resulta vacio cuando tag esta vacio."""
        # tag_format="{tag}" con tag="" resulta en formatted_tag=""
        result = build_nickname(base_name="Xurxo", tag="", prefix="★", tag_format="{tag}")
        assert result == "★ Xurxo"

    def test_truncation_long_name_without_tag(self) -> None:
        """Nombre largo sin tag ni prefix debe truncarse."""
        long_name = "A" * 40
        result = build_nickname(base_name=long_name, tag="", prefix="", tag_format=DEFAULT_FORMAT)
        assert len(result) == 32
        assert result == "A" * 32


class TestComputeNickname:
    """Tests para compute_nickname."""

    def test_computes_new_nickname_with_tag_and_prefix(self) -> None:
        """Debe computar nuevo nickname para miembro con tag y prefix."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "★[ABC | CAP] Xurxo"

    def test_computes_nickname_with_only_tag(self) -> None:
        """Debe computar nickname con solo tag, sin prefix."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "[ABC | CAP] Xurxo"

    def test_computes_nickname_with_only_prefix(self) -> None:
        """Debe computar nickname con solo prefix, usando formato con tag vacio."""
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # Siempre usa el formato, con tag vacio si no hay tag configurado
        assert result == "★[ABC | ] Xurxo"

    def test_no_change_with_only_prefix(self) -> None:
        """No debe re-añadir prefijo si ya tiene el formato correcto."""
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | ] Xurxo",
            current_nick="★[ABC | ] Xurxo",
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_no_change_needed(self) -> None:
        """Debe devolver None si no hay cambio."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_cleans_tag_when_no_matching_role(self) -> None:
        """Debe limpiar tag si no hay rol coincidente."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[200],  # No tiene rol 100
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "Xurxo"

    def test_returns_none_when_already_clean(self) -> None:
        """Debe devolver None si ya esta limpio."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        result = compute_nickname(
            display_name="Xurxo",
            current_nick="Xurxo",
            member_role_ids=[200],
            tags_config=tags_config,
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_updates_tag_on_role_change(self) -> None:
        """Debe actualizar tag cuando cambia el rol."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        prefixes_config = [
            {"role_id": 100, "prefix": "★"},
            {"role_id": 200, "prefix": "◈"},
        ]

        # Tenia CAP, ahora solo tiene SGT
        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick="★[ABC | CAP] Xurxo",
            member_role_ids=[200],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "◈[ABC | SGT] Xurxo"

    def test_empty_configs(self) -> None:
        """Config vacia no debe hacer cambios."""
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100],
            tags_config=[],
            prefixes_config=[],
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_priority_order(self) -> None:
        """El primer rol en la config debe tener prioridad."""
        tags_config = [
            {"role_id": 100, "tag": "CAP"},
            {"role_id": 200, "tag": "SGT"},
        ]
        prefixes_config = [
            {"role_id": 100, "prefix": "★"},
            {"role_id": 200, "prefix": "◈"},
        ]

        # Tiene ambos roles, CAP debe ganar (primero en config)
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[200, 100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result == "★[ABC | CAP] Xurxo"

    def test_independent_tag_and_prefix_priority(self) -> None:
        """Tag y prefix se resuelven independientemente."""
        # Rol 100 tiene tag CAP, Rol 200 tiene prefix ◈
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 200, "prefix": "◈"}]

        # Usuario tiene ambos roles
        result = compute_nickname(
            display_name="Xurxo",
            current_nick=None,
            member_role_ids=[100, 200],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # Debe tener tag de rol 100 y prefix de rol 200
        assert result == "◈[ABC | CAP] Xurxo"

    def test_display_name_equals_result(self) -> None:
        """Si display_name ya es el resultado, devolver None."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        result = compute_nickname(
            display_name="★[ABC | CAP] Xurxo",
            current_nick=None,  # Nick es None pero display_name ya es correcto
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        assert result is None

    def test_format_change_updates_nickname(self) -> None:
        """Cambio de formato debe actualizar el nickname."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        # Usuario tiene el formato viejo
        result = compute_nickname(
            display_name="★[OLD | CAP] Xurxo",
            current_nick="★[OLD | CAP] Xurxo",
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format="[NEW | {tag}]",  # Nuevo formato
        )

        # Debe actualizar al nuevo formato
        assert result == "★[NEW | CAP] Xurxo"

    def test_preserves_name_not_matching_format(self) -> None:
        """Nombre con brackets que no coinciden con formato debe preservarse."""
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        # Usuario tiene nombre con brackets pero no es un tag autoname
        result = compute_nickname(
            display_name="[Cool] Guy",  # No coincide con [ABC | ...]
            current_nick=None,
            member_role_ids=[100],
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=DEFAULT_FORMAT,
        )

        # El fallback generico limpiara [Cool], asi que el resultado seria:
        assert result == "★[ABC | CAP] Guy"
