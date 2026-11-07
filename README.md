# Botathon 2026 · Equipo 35 · "Cada hora cuenta" (Teletón)

Prototipo que transforma la planificación de horas asistenciales de Teletón (hoy un Excel alimentado a mano)
en un proceso trazable y parametrizable con **Blue Prism** como núcleo.

## Arquitectura

```
Excel crudos (BUK / SIC simulados)
        │
        ▼
[1] bot_traductor.py  (Python)  → Planificacion_Input_BluePrism.xlsx  (20 tablas planas + log)
        │
        ▼
[2] Blue Prism: proceso "Planificación Asistencial"
      · carga Cambios_Mes / Dotacion_Mes a la Work Queue (1 ítem por profesional)
      · aplica la cadena de cálculo leyendo Param_* y Entradas humanas
      · marca excepciones (cargo sin matriz, asignación por autorizar, horas en 0...)
        │
        ▼
[3] Salida: planificación por persona + consolidado por instituto + log de auditoría
```

## Estructura del repositorio

```
bot_traductor/     script Python que traduce los Excel crudos (ver bot_traductor/LEEME.md)
blueprism/         releases .bprelease del proceso y objetos (exportar desde Blue Prism)
docs/              diagrama del proceso, reglas de cálculo, pitch
data/ejemplo/      salida de ejemplo del traductor (datos ficticios)
```

## Equipo

- Persona A – Blue Prism (proceso, objetos, Work Queue)
- Persona B – Datos y parámetros (bot traductor, datos de prueba)
- Persona C – Lógica de cálculo y validación
- Persona D – Diseño del proceso, pitch y demo

## Cómo correr el traductor

Ver [bot_traductor/LEEME.md](bot_traductor/LEEME.md). Resumen:

```
pip install openpyxl
python bot_traductor/bot_traductor.py --contratos "Nac - Base contratos x mes.xlsx" --planificacion "Nac - Planificación Asistencial x mes.xlsx" --salida salida --csv
```

> Todos los datos son ficticios (sin nombres ni RUT reales). No subir credenciales de la VM ni de Blue Prism a este repositorio.
