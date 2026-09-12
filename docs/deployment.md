# Despliegue y operación

## Laboratorio Kubernetes local

Requiere Docker, kubectl y kind v0.33.0. Instalar kind desde su distribución oficial
verificando checksum. Si se usa el binario descargado durante esta implementación,
se encuentra en `.runtime/kind.exe` (no forma parte del repositorio).

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_local
docker build --provenance=false --platform linux/amd64 -t pichincha-devops:local .
.\.runtime\kind.exe create cluster --name devops-assessment --config infra/kind.yaml --kubeconfig .runtime/kubeconfig-kind --wait 120s
.\.runtime\kind.exe load docker-image pichincha-devops:local --name devops-assessment
$env:KUBECONFIG = Join-Path (Get-Location) '.runtime/kubeconfig-kind'
kubectl --context kind-devops-assessment apply -f infra/k8s/bootstrap.yaml
kubectl --context kind-devops-assessment apply -f infra/metrics-server-kind.yaml
.\.venv\Scripts\python.exe -m scripts.deploy --local --context kind-devops-assessment --image pichincha-devops:local
.\.venv\Scripts\python.exe -m scripts.smoke --url https://localhost:9443 --require-two-backends
```

No repetir `kind create cluster` si ya existe. El kubeconfig queda en `.runtime/`;
no se cambia el contexto global del usuario. El archivo Metrics Server es una copia
versionada de la publicación oficial indicada en su cabecera. Su flag
`--kubelet-insecure-tls` es exclusivamente para certificados autofirmados de kind;
no usar ese manifiesto en producción.

Validar distribución, métricas y escalado:

```powershell
kubectl --context kind-devops-assessment -n devops get pods -o wide
kubectl --context kind-devops-assessment -n devops get hpa
.\.venv\Scripts\python.exe -m scripts.load --seconds 120 --workers 16
kubectl --context kind-devops-assessment -n devops get hpa
kubectl --context kind-devops-assessment -n devops get pods -o wide
```

Para observar en paralelo: `kubectl --context kind-devops-assessment -n devops get hpa -w`.
HPA depende de carga y métricas; puede tardar varios ciclos. La reducción espera
120 segundos de estabilización y puede prolongarse por el promedio de métricas.

## Preparar producción

1. Disponer de un cluster con dos workers elegibles, Kubernetes compatible, Metrics
   Server, StorageClass predeterminada y CNI que aplique NetworkPolicy. El pipeline
   usa kubectl 1.37.0; para otra versión de servidor respetar el version skew oficial.
2. Un administrador aplica `infra/k8s/bootstrap.yaml` una vez. Crea el namespace
   `devops`, ServiceAccount `deployer` y permisos limitados a ese namespace.
3. Proporcionar kubeconfig de despliegue con TLS verificado y credencial vigente de
   ese ServiceAccount. La autenticación debe ser renovable según la plataforma;
   no entregar kubeconfig administrador a GitHub. El endpoint del API server debe
   ser alcanzable por el runner seleccionado.
4. Configurar el proveedor de `Service type LoadBalancer`, o adaptar el servicio al
   balanceador existente. En bare metal hace falta una implementación de LoadBalancer.
5. Apuntar DNS al balanceador y disponer de certificado público válido para ese
   dominio con cadena completa y su clave privada. Kong termina TLS en 8443 detrás
   del puerto 443 del servicio.
6. Crear el repositorio **público** en GitHub con rama predeterminada `master` y subir
   estos archivos. No subir `.env`, `.runtime`, claves ni kubeconfigs.
7. GHCR crea paquetes privados por defecto: hacer público el paquete de imagen de
   esta prueba antes de que Kubernetes deba descargarlo, o configurar credenciales
   de pull en los nodos. Este proyecto no crea un imagePullSecret automáticamente.
   La primera publicación puede completar `publish` y fallar en `deploy` hasta que
   exista ese acceso; corregirlo y reejecutar el job de despliegue.

### Environment GitHub `production`

| Tipo | Nombre | Contenido |
|---|---|---|
| Secret | `KUBECONFIG_B64` | Kubeconfig restringido, codificado en Base64 |
| Secret | `API_KEY` | Clave literal suministrada por el PDF |
| Secret | `JWT_SECRET` | Clave aleatoria, al menos 32 bytes; distinta de la local |
| Secret | `TLS_CERT_B64` | Certificado y cadena PEM en Base64 |
| Secret | `TLS_KEY_B64` | Clave privada PEM en Base64 |
| Variable | `PUBLIC_URL` | `https://` y dominio público, sin `/DevOps` final |

Base64 no cifra los datos. Cargar los valores mediante el gestor de secretos de
GitHub; no pegarlos en commits ni mensajes. Restringir el environment a `master`.
Si se configura aprobación humana obligatoria, el despliegue deja de ser totalmente
automático; el PDF pide despliegue automático desde master.

`GITHUB_TOKEN` solo obtiene `packages: write` en publish. El resto mantiene
`contents: read`. Los PR no reciben secretos de producción. La imagen se construye
una vez, se prueba y se publica desde el mismo archivo; no se reconstruye al publicar.

### Despliegue manual o rollback

Ejecutar `workflow_dispatch` sobre **master** e indicar `image_digest` con
`sha256:` y los 64 caracteres hexadecimales de una imagen ya publicada. El workflow
restringe la selección al paquete GHCR del propio repositorio. El digest aparece
en el resumen de cada publicación. Omitirlo construye una nueva imagen del commit.
La prueba HTTPS posterior detecta incompatibilidades con el contrato actual.

En una estación con variables de producción y kubeconfig apropiado:

```bash
python -m scripts.deploy --image ghcr.io/OWNER/REPO@sha256:DIGEST --dry-run
python -m scripts.deploy --image ghcr.io/OWNER/REPO@sha256:DIGEST
python -m scripts.smoke --url https://DOMINIO --public-ca --require-two-backends
```

Sustituir OWNER/REPO por minúsculas y DIGEST por el hash completo. `--dry-run` usa
validación del servidor sin mutaciones. El despliegue aplica Secrets sin anotación
client-side y no imprime su contenido. Cambiar secretos actualiza una anotación de
checksum para reiniciar pods. Rotar la clave invalida tokens anteriores; coordinar
la rotación con el evaluador. Redis y Kong no comparten un mecanismo de rotación
sin interrupción en esta entrega.

### Diagnóstico

```bash
kubectl -n devops get deployments,pods,services,hpa,pvc
kubectl -n devops get events --sort-by=.lastTimestamp
kubectl -n devops logs deployment/devops --tail=50
kubectl -n devops logs deployment/kong --tail=50
```

- `Pending`: verificar dos workers, volumen disponible y recursos.
- `ImagePullBackOff`: verificar visibilidad GHCR o autenticación de los nodos.
- HPA `<unknown>`: revisar Metrics Server y CPU requests de los pods.
- 401: generar JWT nuevo con la misma clave configurada en producción; verificar reloj.
- 409: generar otro JWT; no reintentar con el token consumido.
- 503: revisar Redis y su PVC; el servicio falla cerrado intencionalmente.

### Apagado local

`docker compose down` detiene Compose sin borrar el volumen de Redis.
`kind delete cluster --name devops-assessment` elimina el laboratorio Kubernetes y
sus volúmenes; usar solo cuando ya no se necesite conservar las evidencias.
