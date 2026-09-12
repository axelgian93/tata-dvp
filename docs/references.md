# Referencias oficiales verificadas

- Kong JWT y configuración de consumidores: https://developer.konghq.com/plugins/jwt/
- Kong API key: https://developer.konghq.com/plugins/key-auth/
- Kong JWT en header: https://developer.konghq.com/plugins/jwt/examples/header/
- El formato Bearer exigido incluso para headers personalizados se verificó además
  en `/usr/local/share/lua/5.1/kong/plugins/jwt/handler.lua` de kong:3.9.1.
- Plantillas de errores: `/etc/kong/kong.conf.default` de la imagen fijada.
- GitHub Actions syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Container registry: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Kubernetes HPA: https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/
- Topology spread: https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/
- kind: https://kind.sigs.k8s.io/docs/user/quick-start/
- Metrics Server: https://github.com/kubernetes-sigs/metrics-server/releases/tag/v0.9.0
- kubectl version skew: https://kubernetes.io/releases/version-skew-policy/

Las versiones y digests de imágenes y acciones fueron resueltos contra sus registros
oficiales durante la implementación. Dependabot permite proponer actualizaciones;
actualizar las imágenes de workloads/Compose requiere revisar sus digests juntos.
