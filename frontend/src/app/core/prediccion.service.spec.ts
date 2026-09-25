import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from './api.config';
import { RespuestaPrediccion } from './prediccion.model';
import { PrediccionService } from './prediccion.service';

const RESPUESTA: RespuestaPrediccion = {
  site: 'Machu Picchu',
  target_date: '2026-09-26',
  weather: { temperature_max: 23.4, precipitation_probability: 55, condition: 'Nublado' },
  prediction: { estimated_visitors: 4580, capacity_percentage: 81.8, crowd_level: 'Alto' },
};

describe('PrediccionService', () => {
  let servicio: PrediccionService;
  let control: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servicio = TestBed.inject(PrediccionService);
    control = TestBed.inject(HttpTestingController);
  });

  afterEach(() => control.verify());

  it('consulta la ruta relativa que espera el proxy', () => {
    servicio.consultar('2026-09-26').subscribe();
    const peticion = control.expectOne((r) => r.url === '/api/prediction');
    expect(peticion.request.method).toBe('GET');
    peticion.flush(RESPUESTA);
  });

  it('envía la fecha en el parámetro date con formato YYYY-MM-DD', () => {
    servicio.consultar('2026-09-26').subscribe();
    const peticion = control.expectOne((r) => r.url === '/api/prediction');
    expect(peticion.request.params.get('date')).toBe('2026-09-26');
    peticion.flush(RESPUESTA);
  });

  it('devuelve la respuesta de la API sin transformarla', () => {
    let recibida: RespuestaPrediccion | undefined;
    servicio.consultar('2026-09-26').subscribe((r) => (recibida = r));
    control.expectOne((r) => r.url === '/api/prediction').flush(RESPUESTA);
    expect(recibida).toEqual(RESPUESTA);
  });

  it('hace una sola petición por consulta', () => {
    servicio.consultar('2026-09-26').subscribe();
    const peticiones = control.match((r) => r.url === '/api/prediction');
    expect(peticiones.length).toBe(1);
    peticiones[0].flush(RESPUESTA);
  });

  it('usa la URL base inyectada', () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://otro.example/v1' },
      ],
    });
    const otro = TestBed.inject(PrediccionService);
    const controlNuevo = TestBed.inject(HttpTestingController);
    otro.consultar('2026-09-26').subscribe();
    const peticion = controlNuevo.expectOne((r) => r.url === 'https://otro.example/v1/prediction');
    expect(peticion.request.params.get('date')).toBe('2026-09-26');
    peticion.flush(RESPUESTA);
  });
});
