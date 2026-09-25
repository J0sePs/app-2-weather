import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { hoyEnLima } from '../../core/fecha';
import { NivelAfluencia, RespuestaPrediccion } from '../../core/prediccion.model';
import { PrediccionPage } from './prediccion-page';

function respuesta(
  objetivo: string,
  visitantes: number,
  porcentaje: number,
  nivel: NivelAfluencia,
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

describe('PrediccionPage', () => {
  let fixture: ComponentFixture<PrediccionPage>;
  let control: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PrediccionPage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(PrediccionPage);
    control = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => control.verify());

  function elemento(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function consultar(selector = '[data-testid="boton-consultar"]'): void {
    const boton = elemento().querySelector<HTMLButtonElement>(selector);
    boton?.click();
    fixture.detectChanges();
  }

  function cambiarFecha(valor: string): void {
    const entrada = elemento().querySelector<HTMLInputElement>('[data-testid="control-fecha"]');
    if (!entrada) {
      throw new Error('No se encontró el control de fecha');
    }
    entrada.value = valor;
    entrada.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function responder(datos: RespuestaPrediccion): void {
    control.expectOne((r) => r.url === '/api/prediction').flush(datos);
    fixture.detectChanges();
  }

  function fallar(estado: number, cuerpo: object = { detail: 'Mensaje de la API' }): void {
    control
      .expectOne((r) => r.url === '/api/prediction')
      .flush(cuerpo, { status: estado, statusText: 'Error' });
    fixture.detectChanges();
  }

  describe('contenido inicial', () => {
    it('muestra el encabezado, el control de fecha y el botón', () => {
      const texto = elemento().textContent ?? '';
      expect(texto).toContain('Predicción de Afluencia - Machu Picchu');
      expect(elemento().querySelector('[data-testid="control-fecha"]')).toBeTruthy();
      expect(elemento().querySelector('[data-testid="boton-consultar"]')?.textContent).toContain(
        'Consultar Afluencia',
      );
    });

    it('deja el área de resultado vacía', () => {
      expect(elemento().querySelector('[data-testid="tarjeta-resultado"]')).toBeNull();
    });

    it('no muestra errores ni estado de carga antes de consultar', () => {
      expect(elemento().querySelector('[data-testid="mensaje-error"]')).toBeNull();
      expect(elemento().querySelector('[data-testid="estado-carga"]')).toBeNull();
    });

    it('no consulta la API al abrirse', () => {
      expect(control.match(() => true).length).toBe(0);
    });
  });

  describe('selector de fecha', () => {
    it('es un control nativo de tipo fecha, con icono del navegador', () => {
      const entrada = elemento().querySelector<HTMLInputElement>('[data-testid="control-fecha"]');
      expect(entrada?.type).toBe('date');
      expect(entrada?.getAttribute('type')).toBe('date');
    });

    it('arranca con la fecha de hoy en America/Lima en formato YYYY-MM-DD', () => {
      const entrada = elemento().querySelector<HTMLInputElement>('[data-testid="control-fecha"]');
      expect(entrada?.value).toBe(hoyEnLima());
      expect(entrada?.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it('acepta que el usuario elija otra fecha', () => {
      cambiarFecha('2026-09-26');
      const entrada = elemento().querySelector<HTMLInputElement>('[data-testid="control-fecha"]');
      expect(entrada?.value).toBe('2026-09-26');
    });

    it('envía a la API la fecha elegida con formato YYYY-MM-DD', () => {
      cambiarFecha('2026-09-26');
      consultar();
      const peticion = control.expectOne((r) => r.url === '/api/prediction');
      expect(peticion.request.params.get('date')).toBe('2026-09-26');
      peticion.flush(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
    });
  });

  describe('consulta correcta', () => {
    it('muestra la tarjeta con los datos devueltos', () => {
      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      const tarjeta = elemento().querySelector('[data-testid="tarjeta-resultado"]');
      expect(tarjeta).toBeTruthy();
      expect(elemento().textContent).toContain('4,580');
      expect(elemento().textContent).toContain('Afluencia Alta');
    });

    it('retira el estado de carga al recibir la respuesta', () => {
      consultar();
      expect(elemento().querySelector('[data-testid="estado-carga"]')).toBeTruthy();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      expect(elemento().querySelector('[data-testid="estado-carga"]')).toBeNull();
    });

    it('hace una sola petición por consulta', () => {
      consultar();
      control.expectOne((r) => r.url === '/api/prediction').flush(
        respuesta('2026-09-26', 4580, 81.8, 'Alto'),
      );
      expect(control.match(() => true).length).toBe(0);
    });

    it('sustituye por completo las cifras de la consulta anterior', () => {
      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      expect(elemento().textContent).toContain('4,580');

      cambiarFecha('2026-09-27');
      consultar();
      responder(respuesta('2026-09-27', 1200, 21.4, 'Bajo'));

      const texto = elemento().textContent ?? '';
      expect(texto).toContain('1,200');
      expect(texto).toContain('Afluencia Baja');
      expect(texto).not.toContain('4,580');
      expect(elemento().querySelectorAll('[data-testid="tarjeta-resultado"]').length).toBe(1);
    });
  });

  describe('estado de carga', () => {
    it('deshabilita el botón mientras la consulta está en curso', () => {
      consultar();
      const boton = elemento().querySelector<HTMLButtonElement>('[data-testid="boton-consultar"]');
      expect(boton?.disabled).toBe(true);
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
    });

    it('vuelve a habilitar el botón al terminar', () => {
      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      const boton = elemento().querySelector<HTMLButtonElement>('[data-testid="boton-consultar"]');
      expect(boton?.disabled).toBe(false);
    });

    it('no lanza una segunda consulta mientras la primera está en curso', () => {
      consultar();
      consultar();
      const abiertas = control.match((r) => r.url === '/api/prediction');
      expect(abiertas.length).toBe(1);
      abiertas[0].flush(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
    });
  });

  describe('errores', () => {
    it('muestra el mensaje de la API ante un 422 y no renderiza tarjeta', () => {
      consultar();
      fallar(422, { detail: 'La fecha 2026-01-01 ya pasó.' });
      expect(elemento().querySelector('[data-testid="mensaje-error"]')?.textContent).toContain(
        'La fecha 2026-01-01 ya pasó.',
      );
      expect(elemento().querySelector('[data-testid="tarjeta-resultado"]')).toBeNull();
    });

    it('rehabilita el botón tras un 422', () => {
      consultar();
      fallar(422, { detail: 'La fecha ya pasó.' });
      const boton = elemento().querySelector<HTMLButtonElement>('[data-testid="boton-consultar"]');
      expect(boton?.disabled).toBe(false);
    });

    it('indica que no se pudo obtener el pronóstico ante un 502', () => {
      consultar();
      fallar(502, { detail: 'No se pudo obtener el pronóstico del clima.' });
      const mensaje = elemento().querySelector('[data-testid="mensaje-error"]')?.textContent ?? '';
      expect(mensaje).toContain('No se pudo obtener el pronóstico');
      expect(elemento().querySelector('[data-testid="tarjeta-resultado"]')).toBeNull();
    });

    it('no filtra el detalle técnico de un 502', () => {
      consultar();
      fallar(502, { detail: 'Traceback (most recent call last): httpx.ReadTimeout at /app/weather.py' });
      const mensaje = elemento().querySelector('[data-testid="mensaje-error"]')?.textContent ?? '';
      expect(mensaje).not.toContain('Traceback');
      expect(mensaje).not.toContain('weather.py');
    });

    it('trata un fallo de red como servicio no disponible', () => {
      consultar();
      control
        .expectOne((r) => r.url === '/api/prediction')
        .error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });
      fixture.detectChanges();
      const mensaje = elemento().querySelector('[data-testid="mensaje-error"]')?.textContent ?? '';
      expect(mensaje).toContain('No se pudo contactar con el servicio');
      expect(elemento().querySelector('[data-testid="tarjeta-resultado"]')).toBeNull();
      const boton = elemento().querySelector<HTMLButtonElement>('[data-testid="boton-consultar"]');
      expect(boton?.disabled).toBe(false);
    });

    it('usa un mensaje propio cuando la API no envía detalle', () => {
      consultar();
      fallar(400, {});
      expect(elemento().querySelector('[data-testid="mensaje-error"]')?.textContent).toContain(
        'No se pudo completar la consulta',
      );
    });

    it('trata un 5xx sin detalle como servicio no disponible, no como clima', () => {
      consultar();
      fallar(500, {});
      const mensaje = elemento().querySelector('[data-testid="mensaje-error"]')?.textContent ?? '';
      expect(mensaje).toContain('No se pudo contactar con el servicio');
      expect(mensaje).not.toContain('pronóstico');
    });

    it('limpia el error anterior al reintentar', () => {
      consultar();
      fallar(422, { detail: 'La fecha ya pasó.' });
      expect(elemento().querySelector('[data-testid="mensaje-error"]')).toBeTruthy();

      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      expect(elemento().querySelector('[data-testid="mensaje-error"]')).toBeNull();
    });

    it('retira la tarjeta anterior si la nueva consulta falla', () => {
      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      cambiarFecha('2026-09-27');
      consultar();
      fallar(502, { detail: 'sin clima' });
      expect(elemento().querySelector('[data-testid="tarjeta-resultado"]')).toBeNull();
      expect(elemento().textContent).not.toContain('4,580');
    });
  });

  describe('aviso sobre el origen de los datos', () => {
    it('acompaña a toda predicción en pantalla', () => {
      consultar();
      responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      const aviso = elemento().querySelector('[data-testid="aviso-sintetico"]');
      expect(aviso).toBeTruthy();
      expect(aviso?.textContent).toContain('sintético');
    });
  });

  describe('pantallas estrechas', () => {
    /**
     * Monta la página dentro de un contenedor de 360 px y comprueba que nada se sale.
     *
     * Karma corre en un Chrome real, así que `scrollWidth` mide el desbordamiento de
     * verdad y no una aproximación. El contenedor se retira al terminar para no
     * arrastrar el nodo entre pruebas.
     */
    function medirEn360(alMedir: () => void): { scroll: number; visible: number } {
      const anfitrion = document.createElement('div');
      anfitrion.style.width = '360px';
      document.body.appendChild(anfitrion);
      try {
        anfitrion.appendChild(fixture.nativeElement);
        fixture.detectChanges();
        alMedir();
        return { scroll: anfitrion.scrollWidth, visible: anfitrion.clientWidth };
      } finally {
        anfitrion.remove();
      }
    }

    it('no desborda horizontalmente en el estado inicial', () => {
      const { scroll, visible } = medirEn360(() => undefined);
      expect(scroll).toBeLessThanOrEqual(visible);
    });

    it('no desborda horizontalmente con una tarjeta de resultado', () => {
      const { scroll, visible } = medirEn360(() => {
        consultar();
        responder(respuesta('2026-09-26', 4580, 81.8, 'Alto'));
      });
      expect(scroll).toBeLessThanOrEqual(visible);
    });

    it('no desborda horizontalmente con un mensaje de error largo', () => {
      const { scroll, visible } = medirEn360(() => {
        consultar();
        fallar(422, {
          detail:
            'La fecha 2027-01-01 está fuera de la ventana de pronóstico. La última fecha consultable es 2026-09-28.',
        });
      });
      expect(scroll).toBeLessThanOrEqual(visible);
    });

    it('mantiene visibles el control de fecha y el botón a 360 px', () => {
      medirEn360(() => {
        const entrada = elemento().querySelector('[data-testid="control-fecha"]');
        const boton = elemento().querySelector('[data-testid="boton-consultar"]');
        expect(entrada).toBeTruthy();
        expect(boton).toBeTruthy();
      });
    });
  });
});
