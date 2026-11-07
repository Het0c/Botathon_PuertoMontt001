# Blue Prism → Backend

Blue Prism no inserta directamente en la base de datos:

1. Lee BUK/SIC.
2. En BUK conserva solo `Reg_SIC = "D - SIC"`.
3. Detecta errores y deltas.
4. Crea una importación HTTP.
5. Envía registros JSON, errores y deltas.
6. Completa la importación con el total de filas procesadas.
7. Consulta el estado.

Todas las rutas RPA usan:

```http
Authorization: Bearer <RPA_API_KEY>
Content-Type: application/json
```

## Crear lote

```bash
curl -X POST http://127.0.0.1:8000/api/v1/rpa/imports \
  -H "Authorization: Bearer $RPA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @Fase_3_Arquitecto_de_Software/examples/blue_prism/import_buk.json
```

La respuesta entrega `importacionId`. Repetir la misma clave y hash devuelve el mismo lote.

## Enviar BUK normalizado

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/rpa/imports/$IMPORT_ID/records" \
  -H "Authorization: Bearer $RPA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @Fase_3_Arquitecto_de_Software/examples/blue_prism/buk_records.json
```

El backend acepta el formato normalizado de `examples/blue_prism/buk_records.json` y también el contrato ya acordado en `motor-calculo/data/persona_137732.json`. En este último, los descuentos se expresan en semanas. El backend vuelve a validar `regSic`; si viene con un valor distinto de `D - SIC`, rechaza la fila.

## Enviar deltas

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/rpa/imports/$IMPORT_ID/deltas" \
  -H "Authorization: Bearer $RPA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @Fase_3_Arquitecto_de_Software/examples/blue_prism/contract_delta.json
```

## Registrar errores del archivo

```json
{"errors":[{"fila":83,"campo":"Horas Semanales","codigo":"DATO_FALTANTE","mensaje":"La fila no tiene jornada"}]}
```

## Completar

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/rpa/imports/$IMPORT_ID/complete" \
  -H "Authorization: Bearer $RPA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"filasEsperadas": 1}'
```

El total debe coincidir con aceptadas + rechazadas. La aplicación y recálculo son transaccionales.

## SIC

Crear un lote con `source: "SIC"` y enviar `Fase_3_Arquitecto_de_Software/examples/blue_prism/sic_records.json`. Cero con `reporteValidado: true` significa cero ejecutado; ausencia del registro significa **sin reporte** y no genera alerta.

## Códigos

| Código | Significado |
|---:|---|
| 200/201 | Aceptado |
| 401 | Credencial RPA inválida |
| 409 | Conflicto de idempotencia, conteo o estado |
| 422 | JSON o regla inválida |

En reintentos se reutilizan `idempotencyKey` y `sourceRecordId`.
