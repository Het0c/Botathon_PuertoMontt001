# Motor de Cálculo — Planificación Asistencial (Botathon 2026)

Cálculo por profesional y mes de atenciones directas, indirectas y meta de gestión.
Lógica reconstruida y verificada contra el Excel de referencia `Nac - Planificación Asistencial x mes.xlsx`.

## Estado

- Fase 1 lista: `fase1_un_numero.py` calcula la persona 137732 (médico fisiatra, Arica) y los 33 valores coinciden con el Excel.
- Fase 2 en curso: generalizar a todos los cargos, tramos y factor grupal usando los CSV de `data/`.

## Cómo correr

```
pip install openpyxl
python fase1_un_numero.py "Nac - Planificación Asistencial x mes.xlsx"
```

## Contenido

| Ruta | Para quién | Qué es |
| --- | --- | --- |
| `fase1_un_numero.py` | Backend | Cálculo de una persona con parámetros a mano y comparación contra el Excel |
| `data/parametros_cargo.csv` | Base de datos + Backend | 92 cargos × 3 tramos: % directo, % indirecto, % NAS, minutos estándar (hoja Distribucion_NAC) |
| `data/factor_grupal.csv` | Base de datos + Backend | % grupal y pacientes por grupo por área (AS, ED, ULAB, UTAC, UEDA) |
| `data/asignaciones_especiales.csv` | Base de datos | Catálogo de 31 asignaciones con horas semanales y si requieren DMN |
| `data/calendario_2026.csv` | Base de datos | Días y semanas hábiles por mes (Parámetros) |
| `data/persona_137732.json` | Blue Prism + Backend | Contrato JSON de ejemplo que el bot debe generar por persona; incluye los valores esperados del Excel para probar |
| `db/schema.sql` | Base de datos | Tablas de parámetros, generales y log de auditoría para Supabase |

## Reglas clave del cálculo

1. Tramo según promedio ponderado de H/S: `>=40`, `22-40`, `<22`.
2. `%NAS_final = (H/S × %NAS + horas_asignaciones) / H/S`.
3. `%Dir_final = %Dir × (1 − %NAS_final) / (1 − %NAS)`; igual para indirecto.
4. Atenciones/semana = piso(H/S × %_final × 60 / minutos estándar). Indirecta siempre 30 min.
5. Grupal (solo AS, ED, ULAB, UTAC, UEDA): `Dir × (1 − %grupal) + Dir × %grupal × pacientes_por_grupo`.
6. Por mes: piso(atenciones/semana × semanas hábiles de la persona en el mes).
7. Meta de gestión: piso(plan mensual × 0,90), mes a mes, luego se suma.

## Contrato JSON (bot → backend)

Ver `data/persona_137732.json`. Campos mínimos: `personaId`, `instituto`, `it`, `cargo`, `codEsp`,
`tipoContrato`, `tipoTrabajador`, `fechaIngreso`, `fechaTermino`, `mesCumpleanos`,
`horasSemanalesPorMes` (12 valores), `asignaciones[]`, `licenciaExtensa`,
`descuentos.{vacacionesSemanas, licenciasSemanas, permisosSemanas}` (12 valores cada uno).
