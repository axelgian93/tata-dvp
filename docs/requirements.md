# Matriz de requisitos

| Requisito del PDF | Implementación | Comprobación |
|---|---|---|
| POST /DevOps y JSON exacto | src/devops_service/app.py | tests/test_api.py + scripts/smoke.py |
| Otros métodos ERROR | Middleware y plantillas de error de Kong | Tests de métodos + smoke HTTPS |
| API key en headers | Kong key-auth + validación del backend | Faltante/incorrecta rechazada |
| JWT único por transacción | Emisión UUID, expiración, Redis SET NX EX | Replay entre réplicas y concurrente |
| JWT suministrado al evaluador | scripts/issue_token.py | CLI emite token nuevo por invocación |
| API Manager | Kong DB-less configurado como código | Gateway real en integración |
| Docker | Dockerfile multietapa y usuario no root | Build y ejecución real |
| Balanceador y dos nodos | Kong + dos workers, topology spread | Pods en hosts distintos y smoke |
| IaC versionada | infra/kind.yaml e infra/k8s/*.yaml | Aplicación y validación Kubernetes |
| Gestión de dependencias | pyproject.toml y dos lockfiles | Instalación y pip-audit |
| Build/test mínimos | Jobs build y test | Pipeline + reproducción local |
| Automático en cualquier rama | push branches ['**'] y pull_request | Workflow versionado |
| master despliega producción | publish/deploy condicionados a master | Requiere destino y secretos |
| Ejecución bajo demanda | workflow_dispatch | Input digest opcional |
| Desplegar cualquier versión | Digest inmutable del mismo paquete | Selección de release / rollback |
| Pruebas automáticas | pytest y smoke con contenedores | Reporte cobertura y JUnit |
| Revisión estática | Ruff + Bandit + auditoría dependencias | Gates del job test |
| Dynamic grow | HPA CPU 60%, 2..6 réplicas | scripts/load.py y métricas HPA |
| Clean Code | Factoría de app, configuración y seguridad separadas | Revisión de código |
| TDD/cobertura | Commit de pruebas fallidas previo al servicio | Historial Git y reporte de cobertura |
| GitHub público + HOST | Preparado para publicación | Pendiente de repo y dominio del candidato |

Los dos nodos de kind son una prueba local, no dos máquinas físicas. Los manifiestos
se pueden aplicar a dos workers físicos o cloud sin cambiar la aplicación. No se
requiere contratar nube para construir y verificar la solución local.
