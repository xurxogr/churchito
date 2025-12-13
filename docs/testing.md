# Guía de Testing

## Filosofía de Testing

Este proyecto sigue una **arquitectura basada en características** con clara separación entre lógica de negocio y código de interfaz de Discord. Cada capa tiene diferentes características de testabilidad y expectativas de cobertura.

## Estrategia de Cobertura

### Cobertura Objetivo por Capa

| Capa | Objetivo | Justificación |
|------|----------|---------------|
| **Lógica de Negocio** (Servicios) | 95-100% | Lógica pura, totalmente testeable |
| **Capa de Datos** (Modelos, Schemas) | 95-100% | Clases simples, fáciles de testear |
| **Infraestructura Principal** | 95-100% | Código framework, crítico |
| **Interfaz Discord** (Cogs) | 50-70% | Pesado en UI, mejor para tests de integración |
| **Proyecto General** | 75-85% | Cobertura balanceada |

## La Arquitectura Asegura Testeabilidad

El principio clave: **La lógica de negocio es agnóstica de Discord y está testeada al 95%+.**

```
┌─────────────────────────────────────────────────┐
│ Cogs de Discord (50-70% cobertura)              │
│ - Adaptadores DELGADOS                          │
│ - Parsean objetos de Discord → UserContext/primitivos│
│ - Llaman a servicios                            │
│ - Formatean respuestas                          │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│ Servicios (95-100% cobertura)                   │
│ - TODA la lógica de negocio                     │
│ - SIN dependencias de Discord                   │
│ - Recibe UserContext/primitivos                 │
│ - Retorna modelos/primitivos                    │
│ - Totalmente testeable con tests unitarios      │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│ Modelos/Conectores (95-100% cobertura)          │
│ - Modelos de base de datos (SQLAlchemy)         │
│ - DTOs (Pydantic)                               │
│ - Clientes de APIs externas                     │
│ - Lógica pura, totalmente testeable             │
└─────────────────────────────────────────────────┘
```

## Organización de Tests

Los tests reflejan la estructura del código:

```
tests/
├── common/                 # Tests para código compartido
│   ├── models/            # Tests de modelos de base de datos
│   ├── schemas/           # Tests de DTOs de Pydantic
│   ├── services/          # Tests de servicios compartidos
│   ├── enums/             # Tests de enums
│   └── core/              # Tests de infraestructura principal
├── general/               # Tests del cog general
├── conftest.py            # Fixtures compartidas
└── test_main.py           # Tests del punto de entrada
```

## Ejecutar Tests

### Comandos Básicos

```bash
# Ejecutar todos los tests
pytest

# Ejecutar con reporte de cobertura
pytest --cov=discord_bot --cov-report=term-missing

# Generar reporte HTML de cobertura
pytest --cov=discord_bot --cov-report=html
open htmlcov/index.html

# Ejecutar tests de una característica específica
pytest tests/common/

# Ejecutar con salida verbosa
pytest -v

# Ejecutar archivo de test específico
pytest tests/common/services/test_database.py

# Ejecutar test específico
pytest tests/common/services/test_database.py::test_database_initialization
```

### Cobertura por Capa

```bash
# Testear lógica de negocio (debería ser 95%+)
pytest tests/common/services/ --cov=discord_bot

# Testear capa de datos (debería ser 95-100%)
pytest tests/common/models/ tests/common/schemas/ --cov=discord_bot

# Testear interfaz de Discord (esperar 50-70%)
pytest tests/general/ --cov=discord_bot
```

## Qué Testear

### ✅ Testear Completamente (95-100% cobertura)

**Servicios (Lógica de Negocio):**
- Comprobaciones de permisos
- Lógica de flujo de trabajo
- Gestión de configuración
- Manejo de errores
- Casos extremos

**Modelos y Schemas:**
- Validación de campos
- Relaciones
- Métodos auxiliares
- Serialización/deserialización

**Conectores:**
- Llamadas a APIs
- Manejo de errores
- Parseo de respuestas
- Lógica de reintentos

**Ejemplo:**
```python
# tests/common/services/test_event_bus.py

def test_subscribe_and_emit(event_bus):
    """Test suscripción y emisión de eventos."""
    received_data = []

    def handler(data):
        received_data.append(data)

    # Suscribirse
    event_bus.subscribe("test.event", handler)

    # Emitir
    event_bus.emit("test.event", {"foo": "bar"})

    assert len(received_data) == 1
    assert received_data[0] == {"foo": "bar"}
```

### ⚠️ Testear Parcialmente (50-70% cobertura)

**Cogs de Discord:**
- Registro de comandos
- Manejo básico de interacciones
- Rutas de error (sin servidor, sin permisos)
- Métodos auxiliares

**Qué NO testear en exceso:**
- Flujos UI complejos de múltiples pasos (botones → modales → formularios)
- Jerarquías de permisos de Discord
- Detalles de formato de mensajes/embeds

**Ejemplo:**
```python
# tests/general/test_cog.py

async def test_ping_command(general_cog, mock_context, mock_bot):
    """Test comando ping."""
    await general_cog.ping.callback(general_cog, mock_context)

    # Verificar que se envió el mensaje
    mock_context.send.assert_called_once()
    sent_message = mock_context.send.call_args[0][0]
    assert "Pong!" in sent_message
```

### ❌ Tests de Integración (No tests unitarios)

Estos pertenecen a suites de tests end-to-end:
- Interacciones reales del bot de Discord
- Clicks reales de botones y envíos de modales
- Asignación de roles vía API de Discord
- Historial de mensajes y reacciones
- Eventos del gateway

## Fixtures de Tests

Fixtures exhaustivas en `tests/conftest.py`:

```python
@pytest.fixture
async def test_database() -> DatabaseService:
    """Proveer base de datos de test en memoria."""
    # Limpieza automática después de cada test

@pytest.fixture
def test_settings() -> AppSettings:
    """Proveer configuración de aplicación de test."""

@pytest.fixture
def mock_bot() -> MagicMock:
    """Proveer bot de Discord mockeado."""

@pytest.fixture
def mock_context() -> MagicMock:
    """Proveer contexto de comando mockeado."""
```

## Escribir Nuevos Tests

### Patrón 1: Tests de Servicios (Apuntar a 95%+)

```python
@pytest.mark.asyncio
async def test_service_method(test_database):
    """Test lógica de negocio del servicio."""
    # Arrange (Preparar)
    service = MyService(test_database)

    # Act (Actuar)
    result = await service.some_method("test_data")

    # Assert (Afirmar)
    assert result.status == "success"
```

### Patrón 2: Tests de Modelos

```python
def test_model_validation():
    """Test validación del modelo Pydantic."""
    # Entrada válida
    context = UserContext(user_id=123, guild_id=456)
    assert context.user_id == 123

    # Entrada inválida
    with pytest.raises(ValidationError):
        UserContext(user_id=123)  # Falta guild_id
```

### Patrón 3: Tests de Cogs (Apuntar a 50-70%)

```python
@pytest.mark.asyncio
async def test_cog_command_happy_path(cog, mock_context):
    """Test comando del cog con servicio mockeado."""
    # Mockear la capa de servicio
    with patch.object(cog, 'get_service') as mock_service:
        mock_service.return_value.process.return_value = True

        # Llamar comando del cog
        await cog.my_command.callback(cog, mock_context)

        # Verificar que se llamó al servicio
        mock_service.return_value.process.assert_called_once()
```

## Por Qué los Cogs Tienen Menor Cobertura

### Complejidad de las Interacciones de Discord

Los cogs de Discord contienen código UI que es difícil de testear unitariamente:

1. **Flujos de múltiples pasos:** Botón → Modal → Formulario → Asignación de rol
2. **Jerarquía de objetos de Discord:** Guild → Channel → Member → Role
3. **Sistema de eventos async:** Requiere mockeo extensivo
4. **Gestión de estado:** Las interacciones abarcan múltiples callbacks async

### Mejor Adaptado para Tests de Integración

Los flujos completos de Discord deberían testearse con:
- Bot real de Discord en servidor de test
- Interacciones reales de botones/modales
- Respuestas reales de la API de Discord
- Simulación de eventos del gateway

## Mejores Prácticas

### HACER ✅

- Testear exhaustivamente la lógica de negocio en servicios
- Usar `UserContext` para desacoplar de Discord
- Mockear dependencias externas (APIs, Discord)
- Testear casos de error y casos extremos
- Usar fixtures para configuraciones comunes
- Apuntar a 95%+ de cobertura en servicios

### NO HACER ❌

- Testear en exceso código UI de Discord con mocks complejos
- Testear internals de Discord.py
- Duplicar tests entre capas de servicio y cog
- Usar `type: ignore` para saltar errores de tipo
- Escribir tests solo por números de cobertura

## Integración Continua

```bash
# Ejecutar en pipeline de CI
pytest --cov=discord_bot --cov-report=xml --cov-fail-under=75

# Type checking
mypy discord_bot

# Linting
ruff check .

# Comprobación de formato
ruff format --check .
```

## Resumen

- **Servicios: 95-100%** - Toda la lógica de negocio completamente testeada
- **Modelos/Schemas: 95-100%** - Validación de datos cubierta
- **Core: 95-100%** - Infraestructura bien testeada
- **Cogs: 50-70%** - Aceptable para código pesado en UI
- **General: 75-85%** - Cobertura fuerte donde importa

La arquitectura basada en características asegura que la lógica crítica es agnóstica de Discord, totalmente testeable y mantenible.
