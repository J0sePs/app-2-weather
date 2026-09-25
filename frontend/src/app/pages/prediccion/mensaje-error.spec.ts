import { HttpErrorResponse } from '@angular/common/http';

import { mensajeDeError } from './prediccion-page';

/** Error con el cuerpo JSON que devuelve la propia API: siempre bajo la clave `detail`. */
function deLaApi(estado: number, detail: unknown): HttpErrorResponse {
  return new HttpErrorResponse({
    status: estado,
    statusText: 'Error',
    error: { detail },
  });
}

/** Error sin cuerpo JSON, como el que genera un proxy con el backend caído. */
function deProxy(estado: number, cuerpo: string): HttpErrorResponse {
  return new HttpErrorResponse({ status: estado, statusText: 'Error', error: cuerpo });
}

describe('mensajeDeError', () => {
  describe('fallo de red', () => {
    it('informa de que el servicio no está disponible', () => {
      const fallo = new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' });
      expect(mensajeDeError(fallo)).toContain('No se pudo contactar con el servicio');
    });

    it('no culpa al clima cuando la petición ni siquiera salió', () => {
      const fallo = new HttpErrorResponse({ status: 0, statusText: 'Unknown Error' });
      expect(mensajeDeError(fallo)).not.toContain('pronóstico');
    });
  });

  describe('502 con clima caído', () => {
    it('indica que no se pudo obtener el pronóstico', () => {
      const fallo = deLaApi(502, 'No se pudo obtener el pronóstico del clima.');
      expect(mensajeDeError(fallo)).toContain('No se pudo obtener el pronóstico');
    });

    it('no filtra el detalle técnico aunque la API lo incluyera', () => {
      const fallo = deLaApi(502, 'Traceback: httpx.ReadTimeout en /app/weather.py');
      const mensaje = mensajeDeError(fallo);
      expect(mensaje).not.toContain('Traceback');
      expect(mensaje).not.toContain('weather.py');
    });
  });

  describe('5xx generado por el proxy', () => {
    it('trata un 502 sin cuerpo JSON como servicio no disponible', () => {
      const fallo = deProxy(502, '<html><body>502 Bad Gateway</body></html>');
      const mensaje = mensajeDeError(fallo);
      expect(mensaje).toContain('No se pudo contactar con el servicio');
      expect(mensaje).not.toContain('pronóstico');
    });

    it('trata un 500 sin cuerpo JSON como servicio no disponible', () => {
      const fallo = deProxy(500, '');
      expect(mensajeDeError(fallo)).toContain('No se pudo contactar con el servicio');
    });

    it('no muestra el HTML del proxy', () => {
      const fallo = deProxy(502, '<html>nginx</html>');
      expect(mensajeDeError(fallo)).not.toContain('<html>');
    });
  });

  describe('errores de la API con explicación propia', () => {
    it('muestra el 422 tal cual lo redactó el backend', () => {
      const fallo = deLaApi(422, 'La fecha 2019-01-05 ya pasó.');
      expect(mensajeDeError(fallo)).toBe('La fecha 2019-01-05 ya pasó.');
    });

    it('usa un mensaje propio si el detail está vacío', () => {
      expect(mensajeDeError(deLaApi(422, '   '))).toBe(
        'No se pudo completar la consulta. Inténtalo de nuevo.',
      );
    });

    it('usa un mensaje propio si el detail no es texto', () => {
      const fallo = new HttpErrorResponse({ status: 422, error: { detail: ['a', 'b'] } });
      expect(mensajeDeError(fallo)).toBe('No se pudo completar la consulta. Inténtalo de nuevo.');
    });

    it('usa un mensaje propio si no hay cuerpo de error', () => {
      const fallo = new HttpErrorResponse({ status: 400, statusText: 'Bad Request' });
      expect(mensajeDeError(fallo)).toBe('No se pudo completar la consulta. Inténtalo de nuevo.');
    });
  });
});
