/** Zona horaria del sitio. "Hoy" para Machu Picchu no es "hoy" en UTC. */
export const ZONA_HORARIA_SITIO = 'America/Lima';

/** Formato que espera la API en el parámetro `date`. */
export const FORMATO_FECHA = 'yyyy-MM-dd';

/**
 * Devuelve la fecha de hoy en la zona horaria del sitio, en formato `YYYY-MM-DD`.
 *
 * Se arma con `formatToParts` en lugar de con un `toISOString()`, porque el formato
 * ISO siempre es UTC: cerca de la medianoche de Lima devolvería el día anterior.
 * Tampoco se usa `toLocaleDateString` con un locale, porque el orden de los campos
 * depende de los datos de locale del navegador.
 */
export function hoyEnLima(ahora: Date = new Date()): string {
  const partes = new Intl.DateTimeFormat('en-CA', {
    timeZone: ZONA_HORARIA_SITIO,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(ahora);

  const valor = (tipo: Intl.DateTimeFormatPartTypes): string =>
    partes.find((parte) => parte.type === tipo)?.value ?? '';

  return `${valor('year')}-${valor('month')}-${valor('day')}`;
}

/** Indica si una cadena tiene forma `YYYY-MM-DD`. */
export function esFormatoFecha(valor: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valor)) {
    return false;
  }
  const [anio, mes, dia] = valor.split('-').map(Number);
  const fecha = new Date(Date.UTC(anio, mes - 1, dia));
  return (
    fecha.getUTCFullYear() === anio &&
    fecha.getUTCMonth() === mes - 1 &&
    fecha.getUTCDate() === dia
  );
}
