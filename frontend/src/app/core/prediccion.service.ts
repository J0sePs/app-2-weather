import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from './api.config';
import { RespuestaPrediccion } from './prediccion.model';

/**
 * Cliente de la API de predicción.
 *
 * Un solo método, una sola ruta. La ruta se compone con la URL base inyectada para que
 * las pruebas puedan apuntar a otro destino sin tocar el servicio.
 */
@Injectable({ providedIn: 'root' })
export class PrediccionService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  /** Consulta la predicción de una fecha en formato `YYYY-MM-DD`. */
  consultar(fecha: string): Observable<RespuestaPrediccion> {
    const parametros = new HttpParams().set('date', fecha);
    return this.http.get<RespuestaPrediccion>(`${this.base}/prediction`, {
      params: parametros,
    });
  }
}
