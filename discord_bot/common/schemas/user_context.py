"""Contexto del usuario para la verificación de permisos."""

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Contexto del usuario para la verificación de permisos.

    Este modelo representa la identidad y los permisos de un usuario sin
    dependencias específicas de Discord. Tanto los cogs de Discord como
    los enrutadores web pueden crear este contexto desde sus respectivas fuentes.
    """

    user_id: int = Field(description="ID único del usuario")
    guild_id: int = Field(description="ID del gremio/servidor")
    role_ids: list[int] = Field(default_factory=lambda: [], description="IDs de roles del usuario")
    username: str | None = Field(default=None, description="Nombre de visualización del usuario")

    def has_role(self, role_id: int) -> bool:
        """Verifica si el usuario tiene un rol específico.

        Args:
            role_id (int): ID del rol a verificar

        Returns:
            bool: True si el usuario tiene el rol
        """
        return role_id in self.role_ids

    def has_any_role(self, role_ids: list[int]) -> bool:
        """Verifica si el usuario tiene alguno de los roles especificados.

        Args:
            role_ids (list[int]): Lista de IDs de roles a verificar

        Returns:
            bool: True si el usuario tiene al menos uno de los roles
        """
        return any(role_id in self.role_ids for role_id in role_ids)

    def has_all_roles(self, role_ids: list[int]) -> bool:
        """Verifica si el usuario tiene todos los roles especificados.

        Args:
            role_ids (list[int]): Lista de IDs de roles a verificar

        Returns:
            bool: True si el usuario tiene todos los roles
        """
        return all(role_id in self.role_ids for role_id in role_ids)
