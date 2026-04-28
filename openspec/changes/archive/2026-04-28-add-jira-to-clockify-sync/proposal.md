## Why

Hoy registrar manualmente las horas trabajadas en Clockify duplica el esfuerzo de gestión que ya queda reflejado de forma orgánica en JIRA al mover tickets a "In Progress". El registro no requiere precisión de auditoría — solo evidencia de dedicación — pero hacerlo a mano es tedioso, fácil de olvidar y desincentiva el seguimiento. Una automatización que traduzca actividad de JIRA a entries de Clockify recupera ese tiempo y mantiene el calendario al día sin disciplina extra.

## What Changes

- Nueva CLI en Python `clockify-sync` que recibe un rango de fechas y crea time entries en Clockify a partir de actividad detectada en JIRA.
- Detección de tickets "trabajados" mediante JQL (`assignee was currentUser() AND status was "In Progress" DURING (...)`) y reconstrucción de intervalos vía changelog.
- Reparto determinístico de las 8 horas laborales (9:00–17:00, L–V, zona `America/Mexico_City`) entre los tickets activos de cada día, en bloques de horas enteras y orden alfabético.
- Archivo `holidays.yaml` committeado para excluir festivos del rango.
- Idempotencia: el comando aborta por defecto si encuentra entries propios previos en el rango; flags `--dry-run`, `--force` y `--skip` cubren los casos de re-ejecución.
- Configuración 100% por variables de entorno (mismo código corre con `.env` local o secrets/vars de GitHub Actions).

## Capabilities

### New Capabilities
- `jira-source`: autenticación contra JIRA Cloud, búsqueda JQL, descarga de changelog y reconstrucción de intervalos `(assignee=usuario ∧ status="In Progress")` por ticket.
- `time-allocator`: lógica pura, sin I/O, que toma `(rango, festivos, mapa día→tickets)` y produce entries con start/end según el algoritmo `base + sobrante` en horas enteras.
- `clockify-sink`: autenticación contra Clockify, detección de entries propios (proyecto+tag+regex de descripción), creación de time entries y políticas `--force` / `--skip` / `--dry-run`.

### Modified Capabilities
<!-- Ninguna: proyecto greenfield, no hay specs previos -->

## Impact

- **Código nuevo**: paquete Python `src/clockify_automation/` con módulos para JIRA, Clockify, allocator y CLI; tests unitarios sobre allocator y reconstrucción de intervalos.
- **Configuración nueva**: `pyproject.toml` (uv), `.env.example`, `.gitignore`, `holidays.yaml`, `README.md`.
- **APIs externas**: JIRA Cloud REST v3 (`/rest/api/3/search`, `/rest/api/3/issue/{key}?expand=changelog`) con autenticación Basic; Clockify v1 (`/api/v1/workspaces/.../time-entries`) con header `X-Api-Key`.
- **Credenciales**: API token de JIRA, API key de Clockify, IDs de workspace/project/tag — gestionados localmente vía `.env` (gitignored) y luego como secrets/vars de GitHub Actions.
- **Sin impacto en sistemas existentes**: proyecto greenfield, no se modifica ningún workflow ni se escribe nada de vuelta en JIRA.
- **Fuera de scope**: workflow de GitHub Actions (preparado por config pero no implementado), múltiples proyectos Clockify, edición de entries existentes, detección automática de festivos, UI web/desktop.
