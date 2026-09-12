# Diseño de la prueba DevOps

El PDF es la especificación de aceptación. El proyecto parte de cero.

## Arquitectura elegida

Cliente HTTPS -> Kong (API Manager y balanceador) -> FastAPI (2-6 réplicas)
-> Redis (registro atómico de JWT consumidos). Kubernetes administra las cargas,
el Service LoadBalancer expone Kong y HPA aumenta las réplicas por CPU.
Docker Compose proporciona una demostración local con dos instancias explícitas.

Alternativas consideradas: Compose solo no demuestra HPA ni dos nodos Kubernetes;
un servicio cloud gestionado acopla la entrega a una cuenta aún no indicada.
Se elige Kubernetes portable con configuración versionada y un cluster kind de
dos workers para verificar la separación de nodos sin contratar infraestructura.

## Contrato y decisiones

- POST /DevOps devuelve el JSON exacto del PDF interpolando `to`.
- Otros métodos: 405 y texto ERROR; HEAD conserva semántica HTTP sin cuerpo.
- API key exacta del PDF en X-Parse-REST-API-Key. JWT en X-JWT-KWY (literal).
- Kong valida ambas credenciales. La aplicación repite la validación para que
  una exposición accidental del backend no evite la autenticación.
- JWT HS256 con iss=devops-assessment, aud=devops, iat, nbf, exp y jti UUID.
  La CLI operada por el candidato emite tokens de corta duración (máximo 300s).
  No se expone un emisor público respaldado únicamente por la API key publicada.
- Redis SET NX EX consume un jti una sola vez, compartido entre réplicas. Un JWT
  reutilizado devuelve 409. Redis caído devuelve 503 (sin permitir la operación).
- timeToLifeSec entero positivo, máximo 86400; se valida como dato del mensaje,
  no como duración de JWT. No se implementa envío real ni almacenamiento de mensajes.
- Métodos distintos de POST usan una ruta de rechazo sin autenticación en Kong;
  no llegan a ejecutar lógica de negocio. Las rutas desconocidas devuelven 404.
- JSON inválido o campos inválidos devuelven 422; Content-Type incorrecto, 415.
- Cuerpo máximo 16 KiB. No se registran cuerpos, API keys ni JWT.
- Dos réplicas distribuidas en al menos dos hosts mediante topology spread con
  minDomains=2. Se requieren dos workers y Metrics Server para demostrar HPA.
- Redis con persistencia AOF es suficiente para la prueba, pero es un punto único
  de fallo: la API deja de aceptar transacciones si no está disponible.

## Pipeline y entrega

GitHub Actions: build -> test (cobertura >=95%, lint, análisis de seguridad,
auditoría de dependencias) -> integración Docker -> publicación GHCR -> deploy.
Push a cualquier rama y PR ejecutan validación. Solo master despliega producción.
workflow_dispatch permite desplegar un digest SHA256 previamente publicado.
El despliegue usa un kubeconfig restringido al namespace y secrets del environment
production. La imagen se fija por digest y se verifica rollout y prueba HTTPS.

Se entregan instrucciones de operación, JWT, rollback, carga, escalado y una matriz
de evidencias. Publicación y despliegue real dependen de repo, dominio y destino
proporcionados por el candidato; no se inventan URLs ni ejecuciones exitosas.
