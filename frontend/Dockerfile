FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_DEMO=false
ENV VITE_DEMO=$VITE_DEMO

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
