import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import {
  acotarPorcentaje,
  etiquetaNivel,
  formatearPorcentaje,
  formatearVisitas,
} from '../../core/formato';
import { RespuestaPrediccion } from '../../core/prediccion.model';

/**
 * Tarjeta de resultado: clima, estimación, aforo y aviso sobre el origen de los datos.
 *
 * Es un componente tonto de presentación. Todo lo que decide son números que ya
 * vienen en la respuesta, así que no necesita inyectar nada.
 */
@Component({
  selector: 'app-resultado-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './resultado-card.html',
  styleUrl: './resultado-card.css',
})
export class ResultadoCard {
  /** Respuesta completa de la API. */
  readonly resultado = input.required<RespuestaPrediccion>();

  protected readonly visitas = computed(() => formatearVisitas(this.resultado().prediction.estimated_visitors));
  protected readonly porcentaje = computed(() => formatearPorcentaje(this.resultado().prediction.capacity_percentage));
  protected readonly anchoBarra = computed(() =>
    acotarPorcentaje(this.resultado().prediction.capacity_percentage),
  );
  protected readonly nivel = computed(() => etiquetaNivel(this.resultado().prediction.crowd_level));
  protected readonly condicion = computed(() => this.resultado().weather.condition);
  protected readonly temperatura = computed(() => this.resultado().weather.temperature_max);
  protected readonly probabilidadLluvia = computed(
    () => this.resultado().weather.precipitation_probability,
  );
  protected readonly fechaResultado = computed(() => this.resultado().target_date);
}
