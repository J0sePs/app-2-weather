import { acotarPorcentaje, etiquetaNivel, formatearPorcentaje, formatearVisitas } from './formato';
import { NivelAfluencia } from './prediccion.model';

describe('formato', () => {
  describe('formatearVisitas', () => {
    it('añade el separador de miles', () => {
      expect(formatearVisitas(4580)).toBe('4,580');
    });

    it('usa coma, no punto, como separador de miles', () => {
      expect(formatearVisitas(5600)).toBe('5,600');
      expect(formatearVisitas(1000)).toBe('1,000');
    });

    it('no añade decimales a un número entero', () => {
      expect(formatearVisitas(3000)).toBe('3,000');
    });

    it('formatea el cero sin decimales', () => {
      expect(formatearVisitas(0)).toBe('0');
    });
  });

  describe('formatearPorcentaje', () => {
    it('mantiene un decimal', () => {
      expect(formatearPorcentaje(81.8)).toBe('81.8');
    });

    it('añade el decimal que falta', () => {
      expect(formatearPorcentaje(100)).toBe('100.0');
      expect(formatearPorcentaje(0)).toBe('0.0');
    });
  });

  describe('etiquetaNivel', () => {
    const casos: Array<[NivelAfluencia, string]> = [
      ['Bajo', 'Afluencia Baja'],
      ['Moderado', 'Afluencia Moderada'],
      ['Alto', 'Afluencia Alta'],
    ];

    for (const [nivel, esperado] of casos) {
      it(`traduce ${nivel} a "${esperado}"`, () => {
        expect(etiquetaNivel(nivel)).toBe(esperado);
      });
    }
  });

  describe('acotarPorcentaje', () => {
    it('deja pasar un valor dentro de rango', () => {
      expect(acotarPorcentaje(81.8)).toBe(81.8);
    });

    it('acota por arriba y por abajo', () => {
      expect(acotarPorcentaje(140)).toBe(100);
      expect(acotarPorcentaje(-20)).toBe(0);
    });

    it('devuelve cero ante un valor no numérico', () => {
      expect(acotarPorcentaje(Number.NaN)).toBe(0);
      expect(acotarPorcentaje(Number.POSITIVE_INFINITY)).toBe(0);
    });
  });
});
