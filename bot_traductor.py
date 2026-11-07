#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT TRADUCTOR – Botathon 2026 · Equipo 35 · Desafío "Cada hora cuenta" (Teletón)

Lee los dos Excel CRUDOS que entrega Teletón y genera UN solo libro plano,
listo para que Blue Prism lo lea con el VBO "MS Excel" (una tabla por hoja,
encabezado en la fila 1, un registro por fila, sin celdas combinadas, sin fórmulas).

Uso:
    python bot_traductor.py --contratos "Nac - Base contratos x mes.xlsx" ^
                            --planificacion "Nac - Planificación Asistencial x mes.xlsx" ^
                            --salida C:\\Botathon\\salida  [--csv]

Salida:
    <salida>/Planificacion_Input_BluePrism.xlsx   (todas las tablas)
    <salida>/csv/*.csv                             (opcional, --csv: una tabla por archivo)
    <salida>/bot_traductor.log                     (log de ejecución y hallazgos)

Requisitos: Python 3.8+ y openpyxl  (pip install openpyxl)
"""
import argparse
import collections
import datetime as dt
import logging
import os
import sys
import csv

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Falta openpyxl. Instalar con:  pip install openpyxl")
    sys.exit(1)

MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
log = logging.getLogger('bot')


# ----------------------------------------------------------------------------- utilidades
def to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        for f in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return dt.datetime.strptime(v.strip(), f).date()
            except ValueError:
                pass
    return None


def to_hours(v):
    """El original guarda algunas horas como tiempo (timedelta / fecha serial). Se convierten a horas decimales."""
    if isinstance(v, dt.timedelta):
        return round(v.total_seconds() / 3600, 4)
    if isinstance(v, dt.datetime):
        return round((v - dt.datetime(1899, 12, 30)).total_seconds() / 3600, 4)
    return v


def clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def upper(v):
    v = clean(v)
    return v.upper() if isinstance(v, str) else v


def tramo(h, t1=40, t2=22):
    if not isinstance(h, (int, float)):
        return None
    return 'T1_>=40' if h >= t1 else ('T2_22-39' if h >= t2 else 'T3_<22')


def find_header_row(ws, must_contain, max_scan=15):
    """Busca la fila de encabezado: la primera que contenga todos los textos de must_contain."""
    for r in range(1, max_scan + 1):
        vals = {str(c.value).strip().replace('\n', ' ').lower() for c in ws[r] if c.value is not None}
        if all(m.lower() in vals for m in must_contain):
            return r
    raise ValueError(f"No se encontró el encabezado con {must_contain} en la hoja {ws.title}")


def header_map(ws, row):
    m = {}
    for c in ws[row]:
        if c.value is not None:
            m[str(c.value).strip().replace('\n', ' ')] = c.column
    return m


# ----------------------------------------------------------------------------- lectura: contratos
def leer_contratos(path):
    log.info("Leyendo contratos: %s", path)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr_idx = None
    for i, r in enumerate(rows[:15]):
        vals = [str(x).strip() for x in r if x is not None]
        if 'PersonaId' in vals and 'Horas Semanales' in vals:
            hdr_idx = i
            break
    if hdr_idx is None:
        raise ValueError("Contratos: no se encontró la fila de encabezado (PersonaId / Horas Semanales)")
    hdr = [str(x).strip() if x is not None else '' for x in rows[hdr_idx]]
    col = {h: i for i, h in enumerate(hdr) if h}
    log.info("Contratos: encabezado en fila %d, %d columnas", hdr_idx + 1, len(col))

    def g(r, name):
        i = col.get(name)
        return r[i] if i is not None and i < len(r) else None

    out, vacias = [], 0
    for r in rows[hdr_idx + 1:]:
        pid = clean(g(r, 'PersonaId'))
        if pid is None:
            vacias += 1
            continue
        per = to_date(g(r, 'Periodo'))
        out.append(dict(
            IT=g(r, 'IT'), Instituto=clean(g(r, 'Instituto')), PersonaId=pid,
            Area_Instituto=clean(g(r, 'Área')), SubArea=clean(g(r, 'Nombre Sub-área')),
            CCosto=str(clean(g(r, 'Centro de Costo'))) if clean(g(r, 'Centro de Costo')) is not None else None,
            FecNac=to_date(g(r, 'Fecha de Nacimiento')), Periodo=per, Mes=per.month if per else None,
            TipoContrato=clean(g(r, 'Tipo de Contrato')),
            TipoTrabajador=clean(g(r, 'Tipo_Trabajador')) or clean(g(r, 'Tipo_Trab_161225')),
            FecIngreso=to_date(g(r, 'Fecha Ingreso Compañía')), FecTermino=to_date(g(r, 'Fecha Término')),
            HorasSem=clean(g(r, 'Horas Semanales')), Cargo=upper(g(r, 'Cargo')),
            DiasJornada=clean(g(r, 'Días de la Jornada')), RegSIC=clean(g(r, 'Reg_SIC')),
            CodEsp=upper(g(r, 'Cod_Esp')), NDias=clean(g(r, 'Ndias'))))
    log.info("Contratos: %d registros válidos, %d filas vacías descartadas", len(out), vacias)
    out.sort(key=lambda x: (x['IT'] or 0, str(x['PersonaId']), x['Mes'] or 0))
    return out


# ----------------------------------------------------------------------------- tablas de salida
class Salida:
    def __init__(self):
        self.tablas = collections.OrderedDict()   # nombre -> (headers, rows)

    def add(self, nombre, headers, rows):
        self.tablas[nombre] = (headers, rows)
        log.info("Tabla %-26s %6d filas x %d columnas", nombre, len(rows), len(headers))


def tabla_dotacion(contr, gen):
    hdr = ['Clave', 'IT', 'Instituto', 'PersonaId', 'Periodo', 'Mes', 'Cargo', 'Cod_Esp', 'Centro_Costo', 'Sub_Area',
           'Tipo_Contrato', 'Tipo_Trabajador', 'Reg_SIC', 'Fecha_Ingreso', 'Fecha_Termino', 'Fecha_Nacimiento',
           'Mes_Cumpleanos', 'Horas_Semanales', 'Tramo_Horas', 'Dias_Jornada', 'N_Dias_Semana', 'Horas_Dia_Promedio',
           'Vigente_Mes', 'Alerta']
    rows, alertas = [], collections.Counter()
    for c in contr:
        vig = 'NO' if (c['FecTermino'] and c['Periodo'] and c['FecTermino'] < c['Periodo']) else 'SI'
        al = []
        if not c['HorasSem']:
            al.append('SIN_HORAS')
        if not c['Cargo']:
            al.append('SIN_CARGO')
        if not c['CodEsp']:
            al.append('SIN_COD_ESP')
        if c['NDias'] and c['DiasJornada'] and len(c['DiasJornada']) != c['NDias']:
            al.append('NDIAS_NO_CUADRA')
        for a in al:
            alertas[a] += 1
        mes = c['Mes'] or 0
        rows.append([f"{c['PersonaId']}-{c['IT']}-{mes:02d}", c['IT'], c['Instituto'], c['PersonaId'], c['Periodo'], c['Mes'],
                     c['Cargo'], c['CodEsp'], c['CCosto'], c['SubArea'], c['TipoContrato'], c['TipoTrabajador'], c['RegSIC'],
                     c['FecIngreso'], c['FecTermino'], c['FecNac'], c['FecNac'].month if c['FecNac'] else None,
                     c['HorasSem'], tramo(c['HorasSem'], gen['UMBRAL_TRAMO_1'], gen['UMBRAL_TRAMO_2']),
                     c['DiasJornada'], c['NDias'],
                     round(c['HorasSem'] / c['NDias'], 2) if c['HorasSem'] and c['NDias'] else None,
                     vig, ';'.join(al) or None])
    if alertas:
        log.warning("Alertas en contratos: %s", dict(alertas))
    return hdr, rows


def tabla_personas(contr):
    by = collections.defaultdict(list)
    for c in contr:
        by[(c['PersonaId'], c['IT'])].append(c)
    rows = []
    for (pid, it), lst in sorted(by.items(), key=lambda x: (x[0][1] or 0, str(x[0][0]))):
        lst.sort(key=lambda x: x['Mes'] or 0)
        first, last = lst[0], lst[-1]
        hs = [x['HorasSem'] for x in lst]
        rows.append([pid, it, last['Instituto'], last['Cargo'], last['CodEsp'], last['TipoContrato'], last['FecIngreso'],
                     last['FecTermino'], first['Mes'], last['Mes'], len(lst), hs[0], hs[-1],
                     'SI' if len(set(hs)) > 1 else 'NO', '/'.join(str(h) for h in hs)])
    hdr = ['PersonaId', 'IT', 'Instituto', 'Cargo', 'Cod_Esp', 'Tipo_Contrato', 'Fecha_Ingreso', 'Fecha_Termino',
           'Primer_Mes', 'Ultimo_Mes', 'N_Meses', 'Horas_Primer_Mes', 'Horas_Ultimo_Mes', 'Cambio_Horas', 'Horas_x_Mes']
    return hdr, rows


def tabla_cambios(contr, gen):
    bymes = collections.defaultdict(dict)
    for c in contr:
        bymes[c['Mes']][(c['PersonaId'], c['IT'])] = c
    meses = sorted(m for m in bymes if m)
    rows = []
    for i in range(1, len(meses)):
        m0, m1 = meses[i - 1], meses[i]
        prev, cur = bymes[m0], bymes[m1]
        for k, c in cur.items():
            if k not in prev:
                rows.append([m1, k[0], k[1], c['Instituto'], c['Cargo'], 'ALTA', None, c['HorasSem'], 'Nuevo en la base este mes'])
                continue
            p = prev[k]
            if p['HorasSem'] != c['HorasSem']:
                t0 = tramo(p['HorasSem'], gen['UMBRAL_TRAMO_1'], gen['UMBRAL_TRAMO_2'])
                t1 = tramo(c['HorasSem'], gen['UMBRAL_TRAMO_1'], gen['UMBRAL_TRAMO_2'])
                rows.append([m1, k[0], k[1], c['Instituto'], c['Cargo'], 'CAMBIO_HORAS', p['HorasSem'], c['HorasSem'],
                             'Cambio de tramo' if t0 != t1 else 'Mismo tramo'])
            if p['Cargo'] != c['Cargo']:
                rows.append([m1, k[0], k[1], c['Instituto'], c['Cargo'], 'CAMBIO_CARGO', p['Cargo'], c['Cargo'], None])
            if (p['FecTermino'] or '') != (c['FecTermino'] or ''):
                rows.append([m1, k[0], k[1], c['Instituto'], c['Cargo'], 'FECHA_TERMINO', p['FecTermino'], c['FecTermino'], None])
        for k, p in prev.items():
            if k not in cur:
                rows.append([m1, k[0], k[1], p['Instituto'], p['Cargo'], 'BAJA', p['HorasSem'], None, 'Desaparece de la base este mes'])
    log.info("Cambios detectados: %s", dict(collections.Counter(r[5] for r in rows)))
    hdr = ['Mes', 'PersonaId', 'IT', 'Instituto', 'Cargo', 'Tipo_Cambio', 'Valor_Anterior', 'Valor_Nuevo', 'Comentario']
    return hdr, rows


# ----------------------------------------------------------------------------- lectura: planificación (parámetros + entradas humanas + referencia)
GENERALES = [
    ('META_GESTION', 0.9, 'Fracción del plan que se fija como meta de gestión'),
    ('PCT_PAUSA_SALUDABLE_40H', 0.10, 'Pausa saludable como % de H/S cuando H/S >= 40'),
    ('PCT_PAUSA_SALUDABLE_MENOS_40H', 0.06, 'Pausa saludable como % de H/S cuando H/S < 40'),
    ('HORAS_COLACION_15MIN_POR_DIA', 0.25, 'Beneficio colación 15 min por día trabajado (0 si la colación está en el contrato)'),
    ('MIN_ESTANDAR_INDIRECTA', 30, 'Minutos estándar de una atención indirecta'),
    ('UMBRAL_TRAMO_1', 40, 'H/S >= este valor -> tramo 1'),
    ('UMBRAL_TRAMO_2', 22, 'H/S >= este valor y < tramo 1 -> tramo 2; menor -> tramo 3'),
    ('MAX_ASIGNACIONES_ESPECIALES', 2, 'Máximo de asignaciones especiales por profesional'),
    ('MIN_HS_PARA_ASIGNACION', 30, 'Horas semanales mínimas para tener asignación especial'),
    ('DIAS_FERIADO_LEGAL_ADICIONAL', 5, 'Días adicionales de feriado legal por persona-año'),
    ('DIAS_CUMPLEANOS', 0.5, 'Medio día por cumpleaños, en el mes de cumpleaños'),
    ('DIAS_VISPERA_FIESTAS_PATRIAS', 0.5, 'Se descuenta en septiembre'),
    ('DIAS_VISPERAS_NAVIDAD_ANO_NUEVO', 1, 'Se descuenta en diciembre'),
    ('FACTOR_DIAS_PROGRESIVOS', 0.7, 'Ponderador de días progresivos'),
    ('FACTOR_DIAS_COMPLEMENTARIOS', 0.8, 'Ponderador de días complementarios'),
    ('FACTOR_LEY_21530', 1, 'Ponderador descanso reparatorio Ley 21.530'),
    ('FACTOR_VAC_PENDIENTES', 1, 'Ponderador vacaciones legales pendientes'),
    ('MESES_2DO_SEMESTRE', 6, 'Meses sobre los que se prorratean los días adicionales (jul-dic)'),
    ('FACTOR_LOP_ENTREGAS', 0.85, 'Factor aplicado a entregas LOP últimos 12 meses'),
    ('ANIO_PLANIFICACION', 2026, 'Año que se planifica'),
]


def leer_planificacion(path, sal):
    log.info("Leyendo planificación: %s", path)
    wb = openpyxl.load_workbook(path, data_only=True)
    need = ['Parámetros', 'Distribucion_NAC', 'Dotacion_Asistencial', 'Excepciones', 'Resumen distribucion NAS', 'Planificacion Total']
    for n in need:
        if n not in wb.sheetnames:
            log.warning("Falta la hoja '%s' en el archivo de planificación (hojas: %s)", n, wb.sheetnames)
    par = wb['Parámetros']; dist = wb['Distribucion_NAC']; dot = wb['Dotacion_Asistencial']
    exc = wb['Excepciones']; resnas = wb['Resumen distribucion NAS']; ptot = wb['Planificacion Total']

    gen = {k: v for k, v, _ in GENERALES}

    # --- Generales
    sal.add('Param_Generales', ['Parametro', 'Valor', 'Descripcion'], [list(x) for x in GENERALES])

    # --- Distribución por cargo y tramo (encabezado doble en filas 5-6 del original)
    hr = find_header_row(dist, ['Cargo', 'STD Minutos Atención'])
    rows, seen = [], set()
    for r in range(hr + 2, dist.max_row + 1):
        cargo = upper(dist.cell(r, 2).value)
        if not cargo or cargo in seen:
            continue
        seen.add(cargo)
        esp, uni = upper(dist.cell(r, 1).value), clean(dist.cell(r, 3).value)
        mind, mini = dist.cell(r, 4).value, dist.cell(r, 5).value
        vals = [dist.cell(r, c).value or 0 for c in range(6, 15)]
        for t, v in zip(['T1_>=40', 'T2_22-39', 'T3_<22'], [vals[0:3], vals[3:6], vals[6:9]]):
            rows.append([cargo, esp, uni, t, v[0], v[1], v[2], mind, mini])
    sal.add('Param_Distribucion_Cargo', ['Cargo', 'Cod_Esp', 'Unidad', 'Tramo_Horas', 'Pct_Directo', 'Pct_Indirecto', 'Pct_NAS',
                                         'Min_Estandar_Directa', 'Min_Estandar_Indirecta'], rows)

    # --- Feriados (columna "Inhábiles 2026")
    hm = header_map(par, 1)
    cfer = hm.get('Inhábiles 2026', 11)
    fer = set()
    for r in range(2, par.max_row + 1):
        v = to_date(par.cell(r, cfer).value)
        if v:
            fer.add((v, v.month, clean(par.cell(r, cfer + 1).value)))
    fer = [list(x) for x in sorted(fer)]
    sal.add('Param_Feriados', ['Fecha', 'Mes', 'Tipo'], fer)
    if fer and max(f[1] for f in fer) < 12:
        log.warning("Feriados: el original sólo trae hasta el mes %d; completar ago-dic si se calcula el año completo", max(f[1] for f in fer))

    # --- Semanas hábiles por mes (bloque "Inhábiles por mes": S:AD)
    hr2 = None
    for r in range(1, 6):
        if any(str(c.value).strip() == 'DiaHabil' for c in par[r] if c.value is not None):
            hr2 = r; break
    # 'Mes' aparece dos veces en esa fila, así que se ubica todo relativo a 'DiaHabil'
    cdh = next(c.column for c in par[hr2] if c.value is not None and str(c.value).strip() == 'DiaHabil')
    cmes, cinh, csin, cdias = cdh - 6, cdh - 5, cdh - 4, cdh - 2
    rows = []
    for r in range(hr2 + 1, hr2 + 13):
        m = par.cell(r, cmes).value
        if not isinstance(m, int):
            continue
        dias = par.cell(r, cdias).value; inh = par.cell(r, cinh).value or 0; sinv = par.cell(r, csin).value or 0
        ajuste = inh - sinv
        hab = dias - inh + ajuste
        rows.append([m, MESES[m - 1], dt.date(gen['ANIO_PLANIFICACION'], m, 1), dias, inh, ajuste, hab, round(hab / 5, 1)])
    sal.add('Param_Semanas_Habiles', ['Mes', 'Nombre', 'Primer_Dia', 'Dias_Mes', 'Dias_Inhabiles', 'Ajuste_Vacaciones_Colectivas',
                                      'Dias_Habiles', 'Semanas_Habiles'], rows)

    # --- Factor grupal (bloque F:I)
    rows = []
    start = None
    for r in range(1, 10):
        if clean(par.cell(r, 6).value) == 'Cod_Esp':
            start = r + 1; break
    for r in range(start, start + 40):
        cod = upper(par.cell(r, 6).value)
        if not cod:
            break
        rows.append([cod, par.cell(r, 7).value or 0, par.cell(r, 8).value or 0, par.cell(r, 9).value or 0])
    sal.add('Param_Factor_Grupal', ['Cod_Esp', 'Pct_Atencion_Grupal', 'N_Pacientes_Grupo_San_Con', 'N_Pacientes_Grupo_Otros_IT'], rows)

    # --- Catálogo de asignaciones (bloque R:T de Distribucion_NAC)
    u = collections.OrderedDict()
    for r in range(hr + 2, 80):
        t = clean(dist.cell(r, 18).value)
        if t and t not in u:
            h = dist.cell(r, 19).value; desc = clean(dist.cell(r, 20).value)
            num = isinstance(h, (int, float))
            u[t] = [t, h if num else None, desc if num else None, desc if not num else None]
    sal.add('Param_Asignaciones', ['Asignacion', 'Horas_Semana', 'Unidad', 'Quien_Define'], list(u.values()))

    # --- Institutos / Especialidades / Homologación (bloques AM:AO, AX:AY, A:D)
    cit, cesp = hm.get('IT', 39), hm.get('Especialidad', 51) - 1
    rows, seen = [], set()
    for r in range(2, par.max_row + 1):
        it = par.cell(r, cit).value
        if it is None:
            break
        if it not in seen:
            seen.add(it); rows.append([it, clean(par.cell(r, cit + 1).value), clean(par.cell(r, cit + 2).value)])
    sal.add('Param_Institutos', ['IT', 'Sigla', 'Nombre'], rows)
    rows = []
    for r in range(2, par.max_row + 1):
        c = upper(par.cell(r, cesp).value)
        if not c:
            break
        rows.append([c, clean(par.cell(r, cesp + 1).value)])
    sal.add('Param_Especialidades', ['Cod_Esp', 'Especialidad'], rows)
    rows = []
    for r in range(2, par.max_row + 1):
        c = upper(par.cell(r, 1).value)
        if c:
            rows.append([upper(par.cell(r, 2).value), c, par.cell(r, 3).value, clean(par.cell(r, 4).value)])
    sal.add('Param_Homologacion_Cargo', ['Cargo_Homologado', 'Cod_Esp', 'Centro_Costo', 'Descripcion_CCosto'], rows)

    # --- Pacientes / LOP
    lop = {}
    for r in range(1, resnas.max_row + 1):
        if clean(resnas.cell(r, 6).value) == 'Planificación LOP VA':
            for rr in range(r + 1, r + 30):
                it = resnas.cell(rr, 1).value
                if isinstance(it, int):
                    lop[it] = resnas.cell(rr, 6).value
            break
    hr3 = find_header_row(ptot, ['IT', 'Instituto'])
    hm3 = header_map(ptot, hr3)
    cpac = next((c for h, c in hm3.items() if 'pacientes' in h.lower()), 9)
    rows = []
    for r in range(hr3 + 1, ptot.max_row + 1):
        it = ptot.cell(r, 1).value
        if isinstance(it, int):
            rows.append([it, clean(ptot.cell(r, 2).value), ptot.cell(r, cpac).value, lop.get(it)])
    sal.add('Param_Pacientes_LOP', ['IT', 'Sigla', 'Pacientes_Unicos_Proyectados', 'Planificacion_LOP'], rows)

    # ================= Dotacion_Asistencial: entradas humanas + referencia
    hr4 = find_header_row(dot, ['PersonaId', 'Cargo', 'Area'])
    hm4 = {k.strip(): v for k, v in header_map(dot, hr4).items()}
    log.info("Dotacion_Asistencial: encabezado en fila %d, %d columnas", hr4, len(hm4))

    def gv(r, name):
        c = hm4.get(name)
        if c is None:
            return None
        return clean(dot.cell(r, c).value)

    people = [r for r in range(hr4 + 1, dot.max_row + 1) if gv(r, 'PersonaId') is not None]
    log.info("Dotacion_Asistencial: %d profesionales", len(people))

    # Asignaciones especiales
    rows = []
    trio = [('Asignación 1 (seleccionar de lista desplegable)', 'Hrs. Asignación 1', 'VIGENTE'),
            ('Asignación 2 (seleccionar de lista desplegable)', 'Hrs. Asignación 2', 'VIGENTE'),
            ('Por Autorizar DMN y VP  (seleccionar de lista desplegable)', 'Hrs. Asignación 3', 'POR_AUTORIZAR')]
    for r in people:
        base = [gv(r, 'PersonaId'), gv(r, 'IT'), gv(r, 'Instituto'), upper(gv(r, 'Cargo'))]
        for k, (a, h, est) in enumerate(trio, 1):
            a_, h_ = gv(r, a), gv(r, h)
            if a_ or h_:
                rows.append(base + [k, clean(a_), h_, est])
        h4 = gv(r, 'Hrs. Asignación 4')
        if h4:
            rows.append(base + [4, 'Reunión sindical (0,25 h)', h4, 'VIGENTE'])
    sal.add('Asignaciones_Especiales', ['PersonaId', 'IT', 'Instituto', 'Cargo', 'N_Asignacion', 'Asignacion', 'Horas_Semana', 'Estado'], rows)

    # Ausencias por mes (semanas)
    rows = []
    for r in people:
        for m in range(1, 13):
            lic, vac, per = gv(r, f'Lic{m}') or 0, gv(r, f'Vac{m}') or 0, gv(r, f'Perm{m}') or 0
            if lic or vac or per:
                rows.append([gv(r, 'PersonaId'), gv(r, 'IT'), gv(r, 'Instituto'), upper(gv(r, 'Cargo')), m, lic, vac, per, lic + vac + per])
    sal.add('Ausencias_Mes', ['PersonaId', 'IT', 'Instituto', 'Cargo', 'Mes', 'Semanas_Licencia', 'Semanas_Vacaciones',
                              'Semanas_Permiso', 'Total_Semanas_Ausente'], rows)

    # Días adicionales
    cols = [("Feriado legal zona extrema ene'26", 'Feriado_Zona_Extrema_Ene'), ("Feriado legal zona extrema feb'26", 'Feriado_Zona_Extrema_Feb'),
            ('Mes cumpleaños', 'Mes_Cumpleanos'), ('Días de cumpleaños', 'Dias_Cumpleanos'), ('Visperas Fiestas Patrias', 'Dias_Vispera_FFPP'),
            ('Visperas Navidad y Año Nuevo', 'Dias_Visperas_Navidad'), ('Feriado legal adicional', 'Feriado_Legal_Adicional'),
            ('Días administrativos y 1/2 jornada familiar', 'Dias_Administrativos'), ('Plan anual capacitación por cargo', 'Dias_Capacitacion'),
            ('HEXA - CTR', 'Dias_HEXA_CTR'), ('Jornada nacional', 'Dias_Jornada_Nacional'), ('Días Progresivos', 'Dias_Progresivos'),
            ('Días Complementario', 'Dias_Complementarios'), ('Ley 21530', 'Dias_Ley_21530'),
            ('Vacaciones Legales Pendientes Periodos Anteriores', 'Dias_Vac_Pendientes'), ('Jornadas Directiva Sindical', 'Dias_Directiva_Sindical'),
            ('Lactancia (Equiv_días/año)', 'Dias_Lactancia'), ('Licencia Extensa', 'Licencia_Extensa'), ('Observaciones', 'Observaciones')]
    rows = [[gv(r, 'PersonaId'), gv(r, 'IT'), gv(r, 'Instituto'), upper(gv(r, 'Cargo'))] + [gv(r, a) for a, _ in cols] for r in people]
    sal.add('Dias_Adicionales', ['PersonaId', 'IT', 'Instituto', 'Cargo'] + [b for _, b in cols], rows)

    # Excepciones de horas entre institutos
    hr5 = find_header_row(exc, ['PersonaId', 'Instituto'])
    hm5 = header_map(exc, hr5)
    rows = []
    for r in range(hr5 + 1, exc.max_row + 1):
        pid = exc.cell(r, hm5['PersonaId']).value
        if not pid:
            continue
        mes_cols = [exc.cell(r, c).value for h, c in sorted(hm5.items(), key=lambda x: x[1]) if h[:3] == '01-']
        rows.append([pid, exc.cell(r, hm5['IT']).value, clean(exc.cell(r, hm5['Instituto']).value), clean(exc.cell(r, hm5['Nombre IT']).value),
                     exc.cell(r, hm5['H/S ene - dic']).value, exc.cell(r, hm5['H/S abr-dic']).value] + mes_cols + [exc.cell(r, hm5['D/S']).value])
    sal.add('Excepciones_Horas', ['PersonaId', 'IT', 'Sigla', 'Instituto', 'HS_Ene_Dic', 'HS_Abr_Dic'] + [f'HS_{m}' for m in MESES] + ['Dias_Semana'], rows)

    # Referencia por persona (lo que calcula hoy el Excel; para validar el bot)
    ref = [('PersonaId', 'PersonaId'), ('IT', 'IT'), ('Instituto', 'Instituto'), ('Cargo', 'Cargo'), ('Cod_Esp', 'Area'),
           ('Horas_Sem_Dic', 'H/S dic'), ('Prom_Pond_HS', 'Prom_Pond Horas Semanales'), ('N_Dias_Semana', 'N° Días Semana Contrato'),
           ('HS_Pausa_Saludable', 'H/Sem Pausa Saludable'), ('HS_Colacion_15min', 'H/Sem Beneficio Colación 15 minutos'),
           ('HS_Otras_NAS', 'H/Sem Otras NAS'), ('HS_NAS_Total', 'H/Sem NAS Total'), ('Pct_NAS', '% NAS'), ('Pct_Directo_Matriz', '%Directo'),
           ('Pct_Indirecto_Matriz', '%Indirecto'), ('Total_Hrs_Asignacion', 'Total Hrs. Asignación'), ('Pct_NAS_mas_Asig', '%NAS + Asig. Especiales'),
           ('Pct_Directo_Final', '%Directo Final'), ('Pct_Indirecto_Final', '%Indirecto Final'), ('Pct_Asistencial', '% Asistencial'),
           ('HS_Disponible_Atencion', 'H/Sem Disp.Ate'), ('Min_Directa', 'Estándar Minutos Atención Directa'),
           ('Min_Indirecta', 'Estándar Minutos Atención Indirecta'),
           ('Ate_Directas_Semana', 'N° Ate Directas (minutos estándar) - Semana may - dic'),
           ('Ate_Indirectas_Semana', 'N° Ate Indirectas (30 min) - Semana may - dic'),
           ('Pct_Grupal', '% Atención Grupal Estándar'), ('N_Pac_Grupo', 'N° Pacientes por Grupo'),
           ('Ate_Sem_Directa_Grupal', 'Atención Semanal Directa + Grupal'), ('Ate_Sem_Indirecta', 'Atención Semanal Indirecta Total'),
           ('Ate_Sem_Total', 'Total Atenciones por Semana Total')]
    ref += [(f'SemHab_{MESES[m-1]}', f'SemHab{m}') for m in range(1, 13)]
    ref += [('Semanas_Habiles_Totales', 'Semanas Hábiles Totales'), ('Dias_Habiles_Totales', 'Días Hábiles con D_Prog y Ley 21531')]
    ref += [(f'PlanDir_{MESES[m-1]}', f'PlanAteDir{m}') for m in range(1, 13)]
    ref += [('Plan_Anual_Directa', 'Plan_Atención Anual Directa'), ('Plan_Anual_Indirecta', 'Plan_Atención Anual Indirecta'),
            ('Plan_Anual_Total', 'Plan_Total Atenciones por Año')]
    ref += [(f'MG_Dir_{MESES[m-1]}', f'MG_AteDir{m}') for m in range(1, 13)]
    ref += [('MG_Anual_Directa', 'MG_Atención Anual Directa'), ('MG_Anual_Indirecta', 'MG_Atención Anual Indirecta'),
            ('MG_Anual_Total', 'MG_Total Atenciones por Año'), ('Horas_Anual_Directa', 'Tiempo en Atención Anual Directa'),
            ('Horas_Anual_Indirecta', 'Tiempo en Atención Anual Indirecta'), ('Horas_Anual_Total', 'Total Tiempo en Atenciones por Año')]
    faltan = [s for _, s in ref if s not in hm4]
    if faltan:
        log.warning("Referencia: columnas no encontradas en el original: %s", faltan)
    rows = []
    for r in people:
        row = []
        for out, s in ref:
            v = to_hours(gv(r, s))
            if s == 'Cargo':
                v = upper(v)
            if isinstance(v, float):
                v = round(v, 4)
            row.append(v)
        rows.append(row)
    sal.add('Referencia_Por_Persona', [o for o, _ in ref], rows)

    rows = []
    for r in range(hr3 + 1, ptot.max_row + 1):
        it = ptot.cell(r, 1).value
        if isinstance(it, int):
            rows.append([it, clean(ptot.cell(r, 2).value)] + [ptot.cell(r, c).value for c in range(3, 13)])
    sal.add('Referencia_Por_Instituto', ['IT', 'Sigla', 'Suma_Horas_Semanales', 'Atencion_Anual_Directa_MG', 'Atencion_Anual_Indirecta_MG',
                                         'Total_Atenciones_Anio', 'Total_LOP', 'Total_Planificacion', 'Pacientes_Unicos_Proyectados',
                                         'Intensidad_Total', 'Intensidad_Directa', 'Meta_90pct'], rows)
    return gen


# ----------------------------------------------------------------------------- escritura
def escribir(sal, carpeta, csv_tambien, log_lines):
    os.makedirs(carpeta, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    hfont = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    hfill = PatternFill('solid', fgColor='1F4E78')
    bfont = Font(name='Arial', size=10)
    for nombre, (hdr, rows) in sal.tablas.items():
        ws = wb.create_sheet(nombre[:31])
        for j, h in enumerate(hdr, 1):
            c = ws.cell(1, j, h); c.font = hfont; c.fill = hfill; c.alignment = Alignment(horizontal='center', vertical='center')
        for i, row in enumerate(rows, 2):
            for j, v in enumerate(row, 1):
                c = ws.cell(i, j, v); c.font = bfont
                if isinstance(v, (dt.date, dt.datetime)):
                    c.number_format = 'DD-MM-YYYY'
        ws.freeze_panes = 'A2'
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(hdr))}{len(rows)+1}"
        for j, h in enumerate(hdr, 1):
            ws.column_dimensions[get_column_letter(j)].width = min(max(len(str(h)), 10) + 2, 45)
    # Hoja Log
    ws = wb.create_sheet('Log', 0)
    ws.cell(1, 1, 'Linea').font = hfont; ws.cell(1, 1).fill = hfill
    ws.cell(1, 2, 'Mensaje').font = hfont; ws.cell(1, 2).fill = hfill
    for i, l in enumerate(log_lines, 2):
        ws.cell(i, 1, i - 1).font = bfont; ws.cell(i, 2, l).font = bfont
    ws.column_dimensions['B'].width = 140
    out = os.path.join(carpeta, 'Planificacion_Input_BluePrism.xlsx')
    wb.save(out)
    log.info("Libro generado: %s (%d hojas)", out, len(sal.tablas) + 1)
    if csv_tambien:
        d = os.path.join(carpeta, 'csv'); os.makedirs(d, exist_ok=True)
        for nombre, (hdr, rows) in sal.tablas.items():
            p = os.path.join(d, nombre + '.csv')
            with open(p, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f, delimiter=';')
                w.writerow(hdr)
                for row in rows:
                    w.writerow(['' if v is None else (v.strftime('%d-%m-%Y') if isinstance(v, (dt.date, dt.datetime)) else v) for v in row])
        log.info("CSV generados en %s (separador ;)", d)
    return out


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__(); self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


def main():
    ap = argparse.ArgumentParser(description='Traduce los Excel crudos de Teletón a tablas planas para Blue Prism')
    ap.add_argument('--contratos', required=True, help='Ruta a "Nac - Base contratos x mes.xlsx"')
    ap.add_argument('--planificacion', required=True, help='Ruta a "Nac - Planificación Asistencial x mes.xlsx"')
    ap.add_argument('--salida', default='salida', help='Carpeta de salida (se crea si no existe)')
    ap.add_argument('--csv', action='store_true', help='Además del .xlsx, exportar cada tabla como CSV (;)')
    a = ap.parse_args()

    os.makedirs(a.salida, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%H:%M:%S')
    lh = ListHandler(); lh.setFormatter(fmt)
    fh = logging.FileHandler(os.path.join(a.salida, 'bot_traductor.log'), encoding='utf-8'); fh.setFormatter(fmt)
    sh = logging.StreamHandler(); sh.setFormatter(fmt)
    log.setLevel(logging.INFO)
    for h in (lh, fh, sh):
        log.addHandler(h)

    log.info("=== BOT TRADUCTOR – inicio ===")
    sal = Salida()
    try:
        gen = leer_planificacion(a.planificacion, sal)
        contr = leer_contratos(a.contratos)
        hdr, rows = tabla_dotacion(contr, gen); sal.tablas['Dotacion_Mes'] = (hdr, rows); sal.tablas.move_to_end('Dotacion_Mes', last=False)
        log.info("Tabla %-26s %6d filas x %d columnas", 'Dotacion_Mes', len(rows), len(hdr))
        hdr, rows = tabla_personas(contr); sal.tablas['Personas'] = (hdr, rows)
        log.info("Tabla %-26s %6d filas x %d columnas", 'Personas', len(rows), len(hdr))
        hdr, rows = tabla_cambios(contr, gen); sal.tablas['Cambios_Mes'] = (hdr, rows)
        log.info("Tabla %-26s %6d filas x %d columnas", 'Cambios_Mes', len(rows), len(hdr))
        # orden final de hojas
        orden = ['Dotacion_Mes', 'Personas', 'Cambios_Mes'] + [k for k in sal.tablas if k.startswith('Param_')] + \
                ['Asignaciones_Especiales', 'Ausencias_Mes', 'Dias_Adicionales', 'Excepciones_Horas', 'Referencia_Por_Persona', 'Referencia_Por_Instituto']
        sal.tablas = collections.OrderedDict((k, sal.tablas[k]) for k in orden if k in sal.tablas)
        out = escribir(sal, a.salida, a.csv, lh.lines)
        log.info("=== fin OK: %s ===", out)
    except Exception as e:
        log.exception("ERROR: %s", e)
        sys.exit(2)


if __name__ == '__main__':
    main()
