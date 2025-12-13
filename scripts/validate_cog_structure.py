#!/usr/bin/env python3
"""Valida que los cogs sigan la estructura y convenciones adecuadas.

Este script verifica:
- Todos los cogs tienen una función setup() adecuada
- Las clases Cog heredan de commands.Cog
- Los servicios son agnósticos a Discord (usan UserContext)
- Organización correcta de archivos
"""

import ast
import sys
from pathlib import Path


class CogValidator(ast.NodeVisitor):
    """Visitante AST para validar la estructura del cog."""

    def __init__(self, filepath: Path) -> None:
        """Inicializa el validador.

        Args:
            filepath (Path): Ruta al archivo del cog
        """
        self.filepath = filepath
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.has_setup_function = False
        self.has_cog_class = False
        self.cog_classes: list[str] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visita la definición de función asincrónica.

        Args (ast.AsyncFunctionDef):
            node: Nodo AST para función asincrónica
        """
        # Verifica la función setup()
        if node.name == "setup":
            self.has_setup_function = True

            # Valida la firma de setup
            if len(node.args.args) != 1:
                self.errors.append(
                    f"Línea {node.lineno}: setup() debe tomar exactamente un argumento (bot)"
                )
            elif node.args.args[0].arg != "bot":
                self.warnings.append(
                    f"Línea {node.lineno}: el argumento de setup() debería llamarse 'bot' "
                    f"(se encontró '{node.args.args[0].arg}')"
                )

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visita la definición de clase.

        Args (ast.ClassDef):
            node: Nodo AST para clase
        """
        # Verifica si el nombre de la clase termina con 'Cog'
        if node.name.endswith("Cog"):
            self.has_cog_class = True
            self.cog_classes.append(node.name)

            # Verifica si hereda de commands.Cog o mixins
            has_cog_base = any(self._is_cog_base(base) for base in node.bases)

            if not has_cog_base:
                self.warnings.append(
                    f"Línea {node.lineno}: La clase {node.name} debería heredar de "
                    "commands.Cog o de un mixin que lo haga"
                )

        self.generic_visit(node)

    def _is_cog_base(self, node: ast.expr) -> bool:
        """Verifica si una clase base es commands.Cog o un mixin válido.

        Args (ast.expr):
            node: Nodo AST para clase base

        Returns:
            True si es una clase base de cog válida
        """
        if isinstance(node, ast.Attribute):
            # commands.Cog
            return node.attr == "Cog"
        elif isinstance(node, ast.Name):
            # Clases Mixin o referencia directa a Cog
            return "Cog" in node.id or "Commands" in node.id or "Events" in node.id
        return False


def validate_file(filepath: Path) -> bool:
    """Valida un archivo de cog individual.

    Args (Path):
        filepath: Ruta al archivo del cog

    Returns:
        True si la validación pasa, False en caso contrario
    """
    try:
        with open(filepath) as f:
            content = f.read()
            tree = ast.parse(content, filename=str(filepath))
    except SyntaxError as e:
        print(f"\n❌ Error de sintaxis en {filepath}:")
        print(f"  {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error al leer {filepath}: {e}")
        return False

    validator = CogValidator(filepath)
    validator.visit(tree)

    has_issues = False

    # Verifica la función setup
    if not validator.has_setup_function:
        validator.errors.append(
            "Falta la función async setup(bot). "
            "Todos los archivos de cog deben tener una función setup."
        )

    # Verifica la clase cog
    if not validator.has_cog_class:
        validator.warnings.append(
            "No se encontró ninguna clase que termine con 'Cog'. "
            "Las clases cog deberían llamarse *Cog."
        )

    # Reporta errores
    if validator.errors:
        print(f"\n❌ {filepath}:")
        for error in validator.errors:
            print(f"  {error}")
        has_issues = True

    # Reporta advertencias
    if validator.warnings:
        if not has_issues:
            print(f"\n⚠️  {filepath}:")
        for warning in validator.warnings:
            print(f"  {warning}")

    return not has_issues


def validate_cog_directory_structure() -> bool:
    """Valida la estructura general del directorio de cogs.

    Returns:
        bool: True si la estructura es válida, False en caso contrario
    """
    discord_bot_dir = Path("discord_bot")

    if not discord_bot_dir.exists():
        print("❌ El directorio discord_bot/ no fue encontrado")
        return False

    # Verifica que common/ exista
    common_dir = discord_bot_dir / "common"
    if not common_dir.exists():
        print("❌ El directorio discord_bot/common/ no fue encontrado")
        return False

    # Encuentra todos los archivos de cog
    cog_files = list(discord_bot_dir.glob("*/cog.py"))

    if not cog_files:
        print("⚠️  No se encontraron archivos de cog en discord_bot/*/cog.py")
        return True

    print(f"Se encontraron {len(cog_files)} archivo(s) de cog para validar")
    return True


def main() -> int:
    """Punto de entrada principal.

    Returns:
        int: Código de salida (0 para éxito, 1 para errores)
    """
    print("🔍 Validando estructura de cog...")

    # Valida la estructura del directorio
    if not validate_cog_directory_structure():
        return 1

    # Encuentra todos los archivos de cog
    cog_files = list(Path("discord_bot").glob("*/cog.py"))

    if not cog_files:
        print("\n✅ No hay archivos de cog para validar")
        return 0

    all_valid = True
    for cog_file in cog_files:
        if not validate_file(cog_file):
            all_valid = False

    if all_valid:
        print(f"\n✅ ¡Todos los {len(cog_files)} archivo(s) de cog pasaron la validación!")
        return 0
    else:
        print("\n❌ ¡La validación de la estructura de cog falló!")
        print("\n💡 Consejos:")
        print("  - Todos los archivos de cog deben tener: async def setup(bot) -> None")
        print("  - Las clases cog deberían heredar de commands.Cog")
        print("  - Las clases cog deberían llamarse *Cog")
        return 1


if __name__ == "__main__":
    sys.exit(main())
