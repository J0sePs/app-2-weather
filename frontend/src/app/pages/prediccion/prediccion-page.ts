import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { hoyEnLima } from '../../core/fecha';
import { DetalleError, RespuestaPrediccion } from '../../core/prediccion.model';
import { PrediccionService } from '../../core/prediccion.service';
import { ResultadoCard } from '../../shared/resultado-card/resultado-card';

/**
 * Página única de la aplicación: control de fecha, consulta y área de resultado.
 *
 * El estado son cuatro señales y nada más: fecha elegida, consulta en curso, último
 * resultado y último error. Cada consulta reemplaza el resultado anterior por completo,
 * de modo que nunca se mezclan cifras de dos fechas distintas.
 */
@Component({
  selector: 'app-prediccion-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ResultadoCard],
  templateUrl: './prediccion-page.html',
  styleUrl: './prediccion-page.css',
})
export class PrediccionPage {
  private readonly servicio = inject(PrediccionService);

  /** Fecha elegida en el control, inicializada a hoy en la zona del sitio. */
  protected readonly fecha = signal(hoyEnLima());

  /** Verdadero mientras hay una petición en vuelo. */
  protected readonly cargando = signal(false);

  /** Último resultado válido, o `null` si no hay ninguno en pantalla. */
  protected readonly resultado = signal<RespuestaPrediccion | null>(null);

  /** Mensaje de error legible, o `null` si no hay error. */
  protected readonly error = signal<string | null>(null);

  /** El botón se bloquea durante la consulta y sin fecha que consultar. */
  protected readonly botonBloqueado = () => this.cargando() || this.fecha() === '';

  protected alCambiarFecha(evento: Event): void {
    this.fecha.set((evento.target as HTMLInputElement).value);
  }

  protected consultar(): void {
    if (this.botonBloqueado()) {
      return;
    }
    // El error anterior desaparece al reintentar; el resultado también, para que
    // nunca haya cifras visibles que no correspondan a la consulta en curso.
    this.error.set(null);
    this.resultado.set(null);
    this.cargando.set(true);

    this.servicio.consultar(this.fecha()).subscribe({
      next: (respuesta) => {
        this.resultado.set(respuesta);
        this.cargando.set(false);
      },
      error: (fallo: HttpErrorResponse) => {
        this.resultado.set(null);
        this.error.set(mensajeDeError(fallo));
        this.cargando.set(false);
      },
    });
  }
}

/**
 * Mensajes fijos del cliente.
 *
 * El de clima no reutiliza el `detail` de la API: garantiza por construcción que un
 * detalle técnico del proveedor o del proxy no llegue nunca a pantalla. El de servicio
 * cubre el caso en que no hay API a la que preguntarle.
 */
const MENSAJE_SERVICIO_NO_DISPONIBLE =
  'No se pudo contactar con el servicio de predicción. Comprueba tu conexión e inténtalo de nuevo.';
const MENSAJE_CLIMA_NO_DISPONIBLE =
  'No se pudo obtener el pronóstico del clima para esa fecha. Inténtalo de nuevo en unos minutos.';
const MENSAJE_GENERICO = 'No se pudo completar la consulta. Inténtalo de nuevo.';

/** Extrae el `detail` de la API, o `null` si la respuesta no lo trae. */
function detalleDeLaApi(fallo: HttpErrorResponse): string | null {
  const detalle = (fallo.error as DetalleError | null | undefined)?.detail;
  return typeof detalle === 'string' && detalle.trim() !== '' ? detalle : null;
}

/**
 * Traduce un fallo de la API a un mensaje para la persona que consulta.
 *
 * Hay que distinguir quién generó el fallo, no sólo el código: un 502 con `detail`
 * en JSON es el backend avisando de que no hay pronóstico, mientras que un 5xx sin
 * cuerpo JSON lo produce el proxy cuando el backend no está, y un 0 es que ni la
 * petición salió. En los dos últimos casos la culpa no es del clima, y decirlo
 * sería confundir a quien consulta.
 */
export function mensajeDeError(fallo: HttpErrorResponse): string {
  if (fallo.status === 0) {
    return MENSAJE_SERVICIO_NO_DISPONIBLE;
  }
  const detalle = detalleDeLaApi(fallo);
  if (fallo.status === 502) {
    // Un 502 con cuerpo JSON significa que el backend respondió y fue el clima.
    // Sin ese cuerpo JSON el 502 lo generó el proxy con el backend caído.
    return detalle !== null ? MENSAJE_CLIMA_NO_DISPONIBLE : MENSAJE_SERVICIO_NO_DISPONIBLE;
  }
  if (detalle !== null) {
    return detalle;
  }
  if (fallo.status >= 500) {
    return MENSAJE_SERVICIO_NO_DISPONIBLE;
  }
  return MENSAJE_GENERICO;
}
