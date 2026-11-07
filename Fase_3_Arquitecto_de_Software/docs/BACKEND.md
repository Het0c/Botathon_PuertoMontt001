# Backend — Cada Hora Cuenta

## Arquitectura encontrada y decisión

Este backend vive dentro de `Fase_3_Arquitecto_de_Software` y complementa el motor de cálculo existente. No lee Excel: leer BUK/SIC, filtrar `Reg_SIC` y detectar deltas permanece bajo responsabilidad de Blue Prism.

```text
Fase_3_Arquitecto_de_Software/backend/
├── main.py                 FastAPI, CORS y OpenAPI
├── auth.py                 credencial RPA, JWT Supabase y RBAC
├── config.py               variables de entorno
├── database.py             sesiones SQLAlchemy
├── models.py               modelo relacional
├── schemas.py              contratos Pydantic camelCase
├── domain/calculation.py   motor puro con Decimal
├── services/               importación, cálculo, auditoría y gobernanza
└── routers/                rutas /api/v1

Fase_3_Arquitecto_de_Software/motor-calculo/db/migrations/
└── 002_backend_core.sql
```

## Separación de responsabilidades

- **Blue Prism:** lee BUK/SIC, conserva solo `Reg_SIC = "D - SIC"`, valida el origen, detecta deltas y entrega JSON.
- **Backend:** vuelve a validar, persiste, aplica deltas desde su vigencia, calcula, recalcula, gestiona aprobaciones y audita.
- **Supabase/PostgreSQL:** fuente de verdad, integridad, RLS y auditoría inmutable.
- **React:** visualiza y administra consumiendo la API, sin reglas críticas.

SQLite se utiliza únicamente para desarrollo y pruebas.

## Motor

El motor no depende de HTTP ni de la base de datos. Utiliza `Decimal` y contempla contratos parciales, cambios a mitad de mes, suma multi-instituto, tramos 22/40, calendarios regionales, ausencias, matriz por cargo/tramo, asignaciones aprobadas, redondeo inferior, atención grupal, meta y FOJA.

La referencia legal 44/42 horas es un parámetro temporal y no modifica por sí sola un contrato BUK.

## Instalación y ejecución

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
PYTHONPATH=Fase_3_Arquitecto_de_Software .venv/bin/python -m backend.seed_reference_data --instituto Ari:Arica:norte
.venv/bin/uvicorn backend.main:app --app-dir Fase_3_Arquitecto_de_Software --host 127.0.0.1 --port 8000
```

El cargador anterior reutiliza directamente los CSV versionados de `motor-calculo/data`; se puede repetir `--instituto` para crear los doce calendarios base de cada IT. Las asignaciones cuyo número de horas define DMN conservan `null` en lugar de inventar un valor.

Documentación: `http://127.0.0.1:8000/api/v1/docs`.

Para Supabase:

1. Aplicar primero `motor-calculo/db/schema.sql` y luego `motor-calculo/db/migrations/002_backend_core.sql`.
2. Configurar `DATABASE_URL` con el pooler PostgreSQL.
3. Configurar `RPA_API_KEY` solo en Blue Prism y el backend.
4. Configurar `SUPABASE_JWT_SECRET` y `app_metadata.app_role` para usuarios.
5. Ejecutar con `APP_ENV=production`.

En producción no se crean tablas automáticamente.

## Variables

| Variable | Uso |
|---|---|
| `DATABASE_URL` | Conexión SQLAlchemy a PostgreSQL/Supabase |
| `RPA_API_KEY` | Bearer token exclusivo de Blue Prism |
| `SUPABASE_JWT_SECRET` | Validación HS256 de sesiones Supabase |
| `USER_API_KEY` | Autenticación simplificada solo para desarrollo |
| `ALLOWED_ORIGINS` | Orígenes CORS separados por coma |
| `APP_ENV` | `development`, `test` o `production` |

## API implementada

RPA: snapshot contractual, creación de importaciones, registros, deltas, errores, cierre y estado.

Negocio: profesionales, contratos, institutos, matriz, calendarios, meta, jornada legal, catálogo de asignaciones, solicitudes, aprobación/rechazo DMN, planificación, recálculo, simulación, comparativa SIC, dashboard y auditoría.

El contrato completo está en OpenAPI.

## Pruebas

```bash
APP_ENV=test DATABASE_URL=sqlite:////tmp/cada-hora-test.db .venv/bin/pytest -q
```

Cubren el motor, contratos parciales, cambio a mitad de mes, 44/42, límites 22/40, multi-instituto, licencias, asignaciones, aprobación/rechazo, tope de dos, redondeo, grupos, meta, FOJA cero, idempotencia, delta retroactivo, SIC ausente/cero, simulación, permisos, auditoría y HTTP real.

## Limitaciones

- Supabase no fue probado en vivo porque no se entregaron URL ni credenciales; la migración y el adaptador PostgreSQL están preparados.
- Blue Prism 7 no fue ejecutado. Se probó el contrato con un cliente HTTP real; no se afirma integración RPA completa.
- La paridad total con las 471 referencias Excel aún requiere validación institucional de NAS y atención grupal.
- Reemplazos y vacantes están modelados, pero sus endpoints y efectos quedan P1.
- Distribución automática de reportes queda pendiente; no hay envíos ficticios.
- JWT admite el secreto HS256. Proyectos Supabase solo con claves asimétricas requieren validación JWKS.
