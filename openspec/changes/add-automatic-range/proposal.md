## Why

Hoy `clockify-sync` exige `--from` y `--to` en cada ejecución. Eso obliga al
usuario a recordar hasta qué día llenó Clockify la última vez y a calcular el
rango a mano — precisamente el trabajo manual que la herramienta existe para
eliminar. Además impide programar la sincronización (cron, Task Scheduler,
GitHub Actions) porque no hay forma de expresar "desde donde me quedé".

## What Changes

- Nuevo flag `--automatic` / `-a` que deriva el rango de fechas consultando
  Clockify: busca el último día con cualquier entrada del usuario y sincroniza
  desde el día siguiente hasta hoy inclusive.
- `--from` y `--to` dejan de ser obligatorios: se requieren solo cuando NO se
  usa `--automatic`, y se prohíben cuando sí se usa.
- `--automatic` es excluyente con `--force` y `--skip`; es compatible con
  `--dry-run`, `--yes`, `--verbose` y `--holidays`.
- Guard de 20 días implementado como ventana de búsqueda de 21 días: si no hay
  ninguna entrada en la ventana, el comando aborta y pide `--from`.
- Salidas silenciosas para cron: si Clockify ya está al día, o si el rango
  derivado no contiene días hábiles, el comando informa y sale con código 0.

## Capabilities

### New Capabilities
- `auto-range`: derivar el rango de sincronización a partir del estado actual de
  Clockify, incluyendo la ventana de búsqueda, el guard de tamaño, y el contrato
  de flags de la CLI que lo activa.

### Modified Capabilities
- `clockify-sink`: expone el listado de entradas del usuario sin filtrar por
  proyecto ni tag, y publica el cálculo de "día local de una entrada" como parte
  de su superficie pública para que `auto-range` lo consuma.

## Impact

- **Código**: nuevo módulo `src/clockify_automation/auto_range.py`; cambios en
  `cli.py` (flag, validación, resolución de rango, códigos de salida) y en
  `clockify/sink.py` (`_entry_local_date` → `entry_local_date`).
- **Tests**: nuevo `tests/test_auto_range.py`; nuevo `tests/test_cli.py` para el
  contrato de flags.
- **APIs externas**: una llamada adicional a
  `GET /api/v1/workspaces/{ws}/user/{uid}/time-entries` por ejecución con
  `--automatic`, sobre una ventana de 21 días.
- **Docs**: `README.md` (sección de uso, tabla de flags, nota de cron).
- **Sin cambios** en la lógica de JIRA, el allocator, el formato de payload, ni
  en la detección de entradas propias de la automatización.
- **Fuera de scope**: rellenar huecos intermedios (el modo solo avanza el
  frente), cache local de estado, detección de festivos, workflow de CI que lo
  ejecute.
