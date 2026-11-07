"""
Fase 1 — Un número correcto.
Calcula la planificación de UNA persona (PersonaId 137732, médico fisiatra, Arica)
y la compara con el Excel de referencia.

Uso:  python fase1_un_numero.py "Nac - Planificación Asistencial x mes.xlsx"
Requiere: pip install openpyxl
"""
import math
import sys
import openpyxl

PERSONA = 137732

# ---------- Paso 2: parámetros a mano, solo médico fisiatra ----------
PARAMETROS = {
    "MEDICO FISIATRA": {
        "pct_dir": 0.65,
        "pct_ind": 0.15,
        "pct_nas": 0.20,
        "min_directa": 40,
        "min_indirecta": 30,
    }
}
META_GESTION = 0.90

# Semanas hábiles por mes del calendario 2026 (Parámetros, días hábiles / 5)
SEMANAS_BASE = [4.2, 4.0, 4.4, 4.2, 3.8, 4.2, 4.4, 4.2, 4.2, 4.2, 4.2, 4.2]


# ---------- Paso 1: leer la fila de la persona en el Excel ----------
def leer_persona(ruta, persona_id):
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb["Dotacion_Asistencial"]
    filas = ws.iter_rows(min_row=4, values_only=True)
    cabecera = [str(c).strip() if c is not None else "" for c in next(filas)]
    for fila in filas:
        d = dict(zip(cabecera, fila))
        if d.get("PersonaId") == persona_id:
            return d
    raise SystemExit(f"PersonaId {persona_id} no está en el Excel")


# ---------- Pasos 3 a 5: el cálculo ----------
def calcular(horas_semana, cargo, horas_asignaciones, semanas_habiles):
    p = PARAMETROS[cargo]

    # Paso 3: porcentajes finales (las asignaciones suben el NAS y bajan dir/ind en proporción)
    nas_final = (horas_semana * p["pct_nas"] + horas_asignaciones) / horas_semana
    factor = (1 - nas_final) / (1 - p["pct_nas"])
    dir_final = p["pct_dir"] * factor
    ind_final = p["pct_ind"] * factor

    # Paso 4: atenciones por semana, redondeando hacia abajo
    dir_semana = math.floor(horas_semana * dir_final * 60 / p["min_directa"])
    ind_semana = math.floor(horas_semana * ind_final * 60 / p["min_indirecta"])

    # Paso 5: por mes y meta al 90 %
    plan_dir = [math.floor(dir_semana * s) for s in semanas_habiles]
    plan_tot = [math.floor((dir_semana + ind_semana) * s) for s in semanas_habiles]
    mg_dir = [math.floor(x * META_GESTION) for x in plan_dir]
    mg_tot = [math.floor(x * META_GESTION) for x in plan_tot]

    return {
        "nas_final": nas_final, "dir_final": dir_final, "ind_final": ind_final,
        "dir_semana": dir_semana, "ind_semana": ind_semana,
        "plan_dir": plan_dir, "plan_tot": plan_tot, "mg_dir": mg_dir, "mg_tot": mg_tot,
    }


def check(nombre, mio, excel):
    ok = "OK " if abs(float(mio) - float(excel)) < 1e-6 else "XX "
    print(f"  {ok}{nombre:<28} mío={mio!s:<12} excel={excel}")


if __name__ == "__main__":
    ruta = sys.argv[1] if len(sys.argv) > 1 else "Nac - Planificación Asistencial x mes.xlsx"
    d = leer_persona(ruta, PERSONA)

    print(f"Persona {PERSONA}: {d['Cargo']}, {d['Instituto']}, {d['H/S dic']} h/s, "
          f"asignación '{d['Asignación 1 (seleccionar de lista desplegable)']}' = {d['Hrs. Asignación 1']} h")

    # Semanas hábiles de ESTA persona (ya descontadas vacaciones, licencias, permisos)
    semanas_persona = [d[f"SemHab{m}"] for m in range(1, 13)]

    r = calcular(
        horas_semana=d["H/S dic"],
        cargo=d["Cargo"],
        horas_asignaciones=d["Total Hrs. Asignación"] or 0,
        semanas_habiles=semanas_persona,
    )

    print("\nPaso 3 — porcentajes finales")
    check("%NAS final", r["nas_final"], d["%NAS + Asig. Especiales"])
    check("%Directo final", round(r["dir_final"], 6), round(d["%Directo Final"], 6))
    check("%Indirecto final", round(r["ind_final"], 6), round(d["%Indirecto Final"], 6))

    print("\nPaso 4 — atenciones por semana")
    check("Directas/semana", r["dir_semana"], d["Atención Semanal Directa + Grupal"])
    check("Indirectas/semana", r["ind_semana"], d["Atención Semanal Indirecta Total"])

    print("\nPaso 5 — por mes (directas / meta 90 %)")
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    for i, m in enumerate(meses, start=1):
        check(f"{m} PlanAteDir", r["plan_dir"][i - 1], d[f"PlanAteDir{i}"])
        check(f"{m} MG_AteDir", r["mg_dir"][i - 1], d[f"MG_AteDir{i}"])

    print("\nTotales anuales")
    check("Total directas", sum(r["plan_dir"]), d["Total Plan Atenciones Directas"])
    check("Total dir+ind", sum(r["plan_tot"]), d["Total Atenciones Dir+Indir"])
    check("Total MG directa", sum(r["mg_dir"]), d["Total MG Directa"])
    check("Total MG", sum(r["mg_tot"]), d["Total MG"])
