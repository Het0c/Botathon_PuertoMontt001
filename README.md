# Botathon 2026 · Equipo 35 · "Cada hora cuenta" (Teletón)

Prototipo que transforma la planificación de horas asistenciales de Teletón (hoy un Excel alimentado a mano)
en un proceso trazable y parametrizable con **Blue Prism para la automatización documental** y un backend Python para reglas, persistencia y cálculo.

## Arquitectura

```
Excel crudos (BUK / SIC simulados)
        │
        ▼
[1] bot_traductor.py  (Python)  → Planificacion_Input_BluePrism.xlsx  (20 tablas planas + log)
        │
        ▼
[2] Blue Prism: proceso "Planificación Asistencial"
      · lee automáticamente BUK y SIC
      · conserva solo filas Reg_SIC = "D - SIC"
      · valida, detecta deltas y genera JSON; no inserta directo a la BD
        │
        ▼
[3] FastAPI + motor de cálculo
      · valida y persiste en PostgreSQL/Supabase
      · calcula, gestiona asignaciones/DMN y mantiene auditoría
      · expone planificación, simulación y dashboard por API
```

## Estructura del repositorio

```
bot_traductor.py                     apoyo para inspección y preparación de archivos
Fase_3_Arquitecto_de_Software/       motor, backend FastAPI, contrato RPA y pruebas
Fase_3_Arquitecto_de_Software/docs/  arquitectura y guía Blue Prism → API
```

## Equipo

- Persona A – Blue Prism (proceso, objetos, Work Queue)
- Persona B – Datos y parámetros (bot traductor, datos de prueba)
- Persona C – Lógica de cálculo y validación
- Persona D – Diseño del proceso, pitch y demo

## Cómo correr el traductor

Ver [LEEME.md](LEEME.md). Resumen:

```
pip install openpyxl
python bot_traductor.py --contratos "Nac - Base contratos x mes.xlsx" --planificacion "Nac - Planificación Asistencial x mes.xlsx" --salida salida --csv
```

> Todos los datos son ficticios (sin nombres ni RUT reales). No subir credenciales de la VM ni de Blue Prism a este repositorio.

## Backend FastAPI

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn backend.main:app --app-dir Fase_3_Arquitecto_de_Software --reload
```

OpenAPI: `http://127.0.0.1:8000/api/v1/docs`.

- Guía técnica: [`Fase_3_Arquitecto_de_Software/docs/BACKEND.md`](Fase_3_Arquitecto_de_Software/docs/BACKEND.md)
- Contrato Blue Prism: [`Fase_3_Arquitecto_de_Software/docs/INTEGRACION_BLUE_PRISM.md`](Fase_3_Arquitecto_de_Software/docs/INTEGRACION_BLUE_PRISM.md)
