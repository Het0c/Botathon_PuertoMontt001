/* Cada hora cuenta — frontend sin framework.
   Todo dato visible viene de /api/v1; aquí solo se agrupa, filtra y formatea. */

const ANIO = 2026;
const API = '/api/v1';
const VISTAS = ['consolidado', 'profesionales', 'parametros', 'asignaciones', 'bitacora'];
const TITULOS = {
  consolidado: 'Consolidado nacional',
  profesionales: 'Profesionales',
  parametros: 'Parámetros',
  asignaciones: 'Asignaciones por aprobar',
  bitacora: 'Bitácora',
};
const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
const ROLES = { management: 'Gerencia', rrhh: 'RRHH', dmn: 'DMN', professional: 'Profesional', rpa: 'RPA' };
const PERMISOS_TEXTO = {
  management: 'Solo lectura.',
  rrhh: 'Puede editar parámetros y crear solicitudes.',
  dmn: 'Puede editar parámetros, crear solicitudes y aprobarlas o rechazarlas.',
  professional: 'Solo puede ver su propia planificación.',
};
const PUEDE = {
  gestion: (rol) => rol !== 'professional', // lectura de vistas de gestión (management, rrhh, dmn)
  editar: (rol) => rol === 'rrhh' || rol === 'dmn',
  aprobar: (rol) => rol === 'dmn',
};
const TRAMOS = { 'T1_>=40': 'T1 (40 h o más)', 'T2_22-39': 'T2 (22 a 39 h)', 'T3_<22': 'T3 (menos de 22 h)' };
const ORDEN_TRAMO = { 'T1_>=40': 1, 'T2_22-39': 2, 'T3_<22': 3 };
const VACIO_BUK = 'Sin datos. Importa un reporte BUK con el bot de Blue Prism.';
const VACIO_PARAM = 'Sin datos. Carga los parámetros de referencia con seed_reference_data.';
const VACIO_ERROR = 'No se pudo cargar. Revisa el mensaje de error.';
const ACCIONES = {
  import_created: 'Importación creada',
  import_completed: 'Importación completada',
  contract_delta_applied: 'Cambio contractual aplicado',
  parameter_created: 'Parámetro creado',
  legal_reference_created: 'Jornada legal creada',
  calendar_created: 'Calendario creado',
  assignment_catalog_created: 'Asignación agregada al catálogo',
  assignment_requested: 'Asignación solicitada',
  assignment_approved: 'Asignación aprobada',
  assignment_rejected: 'Asignación rechazada',
  planning_recalculated: 'Planificación recalculada',
};
const ENTIDADES = {
  rpa_import: 'Importación RPA',
  contract: 'Contrato',
  distribution_parameter: 'Distribución cargo y tramo',
  system_parameter: 'Parámetro general',
  legal_workweek_reference: 'Jornada legal',
  institutional_calendar: 'Calendario',
  assignment_catalog: 'Catálogo de asignaciones',
  assignment_request: 'Solicitud de asignación',
  planning: 'Planificación',
};
// [tipo de insignia, símbolo, texto]: el estado nunca depende solo del color.
const ESTADOS_SOL = {
  pending: ['warn', '○', 'Pendiente'],
  approved: ['ok', '✓', 'Aprobada'],
  rejected: ['error', '✕', 'Rechazada'],
};
const ESTADOS_COMP = {
  BAJO_META: ['error', '▼', 'Bajo meta'],
  EN_META: ['ok', '✓', 'En meta'],
  SIN_REPORTE: ['neutral', '–', 'Sin reporte'],
};

/* ------------------------------------------------------------------ utilidades DOM */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : String(c));
  }
  return node;
}

function sinDato() {
  return el('span', {}, el('span', { 'aria-hidden': 'true' }, '—'), el('span', { class: 'visually-hidden' }, 'sin dato'));
}

function cell(valor, opts = {}) {
  const attrs = { class: [opts.num ? 'num' : '', opts.class || ''].join(' ').trim() || null };
  if (opts.th) attrs.scope = opts.scope || 'row';
  if (opts.colspan) attrs.colspan = opts.colspan;
  const vacio = valor == null || valor === '' || (Array.isArray(valor) && !valor.some((v) => v != null));
  return el(opts.th ? 'th' : 'td', attrs, vacio ? sinDato() : valor);
}

function badge([tipo, simbolo, texto]) {
  return el('span', { class: `badge badge-${tipo}` }, el('span', { 'aria-hidden': 'true' }, simbolo), texto);
}

/** Llena un tbody. filas === null significa que la carga falló. */
function llenar(tbody, filas, filaFn, textoVacio) {
  tbody.replaceChildren();
  if (!filas || !filas.length) {
    const primera = $('thead tr', tbody.closest('table'));
    const cols = primera ? [...primera.cells].filter((c) => !c.hidden).reduce((s, c) => s + c.colSpan, 0) : 1;
    tbody.append(el('tr', {}, el('td', { colspan: cols, class: 'empty' }, filas === null ? VACIO_ERROR : textoVacio)));
  } else {
    const frag = document.createDocumentFragment();
    for (const f of filas) frag.append(filaFn(f));
    tbody.append(frag);
  }
  programarAjusteScroll();
}

function opciones(select, valores, primera) {
  const actual = select.value;
  const lista = primera != null ? [el('option', { value: '' }, primera)] : [];
  for (const v of valores) {
    lista.push(typeof v === 'object' ? el('option', { value: v.value }, v.text) : el('option', { value: v }, v));
  }
  select.replaceChildren(...lista);
  if ([...select.options].some((o) => o.value === actual)) select.value = actual;
}
const opcionesMeses = (select, primera) => opciones(select, MESES.map((m, i) => ({ value: String(i + 1), text: m })), primera);

let ajustePendiente = false;
/** Las tablas que desbordan se vuelven regiones enfocables para poder desplazarlas con teclado. */
function programarAjusteScroll() {
  if (ajustePendiente) return;
  ajustePendiente = true;
  requestAnimationFrame(() => {
    ajustePendiente = false;
    for (const w of $$('.table-wrap')) {
      const desborda = w.scrollWidth > w.clientWidth + 1 || w.scrollHeight > w.clientHeight + 1;
      if (desborda) {
        w.tabIndex = 0;
        w.setAttribute('role', 'region');
        w.setAttribute('aria-label', `${$('caption', w)?.textContent.trim() || 'Tabla'} (desplazable)`);
      } else {
        w.removeAttribute('tabindex');
        w.removeAttribute('role');
        w.removeAttribute('aria-label');
      }
    }
  });
}

/* ------------------------------------------------------------------ formato es-CL */
function fmtNum(v, dec = 0) {
  if (v == null || v === '' || !Number.isFinite(Number(v))) return null;
  const n = Number(v);
  const fijo = Math.abs(n).toFixed(dec);
  const [entero, fraccion] = fijo.split('.');
  const miles = entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  const negativo = n < 0 && Number(fijo) !== 0;
  return (negativo ? '-' : '') + miles + (fraccion ? `,${fraccion}` : '');
}
const fmtInt = (v) => fmtNum(v, 0);
const fmtHoras = (v) => fmtNum(v, 1);
const fmtDias = (v) => (Number.isInteger(Number(v)) ? fmtInt(v) : fmtNum(v, 1));
const fmtPct = (fraccion) => (fraccion == null || !Number.isFinite(Number(fraccion)) ? null : `${fmtNum(Number(fraccion) * 100, 1)} %`);

function fmtFecha(iso) {
  if (!iso) return null;
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return d ? `${d}-${m}-${y}` : String(iso);
}
function fmtFechaHora(iso) {
  if (!iso) return null;
  let s = String(iso);
  if (!/(Z|[+-]\d\d:?\d\d)$/i.test(s)) s += 'Z'; // SQLite entrega UTC sin zona horaria
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return String(iso);
  const p = (x) => String(x).padStart(2, '0');
  return `${p(d.getDate())}-${p(d.getMonth() + 1)}-${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
const fraccion = (pct) => Number((pct / 100).toFixed(6));
const pctTexto = (frac) => fmtNum(Number(frac) * 100, 1).replace(/,0$/, '');

/** Lee un porcentaje escrito de 0 a 100 ("85", "85,5", "85 %"). Marca el campo y devuelve {valor} o {error}.
    Rechaza valores entre 0 y 1: casi siempre son fracciones (0,85 en vez de 85). */
function leerPorcentaje(input, { nombre, min = 0, obligatorio = false }) {
  input.setCustomValidity('');
  input.removeAttribute('aria-invalid');
  const crudo = input.value.trim().replace(/\s*%$/, '').replace(',', '.');
  let error;
  if (crudo === '') {
    if (!obligatorio) return { valor: undefined };
    error = `${nombre}: escribe un valor de ${min} a 100.`;
  } else if (!/^\d+(\.\d+)?$/.test(crudo)) {
    error = `${nombre}: escribe un número de ${min} a 100, por ejemplo 85.`;
  } else {
    const v = Number(crudo);
    if (v > 100) error = `${nombre}: no puede superar 100.`;
    else if (v < min || (v > 0 && v < 1)) error = `${nombre}: los porcentajes van de ${min} a 100. Para 85 % escribe 85, no 0,85.`;
    else return { valor: v };
  }
  input.setCustomValidity(error);
  input.setAttribute('aria-invalid', 'true');
  return { error };
}
const normalizar = (s) => String(s ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
const distintos = (filas, k) => [...new Set(filas.map((f) => f[k]).filter((v) => v != null && v !== ''))].sort((a, b) => String(a).localeCompare(String(b), 'es'));
const mesNombre = (m) => MESES[Number(m) - 1] ?? String(m);

/* ------------------------------------------------------------------ sesión */
const store = {
  get(k, def = '') {
    try { return localStorage.getItem(k) ?? def; } catch { return def; }
  },
  set(k, v) {
    try { localStorage.setItem(k, v); } catch { /* almacenamiento no disponible */ }
  },
};
const sesion = {
  apiKey: store.get('chc.apiKey'),
  usuario: store.get('chc.usuario'),
  rol: store.get('chc.rol', 'management'),
};
if (!PERMISOS_TEXTO[sesion.rol]) sesion.rol = 'management';

/* ------------------------------------------------------------------ mensajes (aria-live) */
const TIPOS_MSG = { error: ['✕', 'Error'], ok: ['✓', 'Listo'], info: ['i', 'Aviso'] };

function avisar(tipo, texto) {
  const zona = $('#mensajes');
  if ([...zona.children].some((m) => m.dataset.texto === texto)) return;
  // Un aviso nuevo deja obsoletos los de éxito/información anteriores; un éxito también reemplaza errores previos.
  for (const m of [...zona.children]) if (tipo === 'ok' || !m.classList.contains('msg-error')) m.remove();
  const [simbolo, etiqueta] = TIPOS_MSG[tipo];
  const caja = el('div', { class: `msg msg-${tipo}`, dataset: { texto } },
    el('span', { class: 'msg-icon', 'aria-hidden': 'true' }, simbolo),
    el('p', {}, el('strong', {}, `${etiqueta}: `), texto),
    el('button', {
      type: 'button',
      class: 'btn-link',
      'aria-label': `Cerrar mensaje: ${etiqueta}`,
      onclick: () => { caja.remove(); ajustarMargenScroll(); enfocarTitulo(); },
    }, 'Cerrar'));
  zona.append(caja);
  while (zona.children.length > 3) zona.firstElementChild.remove();
  if (tipo === 'ok') cerrarSolo(caja);
  ajustarMargenScroll();
}
/** Los avisos de éxito se cierran solos a los 5 s (los errores quedan). Se espera si el puntero o el foco están encima. */
function cerrarSolo(caja, ms = 5000) {
  setTimeout(() => {
    if (!caja.isConnected) return;
    if (caja.matches(':hover') || caja.contains(document.activeElement)) {
      cerrarSolo(caja, 1500);
      return;
    }
    caja.remove();
    ajustarMargenScroll();
  }, ms);
}
/** La zona de mensajes es fija arriba: el foco por teclado se desplaza para no quedar debajo de ella. */
function ajustarMargenScroll() {
  const alto = $('#mensajes').offsetHeight;
  document.documentElement.style.scrollPaddingTop = alto ? `${alto + 16}px` : '';
}
const limpiarMensajes = () => { $('#mensajes').replaceChildren(); ajustarMargenScroll(); };
const enfocarTitulo = () => $(`#t-${vistaActual}`)?.focus();

/* ------------------------------------------------------------------ API */
class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}
const PREFIJOS = {
  400: 'Solicitud inválida (400)',
  401: 'No autorizado (401)',
  403: 'Sin permiso (403)',
  404: 'No encontrado (404)',
  409: 'Conflicto (409)',
  422: 'Datos inválidos (422)',
  500: 'Error del servidor (500)',
};
const TRADUCCIONES = [
  [/^Field required$/, 'campo obligatorio'],
  [/^Input should be a valid number.*$/, 'debe ser un número'],
  [/^Input should be a valid date.*$/, 'debe ser una fecha válida'],
  [/^Input should be less than or equal to (.*)$/, 'debe ser menor o igual a $1'],
  [/^Input should be greater than or equal to (.*)$/, 'debe ser mayor o igual a $1'],
  [/^Input should be greater than (.*)$/, 'debe ser mayor que $1'],
  [/^Input should be (.*)$/, 'debe ser $1'],
  [/^String should have at least (\d+) characters?$/, 'debe tener al menos $1 caracteres'],
  [/^String should have at most (\d+) characters?$/, 'debe tener como máximo $1 caracteres'],
];
function traducir(msg) {
  const m = String(msg).replace(/^Value error, /, '');
  for (const [re, rep] of TRADUCCIONES) if (re.test(m)) return m.replace(re, rep);
  return m;
}
function detalleError(detail) {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const campo = (d.loc || []).filter((x) => x !== 'body').join('.');
      return campo ? `${campo}: ${traducir(d.msg)}` : traducir(d.msg);
    }).join('; ');
  }
  if (typeof detail === 'object' && 'detail' in detail) return detalleError(detail.detail);
  return JSON.stringify(detail);
}

let pendientes = 0;
function marcarCarga(delta) {
  pendientes = Math.max(0, pendientes + delta);
  $('#cargando').hidden = pendientes === 0;
  const vista = vistaActual && $(`#vista-${vistaActual}`);
  if (vista) vista.setAttribute('aria-busy', pendientes > 0 ? 'true' : 'false');
}

/** Única puerta a la API: agrega cabeceras, maneja errores HTTP, parsea JSON y muestra la carga. */
async function api(ruta, { method = 'GET', query, body } = {}) {
  if (!sesion.apiKey) throw new ApiError(0, 'Falta la API key. Ingrésala en la barra superior y presiona Aplicar.');
  if (!sesion.usuario) throw new ApiError(0, 'Falta el usuario. Escríbelo en la barra superior y presiona Aplicar.');
  if (/[^\u0000-ÿ]/.test(sesion.apiKey + sesion.usuario)) {
    throw new ApiError(0, 'La API key y el usuario solo admiten letras latinas, números y signos comunes.');
  }
  const url = new URL(API + ruta, location.origin);
  for (const [k, v] of Object.entries(query || {})) {
    if (v !== '' && v != null) url.searchParams.set(k, v);
  }
  const headers = {
    Accept: 'application/json',
    'X-API-Key': sesion.apiKey,
    'X-User-ID': sesion.usuario,
    'X-Role': sesion.rol,
  };
  const init = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  marcarCarga(1);
  try {
    let res;
    try {
      res = await fetch(url, init);
    } catch {
      throw new ApiError(0, 'No se pudo conectar con el servidor. Verifica que el backend esté corriendo.');
    }
    const texto = await res.text();
    let datos = null;
    if (texto) {
      try { datos = JSON.parse(texto); } catch { datos = texto; }
    }
    if (!res.ok) {
      const det = detalleError(datos && typeof datos === 'object' ? datos.detail : datos) || res.statusText;
      let msg = `${PREFIJOS[res.status] || `Error HTTP ${res.status}`}: ${det}`;
      if (res.status === 403) msg += ` (rol actual: ${ROLES[sesion.rol]})`;
      if (res.status === 401) msg += '. Revisa la API key en «Configuración».';
      throw new ApiError(res.status, msg);
    }
    return datos;
  } finally {
    marcarCarga(-1);
  }
}

function mostrarError(err) {
  avisar('error', err instanceof ApiError ? err.message : `Error inesperado: ${err?.message ?? err}`);
}
/** Ejecuta fn y muestra cualquier error en la zona de mensajes. Devuelve undefined si falló. */
async function intentar(fn) {
  try {
    return await fn();
  } catch (err) {
    mostrarError(err);
    return undefined;
  }
}
/** Como Promise.all sobre un objeto, pero cada falla se informa y su valor queda en null. */
async function todas(promesas) {
  const claves = Object.keys(promesas);
  const res = await Promise.allSettled(Object.values(promesas));
  const out = {};
  res.forEach((r, i) => {
    if (r.status === 'fulfilled') out[claves[i]] = r.value;
    else { mostrarError(r.reason); out[claves[i]] = null; }
  });
  return out;
}

/** Trae todas las páginas de un endpoint paginado {items, total}. */
async function traerTodo(ruta, query, size) {
  const primera = await api(ruta, { query: { ...query, page: 1, size } });
  const items = [...primera.items];
  const paginas = Math.ceil(primera.total / size);
  if (paginas > 1) {
    const resto = await Promise.all(
      Array.from({ length: paginas - 1 }, (_, i) => api(ruta, { query: { ...query, page: i + 2, size } })),
    );
    for (const r of resto) items.push(...r.items);
  }
  return items;
}
const traerPlanificacion = (filtros = {}) => traerTodo('/planificacion', { ...filtros, year: ANIO }, 500);
const traerProfesionales = () => traerTodo('/profesionales', {}, 200);

let institutos = [];
async function cargarInstitutos() {
  institutos = (await api('/institutos')) || [];
  return institutos;
}
const nombreInst = (codigo) => institutos.find((i) => i.codigo === codigo)?.nombre || codigo;
const opcionesInst = (select, primera) => opciones(select, institutos.map((i) => ({ value: i.codigo, text: `${i.nombre} (${i.codigo})` })), primera);

/** Meta vigente hoy desde /parametros.generales; si no hay, el backend usa 0,90. */
function metaVigente(generales) {
  const hoy = hoyISO();
  const filas = (generales || [])
    .filter((g) => g.codigo === 'META_GESTION' && (!g.vigenteDesde || g.vigenteDesde <= hoy))
    .sort((a, b) => String(b.vigenteDesde).localeCompare(String(a.vigenteDesde)));
  if (!filas.length) return { valor: 0.9, desde: null, omision: true };
  const v = filas[0].valor;
  return { valor: Number(v && typeof v === 'object' ? v.value : v), desde: filas[0].vigenteDesde, omision: false };
}

/* ================================================================== 1. CONSOLIDADO */
const consol = { filas: [], nacional: null, porInst: [], profs: null, meta: null, token: 0, grafico: null };

async function cargarConsolidado() {
  const r = await todas({
    inst: cargarInstitutos(),
    filas: traerPlanificacion(),
    nacional: api('/dashboard/nacional', { query: { year: ANIO } }),
    porInst: api('/dashboard/institutos', { query: { year: ANIO } }),
    alertas: api('/dashboard/alertas', { query: { year: ANIO } }),
    profs: traerProfesionales(),
    params: api('/parametros'),
  });
  opcionesInst($('#f-instituto'), 'Todos');
  consol.filas = r.filas || [];
  opciones($('#f-area'), distintos(consol.filas, 'area'), 'Todas');
  opciones($('#f-cargo'), distintos(consol.filas, 'cargo'), 'Todos');
  consol.nacional = r.nacional;
  consol.porInst = r.porInst;
  consol.profs = r.profs;
  consol.meta = r.params ? metaVigente(r.params.generales) : null;

  const etiquetaMeta = consol.meta ? ` (${fmtPct(consol.meta.valor)})` : '';
  $('#k-meta-label').textContent = `Meta de Gestión Asistencial${etiquetaMeta}`;
  $('#th-meta-inst').textContent = `Meta${etiquetaMeta.replace(/[()]/g, '')}`;
  pintarAlertas(r.alertas);
  await aplicarFiltros();
}

const filtrosActuales = () => ({
  instituto: $('#f-instituto').value,
  area: $('#f-area').value,
  cargo: $('#f-cargo').value,
  mes: $('#f-mes').value,
});

async function aplicarFiltros() {
  const f = filtrosActuales();
  const token = ++consol.token;
  const filtroBase = Boolean(f.instituto || f.area || f.cargo);
  let filas = consol.filas;
  if (filtroBase) {
    filas = await intentar(() => traerPlanificacion({ institute: f.instituto, area: f.area, role: f.cargo }));
    if (token !== consol.token) return; // llegó una respuesta vieja
    filas = filas || [];
  }
  const filasMes = f.mes ? filas.filter((x) => x.mes === Number(f.mes)) : filas;
  pintarTarjetas(filtroBase || f.mes ? sumar(filasMes) : null);
  pintarGrafico(filas, f.mes);
  pintarResumenFiltro(f, filasMes.length);
  pintarInstitutos(f);
  if (consol.focoInst) {
    $(`#tb-institutos button[data-inst="${CSS.escape(consol.focoInst)}"]`)?.focus();
    consol.focoInst = null;
  }
}

/** Suma filas mensuales con la misma forma que /dashboard (FOJA = horas directas / contratadas). */
function agregar(filas, instituto = null) {
  const s = { instituto, horasContratadas: 0, horasDirectas: 0, atencionesDirectas: 0, atencionesIndirectas: 0, atencionesPlanificadas: 0, metaGestion: 0 };
  for (const f of filas) for (const k of Object.keys(s)) if (k !== 'instituto') s[k] += Number(f[k]) || 0;
  s.foja = s.horasContratadas ? s.horasDirectas / s.horasContratadas : null;
  return s;
}

function sumar(filas) {
  const s = { atencionesPlanificadas: 0, metaGestion: 0, horasDirectas: 0, horasContratadas: 0 };
  const personas = new Set();
  for (const f of filas) {
    for (const k of Object.keys(s)) s[k] += Number(f[k]) || 0;
    personas.add(f.personaId);
  }
  s.foja = s.horasContratadas ? s.horasDirectas / s.horasContratadas : null;
  s.personas = personas.size;
  return s;
}

function ponerValor(sel, texto) {
  $(sel).replaceChildren(texto == null ? sinDato() : texto);
}

function pintarTarjetas(suma) {
  if (!suma) {
    const n = consol.nacional;
    ponerValor('#k-planificadas', fmtInt(n?.atencionesPlanificadas));
    ponerValor('#k-meta', fmtInt(n?.metaGestion));
    ponerValor('#k-foja', fmtPct(n?.foja));
    $('#k-planificadas-sub').textContent = `Total nacional, año ${ANIO}`;
    $('#k-meta-sub').textContent = `Total nacional, año ${ANIO}`;
    if (consol.profs) {
      const activos = consol.profs.filter((p) => p.activa).length;
      ponerValor('#k-profesionales', fmtInt(activos));
      $('#k-profesionales-sub').textContent = `de ${fmtInt(consol.profs.length)} registrados`;
    } else {
      ponerValor('#k-profesionales', null);
      $('#k-profesionales-sub').textContent = '';
    }
    return;
  }
  ponerValor('#k-planificadas', fmtInt(suma.atencionesPlanificadas));
  ponerValor('#k-meta', fmtInt(suma.metaGestion));
  ponerValor('#k-foja', fmtPct(suma.foja));
  ponerValor('#k-profesionales', fmtInt(suma.personas));
  $('#k-planificadas-sub').textContent = 'Según los filtros aplicados';
  $('#k-meta-sub').textContent = 'Según los filtros aplicados';
  $('#k-profesionales-sub').textContent = 'con planificación en la selección';
}

function pintarResumenFiltro(f, nFilas) {
  const partes = [];
  partes.push(f.instituto ? nombreInst(f.instituto) : 'todos los institutos');
  if (f.area) partes.push(`área ${f.area}`);
  if (f.cargo) partes.push(`cargo ${f.cargo}`);
  partes.push(f.mes ? mesNombre(f.mes) : `año ${ANIO} completo`);
  const filtrado = f.instituto || f.area || f.cargo || f.mes;
  let texto = `Mostrando: ${partes.join(' · ')}.`;
  if (filtrado) {
    if (!nFilas) texto += ' No hay filas de planificación para esta combinación.';
    else texto += nFilas === 1 ? ' 1 fila mensual de planificación.' : ` ${fmtInt(nFilas)} filas mensuales de planificación.`;
  }
  $('#filtro-resumen').textContent = texto;
}

function iconoFiltro() {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', 'M1 2h14l-5.5 6.5V14l-3-1.5V8.5z');
  path.setAttribute('fill', 'currentColor');
  svg.append(path);
  return svg;
}

/** Sin área, cargo ni mes: datos anuales de /dashboard/institutos. Con alguno: se agrupan las filas de /planificacion. */
function pintarInstitutos(f) {
  const subfiltro = Boolean(f.area || f.cargo || f.mes);
  let filas;
  let total;
  if (subfiltro) {
    const base = consol.filas.filter((x) => (!f.area || x.area === f.area) && (!f.cargo || x.cargo === f.cargo) && (!f.mes || x.mes === Number(f.mes)));
    const grupos = new Map();
    for (const x of base) grupos.set(x.instituto, [...(grupos.get(x.instituto) || []), x]);
    filas = [...grupos].map(([codigo, lista]) => agregar(lista, codigo));
    total = base.length ? agregar(base) : null;
  } else {
    filas = consol.porInst;
    total = consol.nacional;
  }
  const partes = [f.mes ? `${mesNombre(f.mes)} ${ANIO}` : `año ${ANIO}`];
  if (f.area) partes.push(`área ${f.area}`);
  if (f.cargo) partes.push(`cargo ${f.cargo}`);
  const titulo = subfiltro ? `Resumen por instituto · ${partes.join(' · ')}` : `Resumen anual por instituto · ${ANIO}`;
  $('#t-resumen-inst').textContent = titulo;
  $('#resumen-inst-caption').textContent = titulo;

  const ordenadas = filas ? [...filas].sort((a, b) => nombreInst(a.instituto).localeCompare(nombreInst(b.instituto), 'es')) : null;
  llenar($('#tb-institutos'), ordenadas, (r) => {
    const nombre = nombreInst(r.instituto);
    const activo = r.instituto === f.instituto;
    const alternar = () => {
      const sel = $('#f-instituto');
      if (activo) sel.value = '';
      else {
        if (![...sel.options].some((o) => o.value === r.instituto)) sel.append(el('option', { value: r.instituto }, nombre));
        sel.value = r.instituto;
      }
      consol.focoInst = r.instituto;
      intentar(aplicarFiltros);
    };
    return el('tr', { class: activo ? 'clickable is-selected' : 'clickable', dataset: { inst: r.instituto }, onclick: (e) => { if (!e.target.closest('button')) alternar(); } },
      el('th', { scope: 'row' },
        el('button', {
          type: 'button',
          class: 'btn-link filter-btn',
          dataset: { inst: r.instituto },
          'aria-pressed': String(activo),
          'aria-label': `Filtrar por ${nombre}`,
          onclick: alternar,
        }, iconoFiltro(), nombre),
        activo ? el('span', { class: 'muted' }, ' (filtro activo)') : null),
      cell(fmtHoras(r.horasContratadas), { num: true }),
      cell(fmtInt(r.atencionesDirectas), { num: true }),
      cell(fmtInt(r.atencionesIndirectas), { num: true }),
      cell(fmtInt(r.atencionesPlanificadas), { num: true }),
      cell(fmtInt(r.metaGestion), { num: true }),
      cell(fmtPct(r.foja), { num: true }));
  }, VACIO_BUK);

  $('#tf-institutos').replaceChildren(total && ordenadas?.length
    ? el('tr', {},
      cell(subfiltro ? 'Total de la selección' : 'Total nacional', { th: true }),
      cell(fmtHoras(total.horasContratadas), { num: true }),
      cell(fmtInt(total.atencionesDirectas), { num: true }),
      cell(fmtInt(total.atencionesIndirectas), { num: true }),
      cell(fmtInt(total.atencionesPlanificadas), { num: true }),
      cell(fmtInt(total.metaGestion), { num: true }),
      cell(fmtPct(total.foja), { num: true }))
    : '');
}

function pintarAlertas(alertas) {
  const filas = alertas
    ? [...alertas].sort((a, b) => String(a.instituto).localeCompare(String(b.instituto)) || String(a.personaId).localeCompare(String(b.personaId), 'es', { numeric: true }) || a.mes - b.mes)
    : null;
  llenar($('#tb-alertas'), filas, (a) => el('tr', {},
    el('th', { scope: 'row' }, el('button', {
      type: 'button',
      class: 'btn-link',
      'aria-label': `${a.personaId}, ver detalle del profesional`,
      onclick: () => { prof.seleccionado = a.personaId; location.hash = '#profesionales'; },
    }, a.personaId)),
    cell(nombreInst(a.instituto)),
    cell(mesNombre(a.mes)),
    cell(fmtInt(a.meta), { num: true }),
    cell(fmtInt(a.ejecutado), { num: true }),
    cell(fmtInt(a.desviacion), { num: true }),
    cell(fmtPct(a.cumplimiento), { num: true }),
    cell(badge(ESTADOS_COMP[a.estado] || ['neutral', '•', a.estado]))), 'Sin alertas de desviación');
}

const AZUL = '#0b5cad';
const AZUL_TENUE = 'rgba(11, 92, 173, 0.28)';

function rayado(linea = '#8a4b00', fondo = '#f6e7d2') {
  const c = document.createElement('canvas');
  c.width = 8;
  c.height = 8;
  const x = c.getContext('2d');
  x.fillStyle = fondo;
  x.fillRect(0, 0, 8, 8);
  x.strokeStyle = linea;
  x.lineWidth = 2;
  x.beginPath();
  x.moveTo(0, 8); x.lineTo(8, 0);
  x.moveTo(-2, 2); x.lineTo(2, -2);
  x.moveTo(6, 10); x.lineTo(10, 6);
  x.stroke();
  return x.createPattern(c, 'repeat');
}

function crearGrafico() {
  const Chart = window.Chart;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 14;
  Chart.defaults.color = '#17202c';
  Chart.defaults.animation = false;
  consol.patron = rayado();
  consol.patronTenue = rayado('rgba(138, 75, 0, 0.3)', '#fdf8f1');
  return new Chart($('#grafico-mensual'), {
    type: 'bar',
    data: {
      labels: MESES.map((m) => m.slice(0, 3)),
      datasets: [
        { label: 'Atenciones planificadas', data: [], backgroundColor: AZUL, borderColor: AZUL, borderWidth: 1 },
        { label: 'Meta de gestión (barras rayadas)', data: [], backgroundColor: consol.patron, borderColor: '#8a4b00', borderWidth: 2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        title: { display: true, text: `Atenciones planificadas y meta de gestión por mes, ${ANIO}`, font: { size: 16, weight: 'bold' }, padding: { bottom: 12 } },
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 28,
            boxHeight: 16,
            padding: 16,
            // La leyenda conserva el color pleno aunque haya meses atenuados.
            generateLabels: (chart) => Chart.defaults.plugins.legend.labels.generateLabels(chart)
              .map((l, i) => ({ ...l, fillStyle: i === 0 ? AZUL : consol.patron })),
          },
        },
        tooltip: {
          callbacks: {
            title: (items) => MESES[items[0].dataIndex],
            label: (c) => `${c.dataset.label.replace(' (barras rayadas)', '')}: ${fmtInt(c.parsed.y)}`,
          },
        },
      },
      scales: {
        x: { title: { display: true, text: 'Mes' }, grid: { display: false } },
        y: {
          beginAtZero: true,
          title: { display: true, text: 'Número de atenciones' },
          ticks: { precision: 0, callback: (v) => fmtInt(v) },
          grid: { color: '#d5dbe3' },
        },
      },
    },
  });
}

function pintarGrafico(filas, mes) {
  const sel = mes ? Number(mes) - 1 : -1;
  const plan = Array(12).fill(0);
  const meta = Array(12).fill(0);
  for (const f of filas) {
    if (f.mes >= 1 && f.mes <= 12) {
      plan[f.mes - 1] += f.atencionesPlanificadas || 0;
      meta[f.mes - 1] += f.metaGestion || 0;
    }
  }
  const hayDatos = filas.length > 0;
  llenar($('#tb-grafico'), hayDatos ? MESES.map((m, i) => ({ m: i === sel ? `${m} (mes filtrado)` : m, p: plan[i], t: meta[i] })) : [], (x) => el('tr', {},
    cell(x.m, { th: true }), cell(fmtInt(x.p), { num: true }), cell(fmtInt(x.t), { num: true })), VACIO_BUK);
  $('#grafico-nota').textContent = sel >= 0
    ? `Muestra los 12 meses para dar contexto: ${MESES[sel]} es el mes filtrado (barras plenas, igual que las tarjetas) y los demás meses aparecen atenuados.`
    : 'Muestra los 12 meses del año con los filtros de instituto, área y cargo.';

  const estado = $('#grafico-estado');
  const caja = $('.chart-box');
  if (!window.Chart) {
    estado.textContent = 'No se pudo cargar la librería de gráficos. Los datos se muestran en la tabla.';
    estado.hidden = false;
    caja.hidden = true;
    $('#grafico-tabla-wrap').classList.remove('visually-hidden');
    return;
  }
  estado.textContent = VACIO_BUK;
  estado.hidden = hayDatos;
  caja.hidden = !hayDatos;
  if (!hayDatos) return;
  if (!consol.grafico) consol.grafico = crearGrafico();
  const [dsPlan, dsMeta] = consol.grafico.data.datasets;
  dsPlan.data = plan;
  dsMeta.data = meta;
  dsPlan.backgroundColor = sel < 0 ? AZUL : MESES.map((_, i) => (i === sel ? AZUL : AZUL_TENUE));
  dsMeta.backgroundColor = sel < 0 ? consol.patron : MESES.map((_, i) => (i === sel ? consol.patron : consol.patronTenue));
  consol.grafico.update('none');
}

/* ================================================================== 2. PROFESIONALES */
const prof = { todos: [], error: false, pagina: 1, porPagina: 12, seleccionado: null, filas: [], dist: new Map() };

async function cargarProfesionales() {
  // El rol Profesional no puede leer /institutos: se muestran los códigos.
  const gestion = PUEDE.gestion(sesion.rol);
  const r = await todas({
    inst: gestion ? cargarInstitutos() : Promise.resolve([]),
    profs: traerProfesionales(),
    params: gestion ? api('/parametros') : Promise.resolve(null), // valores vigentes para el simulador
  });
  prof.dist = new Map((r.params?.distribuciones || []).map((d) => [d.id, d]));
  prof.error = r.profs === null;
  prof.todos = (r.profs || []).sort((a, b) => String(a.personaId).localeCompare(String(b.personaId), 'es', { numeric: true }));
  pintarListaProf();
  if (prof.seleccionado) await verDetalle(prof.seleccionado, false);
}

function listaFiltrada() {
  const q = $('#buscar-prof').value.trim();
  return q ? prof.todos.filter((p) => String(p.personaId).includes(q)) : prof.todos;
}

function pintarListaProf() {
  const lista = listaFiltrada();
  const paginas = Math.max(1, Math.ceil(lista.length / prof.porPagina));
  prof.pagina = Math.min(Math.max(1, prof.pagina), paginas);
  const desde = (prof.pagina - 1) * prof.porPagina;
  const buscando = $('#buscar-prof').value.trim() !== '';
  const ul = $('#lista-prof');
  const pagina = lista.slice(desde, desde + prof.porPagina);
  if (prof.error || !pagina.length) {
    ul.replaceChildren(el('li', { class: 'empty-state' },
      prof.error ? VACIO_ERROR : buscando ? 'Ningún PersonaId coincide con la búsqueda.' : VACIO_BUK));
  } else {
    ul.replaceChildren(...pagina.map((p) => {
      const actual = p.personaId === prof.seleccionado;
      return el('li', {}, el('button', {
        type: 'button',
        class: 'chip',
        'aria-current': actual ? 'true' : null,
        onclick: () => intentar(() => verDetalle(p.personaId, true)),
      },
      el('span', { class: 'visually-hidden' }, 'Ver detalle de '),
      el('span', { class: 'chip-id' }, p.personaId),
      el('span', { class: 'chip-estado' }, el('span', { 'aria-hidden': 'true' }, p.activa ? '✓ ' : '✕ '), p.activa ? 'Activa' : 'Inactiva'),
      actual ? el('span', { class: 'chip-viendo' }, '· en detalle') : null));
    }));
  }
  const plural = (n, uno, varios) => `${fmtInt(n)} ${n === 1 ? uno : varios}`;
  $('#prof-conteo').textContent = buscando
    ? `${plural(lista.length, 'coincidencia', 'coincidencias')} de ${plural(prof.todos.length, 'profesional', 'profesionales')}.`
    : `${plural(prof.todos.length, 'profesional', 'profesionales')}.`;
  $('#prof-pagina').textContent = `Página ${prof.pagina} de ${paginas}`;
  $('#prof-anterior').disabled = prof.pagina <= 1;
  $('#prof-siguiente').disabled = prof.pagina >= paginas;
}

function cambiarPagina(delta) {
  prof.pagina += delta;
  pintarListaProf();
  const act = document.activeElement;
  if (act && act.disabled) (act.id === 'prof-anterior' ? $('#prof-siguiente') : $('#prof-anterior')).focus();
}

async function verDetalle(id, enfocar) {
  prof.seleccionado = id;
  pintarListaProf();
  const filas = await api(`/profesionales/${encodeURIComponent(id)}/planificacion`, { query: { year: ANIO } });
  prof.filas = [...filas].sort((a, b) => String(a.instituto).localeCompare(String(b.instituto)) || a.mes - b.mes);
  $('#t-detalle-prof').textContent = `Profesional ${id}`;
  $('#detalle-vacio').hidden = true;
  $('#detalle-contenido').hidden = false;
  pintarFicha(id);
  pintarDetalle();
  prepararSimulacion();
  if (enfocar) $('#t-detalle-prof').focus();
}

function pintarFicha(id) {
  const d = (k) => distintos(prof.filas, k);
  const persona = prof.todos.find((p) => p.personaId === id);
  const datos = [
    ['PersonaId', id],
    ['Instituto', d('instituto').map((c) => `${nombreInst(c)} (${c})`).join(', ')],
    ['Cargo', d('cargo').join(', ')],
    ['Área', d('area').join(', ')],
    ['Tramo', d('tramo').map((t) => TRAMOS[t] || t).join(', ')],
    ['Estado', persona ? (persona.activa ? 'Activa' : 'Inactiva') : null],
  ];
  $('#ficha-prof').replaceChildren(...datos.map(([k, v]) => el('div', {}, el('dt', {}, k), el('dd', {}, v || sinDato()))));
}

function pintarDetalle() {
  const variosInst = distintos(prof.filas, 'instituto').length > 1;
  llenar($('#tb-detalle'), prof.filas, (f) => el('tr', {},
    cell(variosInst ? `${mesNombre(f.mes)} · ${f.instituto}` : mesNombre(f.mes), { th: true }),
    cell(fmtHoras(f.horasContratadas), { num: true }),
    cell(fmtHoras(f.horasDirectas), { num: true }),
    cell(fmtHoras(f.horasIndirectas), { num: true }),
    cell(fmtHoras(f.horasNas), { num: true }),
    cell(fmtHoras(f.horasAusencia), { num: true }),
    cell(fmtInt(f.atencionesDirectas), { num: true }),
    cell(fmtInt(f.atencionesIndirectas), { num: true }),
    cell(fmtInt(f.atencionesPlanificadas), { num: true }),
    cell(fmtInt(f.metaGestion), { num: true }),
    cell(fmtPct(f.foja), { num: true })), VACIO_BUK);

  const t = { horasContratadas: 0, horasDirectas: 0, horasIndirectas: 0, horasNas: 0, horasAusencia: 0, atencionesDirectas: 0, atencionesIndirectas: 0, atencionesPlanificadas: 0, metaGestion: 0 };
  for (const f of prof.filas) for (const k of Object.keys(t)) t[k] += Number(f[k]) || 0;
  $('#tf-detalle').replaceChildren(prof.filas.length
    ? el('tr', {},
      cell(`Total anual ${ANIO}`, { th: true }),
      cell(fmtHoras(t.horasContratadas), { num: true }),
      cell(fmtHoras(t.horasDirectas), { num: true }),
      cell(fmtHoras(t.horasIndirectas), { num: true }),
      cell(fmtHoras(t.horasNas), { num: true }),
      cell(fmtHoras(t.horasAusencia), { num: true }),
      cell(fmtInt(t.atencionesDirectas), { num: true }),
      cell(fmtInt(t.atencionesIndirectas), { num: true }),
      cell(fmtInt(t.atencionesPlanificadas), { num: true }),
      cell(fmtInt(t.metaGestion), { num: true }),
      cell(fmtPct(t.horasContratadas ? t.horasDirectas / t.horasContratadas : null), { num: true }))
    : '');
}

function prepararSimulacion() {
  const insts = distintos(prof.filas, 'instituto');
  opciones($('#sim-instituto'), insts.map((c) => ({ value: c, text: `${nombreInst(c)} (${c})` })));
  const meses = distintos(prof.filas, 'mes').map(Number).sort((a, b) => a - b);
  opciones($('#sim-mes'), meses.map((m) => ({ value: String(m), text: mesNombre(m) })));
  const habilitado = prof.filas.length > 0;
  $$('#form-simular input, #form-simular select, #form-simular button').forEach((n) => { n.disabled = !habilitado; });
  $('#sim-resultado').hidden = true;
  actualizarVigentes();
}

/** Valores con que se calculó el mes elegido: versionParametros = "<idDistribucion>:<idCalendario>:meta-0.90". */
function vigentesSimulacion() {
  const inst = $('#sim-instituto').value;
  const mes = Number($('#sim-mes').value);
  const fila = prof.filas.find((f) => f.instituto === inst && f.mes === mes);
  if (!fila) return {};
  const version = String(fila.versionParametros || '');
  const meta = /meta-([\d.]+)/.exec(version);
  let dist = prof.dist.get(version.split(':')[0]);
  if (!dist) {
    const inicio = `${ANIO}-${String(mes).padStart(2, '0')}-01`;
    dist = [...prof.dist.values()]
      .filter((d) => d.cargo === fila.cargo && d.tramo === fila.tramo && d.vigenteDesde <= inicio && (!d.vigenteHasta || d.vigenteHasta >= inicio))
      .sort((a, b) => String(b.vigenteDesde).localeCompare(String(a.vigenteDesde)))[0];
  }
  return { meta: meta ? Number(meta[1]) : null, directo: dist?.pctDirecto, indirecto: dist?.pctIndirecto, minutos: dist?.minutosDirecta };
}

function actualizarVigentes() {
  const v = vigentesSimulacion();
  const poner = (id, frac, min) => {
    $(`#sim-${id}`).placeholder = frac != null ? pctTexto(frac) : '';
    $(`#sim-${id}-ayuda`).textContent = `De ${min} a 100${frac != null ? `. Vigente: ${pctTexto(frac)}\u00a0%` : ''}.`;
  };
  poner('meta', v.meta, 1);
  poner('directo', v.directo, 0);
  poner('indirecto', v.indirecto, 0);
  $('#sim-minutos').options[0].textContent = v.minutos ? `Sin cambio: ${v.minutos}` : 'Sin cambio';
}

async function simular(e) {
  e.preventDefault();
  const form = e.currentTarget;
  const lecturas = {
    pctMeta: leerPorcentaje($('#sim-meta'), { nombre: '% meta', min: 1 }),
    pctDirecto: leerPorcentaje($('#sim-directo'), { nombre: '% directo' }),
    pctIndirecto: leerPorcentaje($('#sim-indirecto'), { nombre: '% indirecto' }),
  };
  const fallo = Object.values(lecturas).find((l) => l.error);
  if (fallo) avisar('error', fallo.error);
  if (!form.reportValidity()) return;
  const body = {
    personaId: prof.seleccionado,
    instituto: $('#sim-instituto').value,
    year: ANIO,
    month: Number($('#sim-mes').value),
  };
  for (const [k, l] of Object.entries(lecturas)) if (l.valor !== undefined) body[k] = fraccion(l.valor);
  if ($('#sim-minutos').value) body.minutosDirecta = Number($('#sim-minutos').value);
  const r = await intentar(() => api('/simulaciones', { method: 'POST', body }));
  if (!r) return;

  const indicadores = [
    ['Horas directas', 'horasDirectas', fmtHoras],
    ['Atenciones planificadas', 'atenciones', fmtInt],
    ['Meta de gestión', 'meta', fmtInt],
  ];
  llenar($('#tb-simulacion'), indicadores, ([nombre, k, fmt]) => el('tr', {},
    cell(nombre, { th: true }),
    cell(fmt(r.actual?.[k]), { num: true }),
    cell(fmt(r.simulado?.[k]), { num: true }),
    cell(diferencia(r.diferencia?.[k], fmt), { num: true })), '');
  $('#sim-caption').textContent = `Resultado de la simulación: ${mesNombre(body.month)} ${ANIO}, ${nombreInst(body.instituto)}`;
  $('#sim-persistido').textContent = r.persistido === false
    ? 'Simulación sin guardar: no se modificó ningún dato.'
    : 'Atención: la API informa que el resultado quedó guardado.';
  $('#sim-resultado').hidden = false;
  avisar('ok', `Simulación de ${mesNombre(body.month)} calculada para ${body.personaId}. No se guardó ningún cambio.`);
}

function diferencia(v, fmt) {
  if (v == null) return null;
  const n = Number(v);
  if (Math.abs(n) < 1e-9) return 'Sin cambio';
  const sube = n > 0;
  return el('span', { class: sube ? 'delta-up' : 'delta-down' },
    el('span', { 'aria-hidden': 'true' }, sube ? '▲ ' : '▼ '),
    `${sube ? '+' : ''}${fmt(n)}`,
    el('span', { class: 'visually-hidden' }, sube ? ' (aumenta)' : ' (disminuye)'));
}

/* ================================================================== 3. PARÁMETROS */
const par = { datos: null, calendario: null, catalogo: null };

async function cargarParametros() {
  const r = await todas({
    inst: cargarInstitutos(),
    params: api('/parametros'),
    cal: api('/calendarios', { query: { year: ANIO } }),
    asig: api('/asignaciones'),
  });
  par.datos = r.params;
  par.calendario = r.cal;
  par.catalogo = r.asig ? r.asig.catalogo : null;
  opcionesInst($('#cal-instituto'), 'Todos');
  $('#lista-cargos').replaceChildren(...distintos(par.datos?.distribuciones || [], 'cargo').map((c) => el('option', { value: c })));
  pintarDistribuciones();
  pintarMeta();
  pintarGenerales();
  pintarCalendario();
  pintarCatalogo();
}

function pintarDistribuciones() {
  const todas_ = par.datos ? par.datos.distribuciones : null;
  const q = normalizar($('#buscar-cargo').value.trim());
  const filas = todas_
    ? todas_.filter((d) => !q || normalizar(d.cargo).includes(q))
      .sort((a, b) => a.cargo.localeCompare(b.cargo, 'es') || (ORDEN_TRAMO[a.tramo] || 9) - (ORDEN_TRAMO[b.tramo] || 9) || String(b.vigenteDesde).localeCompare(String(a.vigenteDesde)))
    : null;
  llenar($('#tb-distribuciones'), filas, (d) => el('tr', {},
    cell(d.cargo, { th: true }),
    cell(TRAMOS[d.tramo] || d.tramo, { class: 'nowrap' }),
    cell(fmtPct(d.pctDirecto), { num: true }),
    cell(fmtPct(d.pctIndirecto), { num: true }),
    cell(fmtPct(d.pctNas), { num: true }),
    cell(fmtInt(d.minutosDirecta), { num: true }),
    cell(fmtInt(d.minutosIndirecta), { num: true }),
    cell(fmtFecha(d.vigenteDesde), { class: 'nowrap' }),
    cell(fmtFecha(d.vigenteHasta) || 'Sin término', { class: 'nowrap' })), q ? 'Ningún cargo coincide con la búsqueda.' : VACIO_PARAM);
  $('#dist-conteo').textContent = todas_ ? `Mostrando ${fmtInt(filas.length)} de ${fmtInt(todas_.length)} vigencias.` : '';
}

function pintarMeta() {
  if (!par.datos) {
    $('#meta-actual').textContent = '—';
    $('#meta-actual-detalle').textContent = '';
    llenar($('#tb-meta'), null);
    return;
  }
  const m = metaVigente(par.datos.generales);
  $('#meta-actual').textContent = fmtPct(m.valor);
  $('#m-valor').placeholder = pctTexto(m.valor);
  $('#m-valor-ayuda').textContent = `De 1 a 100. Vigente: ${pctTexto(m.valor)}\u00a0%.`;
  $('#meta-actual-detalle').textContent = m.omision
    ? 'No hay un parámetro META_GESTION cargado: el cálculo usa el 90 % por omisión del backend.'
    : `Vigente desde el ${fmtFecha(m.desde)}.`;
  const hist = par.datos.generales
    .filter((g) => g.codigo === 'META_GESTION')
    .sort((a, b) => String(b.vigenteDesde).localeCompare(String(a.vigenteDesde)));
  llenar($('#tb-meta'), hist, (g) => el('tr', {},
    cell(fmtPct(g.valor && typeof g.valor === 'object' ? g.valor.value : g.valor), { num: true }),
    cell(fmtFecha(g.vigenteDesde), { class: 'nowrap' })), 'Sin cambios registrados: se aplica el valor por omisión.');
}

function resumenJson(v) {
  if (v == null) return '(sin valor)';
  if (typeof v !== 'object') return String(v);
  if (Array.isArray(v)) return `[${v.length} elementos]`;
  return Object.entries(v).map(([k, x]) => {
    let val = x;
    if (x !== null && typeof x === 'object') val = Array.isArray(x) ? `[${x.length}]` : '{…}';
    return `${k}: ${val}`;
  }).join(', ') || '{}';
}

function pintarGenerales() {
  llenar($('#tb-jornada'), par.datos ? par.datos.jornadaLegal : null, (j) => el('tr', {},
    cell(fmtHoras(j.horasSemanales), { num: true }),
    cell(fmtFecha(j.vigenteDesde), { class: 'nowrap' }),
    cell(fmtFecha(j.vigenteHasta) || 'Sin término', { class: 'nowrap' }),
    cell(j.descripcion)), VACIO_PARAM);
  const gen = par.datos ? [...par.datos.generales].sort((a, b) => a.codigo.localeCompare(b.codigo) || String(b.vigenteDesde).localeCompare(String(a.vigenteDesde))) : null;
  llenar($('#tb-generales'), gen, (g) => el('tr', {},
    cell(g.codigo, { th: true }),
    cell(g.valor && typeof g.valor === 'object' && 'value' in g.valor ? String(g.valor.value) : resumenJson(g.valor)),
    cell(fmtFecha(g.vigenteDesde))), VACIO_PARAM);
}

function pintarCalendario() {
  const inst = $('#cal-instituto').value;
  const filas = par.calendario
    ? par.calendario.filter((c) => !inst || c.instituto === inst)
      .sort((a, b) => nombreInst(a.instituto).localeCompare(nombreInst(b.instituto), 'es') || a.mes - b.mes)
    : null;
  llenar($('#tb-calendario'), filas, (c) => el('tr', {},
    cell(`${nombreInst(c.instituto)} (${c.instituto})`, { th: true }),
    cell(String(c.anio), { num: true }),
    cell(mesNombre(c.mes)),
    cell(fmtDias(c.diasHabiles), { num: true }),
    cell(c.zona)), VACIO_PARAM);
}

function pintarCatalogo() {
  const filas = par.catalogo ? [...par.catalogo].sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')) : null;
  llenar($('#tb-catalogo'), filas, (c) => el('tr', {},
    cell(c.nombre, { th: true }),
    cell(c.horasSemanales == null ? 'Sin valor fijo' : fmtNum(c.horasSemanales, 2).replace(/,?0+$/, ''), { num: true }),
    cell(c.activa ? badge(['ok', '✓', 'Sí']) : badge(['neutral', '✕', 'No'])),
    cell(c.requiereDmn ? 'Sí' : 'No')), VACIO_PARAM);
}

function exigirTexto(campo, mensaje) {
  const vacio = campo.value.trim() === '';
  campo.setCustomValidity(vacio ? mensaje : '');
  campo.setAttribute('aria-invalid', vacio ? 'true' : 'false');
  return !vacio;
}

async function guardarDistribucion(e) {
  e.preventDefault();
  const form = e.currentTarget;
  exigirTexto($('#d-cargo'), 'Escribe el cargo.');
  const l = {
    directo: leerPorcentaje($('#d-directo'), { nombre: '% directo', obligatorio: true }),
    indirecto: leerPorcentaje($('#d-indirecto'), { nombre: '% indirecto', obligatorio: true }),
    nas: leerPorcentaje($('#d-nas'), { nombre: '% NAS', obligatorio: true }),
    grupal: leerPorcentaje($('#d-grupal'), { nombre: '% atención grupal', obligatorio: true }),
  };
  let error = Object.values(l).find((x) => x.error)?.error;
  if (!error) {
    const suma = l.directo.valor + l.indirecto.valor + l.nas.valor;
    if (suma > 100.000001) {
      error = `Directo + indirecto + NAS suma ${fmtNum(suma, 1)} %; no puede superar 100 %.`;
      $('#d-nas').setCustomValidity(error);
      $('#d-nas').setAttribute('aria-invalid', 'true');
    }
  }
  if (error) avisar('error', error);
  if (!form.reportValidity()) return;
  const body = {
    cargo: $('#d-cargo').value.trim().toUpperCase(),
    tramo: $('#d-tramo').value,
    pctDirecto: fraccion(l.directo.valor),
    pctIndirecto: fraccion(l.indirecto.valor),
    pctNas: fraccion(l.nas.valor),
    minutosDirecta: Number($('#d-min-directa').value),
    minutosIndirecta: Number($('#d-min-indirecta').value),
    pctGrupal: fraccion(l.grupal.valor),
    pacientesGrupo: $('#d-pacientes').valueAsNumber,
    vigenteDesde: $('#d-desde').value,
    vigenteHasta: $('#d-hasta').value || null,
  };
  const r = await intentar(() => api('/parametros/distribuciones', { method: 'POST', body }));
  if (!r) return;
  form.reset();
  avisar('ok', `Vigencia guardada para ${body.cargo}, ${TRAMOS[body.tramo]}, desde el ${fmtFecha(body.vigenteDesde)}. Usa «Recalcular planificación» para aplicarla.`);
  await intentar(cargarParametros);
}

async function guardarMeta(e) {
  e.preventDefault();
  const form = e.currentTarget;
  exigirTexto($('#m-justificacion'), 'Escribe la justificación del cambio.');
  const meta = leerPorcentaje($('#m-valor'), { nombre: 'Meta', min: 1, obligatorio: true });
  if (meta.error) avisar('error', meta.error);
  if (!form.reportValidity()) return;
  const body = {
    valor: fraccion(meta.valor),
    vigenteDesde: $('#m-desde').value,
    vigenteHasta: $('#m-hasta').value || null,
    justificacion: $('#m-justificacion').value.trim(),
  };
  const r = await intentar(() => api('/parametros/meta', { method: 'PUT', body }));
  if (!r) return;
  form.reset();
  avisar('ok', `Meta de gestión fijada en ${fmtPct(r.valor ?? body.valor)} desde el ${fmtFecha(body.vigenteDesde)}. Usa «Recalcular planificación» para aplicarla.`);
  await intentar(cargarParametros);
}

function abrirRecalcular() {
  opcionesInst($('#r-instituto'), 'Todos');
  if (!$('#r-mes').value) $('#r-mes').value = '1';
  const dlg = $('#dlg-recalcular');
  dlg.returnValue = '';
  dlg.showModal();
}

async function cerrarRecalcular() {
  const dlg = $('#dlg-recalcular');
  $('#btn-recalcular').focus();
  if (dlg.returnValue !== 'confirmar') return;
  const body = { year: ANIO, mesDesde: Number($('#r-mes').value) };
  if ($('#r-instituto').value) body.instituto = $('#r-instituto').value;
  const r = await intentar(() => api('/planificacion/recalcular', { method: 'POST', body }));
  if (!r) return;
  const omitidos = Array.isArray(r.omitidos) ? r.omitidos.length : 0;
  avisar('ok', `Planificación recalculada: ${fmtInt(r.calculados)} registros mensuales calculados${omitidos ? `, ${fmtInt(omitidos)} omitidos por falta de parámetros` : ''}. Quedó registrado en la bitácora.`);
}

function iniciarPestanas() {
  const tabs = $$('#tabs-parametros [role="tab"]');
  const activar = (tab, foco) => {
    for (const t of tabs) {
      const sel = t === tab;
      t.setAttribute('aria-selected', String(sel));
      t.tabIndex = sel ? 0 : -1;
      $(`#${t.getAttribute('aria-controls')}`).hidden = !sel;
    }
    if (foco) tab.focus();
    store.set('chc.pestana', tab.id);
    programarAjusteScroll();
  };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => activar(t, false));
    t.addEventListener('keydown', (e) => {
      const n = tabs.length;
      const destino = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
      if (destino === undefined) return;
      e.preventDefault();
      activar(tabs[destino], true);
    });
  });
  const guardada = tabs.find((t) => t.id === store.get('chc.pestana'));
  if (guardada) activar(guardada, false);
}

/* ================================================================== 4. ASIGNACIONES */
const asig = { catalogo: [], decision: null };
const nombreAsig = (id) => {
  const c = asig.catalogo.find((x) => x.id === id);
  if (!c) return id;
  return c.horasSemanales == null ? c.nombre : `${c.nombre} (${fmtNum(c.horasSemanales, 2).replace(/,?0+$/, '')} h/sem)`;
};

async function cargarAsignaciones() {
  const editar = PUEDE.editar(sesion.rol);
  const r = await todas({
    inst: cargarInstitutos(),
    asig: api('/asignaciones'),
    profs: editar ? traerProfesionales() : Promise.resolve([]),
  });
  asig.catalogo = r.asig?.catalogo || [];
  if (editar) {
    const profs = (r.profs || []).sort((a, b) => String(a.personaId).localeCompare(String(b.personaId), 'es', { numeric: true }));
    opciones($('#n-persona'), profs.map((p) => ({ value: p.personaId, text: p.activa ? p.personaId : `${p.personaId} (inactiva)` })), 'Elige un profesional');
    opcionesInst($('#n-instituto'), 'Elige un instituto');
    const activas = asig.catalogo.filter((c) => c.activa).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
    opciones($('#n-asignacion'), activas.map((c) => ({ value: c.id, text: `${nombreAsig(c.id)}${c.requiereDmn ? ' · requiere DMN' : ''}` })), 'Elige una asignación');
  }
  await cargarSolicitudes();
}

async function cargarSolicitudes() {
  const sol = await intentar(() => api('/asignaciones/solicitudes', { query: { estado: $('#s-estado').value } }));
  pintarSolicitudes(sol === undefined ? null : sol);
}

function pintarSolicitudes(solicitudes) {
  const dmn = PUEDE.aprobar(sesion.rol);
  llenar($('#tb-solicitudes'), solicitudes, (s) => {
    let acciones = null;
    if (dmn) {
      acciones = s.estado === 'pending'
        ? el('div', { class: 'cell-actions' },
          el('button', { type: 'button', class: 'btn btn-ok btn-small', 'aria-label': `Aprobar solicitud de ${s.personaId}`, onclick: () => abrirDecision(s, true) }, 'Aprobar'),
          el('button', { type: 'button', class: 'btn btn-danger btn-small', 'aria-label': `Rechazar solicitud de ${s.personaId}`, onclick: () => abrirDecision(s, false) }, 'Rechazar'))
        : 'Resuelta';
    }
    return el('tr', {},
      cell(s.personaId, { th: true }),
      cell(`${nombreInst(s.instituto)} (${s.instituto})`),
      cell(nombreAsig(s.asignacionId)),
      cell(badge(ESTADOS_SOL[s.estado] || ['neutral', '•', s.estado])),
      cell(fmtFecha(s.vigenteDesde), { class: 'nowrap' }),
      cell(fmtFecha(s.vigenteHasta) || 'Sin término', { class: 'nowrap' }),
      dmn ? cell(acciones) : null);
  }, 'Sin solicitudes con este estado.');
}

function abrirDecision(s, aprobar) {
  asig.decision = { s, aprobar };
  const verbo = aprobar ? 'Aprobar' : 'Rechazar';
  $('#dlg-decision-t').textContent = `${verbo} solicitud`;
  $('#dlg-decision-d').textContent = `${verbo} la asignación «${nombreAsig(s.asignacionId)}» del profesional ${s.personaId} en ${nombreInst(s.instituto)}, vigente desde el ${fmtFecha(s.vigenteDesde)}.${aprobar ? ' Al aprobarla se recalcula su planificación.' : ''}`;
  const btn = $('#dec-confirmar');
  btn.textContent = verbo;
  btn.className = `btn ${aprobar ? 'btn-ok' : 'btn-danger'}`;
  const just = $('#dec-justificacion');
  just.value = '';
  just.setCustomValidity('');
  just.removeAttribute('aria-invalid');
  const dlg = $('#dlg-decision');
  dlg.returnValue = '';
  dlg.showModal();
  just.focus();
}

async function cerrarDecision() {
  const dlg = $('#dlg-decision');
  const d = asig.decision;
  asig.decision = null;
  if (!d || dlg.returnValue !== 'confirmar') {
    $('#t-solicitudes').focus();
    return;
  }
  const accion = d.aprobar ? 'aprobar' : 'rechazar';
  const r = await intentar(() => api(`/asignaciones/solicitudes/${encodeURIComponent(d.s.id)}/${accion}`, {
    method: 'POST',
    body: { justificacion: $('#dec-justificacion').value.trim() },
  }));
  if (r) avisar('ok', `Solicitud de ${d.s.personaId} ${r.estado === 'approved' ? 'aprobada; su planificación fue recalculada' : 'rechazada'}.`);
  await cargarSolicitudes();
  $('#t-solicitudes').focus();
}

async function crearSolicitud(e) {
  e.preventDefault();
  const form = e.currentTarget;
  exigirTexto($('#n-justificacion'), 'Escribe la justificación de la solicitud.');
  if (!form.reportValidity()) return;
  const body = {
    personaId: $('#n-persona').value,
    instituto: $('#n-instituto').value,
    asignacionId: $('#n-asignacion').value,
    vigenteDesde: $('#n-desde').value,
    vigenteHasta: $('#n-hasta').value || null,
    justificacion: $('#n-justificacion').value.trim(),
  };
  const r = await intentar(() => api('/asignaciones/solicitudes', { method: 'POST', body }));
  if (!r) return;
  form.reset();
  const textos = {
    pending: `Solicitud creada para ${body.personaId}: queda pendiente de aprobación DMN.`,
    approved: `Solicitud de ${body.personaId} aprobada de inmediato (la asignación no requiere DMN); su planificación fue recalculada.`,
  };
  avisar('ok', textos[r.estado] || `Solicitud creada con estado ${r.estado}.`);
  await cargarSolicitudes();
}

async function sugerirInstituto() {
  const id = $('#n-persona').value;
  if (!id) return;
  const contratos = await intentar(() => api(`/profesionales/${encodeURIComponent(id)}/contratos`));
  const codigos = distintos(contratos || [], 'instituto');
  if (codigos.length && [...$('#n-instituto').options].some((o) => o.value === codigos[0])) $('#n-instituto').value = codigos[0];
}

/* ================================================================== 5. BITÁCORA */
const bit = { eventos: null, actualizado: null };

async function cargarBitacora() {
  const ev = await intentar(() => api('/auditoria', { query: { limit: 200 } }));
  bit.eventos = ev === undefined ? null : ev;
  bit.actualizado = new Date();
  pintarBitacora();
}

const textoEvento = (e) => [
  e.actor, e.rol, ROLES[e.rol], e.accion, ACCIONES[e.accion], e.entidad, ENTIDADES[e.entidad], e.entidadId,
  JSON.stringify(e.valorAnterior), JSON.stringify(e.valorNuevo), e.justificacion, e.origen, e.correlacionId, fmtFechaHora(e.fecha),
].join(' ');

function pintarBitacora() {
  const q = normalizar($('#b-texto').value.trim());
  const origen = $('#b-origen').value;
  const lista = (bit.eventos || []).filter((e) => (!origen || e.origen === origen) && (!q || normalizar(textoEvento(e)).includes(q)));
  llenar($('#tb-bitacora'), bit.eventos === null ? null : lista, filaEvento,
    q || origen ? 'Ningún evento coincide con los filtros.' : 'Sin eventos registrados. Aparecerán cuando el bot de Blue Prism o un usuario hagan cambios.');
  const hora = bit.actualizado ? bit.actualizado.toTimeString().slice(0, 8) : '';
  $('#bitacora-conteo').textContent = bit.eventos
    ? `Mostrando ${fmtInt(lista.length)} de ${fmtInt(bit.eventos.length)} eventos (los 200 más recientes). Actualizado a las ${hora}.`
    : '';
}

function filaEvento(e) {
  const bp = e.origen === 'blue_prism';
  const id = e.entidadId ? String(e.entidadId) : '';
  let origen;
  if (bp) origen = badge(['info', '⚙', 'Blue Prism']);
  else if (e.origen === 'user') origen = badge(['neutral', '●', 'Usuario']);
  else origen = badge(['neutral', '•', e.origen || 'sin origen']);
  return el('tr', { class: bp ? 'row-bp' : null },
    cell(fmtFechaHora(e.fecha), { th: true, class: 'nowrap' }),
    cell(e.actor),
    cell(ROLES[e.rol] || e.rol),
    cell(ACCIONES[e.accion] || e.accion),
    cell([ENTIDADES[e.entidad] || e.entidad, id ? el('span', { class: 'small-code' }, id.length > 12 ? `${id.slice(0, 8)}…` : id) : null]),
    cell(cambio(e)),
    cell(e.justificacion),
    cell(origen));
}

function cambio(e) {
  const a = e.valorAnterior;
  const n = e.valorNuevo;
  if (a == null && n == null) return null;
  const json = (v) => (v == null ? 'Sin valor' : JSON.stringify(v, null, 2));
  return el('details', {},
    el('summary', {}, `${resumenJson(a)} → ${resumenJson(n)}`),
    el('p', { class: 'pre-label' }, 'Valor anterior'), el('pre', {}, json(a)),
    el('p', { class: 'pre-label' }, 'Valor nuevo'), el('pre', {}, json(n)),
    e.entidadId ? [el('p', { class: 'pre-label' }, 'Id de la entidad'), el('pre', {}, String(e.entidadId))] : null);
}

/* ================================================================== navegación */
let vistaActual = null;
const CARGAS = {
  consolidado: cargarConsolidado,
  profesionales: cargarProfesionales,
  parametros: cargarParametros,
  asignaciones: cargarAsignaciones,
  bitacora: cargarBitacora,
};

function irA(inicial) {
  const id = location.hash.replace(/^#/, '');
  if (!VISTAS.includes(id) && !inicial) return;
  const vista = VISTAS.includes(id) ? id : 'consolidado';
  if (!VISTAS.includes(id)) history.replaceState(null, '', `#${vista}`);
  vistaActual = vista;
  for (const v of VISTAS) $(`#vista-${v}`).hidden = v !== vista;
  for (const a of $$('.sidenav a')) {
    if (a.dataset.vista === vista) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  document.title = `${TITULOS[vista]} · Cada hora cuenta`;
  $('#menu-actual').textContent = TITULOS[vista];
  abrirMenu(false);
  limpiarMensajes();
  if (!inicial) $(`#t-${vista}`).focus();
  recargarVista();
}

function recargarVista() {
  const seccion = $(`#vista-${vistaActual}`);
  if (!sesion.apiKey || !sesion.usuario) {
    avisar('info', 'Ingresa la API key (USER_API_KEY del archivo .env), tu usuario y tu rol, y presiona Aplicar.');
    return;
  }
  // El backend responde 403 a Profesional en estas vistas: se avisa sin llamar a la API ni dejar datos de otro rol.
  const bloqueada = !PUEDE.gestion(sesion.rol) && vistaActual !== 'profesionales';
  seccion.classList.toggle('bloqueada', bloqueada);
  if (bloqueada) {
    avisar('info', `${TITULOS[vistaActual]} requiere el rol Gerencia, RRHH o DMN. Con el rol Profesional solo puedes ver tu propia planificación en la vista Profesionales (tu usuario debe ser tu PersonaId).`);
    return;
  }
  intentar(CARGAS[vistaActual]);
}

function abrirMenu(abierto) {
  $('#menu-toggle').setAttribute('aria-expanded', String(abierto));
  $('#menu-lista').classList.toggle('abierto', abierto);
}

function aplicarRol() {
  for (const n of $$('[data-requiere]')) n.hidden = !PUEDE[n.dataset.requiere](sesion.rol);
  for (const n of $$('[data-sin-permiso]')) n.hidden = PUEDE[n.dataset.sinPermiso](sesion.rol);
  $('#sesion-resumen').textContent = `${sesion.usuario || 'Sin usuario'} · ${ROLES[sesion.rol]}`;
  $('#sesion-permisos').textContent = PERMISOS_TEXTO[sesion.rol];
}

function guardarSesion() {
  sesion.apiKey = $('#api-key').value.trim();
  sesion.usuario = $('#usuario').value.trim();
  sesion.rol = $('#rol').value;
  store.set('chc.apiKey', sesion.apiKey);
  store.set('chc.usuario', sesion.usuario);
  store.set('chc.rol', sesion.rol);
  aplicarRol();
  actualizarConfig();
}

function actualizarConfig() {
  $('#config-estado').textContent = sesion.apiKey ? '· API key guardada' : '· falta la API key';
}

function enviarSesion(e) {
  e.preventDefault();
  guardarSesion();
  limpiarMensajes();
  for (const [sel, falta] of [['#api-key', !sesion.apiKey], ['#usuario', !sesion.usuario]]) {
    $(sel).setAttribute('aria-invalid', falta ? 'true' : 'false');
  }
  if (!sesion.apiKey) {
    avisar('error', 'Falta la API key: ábrela en «Configuración». Es el valor de USER_API_KEY del archivo .env.');
    $('#config').open = true;
    $('#api-key').focus();
    return;
  }
  if (!sesion.usuario) {
    avisar('error', 'Falta el usuario: escribe tu nombre o identificador.');
    $('#usuario').focus();
    return;
  }
  $('#config').open = false;
  avisar('ok', `Sesión aplicada: ${sesion.usuario} con rol ${ROLES[sesion.rol]}.`);
  recargarVista();
}

function iniciar() {
  $('#anio-actual').textContent = String(ANIO);
  for (const s of $$('.anio')) s.textContent = String(ANIO);
  $('#api-key').value = sesion.apiKey;
  $('#usuario').value = sesion.usuario;
  $('#rol').value = sesion.rol;
  aplicarRol();
  actualizarConfig();
  opcionesMeses($('#f-mes'), 'Todos');
  opcionesMeses($('#r-mes'));
  iniciarPestanas();

  $('#saltar').addEventListener('click', (e) => { e.preventDefault(); $('#contenido').focus(); });
  $('#menu-toggle').addEventListener('click', () => abrirMenu($('#menu-toggle').getAttribute('aria-expanded') !== 'true'));
  const config = $('#config');
  config.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && config.open) {
      config.open = false;
      $('summary', config).focus();
    }
  });
  document.addEventListener('click', (e) => {
    if (config.open && sesion.apiKey && !config.contains(e.target)) config.open = false;
  });
  $('#form-sesion').addEventListener('submit', enviarSesion);
  $('#rol').addEventListener('change', () => { guardarSesion(); limpiarMensajes(); recargarVista(); });

  // Consolidado
  $('#filtros').addEventListener('submit', (e) => e.preventDefault());
  $('#filtros').addEventListener('change', () => intentar(aplicarFiltros));
  $('#filtros').addEventListener('reset', () => setTimeout(() => intentar(aplicarFiltros), 0));

  // Profesionales
  $('#form-buscar-prof').addEventListener('submit', (e) => e.preventDefault());
  $('#buscar-prof').addEventListener('input', () => { prof.pagina = 1; pintarListaProf(); });
  $('#prof-anterior').addEventListener('click', () => cambiarPagina(-1));
  $('#prof-siguiente').addEventListener('click', () => cambiarPagina(1));
  $('#form-simular').addEventListener('submit', simular);
  $('#sim-mes').addEventListener('change', actualizarVigentes);
  $('#sim-instituto').addEventListener('change', actualizarVigentes);

  // Parámetros
  $('#form-buscar-cargo').addEventListener('submit', (e) => e.preventDefault());
  $('#buscar-cargo').addEventListener('input', pintarDistribuciones);
  $('#form-cal').addEventListener('submit', (e) => e.preventDefault());
  $('#cal-instituto').addEventListener('change', pintarCalendario);
  $('#form-distribucion').addEventListener('submit', guardarDistribucion);
  for (const id of ['#d-directo', '#d-indirecto', '#d-nas']) $(id).addEventListener('input', () => $('#d-nas').setCustomValidity(''));
  $('#form-meta').addEventListener('submit', guardarMeta);
  $('#btn-recalcular').addEventListener('click', abrirRecalcular);
  $('#dlg-recalcular').addEventListener('close', () => intentar(cerrarRecalcular));

  // Asignaciones
  $('#form-estado').addEventListener('submit', (e) => e.preventDefault());
  $('#s-estado').addEventListener('change', () => intentar(cargarSolicitudes));
  $('#form-solicitud').addEventListener('submit', crearSolicitud);
  $('#n-persona').addEventListener('change', () => intentar(sugerirInstituto));
  $('#dlg-decision form').addEventListener('submit', (e) => {
    if (e.submitter?.value === 'confirmar' && !exigirTexto($('#dec-justificacion'), 'Escribe la justificación de la decisión.')) {
      e.preventDefault();
      $('#dec-justificacion').reportValidity();
    }
  });
  $('#dlg-decision').addEventListener('close', () => intentar(cerrarDecision));

  // Bitácora
  $('#form-bitacora').addEventListener('submit', (e) => e.preventDefault());
  $('#b-texto').addEventListener('input', pintarBitacora);
  $('#b-origen').addEventListener('change', pintarBitacora);
  $('#btn-bitacora-actualizar').addEventListener('click', () => intentar(cargarBitacora));

  // Limpia el estado de error de los campos de texto obligatorios al escribir.
  for (const id of ['#m-justificacion', '#n-justificacion', '#dec-justificacion', '#d-cargo', '#api-key', '#usuario',
    '#m-valor', '#d-directo', '#d-indirecto', '#d-nas', '#d-grupal', '#sim-meta', '#sim-directo', '#sim-indirecto']) {
    $(id).addEventListener('input', (e) => { e.target.setCustomValidity(''); e.target.removeAttribute('aria-invalid'); });
  }

  window.addEventListener('hashchange', () => irA(false));
  window.addEventListener('resize', programarAjusteScroll);
  irA(true);
  if (!sesion.apiKey) {
    config.open = true;
    $('#api-key').focus();
  }
}

iniciar();
