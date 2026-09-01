## Context

`clockify-sync` nació como un comando retroactivo: el usuario elige un rango y
la herramienta lo llena. En la práctica el uso real es incremental — "llename
desde donde me quedé hasta hoy" — y ese cálculo lo hace hoy el humano. El
objetivo de este cambio es que la herramienta pueda correr sin argumentos de
fecha, de forma segura, idealmente desde un scheduler.

La única fuente de verdad disponible es Clockify: un archivo de estado local
mentiría en cuanto el usuario borre o agregue entradas desde la UI.

## Goals / Non-Goals

**Goals:**
- Que `clockify-sync --automatic --yes` sea seguro de ejecutar a diario sin
  supervisión: nunca duplica horas, nunca borra nada, no genera ruido cuando no
  hay trabajo que hacer.
- Que el rango derivado sea explicable: el usuario ve qué día encontró y qué
  rango dedujo antes de confirmar.
- Que la lógica de derivación sea testeable sin reloj real ni red.

**Non-Goals:**
- No rellena huecos intermedios. Si hay días sin entradas *antes* del último día
  registrado, quedan como están. El modo solo avanza el frente.
- No mantiene estado local ni cache entre ejecuciones.
- No sustituye al modo manual: rangos históricos siguen requiriendo
  `--from`/`--to`.

## Decisions

### Decisión 1: cualquier entrada cuenta como "día cubierto"

El último día sincronizado se calcula sobre **todas** las entradas del usuario
en el workspace, sin filtrar por proyecto, tag ni descripción — a diferencia de
la detección de conflictos, que sí usa el filtro estricto de
`is_automation_owned`.

*Por qué*: el propósito del modo es que el calendario no tenga huecos. Si el
usuario ya registró algo ese día — a mano, en otro proyecto, con otro tag — el
día ya cuenta como reportado y el bot no debe tocarlo.

*Consecuencia aceptada*: una entrada de 1h por un standup en otro proyecto marca
el día completo como cubierto, y ese día nunca recibirá las 8h del bot. Es el
comportamiento deseado: el bot solo avanza sobre terreno completamente virgen.

*Alternativa descartada*: filtrar al proyecto configurado. Habría llenado días
donde el usuario ya reportó tiempo en otro proyecto, inflando el total de horas.

### Decisión 2: la ventana de búsqueda ES el guard de tamaño

Se define `MAX_RANGE_DAYS = 20` y `LOOKBACK_DAYS = MAX_RANGE_DAYS + 1 = 21`.

La API de Clockify no ofrece "dame la última entrada": `list_user_entries` exige
`start` y `end`. Hay que acotar la búsqueda hacia atrás de todos modos. Como
`from_date = D + 1` y `to_date = hoy`, buscar en una ventana de 21 días garantiza
que el rango derivado nunca exceda 20 días — el guard sale gratis, sin un
chequeo de tamaño separado y sin escaneo expansivo.

```
   hoy - 21d                                      hoy
   ├───────────────────────────────────────────────┤
   │          ventana de búsqueda = guard          │
   └───────────────────────────────────────────────┘
        D aquí  → rango ≤ 20 días, siempre válido
        sin D   → abortar, pedir --from
```

*Trade-off aceptado*: si el usuario vuelve de un mes de ausencia, el mensaje es
"no encontré entradas en los últimos 21 días" en vez de "encontré el 15 de julio,
son 33 días, demasiado". Funcionalmente idéntico, mensaje menos informativo, a
cambio de una sola query y cero código de validación redundante.

### Decisión 3: hoy se incluye aunque el día no haya terminado

`to_date = hoy`. Correr a las 10:00 escribe el bloque completo 09:00–17:00 del
día en curso.

*Por qué*: el objetivo declarado es que el calendario esté al día, y el destino
previsto es un scheduler diario. `reconstruct_intervals` ya cierra los intervalos
abiertos en `now`, así que los tickets activos hoy se detectan correctamente.

*Consecuencia aceptada*: se adelantan horas del día en curso.

### Decisión 4: modo de conflicto `error`, nunca `force` ni `skip`

Por construcción el rango empieza *después* del último día con entradas, así que
no debería existir ninguna entrada propia dentro del rango. Dejar el modo default
(`error`) actúa como red de seguridad: si aparece un conflicto, alguna asunción
del modelo es falsa y el usuario debe enterarse en lugar de que el comando lo
resuelva callado.

`--force` se prohíbe explícitamente: borrar entradas en un rango derivado
automáticamente es peligroso y no tiene caso de uso. `--skip` se prohíbe por ser
redundante y por mantener la matriz de combinaciones chica.

### Decisión 5: salidas de código 0 para los no-eventos

| Situación | Salida |
|---|---|
| Sin entradas en la ventana de 21 días | stderr + exit **1** (requiere acción del usuario) |
| `D >= hoy` (ya al día) | stdout + exit **0** |
| Rango sin días hábiles (finde/festivos) | stdout + exit **0** |
| Rango con días hábiles pero sin tickets activos | plan vacío → exit **0** |

*Por qué*: un cron diario debe fallar solo cuando algo requiere intervención
humana. "No hay nada que hacer" es el caso normal, no un error.

### Decisión 6: `today` inyectable, resuelto en la zona configurada

`resolve_automatic_range` recibe `today` como parámetro opcional; cuando falta lo
calcula como `datetime.now(tz=settings.timezone).date()`, no con la hora del
sistema. Es el mismo patrón que `fetch_active_tickets_by_day` ya usa con `now`, y
permite testear la derivación de rangos sin congelar el reloj.

## Risks / Trade-offs

- **Dos llamadas de listado por ejecución**: `resolve_automatic_range` lista 21
  días y luego `apply_blocks` vuelve a listar el rango angosto para su chequeo de
  conflictos. Redundante pero barato; se acepta a cambio de mantener las
  responsabilidades separadas y no filtrar estado entre capas.
- **Un standup bloquea el día completo** (Decisión 1). Mitigación: el usuario
  puede recurrir a `--from`/`--to` manuales para ese día.
- **Horas adelantadas** (Decisión 3). Mitigación: correr por la tarde, o usar
  `--dry-run` para inspeccionar antes.

## Migration Plan

No hay migración. `--from`/`--to` conservan su comportamiento exacto; el único
cambio observable para invocaciones existentes es que omitir ambos ahora produce
un mensaje que menciona `--automatic` en lugar del error de Typer por opción
requerida.

## Open Questions

Ninguna. Las cinco decisiones de diseño quedaron cerradas durante la exploración.
