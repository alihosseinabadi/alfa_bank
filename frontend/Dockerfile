# Build the Vite app, then serve it with nginx and proxy /api to the API service.

FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite variables are build-time. Defaults keep the judge demo explicitly synthetic.
ARG VITE_RECOMMENDATIONS_SOURCE=demo
ARG VITE_API_BASE_URL=
ENV VITE_RECOMMENDATIONS_SOURCE=${VITE_RECOMMENDATIONS_SOURCE} \
    VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
