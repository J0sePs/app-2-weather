import { NivelAfluencia } from './prediccion.model';

/**
 * Formatos numéricos de la tarjeta.
 *
 * Se usa el patrón de separador de miles con coma y punto decimal porque es el que
 * devuelve la propia API en `capacity_percentage` y el que el spec fija en "4,580
 * personas". Fijarlo aquí, en vez de depender de los datos de locale del navegador,
 * hace que la tarjeta se vea igual en cualquier máquina.
 */
const SIN_DECIMALES = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const UN_DECIMAL = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** `4580` -> `4,580`. */
export function formatearVisitas(visitantes: number): string {
  return SIN_DECIMALES.format(visitantes);
}

/** `81.8` -> `81.8`, siempre con un decimal para que la barra y el texto cuadren. */
export function formatearPorcentaje(porcentaje: number): string {
  return UN_DECIMAL.format(porcentaje);
}

/**
 * Traduce el nivel de la API a la etiqueta de la tarjeta.
 *
 * El género cambia con el sustantivo: "Afluencia Alta" pero "Afluencia Baja", así que
 * el mapeo no se puede construir con una simple concatenación.
 */
export function etiquetaNivel(nivel: NivelAfluencia): string {
  const etiquetas: Record<NivelAfluencia, string> = {
    Bajo: 'Afluencia Baja',
    Moderado: 'Afluencia Moderada',
    Alto: 'Afluencia Alta',
  };
  return etiquetas[nivel] ?? nivel;
}

/** Acota el porcentaje a [0, 100] para que la barra nunca se salga de su carril. */
export function acotarPorcentaje(porcentaje: number): number {
  if (!Number.isFinite(porcentaje)) {
    return 0;
  }
  return Math.min(100, Math.max(0, porcentaje));
}
