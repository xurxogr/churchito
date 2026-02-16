"""Funciones puras para el calculo de nicknames."""

import re
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=32)
def build_tag_pattern(tag_format: str) -> re.Pattern[str]:
    """Construir regex para detectar tags en el formato configurado.

    Convierte "[ABC | {tag}]" en un patron que coincide con "[ABC | CAP]", etc.

    Args:
        tag_format: Formato del tag (ej: "[ABC | {tag}]")

    Returns:
        Patron regex compilado
    """
    # Escapar caracteres especiales de regex
    escaped = re.escape(tag_format)
    # Reemplazar el placeholder {tag} escapado con patron para cualquier valor
    tag_pattern = escaped.replace(r"\{tag\}", r"[^\]]+")
    # Patron completo: prefijo opcional (1-5 chars, sin espacio) + tag + espacio + nombre
    full_pattern = rf"^(?:[^\[\]]{{1,5}})?{tag_pattern}\s+(.+)$"
    return re.compile(full_pattern)


# Patron generico de fallback para tags con estructura [ALGO | ALGO]
# Usado cuando el formato cambia para limpiar tags del formato anterior
# El prefijo (1-5 chars, sin espacio) solo se elimina si va seguido de un tag entre corchetes
GENERIC_TAG_RE = re.compile(r"^(?:(?:[^\[\]]{1,5})?\[[^\]]+\]\s+)?(.+)$")


def extract_base_name(
    display_name: str,
    tag_format: str,
    known_prefixes: list[str] | None = None,
) -> str:
    """Extraer el nombre base quitando el tag y/o prefix si coinciden.

    Primero intenta coincidir con el formato configurado.
    Si no coincide, usa un patron generico como fallback (para cambios de formato).
    Finalmente, intenta quitar prefijos conocidos si no hay tag.

    Args:
        display_name: Nombre actual a mostrar
        tag_format: Formato del tag (ej: "[ABC | {tag}]")
        known_prefixes: Lista de prefijos conocidos a quitar

    Returns:
        Nombre base sin tags ni prefijos
    """
    name = display_name.strip()

    # Intentar con el formato configurado
    pattern = build_tag_pattern(tag_format)
    match = pattern.match(name)
    if match:
        return match.group(1).strip()

    # Fallback: patron generico para limpiar tags de formato anterior
    match = GENERIC_TAG_RE.match(name)
    if match:
        extracted = match.group(1).strip()
        # Si el fallback extrajo algo diferente, usarlo
        if extracted != name:
            return extracted

    # Quitar prefijo conocido si no hay tag (ej: "★ Xurxo" -> "Xurxo")
    if known_prefixes:
        for prefix in known_prefixes:
            if prefix and name.startswith(prefix + " "):
                return name[len(prefix) + 1 :].strip()

    return name


def find_matching_value(
    member_role_ids: list[int],
    roles_config: list[dict[str, Any]],
    value_key: str,
) -> str | None:
    """Encontrar el primer valor que coincida con un rol del miembro.

    La lista roles_config esta ordenada por prioridad (primer match gana).

    Args:
        member_role_ids: IDs de roles del miembro
        roles_config: Lista de {"role_id": int|str, value_key: str}
        value_key: Clave del valor a extraer (ej: "tag" o "prefix")

    Returns:
        Valor del primer rol coincidente o None
    """
    member_role_set = set(member_role_ids)
    for role_config in roles_config:
        role_id = role_config.get("role_id")
        if role_id:
            # Handle both string and int role_ids (web form saves as string)
            try:
                role_id_int = int(role_id)
                if role_id_int in member_role_set:
                    value = role_config.get(value_key, "")
                    return str(value) if value else ""
            except (ValueError, TypeError):
                continue
    return None


def build_nickname(
    base_name: str,
    tag: str,
    prefix: str,
    tag_format: str,
) -> str:
    """Construir el nickname completo con prefix, tag y nombre.

    Args:
        base_name: Nombre base del usuario
        tag: Tag a insertar (ej: "CAP")
        prefix: Prefijo unicode (ej: "★")
        tag_format: Formato del tag (ej: "[ABC | {tag}]")

    Returns:
        Nickname completo, truncado a 32 caracteres si es necesario
    """
    # Si hay prefix o tag, siempre aplicar el formato (tag puede estar vacio)
    # Ej: prefix="★ ", tag="" → "★ [ABC | ] Xurxo" (espacio incluido en prefix)
    formatted_tag = tag_format.format(tag=tag) if (tag or prefix) else ""

    # Construir nickname: prefix se pega directamente (sin espacio extra)
    # Si el usuario quiere espacio, lo incluye en el prefix: "★ " en vez de "★"
    if prefix and formatted_tag:
        prefix_part = f"{prefix}{formatted_tag}"
        nickname = f"{prefix_part} {base_name}"
    elif prefix:
        prefix_part = prefix
        nickname = f"{prefix_part} {base_name}"
    elif formatted_tag:
        prefix_part = formatted_tag
        nickname = f"{prefix_part} {base_name}"
    else:
        prefix_part = ""
        nickname = base_name

    # Truncar a 32 caracteres (limite de Discord)
    if len(nickname) > 32:
        if prefix_part:
            # Calcular espacio disponible para el nombre base
            available = 32 - len(prefix_part) - 1  # -1 for space
            if available > 0:
                nickname = f"{prefix_part} {base_name[:available]}"
            else:
                # No hay espacio suficiente, usar solo nombre truncado
                nickname = base_name[:32]
        else:
            nickname = base_name[:32]

    return nickname


def compute_nickname(
    display_name: str,
    current_nick: str | None,
    member_role_ids: list[int],
    tags_config: list[dict[str, Any]],
    prefixes_config: list[dict[str, Any]],
    tag_format: str,
) -> str | None:
    """Calcular el nuevo nickname para un miembro.

    Args:
        display_name: Nombre a mostrar actual (nick o username)
        current_nick: Nick actual del miembro (puede ser None)
        member_role_ids: IDs de roles del miembro
        tags_config: Lista de {"role_id": int, "tag": str}
        prefixes_config: Lista de {"role_id": int, "prefix": str}
        tag_format: Formato del tag (ej: "[ABC | {tag}]")

    Returns:
        Nuevo nickname o None si no hay cambio necesario
    """
    # Extraer prefijos conocidos de la config
    known_prefixes = [cfg.get("prefix", "") for cfg in prefixes_config if cfg.get("prefix")]

    # Extraer nombre base usando el formato configurado y prefijos conocidos
    base_name = extract_base_name(
        display_name=display_name, tag_format=tag_format, known_prefixes=known_prefixes
    )

    # Encontrar tag y prefix coincidentes (independientes)
    tag = find_matching_value(
        member_role_ids=member_role_ids, roles_config=tags_config, value_key="tag"
    )
    prefix = find_matching_value(
        member_role_ids=member_role_ids, roles_config=prefixes_config, value_key="prefix"
    )

    # Si no hay ni tag ni prefix, limpiar el nickname si tenia algo
    if tag is None and prefix is None:
        if base_name != display_name and base_name != current_nick:
            return base_name
        return None

    # Construir nuevo nickname
    new_nickname = build_nickname(
        base_name=base_name, tag=tag or "", prefix=prefix or "", tag_format=tag_format
    )

    # Verificar si hay cambio
    if new_nickname == current_nick or new_nickname == display_name:
        return None

    return new_nickname
