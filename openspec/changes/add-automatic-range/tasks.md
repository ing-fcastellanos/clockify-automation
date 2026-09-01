## 1. Clockify sink — superficie reutilizable

- [x] 1.1 En `clockify/sink.py`, renombrar `_entry_local_date` a `entry_local_date` y mover el `from zoneinfo import ZoneInfo` local de la función al nivel de módulo.
- [x] 1.2 Exportar `entry_local_date` desde `clockify/__init__.py`.

## 2. Módulo auto-range

- [x] 2.1 Crear `src/clockify_automation/auto_range.py` con las constantes `MAX_RANGE_DAYS = 20` y `LOOKBACK_DAYS = MAX_RANGE_DAYS + 1`, documentando que la ventana implementa el guard.
- [x] 2.2 Definir `AutomaticRange` (dataclass frozen: `last_entry_date`, `from_date`, `to_date`) y la excepción `NoRecentEntriesError`.
- [x] 2.3 Implementar `find_last_entry_date(settings, today, lookback_days=LOOKBACK_DAYS) -> date | None`: lista las entradas del usuario en la ventana sin filtrar por proyecto/tag y devuelve el máximo día local.
- [x] 2.4 Implementar `resolve_automatic_range(settings, today=None, lookback_days=LOOKBACK_DAYS) -> AutomaticRange | None`: resuelve `today` en la zona configurada cuando falta, lanza `NoRecentEntriesError` si no hay entradas, devuelve `None` si `D >= today`, y en otro caso devuelve el rango `D+1 .. today`.

## 3. CLI

- [x] 3.1 Volver `--from` y `--to` opcionales (`str | None = None`) y añadir el flag `--automatic` / `-a`.
- [x] 3.2 Implementar la validación del contrato de flags: `--automatic` excluyente con `--from`, `--to`, `--force` y `--skip`; sin `--automatic`, ambas fechas obligatorias con mensaje que sugiere `--automatic`.
- [x] 3.3 Cargar `Settings` antes de resolver fechas y añadir la rama automática: derivar rango, manejar `NoRecentEntriesError` (exit 1) y el caso ya-al-día (exit 0).
- [x] 3.4 Imprimir el último día detectado y el rango derivado antes de planear.
- [x] 3.5 Cortocircuitar con exit 0 cuando la asignación no produce bloques y el modo no es `dry_run`, para que el caso finde/festivo no escriba ni pregunte.

## 4. Tests

- [x] 4.1 `tests/test_auto_range.py` con respx: último día varios días atrás; entrada en otro proyecto cuenta; conversión de zona horaria en el límite del día; ventana vacía lanza `NoRecentEntriesError`; `D == today` y `D > today` devuelven `None`; rango máximo de 20 días.
- [x] 4.2 `tests/test_cli.py` con `typer.testing.CliRunner` para el contrato de flags: `--automatic` con `--from`, con `--to`, con `--force`, con `--skip`; sin fechas ni `--automatic`; y el camino feliz de `--automatic --dry-run`.
- [x] 4.3 Correr `pytest`, `ruff check`, `ruff format --check` y `mypy` en verde.

## 5. Documentación

- [x] 5.1 Añadir `--automatic` a la tabla de flags del `README.md` y documentar la ventana de 21 días, el guard de 20 días y los códigos de salida.
- [x] 5.2 Añadir una sección corta de "ejecución programada" al `README.md` mostrando `clockify-sync --automatic --yes`.
- [x] 5.3 Registrar el cambio en `CHANGELOG.md`.
