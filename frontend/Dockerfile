# syntax=docker/dockerfile:1

# ---------- etapa de compilación ----------
FROM node:20-alpine AS build

WORKDIR /app

# Primero el manifiesto, para que `npm ci` se aproveche en caché mientras el
# código de la aplicación cambie.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# La URL base de la API es relativa (`/api`) y ya viene por defecto en la
# aplicación, así que la imagen se construye sin variables de entorno.
RUN npm run build

# ---------- imagen final ----------
FROM nginx:1.27-alpine AS runtime

# Se copia sólo lo que Nginx necesita servir: los artefactos de `dist/` y la
# configuración. Ni `node_modules` ni el código fuente de la aplicación llegan
# a la imagen final.
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
