import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NivelAfluencia, RespuestaPrediccion } from '../../core/prediccion.model';
import { ResultadoCard } from './resultado-card';

function respuesta(
  visitantes: number,
  porcentaje: number,
  nivel: NivelAfluencia,
  objetivo = '2026-09-26',
): RespuestaPrediccion {
  return {
    site: 'Machu Picchu',
    target_date: objetivo,
    weather: { temperature_max: 23.4, precipitation_probability: 55, condition: 'Nublado' },
    prediction: {
      estimated_visitors: visitantes,
      capacity_percentage: porcentaje,
      crowd_level: nivel,
    },
  };
}

describe('ResultadoCard', () => {
  let fixture: ComponentFixture<ResultadoCard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ResultadoCard] }).compileComponents();
    fixture = TestBed.createComponent(ResultadoCard);
  });

  function mostrar(datos: RespuestaPrediccion): HTMLElement {
    fixture.componentRef.setInput('resultado', datos);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  function texto(datos: RespuestaPrediccion): string {
    return mostrar(datos).textContent ?? '';
  }

  it('muestra la estimación con separador de miles y la palabra personas', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    const visitantes = elemento.querySelector('[data-testid="visitantes"]');
    expect(visitantes?.textContent).toContain('4,580');
    expect(visitantes?.textContent).toContain('personas');
  });

  it('muestra el porcentaje de aforo permitido', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    const porcentaje = elemento.querySelector('[data-testid="porcentaje"]');
    expect(porcentaje?.textContent).toContain('81.8');
    expect(porcentaje?.textContent).toContain('aforo');
  });

  it('muestra la temperatura máxima y la condición', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    expect(elemento.querySelector('[data-testid="temperatura"]')?.textContent).toContain('23.4');
    expect(elemento.querySelector('[data-testid="condicion"]')?.textContent).toContain('Nublado');
  });

  it('indica a qué fecha corresponde el resultado', () => {
    expect(texto(respuesta(4580, 81.8, 'Alto', '2026-09-26'))).toContain('2026-09-26');
  });

  it('muestra la barra de capacidad al mismo porcentaje que el texto', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    const barra = elemento.querySelector<HTMLElement>('[data-testid="barra-capacidad"]');
    expect(barra?.style.width).toBe('81.8%');
  });

  it('expone el valor de la barra como porcentaje accesible', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    const riel = elemento.querySelector('[role="progressbar"]');
    expect(riel?.getAttribute('aria-valuenow')).toBe('81.8');
    expect(riel?.getAttribute('aria-valuemin')).toBe('0');
    expect(riel?.getAttribute('aria-valuemax')).toBe('100');
  });

  it('nunca dibuja la barra fuera de su carril', () => {
    const elemento = mostrar(respuesta(6000, 140, 'Alto'));
    const barra = elemento.querySelector<HTMLElement>('[data-testid="barra-capacidad"]');
    expect(barra?.style.width).toBe('100%');
  });

  const niveles: Array<[NivelAfluencia, string]> = [
    ['Bajo', 'Afluencia Baja'],
    ['Moderado', 'Afluencia Moderada'],
    ['Alto', 'Afluencia Alta'],
  ];

  for (const [nivel, etiqueta] of niveles) {
    it(`etiqueta el nivel ${nivel} como "${etiqueta}"`, () => {
      const visitas = nivel === 'Bajo' ? 2500 : nivel === 'Moderado' ? 4000 : 4580;
      const porcentaje = nivel === 'Bajo' ? 44.6 : nivel === 'Moderado' ? 71.4 : 81.8;
      expect(texto(respuesta(visitas, porcentaje, nivel))).toContain(etiqueta);
    });
  }

  it('muestra el aviso de historial sintético siempre que hay predicción', () => {
    const aviso = mostrar(respuesta(4580, 81.8, 'Alto')).querySelector(
      '[data-testid="aviso-sintetico"]',
    );
    expect(aviso).toBeTruthy();
    expect(aviso?.textContent).toContain('sintético');
    expect(aviso?.textContent).toContain('No representa conteos oficiales');
  });

  it('presenta el aviso como nota y no como otra cifra de aforo', () => {
    const elemento = mostrar(respuesta(4580, 81.8, 'Alto'));
    const aviso = elemento.querySelector('[data-testid="aviso-sintetico"]');
    // El aviso vive fuera de la lista de datos numéricos y lleva su propio rol.
    expect(elemento.querySelector('dl')?.contains(aviso as Node)).toBe(false);
    expect(aviso?.getAttribute('role')).toBe('note');
  });
});
