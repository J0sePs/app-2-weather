import { InjectionToken } from '@angular/core';

/**
 * URL base de la API, relativa a propósito.
 *
 * En producción Nginx sirve la SPA y hace de proxy de `/api/`, de modo que el
 * navegador nunca ve un host distinto del suyo y no hay CORS. En desarrollo
 * `proxy.conf.json` reproduce esa misma relación. Un valor relativo es lo que
 * hace que ambas rutas funcionen sin tocar el código.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: () => '/api',
});
