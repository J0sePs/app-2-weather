import { Routes } from '@angular/router';

import { PrediccionPage } from './pages/prediccion/prediccion-page';

/**
 * Enrutado mínimo: una sola vista real, en la raíz y con un alias legible.
 *
 * El alias `/prediccion` existe para que haya una ruta propia de la SPA que deba
 * sobrevivir a una recarga con el servidor real detrás.
 */
export const routes: Routes = [
  { path: '', pathMatch: 'full', component: PrediccionPage },
  { path: 'prediccion', component: PrediccionPage },
  { path: '**', redirectTo: '' },
];
