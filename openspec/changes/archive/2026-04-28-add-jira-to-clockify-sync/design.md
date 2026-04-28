## Context

El proyecto es greenfield: no hay código previo. El usuario es ingeniero, trabaja a diario con tickets de JIRA Cloud y registra horas en Clockify usando un único proyecto y un único tag. Hoy no usa worklogs en JIRA, así que la única señal disponible para inferir "trabajo" es el changelog: transiciones de estado y cambios de assignee. La intención del registro en Clockify es **demostrar dedicación**, no auditar tiempos exactos — eso permite usar heurísticas en lugar de tracking real.

Stakeholders:
- **Usuario único** (developer): corre el comando localmente cada cierto tiempo para llenar Clockify retroactivamente.
- **Empresa**: consume Clockify como fuente de verdad para reportes de horas; le importa que haya entries plausibles, no exactos al minuto.

Restricciones:
- Python 3.11+ (usa `zoneinfo` nativo).
- Trabajo en Windows 11 (paths, shell), pero el código no debe tener dependencias específicas de OS.
- Mismo código debe ejecutar local con `.env` y en GitHub Actions con secrets/vars — sin ramas de código por entorno.
- Clockify recibe entries en horas enteras; la API acepta minutos pero el usuario quiere que el calendario muestre solo bloques redondos.

## Goals / Non-Goals

**Goals:**
- Reducir a un comando la tarea de llenar Clockify para un rango de fechas dado.
- Detección automática y determinística de qué tickets cuentan en cada día.
- Reparto reproducible: misma entrada → mismo output (idempotencia).
- Lógica de reparto aislada como función pura, fácilmente testeable sin tocar red.
- Configuración por entorno única; preparada para correr en GitHub Actions sin cambios de código.
- Idempotencia segura: nunca borra ni pisa entries hechos a mano.

**Non-Goals:**
- No implementa el workflow de GitHub Actions en este milestone (solo se prepara el terreno con env-only config).
- No escribe worklogs de vuelta a JIRA.
- No soporta múltiples proyectos o tags en Clockify (todo va a uno fijo).
- No edita entries existentes en su lugar; con `--force` los borra y recrea.
- No detecta festivos automáticamente — `holidays.yaml` se mantiene a mano.
- No tiene UI; solo CLI.
- No persiste estado entre ejecuciones (cada corrida es independiente, basada en lo que hay en JIRA + Clockify).

## Decisions

### D1. Definición de "ticket trabajado en el día X" = presencia de intervalo

Un ticket cuenta para el día D si existe al menos un intervalo `[start, end]` reconstruido del changelog donde simultáneamente `assignee = usuario` y `status = "In Progress"`, y ese intervalo intersecta cualquier momento del día D en zona local del usuario.

**Alternativas consideradas:**
- *Solo días con transición ese día*: subreporta — un ticket que vive 5 días en In Progress sin tocarse aparecería un solo día.
- *Días con cualquier comentario o cambio de campo*: sobrereporta y mete ruido (PMs, automation bots).

Razón: presencia es la mejor proxy del trabajo real cuando no hay worklog, y el usuario no necesita auditoría — necesita evidencia.

### D2. Reconstrucción de intervalos desde changelog, no JQL puro

JQL `assignee was currentUser() AND status was "In Progress" DURING (...)` se usa solo como **filtro de candidatos**. La cronología real se reconstruye iterando el changelog de cada issue, fusionando los streams de cambios de `assignee` y `status` en una línea de tiempo y emitiendo intervalos donde ambas condiciones se cumplen a la vez.

**Alternativas consideradas:**
- *Confiar en JQL DURING*: JQL responde "estuvo así en algún momento", no da timestamps. No sirve para mapear día por día.
- *Pedir un endpoint específico de "actividad"*: JIRA Cloud no lo expone con la granularidad que necesitamos.

Razón: el changelog es la única fuente con timestamps por evento. Es más trabajoso pero correcto.

### D3. Algoritmo de reparto: `base + sobrante`, alfabético, horas enteras

Para cada día laboral con N tickets activos:
```
base     = 8 // N
sobrante = 8 - base * N
```
Se ordenan los tickets alfabéticamente por key. Los primeros `sobrante` reciben `(base + 1)` horas; el resto, `base` horas. Bloques contiguos desde 09:00.

Ejemplos:
| N | Reparto | Total |
|---|---------|-------|
| 1 | [8] | 8 |
| 2 | [4, 4] | 8 |
| 3 | [3, 3, 2] | 8 |
| 4 | [2, 2, 2, 2] | 8 |
| 5 | [2, 2, 2, 1, 1] | 8 |
| 6 | [2, 2, 1, 1, 1, 1] | 8 |
| 7 | [2, 1, 1, 1, 1, 1, 1] | 8 |
| 8 | [1, 1, 1, 1, 1, 1, 1, 1] | 8 |

**Alternativas consideradas:**
- *Hash(día) rotativo*: distribuye más "justo" la hora extra entre tickets distintos día a día. Más código, idempotente igual, pero el usuario explícitamente dijo que no le importa la justicia → simplicidad gana.
- *Por fecha de transición*: requiere data extra del changelog y no agrega valor real.
- *Permitir fracciones (15 min, 30 min)*: el usuario quiere ver bloques redondos en su calendario; rompe la estética que pidió.

### D4. Caso N > 8: warning + skip alfabético de los excedentes

Si en un día hay más de 8 tickets activos, los primeros 8 alfabéticamente reciben 1h cada uno y los restantes se omiten con un mensaje en el log indicando los keys excluidos.

**Alternativas consideradas:**
- *Error y abortar*: rompe la corrida por un día atípico; demasiado frágil.
- *Bloques de 30min*: rompe la regla de horas enteras.
- *Día de >8 horas*: rompe el horario fijo 9–17.

### D5. Bloque continuo 9:00–17:00 ignorando comidas y reuniones

Decisión explícita del usuario: el calendario muestra "trabajaste 8h sin pausa". Se acepta que esto es ficticio respecto a la jornada real, pero corresponde al modelo mental del usuario para el reporte de Clockify. No se inserta hueco de almuerzo.

### D6. Zona horaria: `America/Mexico_City` configurable por env

Toda la aritmética de "qué día es este intervalo" se hace en zona local; al enviar a Clockify se convierte a UTC con offset explícito. JIRA changelog viene en UTC con offset (ISO 8601), se convierte a local antes de mapear a días. Default `America/Mexico_City`; configurable por `TIMEZONE`.

### D7. Idempotencia por descripción + proyecto + tag

Un entry en Clockify se considera "creado por la automatización" si y solo si:
- `projectId == CLOCKIFY_PROJECT_ID` configurado
- `CLOCKIFY_TAG_ID` configurado está en `tagIds` del entry
- `description` matchea regex `^[A-Z][A-Z0-9_]+-\d+( — .*)?$`

Comportamiento por defecto: si hay matches en el rango, abortar con error informativo. `--force` los borra y recrea; `--skip` salta días donde haya matches; `--dry-run` no toca nada. Entries que no matchean los tres criterios nunca se tocan.

**Alternativas consideradas:**
- *Tag dedicado "auto-clockyfy"*: el usuario tiene un único tag, no quiere agregar otro.
- *Comparar entry-por-entry y solo crear los que faltan*: complejo y frágil ante cambios mínimos en descripción.

### D8. Stack Python con `uv`, CLI con `typer`, request HTTP con `httpx`

- `uv` por velocidad y manejo nativo de lockfile.
- `typer` por su buena DX para CLIs simples y validación de tipos.
- `httpx` por soporte sync limpio, timeouts explícitos y compatibilidad con tests.
- `pydantic` para Settings y modelos de dominio.
- `pyyaml` para `holidays.yaml`.
- `python-dotenv` para cargar `.env` local (no en CI).
- `pytest` + `freezegun` para tests.

### D9. Separación estricta: `allocator.py` es lógica pura

`allocator.py` no importa nada de red. Recibe estructuras Python plain (dataclasses) y devuelve estructuras Python plain. Esto permite tests unitarios exhaustivos sin mocks HTTP y deja la lógica auditable. Toda la I/O vive en `jira/client.py` y `clockify/client.py`.

### D10. Mismo código local y en CI

`config.py` lee siempre de `os.environ`. `python-dotenv` carga `.env` en arranque local (omitido en CI vía variable `CI=true` o ausencia del archivo). En GitHub Actions, los secrets/vars se exponen como env y todo funciona sin tocar código. Sin lógica condicional por entorno.

## Risks / Trade-offs

| Riesgo | Mitigación |
|---|---|
| **Errores de zona horaria**: día se corre por DST/UTC, entries aparecen en día equivocado | Toda la aritmética de días en zona local con `zoneinfo`. Tests con `freezegun` cubren cambios de mes y casos límite (23:30 local viernes → no es sábado en UTC). México sin DST desde 2022 simplifica. |
| **Rate limits de JIRA Cloud (~100 req/min)**: pull de issues + changelog en rango grande puede saturar | Backoff exponencial con jitter en cliente HTTP. Search inicial trae issues; changelog se solicita uno por uno con respeto a `Retry-After`. Para rangos largos, considerar `?expand=changelog` en search bulk si está disponible. |
| **Múltiples ciclos de status/assignee** en un mismo issue | El reconstructor produce **lista** de intervalos disjuntos, no un solo `[start, end]`. Tests obligatorios cubren: A→B→A, In Progress → Done → In Progress, reasignación temporal. |
| **Entries hechos a mano del usuario en el rango** | Filtro estricto de "entry propio" por proyecto+tag+regex. Cualquier entry que no cumpla los 3 criterios queda intocado. Test con fixtures de entries mixtos. |
| **Tickets sin summary o con summary muy largo** | Si falta summary, descripción degrada a solo key. Si excede longitud razonable (~500 chars), se trunca con `…` antes de enviar. |
| **Días sin tickets activos** dentro del rango | Skip silencioso con un warning en el log; no se crean entries y no es error. |
| **Festivo no listado en holidays.yaml** | Se trata como día laboral. El usuario debe mantener el archivo; el README documenta esto. No se intenta detectar festivos automáticamente. |
| **JIRA Server (no Cloud)**: API ligeramente distinta | Fuera de scope. Asumimos JIRA Cloud (Atlassian). |
| **Credenciales filtradas en logs** | El logger nunca imprime headers ni el body de la request; solo path, método y status. Tests verifican que API tokens no aparecen en captura de logs. |
| **Re-corrida con error en la mitad** (algunos entries creados, otros no) | Sin transacciones cross-API. Mitigación: todas las creaciones se intentan; al final se reporta éxito/fallo por día. La idempotencia (regla de "entry propio") permite re-correr con `--force` para limpiar y reintentar. |
| **JIRA changelog paginado**: issues con miles de cambios | El cliente sigue cursores hasta agotar páginas. Para issues con changelog masivo, se puede acotar con `since` si fuera necesario (no en milestone inicial). |

## Open Questions

Ninguna bloqueante para arrancar. Para revisar después del primer uso real:
- ¿El reparto alfabético se siente injusto en la práctica? Si sí, considerar D3 alternativa con hash rotativo.
- ¿Conviene un modo `--explain` que imprima el razonamiento día por día (intervalos detectados, reparto, tickets descartados) sin enviar nada? Probablemente sí, fácil agregar después.
- ¿El umbral de `~500 chars` para truncar descripción es razonable? Confirmar contra entries reales.
