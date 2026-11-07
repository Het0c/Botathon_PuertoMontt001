# Bot Traductor – Botathon 2026 · Equipo 35

Script en Python que toma los **dos Excel crudos de Teletón tal como vienen** y genera un solo libro plano,
`Planificacion_Input_BluePrism.xlsx`, con una tabla por hoja (encabezado en fila 1, sin celdas combinadas,
sin fórmulas), para que Blue Prism lo lea con el VBO **MS Excel** (o los CSV con el VBO **Utility - File Management**)
y haga el cálculo desde ahí.

## Instalación en la VM (Windows)

1. Instalar Python 3 desde https://www.python.org/downloads/ (marcar **"Add python.exe to PATH"**).
2. Abrir `cmd` y ejecutar: `pip install openpyxl`
3. Copiar esta carpeta a la VM, por ejemplo en `C:\Botathon\bot_traductor\`.

## Ejecución

```
python bot_traductor.py --contratos "C:\Botathon\Nac - Base contratos x mes.xlsx" --planificacion "C:\Botathon\Nac - Planificación Asistencial x mes.xlsx" --salida C:\Botathon\salida --csv
```

O editar las rutas en `ejecutar.bat` y hacer doble clic.

Desde Blue Prism se puede invocar con el VBO **Utility - Environment → Start Process** (o `Start Process and Wait`),
pasando la misma línea de comando. Al terminar, el bot deja en la carpeta de salida:

| Archivo | Qué es |
|---|---|
| `Planificacion_Input_BluePrism.xlsx` | 20 hojas planas (abajo) |
| `csv\*.csv` | las mismas tablas, separador `;`, UTF-8 (opcional con `--csv`) |
| `bot_traductor.log` | log con cantidades, advertencias y errores |

Código de salida 0 = OK, 2 = error (el detalle queda en el log).

## Hojas que genera

**Dotación (desde "Base contratos")**

- `Dotacion_Mes` – un registro por persona-mes. Clave única `PersonaId-IT-Mes`. Agrega `Tramo_Horas`, `Mes_Cumpleanos`,
  `Horas_Dia_Promedio`, `Vigente_Mes` y `Alerta` (SIN_HORAS, SIN_CARGO, SIN_COD_ESP, NDIAS_NO_CUADRA → candidatos a excepción).
- `Personas` – una fila por profesional con primer/último mes y si cambió de horas.
- `Cambios_Mes` – ALTA / BAJA / CAMBIO_HORAS / CAMBIO_CARGO / FECHA_TERMINO entre un mes y el anterior. **Esto es lo que va a la Work Queue.**

**Parámetros (desde "Planificación Asistencial", hojas Parámetros, Distribucion_NAC, Resumen NAS, Planificacion Total)**

- `Param_Generales` – constantes (meta de gestión 90 %, pausa saludable 10 %/6 %, colación 0,25 h/día, minutos indirecta 30, umbrales de tramo 40/22, etc.).
- `Param_Distribucion_Cargo` – por `Cargo` + `Tramo_Horas`: `Pct_Directo`, `Pct_Indirecto`, `Pct_NAS`, minutos estándar.
- `Param_Semanas_Habiles` – por mes: días, inhábiles, hábiles y semanas hábiles (ene 4,2 … dic 4,2).
- `Param_Feriados`, `Param_Factor_Grupal`, `Param_Asignaciones`, `Param_Institutos`, `Param_Especialidades`,
  `Param_Homologacion_Cargo`, `Param_Pacientes_LOP`.

**Entradas humanas (desde Dotacion_Asistencial y Excepciones)**

- `Asignaciones_Especiales` – asignación 1, 2, la reunión sindical (0,25 h, "asignación 4" del original) y las "por autorizar" (Estado POR_AUTORIZAR → excepción).
- `Ausencias_Mes` – licencias / vacaciones / permisos en semanas por persona-mes.
- `Dias_Adicionales` – días por persona-año (cumpleaños, vísperas, feriado legal adicional, progresivos, Ley 21.530, lactancia…).
- `Excepciones_Horas` – horas repartidas en dos institutos.

**Referencia (para validar)**

- `Referencia_Por_Persona` – lo que calcula hoy el Excel para los 471 profesionales, con cada paso intermedio.
- `Referencia_Por_Instituto` – consolidado por IT.
- `Log` – copia del log de la corrida.

## Cadena de cálculo que debe implementar Blue Prism

1. `HS` = `Horas_Semanales` del contrato.
2. `HS_Pausa` = HS × 10 % si HS ≥ 40, si no HS × 6 %.
3. `HS_Colacion` = 0,25 × `N_Dias_Semana` (0 si la colación está en el contrato).
4. Buscar en `Param_Distribucion_Cargo` por `Cargo` + `Tramo_Horas` → `Pct_NAS`, `Pct_Directo`, `Pct_Indirecto`, minutos.
   `HS_NAS_Total` = HS × Pct_NAS. Si el cargo no está → **excepción**.
5. `Hrs_Asig` = suma de `Asignaciones_Especiales` vigentes (máx. 2, sólo HS > 30). `Pct_NAS_Asig` = (HS_NAS_Total + Hrs_Asig) / HS.
6. `Pct_Asistencial` = 1 − Pct_NAS_Asig. `Pct_Dir_Final` = Pct_Asistencial × Pct_Directo / (Pct_Directo + Pct_Indirecto); ídem indirecto.
7. `Ate_Dir_Sem` = ENTERO(HS × Pct_Dir_Final × 60 / Min_Directa). `Ate_Ind_Sem` = ENTERO(HS × Pct_Ind_Final × 60 / Min_Indirecta).
8. `SemHab_m` = `Semanas_Habiles(m)` − ausencias del mes (`Ausencias_Mes`) − prorrateo de `Dias_Adicionales` / 5.
9. `PlanDir_m` = REDONDEAR(Ate_Dir_Sem × SemHab_m). Anual = suma de 12 meses.
10. `MG_m` = REDONDEAR(PlanDir_m × META_GESTION).
11. Consolidado por IT = Σ MG anual + `Planificacion_LOP`; intensidad = total / `Pacientes_Unicos_Proyectados`.

Ejemplo verificado (PersonaId 137732, fisiatra Arica, 40 h): pausa 4, colación 0, NAS 8 (20 %), asignación 2 h → 25 %,
directo final 60,9 %, 36 directas y 11 indirectas por semana, enero 4,2 semanas → 151 directas, meta 135.

## Pendientes / advertencias conocidas

- El original sólo trae feriados de enero a julio (`Param_Feriados`); `Param_Semanas_Habiles` sí tiene los 12 meses.
- La fórmula exacta de la atención grupal (`Pct_Grupal`, `N_Pac_Grupo`) no está cerrada: consultar a los mentores.
- 7 profesionales del original tienen % ajustados a mano que no salen de la matriz: el bot debería marcarlos como excepción.
