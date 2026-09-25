import { esFormatoFecha, hoyEnLima } from './fecha';

describe('fecha', () => {
  describe('hoyEnLima', () => {
    it('devuelve la fecha de hoy en formato YYYY-MM-DD', () => {
      // `sv-SE` ordena año-mes-día de forma nativa, así que es una comprobación
      // independiente de la que hace la implementación con `formatToParts`.
      const esperado = new Intl.DateTimeFormat('sv-SE', {
        timeZone: 'America/Lima',
      }).format(new Date());
      expect(hoyEnLima()).toBe(esperado);
      expect(hoyEnLima()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it('usa la fecha de Lima y no la de UTC junto a la medianoche', () => {
      // 2026-09-26 02:00 UTC son las 21:00 del 25 en Lima: el día anterior allí.
      expect(hoyEnLima(new Date('2026-09-26T02:00:00Z'))).toBe('2026-09-25');
      // 2026-09-26 05:00 UTC es medianoche en Lima: ya es el 26.
      expect(hoyEnLima(new Date('2026-09-26T05:00:00Z'))).toBe('2026-09-26');
    });

    it('da la misma fecha a las 20:00 y a las 23:00 de Lima', () => {
      expect(hoyEnLima(new Date('2026-09-26T01:00:00Z'))).toBe('2026-09-25');
      expect(hoyEnLima(new Date('2026-09-26T04:00:00Z'))).toBe('2026-09-25');
    });
  });

  describe('esFormatoFecha', () => {
    it('acepta una fecha real', () => {
      expect(esFormatoFecha('2026-09-26')).toBe(true);
    });

    it('rechaza otros formatos', () => {
      expect(esFormatoFecha('26-09-2026')).toBe(false);
      expect(esFormatoFecha('2026/09/26')).toBe(false);
      expect(esFormatoFecha('ayer')).toBe(false);
      expect(esFormatoFecha('')).toBe(false);
    });

    it('rechaza fechas que no existen en el calendario', () => {
      expect(esFormatoFecha('2026-02-30')).toBe(false);
      expect(esFormatoFecha('2026-13-01')).toBe(false);
    });
  });
});
