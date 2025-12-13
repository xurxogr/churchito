# Guía de Contribución

¡Gracias por contribuir a este proyecto de bot de Discord! Esta guía te ayudará a escribir código que siga las mejores prácticas y pase todas las comprobaciones automatizadas.

## ⚠️ Reglas Críticas - Estabilidad del Bot

### NUNCA Usar Operaciones Bloqueantes

Las operaciones bloqueantes **congelarán todo el bot** para todos los usuarios. Todos los cogs comparten el mismo event loop.

#### ❌ INCORRECTO - Operaciones Bloqueantes

```python
import time
import requests

@commands.command()
async def comando_malo(self, ctx):
    time.sleep(5)  # ❌ BLOQUEA TODO EL BOT

    response = requests.get("https://api.example.com")  # ❌ BLOQUEA

    with open("archivo.txt") as f:  # ❌ BLOQUEA
        data = f.read()
```

#### ✅ CORRECTO - Operaciones No Bloqueantes

```python
import asyncio
import httpx
import aiofiles

@commands.command()
async def comando_bueno(self, ctx):
    await asyncio.sleep(5)  # ✅ No bloqueante

    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")  # ✅ No bloqueante

    async with aiofiles.open("archivo.txt") as f:  # ✅ No bloqueante
        data = await f.read()
```

### Operaciones Intensivas de CPU

Para tareas pesadas de CPU (procesamiento de imágenes, cálculos complejos), usa threading:

```python
import asyncio

def calculo_pesado(data):
    """Trabajo intensivo de CPU (no async)."""
    return sum(i**2 for i in range(data))

@commands.command()
async def calcular(self, ctx, numero: int):
    # Delegar a thread pool - no bloquea el event loop
    resultado = await asyncio.to_thread(calculo_pesado, numero)
    await ctx.send(f"Resultado: {resultado}")
```

## Principios de Arquitectura

### Organización Basada en Características

```
discord_bot/
├── common/              # Código compartido (2+ características)
│   ├── models/         # Modelos de BD compartidos
│   ├── schemas/        # DTOs compartidos (UserContext)
│   ├── services/       # Servicios compartidos
│   └── decorators.py   # Decoradores compartidos
├── micaracteristica/   # Código específico de característica
│   ├── models/         # Modelos de la característica
│   ├── schemas/        # DTOs de la característica
│   ├── services/       # Lógica de negocio
│   └── cog.py          # Interfaz de Discord
```

**Regla:** Si el código es usado por 2+ características → `common/`. Si es usado por 1 característica → mantenerlo en la carpeta de la característica.

### Los Servicios Son Agnósticos de Discord

Los servicios contienen lógica de negocio y trabajan con primitivos/`UserContext`, no con objetos de Discord.

#### ❌ INCORRECTO - Objetos de Discord en servicio

```python
class MiServicio:
    async def verificar_permiso(self, member: discord.Member) -> bool:
        # ¡El servicio depende de Discord!
        return any(role.id == 123 for role in member.roles)
```

#### ✅ CORRECTO - Servicio agnóstico de Discord

```python
from discord_bot.common.schemas import UserContext

class MiServicio:
    async def verificar_permiso(self, user: UserContext) -> bool:
        # Funciona sin Discord - testeable, reutilizable
        return user.has_role(123)
```

### Los Cogs Son Adaptadores Delgados

Los cogs manejan I/O de Discord y delegan a servicios:

```python
@commands.command()
async def micomando(self, interaction: discord.Interaction):
    # 1. Extraer primitivos de objetos de Discord
    user_context = UserContext(
        user_id=interaction.user.id,
        guild_id=interaction.guild.id,
        role_ids=[r.id for r in interaction.user.roles]
    )

    # 2. Llamar al servicio (lógica de negocio testeable)
    servicio = await self._get_service()
    resultado = await servicio.hacer_algo(user_context)

    # 3. Formatear respuesta para Discord
    await interaction.response.send_message(f"Resultado: {resultado}")
```

## Crear Nuevos Cogs

### Creación Manual

1. **Crear directorio de característica:**
   ```bash
   mkdir discord_bot/mi_caracteristica
   touch discord_bot/mi_caracteristica/__init__.py
   ```

2. **Crear archivo de cog:** `discord_bot/mi_caracteristica/cog.py`
   ```python
   from discord.ext import commands
   import logging

   logger = logging.getLogger(__name__)

   class MiCaracteristicaCog(commands.Cog):
       """Cog de mi característica."""

       def __init__(self, bot: commands.Bot) -> None:
           self.bot = bot

       @commands.command()
       async def micomando(self, ctx: commands.Context) -> None:
           """Mi comando."""
           await ctx.send("¡Hola!")
           logger.info(f"Comando ejecutado por {ctx.author}")

   async def setup(bot: commands.Bot) -> None:
       """Cargar el cog."""
       await bot.add_cog(MiCaracteristicaCog(bot))
   ```

3. **Cargar cog en `bot.py`:**
   ```python
   cogs_to_load = [
       # ...
       "discord_bot.mi_caracteristica.cog",
   ]
   ```

4. **Crear tests:** `tests/mi_caracteristica/test_cog.py`

## Requisitos de Testing

### Objetivos de Cobertura

| Capa | Objetivo | Por Qué |
|------|----------|---------|
| Servicios | 95-100% | Lógica pura, totalmente testeable |
| Modelos/Schemas | 95-100% | Clases simples |
| Cogs | 50-70% | Pesado en UI, material de test de integración |
| General | 75-85% | Balanceado |

### Escribir Tests

**Testear servicios exhaustivamente:**

```python
@pytest.mark.asyncio
async def test_verificacion_permiso_servicio():
    """Test lógica de verificación de permisos."""
    servicio = MiServicio(session)

    # Usuario con rol
    usuario_con_rol = UserContext(user_id=1, guild_id=2, role_ids=[123])
    assert await servicio.puede_usar(usuario_con_rol) is True

    # Usuario sin rol
    usuario_sin_rol = UserContext(user_id=1, guild_id=2, role_ids=[])
    assert await servicio.puede_usar(usuario_sin_rol) is False
```

**Testear cogs ligeramente:**

```python
@pytest.mark.asyncio
async def test_cog_llama_servicio(mock_bot):
    """Test que el cog delega al servicio."""
    cog = MiCog(mock_bot)

    with patch.object(cog, '_get_service') as mock_service:
        mock_service.return_value.hacer_algo.return_value = "resultado"

        await cog.micomando.callback(cog, mock_interaction)

        mock_service.return_value.hacer_algo.assert_called_once()
```

## Checklist Pre-commit

Antes de hacer commit, asegúrate de:

```bash
# 1. Ejecutar pre-commit hooks (incluye comprobaciones ASYNC de Ruff para operaciones bloqueantes)
pre-commit run --all-files

# 2. Ejecutar tests con cobertura
pytest --cov=discord_bot --cov-report=term

# 3. Type checking
mypy discord_bot/
```

Todas estas comprobaciones se ejecutan automáticamente en CI, pero ejecutarlas localmente ahorra tiempo.

**Nota:** Las reglas ASYNC de Ruff detectan automáticamente operaciones bloqueantes como `time.sleep()`, `requests.get()`, y `open()` en funciones async.

## Herramientas de Calidad de Código

### Ruff (Linter + Formateador)

Ruff incluye reglas ASYNC que detectan automáticamente operaciones bloqueantes:

```bash
# Comprobar código (incluye ASYNC251, ASYNC210, ASYNC230 para detección de bloqueos)
ruff check discord_bot/

# Auto-arreglar problemas
ruff check --fix discord_bot/

# Formatear código
ruff format discord_bot/

# Comprobar solo reglas ASYNC
ruff check --select ASYNC discord_bot/
```

**Reglas ASYNC de Ruff:**
- `ASYNC251` - Detecta `time.sleep()` en funciones async
- `ASYNC210` - Detecta llamadas HTTP bloqueantes (`requests.*`)
- `ASYNC230` - Detecta operaciones de archivo bloqueantes (`open()`)
- Más patrones async/await

### MyPy (Type Checking)

```bash
# Comprobar tipos
mypy discord_bot/

# Comprobar archivo específico
mypy discord_bot/mi_caracteristica/cog.py
```

## Patrones Comunes

### Usando el Decorador de Timeout

Protege contra operaciones bloqueantes:

```python
from discord_bot.common.decorators import timeout

@timeout(10)  # Timeout después de 10 segundos
@commands.command()
async def micomando(self, ctx):
    # Si esto toma >10s, el usuario recibe mensaje de error
    await operacion_larga()
```

### Usando el Decorador de Retry

Para operaciones que pueden fallar temporalmente:

```python
from discord_bot.common.decorators import retry

@retry(max_attempts=3, delay=1.0, backoff=2.0)
async def obtener_datos(self):
    """Reintenta con backoff exponencial: 1s, 2s, 4s."""
    async with httpx.AsyncClient() as client:
        return await client.get("https://api.example.com")
```

### Verificación de Permisos con UserContext

```python
from discord_bot.common.schemas import UserContext

# Crear UserContext desde interacción de Discord
user_context = UserContext(
    user_id=interaction.user.id,
    guild_id=interaction.guild.id,
    role_ids=[role.id for role in interaction.user.roles]
    if isinstance(interaction.user, discord.Member) else [],
    username=interaction.user.name
)

# Comprobar permisos (agnóstico de Discord)
if user_context.has_role(ADMIN_ROLE_ID):
    # El usuario es admin
    pass

if user_context.has_any_role([MOD_ROLE, ADMIN_ROLE]):
    # El usuario es mod o admin
    pass

if user_context.has_all_roles([VERIFIED_ROLE, MEMBER_ROLE]):
    # El usuario tiene ambos roles
    pass
```

## Errores Comunes

### 1. Usar time.sleep()

❌ **Incorrecto:**
```python
time.sleep(5)  # ¡Bloquea todo el bot!
```

✅ **Correcto:**
```python
await asyncio.sleep(5)  # No bloqueante
```

### 2. Usar la librería requests

❌ **Incorrecto:**
```python
import requests
response = requests.get("https://api.example.com")  # ¡Bloquea!
```

✅ **Correcto:**
```python
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com")
```

### 3. I/O de archivos síncrono

❌ **Incorrecto:**
```python
with open("archivo.txt") as f:  # ¡Bloquea!
    data = f.read()
```

✅ **Correcto:**
```python
import aiofiles
async with aiofiles.open("archivo.txt") as f:
    data = await f.read()
```

### 4. Olvidar usar await

❌ **Incorrecto:**
```python
resultado = servicio.hacer_algo()  # ¡Retorna coroutine, no ejecuta!
```

✅ **Correcto:**
```python
resultado = await servicio.hacer_algo()
```

### 5. Objetos de Discord en servicios

❌ **Incorrecto:**
```python
class MiServicio:
    async def procesar(self, member: discord.Member):
        # Ata el servicio a Discord
        pass
```

✅ **Correcto:**
```python
class MiServicio:
    async def procesar(self, user: UserContext):
        # Agnóstico de Discord, testeable
        pass
```

## Pipeline de CI/CD

Todos los pull requests ejecutan automáticamente:

1. **Comprobaciones de Ruff** - Linting, formateo, y reglas ASYNC (detección de bloqueos)
2. **MyPy** - Type checking
3. **Suite de tests** - Debe pasar con 75%+ de cobertura

Corrige cualquier fallo antes de mergear.

**Nota:** Las reglas ASYNC de Ruff capturan operaciones bloqueantes automáticamente - ¡no se necesitan scripts personalizados!

## Obtener Ayuda

- **Problemas de configuración:** Ver [docs/setup.md](setup.md)
- **Preguntas de testing:** Ver [docs/testing.md](testing.md)
- **Ayuda con async/await:** Consulta la documentación de asyncio de Python
- **Ayuda con Discord.py:** Ver [documentación de discord.py](https://discordpy.readthedocs.io/)

## Checklist de Resumen

Antes de enviar un PR:

- [ ] Sin operaciones bloqueantes (`time.sleep`, `requests`, I/O de archivos síncrono)
- [ ] Todas las funciones async usan `await` correctamente
- [ ] Los servicios son agnósticos de Discord (usan `UserContext`)
- [ ] El cog tiene función `async def setup(bot)`
- [ ] Tests escritos (95%+ para servicios, 50%+ para cogs)
- [ ] Los pre-commit hooks pasan
- [ ] Todas las comprobaciones de CI pasan
- [ ] El código sigue la estructura basada en características

¡Gracias por seguir estas guías! Mantienen el bot estable y mantenible.
