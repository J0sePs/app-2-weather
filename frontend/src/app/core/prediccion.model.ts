/** Nivel de afluencia publicado por la API. */
export type NivelAfluencia = 'Bajo' | 'Moderado' | 'Alto';

/** Clima esperado para la fecha consultada. */
export interface Clima {
  temperature_max: number;
  precipitation_probability: number;
  condition: string;
}

/** Estimación de visitantes para la fecha consultada. */
export interface Prediccion {
  estimated_visitors: number;
  capacity_percentage: number;
  crowd_level: NivelAfluencia;
}

/** Cuerpo devuelto por `GET /api/prediction`. */
export interface RespuestaPrediccion {
  site: string;
  target_date: string;
  weather: Clima;
  prediction: Prediccion;
}

/** Cuerpo de error devuelto por la API, que siempre usa la clave `detail`. */
export interface DetalleError {
  detail?: string;
}
