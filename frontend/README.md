# Frontend · Cada hora cuenta
HTML + CSS + JS sin build. FastAPI lo sirve en http://127.0.0.1:8000/app/ (montado en `backend/main.py`); todo comando va desde la raíz del repo.
1. `cp .env.example .env` y `pip install -r requirements.txt` (en un venv con Python 3.11 o superior).
2. Parámetros: `PYTHONPATH=Fase_3_Arquitecto_de_Software python -m backend.seed_reference_data --instituto "Ari:Instituto Arica" --instituto "Iqu:Instituto Iquique"`
3. Backend: `uvicorn backend.main:app --app-dir Fase_3_Arquitecto_de_Software --port 8000` y abrir http://127.0.0.1:8000/app/
4. Barra superior: en «Configuración» la API key = `USER_API_KEY` del `.env`; luego usuario y rol según la acción, y Aplicar.
Roles: **management** (Gerencia) lee todo y simula · **rrhh** además edita distribuciones y meta, recalcula y crea solicitudes ·
**dmn** todo lo de rrhh y además aprueba o rechaza solicitudes · **professional** solo su planificación (usuario = su PersonaId).
Sin datos: importa un reporte BUK con el bot de Blue Prism (`Fase_3_Arquitecto_de_Software/docs/INTEGRACION_BLUE_PRISM.md`).
Sin dependencias de internet: Chart.js 4.4.1 está copiado en `vendor/` (licencia MIT en `vendor/LICENSE-chartjs.md`).
