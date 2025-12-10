# Automatización de Instancias VSI en IBM Cloud: Arquitectura Serverless con Code Engine

**Autor:** César Carrasco - IBM Cloud Customer Success Specialist  
**Fecha:** Diciembre 2024  
**Nivel:** Intermedio a Avanzado  

---

## Resumen Ejecutivo

Esta guía documenta la implementación de una solución serverless para automatizar el ciclo de vida de Virtual Server Instances (VSI) en IBM Cloud VPC mediante Code Engine y Event Subscriptions. La arquitectura propuesta permite optimizar costos operacionales al gestionar el encendido y apagado programático de instancias según horarios definidos, reduciendo el gasto en recursos computacionales fuera del horario productivo.

**Beneficios clave:**
- Reducción de costos de infraestructura hasta un 65% en ambientes no productivos
- Ejecución serverless con facturación basada en uso real
- Escalabilidad horizontal para gestión de múltiples instancias
- Orquestación declarativa mediante cron expressions
- Observabilidad integrada con logs centralizados

---

## Arquitectura de la Solución

<img width="924" height="329" alt="Captura de pantalla 2025-12-10 a la(s) 2 25 38 p  m" src="https://github.com/user-attachments/assets/d23224fd-a30c-4e25-a0b9-c8be375b3b13" />

*Flujo end-to-end desde desarrollo hasta ejecución automatizada*

### Componentes Principales

| Componente | Rol | Tecnología |
|------------|-----|------------|
| **Source Repository** | Control de versiones del código fuente | GitHub |
| **Build Environment** | Construcción de imágenes de contenedor | Docker Engine |
| **Container Registry** | Almacenamiento de artefactos | IBM Container Registry (us-south) |
| **Orchestration Platform** | Ejecución serverless y scheduling | IBM Code Engine |
| **Target Infrastructure** | Instancias a gestionar | IBM VPC Gen 2 |

### Flujo de Datos

1. **Phase 1 - Build & Deployment**
   - Clonación del repositorio desde GitHub
   - Construcción local de imagen Docker
   - Push de artefacto a Container Registry (Dallas)

2. **Phase 2 - Runtime Execution**
   - Event Subscription activa job según cron schedule
   - Code Engine ejecuta contenedor con credenciales IAM
   - Invocación a VPC API para operaciones start/stop
   - Persistencia de logs de ejecución

---

## Prerequisitos Técnicos

### 1. Herramientas de Desarrollo

```bash
# Verificar versiones instaladas
ibmcloud --version  # >= 2.0.0
docker --version    # >= 20.10.0
git --version       # >= 2.30.0
```
Instalación de IBM Cloud CLI:
- **macOS/Linux:** `curl -fsSL https://clis.cloud.ibm.com/install/linux | sh`
- **Windows:** Descarga desde https://cloud.ibm.com/docs/cli

Plugins requeridos:
```bash
ibmcloud plugin install container-registry
ibmcloud plugin install code-engine
ibmcloud plugin install vpc-infrastructure
```

### 2. Credenciales y Permisos IAM

**API Key Requirements:**

La API Key debe contar con las siguientes políticas IAM:

| Servicio | Rol Mínimo | Justificación |
|----------|------------|---------------|
| VPC Infrastructure | Editor | Ejecución de acciones start/stop en VSIs |
| Code Engine | Writer | Despliegue de jobs y secrets |
| Container Registry | Reader | Pull de imágenes de contenedor |

<img width="645" height="398" alt="Captura de pantalla 2025-12-10 a la(s) 2 31 38 p  m" src="https://github.com/user-attachments/assets/ee7e80fa-3018-4843-bc1c-2b0f8ca6d0d2" />

*Configuración de políticas IAM requeridas*

Creación de API Key:
```bash
ibmcloud iam api-key-create vsi-automation-key \
  -d "Production VSI Scheduler" \
  --file vsi-automation-key.json
```

**⚠️ Importante:** Almacene la API Key en un gestor de secretos (HashiCorp Vault, IBM Secrets Manager) y rote periódicamente.

### 3. Inventario de Recursos

Documentar IDs de instancias VSI:
```bash
ibmcloud is instances --output json | \
  jq -r '.[] | "\(.id),\(.name),\(.zone.name)"' > vsi-inventory.csv
```

---

## Implementación

### Paso 1: Obtención del Código Fuente

Clone el repositorio que contiene los artefactos de la solución:

```bash
git clone https://github.com/your-org/vsi-automation.git
cd vsi-automation
```

**Estructura del repositorio:**
```
vsi-automation/
├── instance_scheduler.py    # Script principal de automatización
├── Dockerfile                # Definición de imagen
├── requirements.txt          # Dependencias Python
└── README.md                 # Documentación
```

---

### Paso 2: Construcción del Contenedor

La imagen Docker encapsula el runtime de Python y las dependencias del SDK de IBM Cloud.

#### 2.1 Construcción Local

```bash
# Construir imagen
docker build -t vsi-scheduler:latest .

# Verificar construcción exitosa
docker images vsi-scheduler
```

**Output esperado:**
```
REPOSITORY       TAG      IMAGE ID       CREATED         SIZE
vsi-scheduler    latest   abc123def456   2 minutes ago   254MB
```

**[IMAGEN: Terminal mostrando docker build exitoso - docker-build.png]**

#### 2.2 Consideraciones de Optimización

El Dockerfile implementa las siguientes mejores prácticas:

- **Multi-stage builds:** Reducción del tamaño de imagen final
- **Layer caching:** Instalación de dependencias antes de copiar código fuente
- **Slim base image:** Python 3.11-slim para footprint mínimo
- **Non-root user:** Ejecución con usuario sin privilegios

---

### Paso 3: Registro en Container Registry

IBM Container Registry proporciona almacenamiento privado de imágenes con escaneo de vulnerabilidades integrado.

#### 3.1 Configuración Regional

```bash
# Configurar región Dallas (us-south)
ibmcloud cr region-set us-south

# Autenticación
ibmcloud cr login
```

#### 3.2 Gestión de Namespace

Los namespaces proveen aislamiento lógico entre proyectos:

```bash
# Crear namespace (si no existe)
ibmcloud cr namespace-add vsi-automation

# Listar namespaces disponibles
ibmcloud cr namespace-list
```

#### 3.3 Push de Imagen

```bash
# Tag con nomenclatura del registry
docker tag vsi-scheduler:latest \
  us.icr.io/vsi-automation/vsi-scheduler:latest

# Push a registry remoto
docker push us.icr.io/vsi-automation/vsi-scheduler:latest
```

**Monitoreo del push:**
```bash
# Verificar imagen en registry
ibmcloud cr images --restrict vsi-automation
```

**Output esperado:**
```
REPOSITORY                                 TAG      DIGEST         SIZE
us.icr.io/vsi-automation/vsi-scheduler    latest   sha256:abc...  254 MB
```

**⚠️ Troubleshooting:** Si el tamaño reportado es < 10 MB, indica un push incompleto. Elimine la imagen y reintente.

**[IMAGEN: Consola mostrando imagen en Container Registry - registry-image.png]**

---

### Paso 4: Configuración de Code Engine

Code Engine abstrae la complejidad de Kubernetes, proporcionando una capa serverless para ejecución de jobs.

#### 4.1 Creación del Proyecto

Acceda a la consola de Code Engine:
- **URL:** https://cloud.ibm.com/codeengine/projects
- Click en **"Create project"**

**[IMAGEN: Formulario de creación de proyecto - ce-project-create.png]**

**Configuración recomendada:**

| Parámetro | Valor | Notas |
|-----------|-------|-------|
| Name | `vsi-automation-prod` | Nomenclatura descriptiva |
| Location | `us-south (Dallas)` | Colocation con Container Registry |
| Resource Group | Según organización | Alineado a modelo de facturación |

**Documentación oficial:** https://cloud.ibm.com/docs/codeengine?topic=codeengine-getting-started

#### 4.2 Configuración de Secrets

Los secrets almacenan credenciales de forma segura, inyectándolas como variables de entorno en tiempo de ejecución.

**Navegación:**
1. Seleccione el proyecto creado
2. **Secrets and configmaps** → **Create**
3. Seleccione **"Secret"**

**[IMAGEN: Formulario de creación de secret - ce-secret-create.png]**

**Configuración:**
- **Name:** `ibm-api-credentials`
- **Format:** Generic (no Registry)
- **Key-value pair:**
  - **Key:** `IBM_API_KEY`
  - **Value:** `<su-api-key-generada-previamente>`

**⚠️ Seguridad:** Nunca commit API keys en repositorios. Utilice secrets management dedicado para ambientes productivos.

#### 4.3 Creación de Jobs

Los jobs representan cargas de trabajo batch con ejecución finita.

**Navegación:**
1. **Jobs** → **Create**

**[IMAGEN: Formulario de creación de job - ce-job-create.png]**

##### Job 1: Detención de Instancias

| Sección | Parámetro | Valor |
|---------|-----------|-------|
| **General** | Name | `stop-vsis-prod` |
| | Code | Container image |
| | Image reference | `us.icr.io/vsi-automation/vsi-scheduler:latest` |
| | Registry access | Automatic |
| **Resources** | CPU | 0.25 vCPU |
| | Memory | 512 MB |
| | Max execution time | 600 seconds |
| | Retry limit | 2 |
| **Environment Variables** | | |
| | Secret reference | `ibm-api-credentials` (full secret) |
| | INSTANCE_IDS | `<id1>,<id2>,<id3>` (literal) |
| | REGION | `us-east` (literal) |
| | ACTION | `stop` (literal) |
| | EXECUTION_MODE | `sequential` (literal) |
| | CONTINUE_ON_ERROR | `true` (literal) |

**[IMAGEN: Variables de entorno configuradas - ce-job-envvars.png]**

##### Job 2: Inicio de Instancias

Repita la configuración anterior con estas diferencias:

| Parámetro | Valor |
|-----------|-------|
| Name | `start-vsis-prod` |
| ACTION | `start` |

**Todas las demás configuraciones permanecen idénticas.**

**Documentación oficial:** https://cloud.ibm.com/docs/codeengine?topic=codeengine-job-plan

---

### Paso 5: Validación y Testing

Antes de programar ejecuciones automáticas, valide el comportamiento de los jobs mediante invocaciones manuales.

#### 5.1 Ejecución Manual

**Navegación:**
1. **Jobs** → Seleccione `stop-vsis-prod`
2. Click en **"Submit job"**
3. Confirme con **"Submit"**

**[IMAGEN: Consola mostrando job run en ejecución - ce-jobrun-running.png]**

#### 5.2 Análisis de Logs

**Navegación:**
1. **Job runs** → Seleccione el run más reciente
2. Verifique logs en tiempo real

**[IMAGEN: Logs de ejecución exitosa - ce-jobrun-logs-success.png]**

**Logs esperados:**
```
======================================================================
IBM Cloud VPC Instance Scheduler - Multi-Instance
======================================================================

📋 Configuración:
   Región: us-east
   Acción: stop
   Instancias: 3
   Modo: sequential

🚀 Procesando instancias...

⏸️  Deteniendo instancia prod-web-01 (0757_abc...)...
✓ Comando de detención enviado exitosamente

⏸️  Deteniendo instancia prod-api-01 (0757_def...)...
✓ Comando de detención enviado exitosamente

======================================================================
📊 Resumen:
   Total: 3
   ✓ Exitosas: 3
   ✗ Fallidas: 0
======================================================================
```

#### 5.3 Verificación de Estado

Confirme cambio de estado en las instancias:

```bash
ibmcloud is instances | grep -E 'Name|Status'
```

**Output esperado:**
```
Name                Status
prod-web-01        stopping
prod-api-01        stopping
prod-db-01         stopping
```

**[IMAGEN: Consola de VPC mostrando instancias detenidas - vpc-instances-stopped.png]**

#### 5.4 Test del Job de Inicio

Repita el proceso con `start-vsis-prod` y verifique que las instancias transicionen a estado `running`.

---

### Paso 6: Programación con Event Subscriptions

Event Subscriptions proporciona capacidades de scheduling declarativo mediante cron expressions.

#### 6.1 Creación de Subscription

**Navegación:**
1. **Event subscriptions** → **Create**

**[IMAGEN: Formulario de creación de event subscription - ce-subscription-create.png]**

**Configuración para inicio matutino:**

| Sección | Parámetro | Valor |
|---------|-----------|-------|
| **General** | Event type | Periodic timer |
| | Name | `start-vsis-weekday-morning` |
| **Schedule** | Cron expression | `0 8 * * 1-5` |
| | Time zone | `America/Chicago` |
| **Consumer** | Component type | Job |
| | Job | `start-vsis-prod` |

**[IMAGEN: Cron expression configurado - ce-subscription-cron.png]**

#### 6.2 Subscription para Detención

Repita con estos parámetros:

| Parámetro | Valor |
|-----------|-------|
| Name | `stop-vsis-weekday-evening` |
| Cron expression | `0 18 * * 1-5` |
| Job | `stop-vsis-prod` |

**Documentación oficial:** https://cloud.ibm.com/docs/codeengine?topic=codeengine-subscribe-cron

#### 6.3 Catálogo de Cron Expressions

| Caso de Uso | Expresión | Descripción |
|-------------|-----------|-------------|
| Business hours | `0 8 * * 1-5` | L-V 8:00 AM |
| End of day | `0 18 * * 1-5` | L-V 6:00 PM |
| Weekend shutdown | `0 20 * * 5` | Viernes 8:00 PM |
| Weekend startup | `0 7 * * 1` | Lunes 7:00 AM |
| Monthly maintenance | `0 2 1 * *` | Día 1 de cada mes 2:00 AM |
| Bi-hourly check | `0 */2 * * *` | Cada 2 horas |

**Herramienta de validación:** https://crontab.guru

**[IMAGEN: Lista de event subscriptions activas - ce-subscriptions-list.png]**

---

## Variables de Entorno: Referencia Completa

### Variables Obligatorias

| Variable | Tipo | Descripción | Ejemplo |
|----------|------|-------------|---------|
| `IBM_API_KEY` | Secret | Credencial IAM para autenticación VPC API | `<desde secret>` |
| `INSTANCE_IDS` | String | Lista CSV de instance IDs | `0757_a,0757_b,0757_c` |
| `REGION` | String | Región de VPC donde residen las instancias | `us-east`, `us-south` |
| `ACTION` | Enum | Operación a ejecutar | `start`, `stop`, `status` |

### Variables Opcionales

| Variable | Default | Descripción | Valores |
|----------|---------|-------------|---------|
| `EXECUTION_MODE` | `sequential` | Estrategia de procesamiento | `sequential`, `parallel` |
| `CONTINUE_ON_ERROR` | `true` | Comportamiento ante fallos | `true`, `false` |

### Consideraciones de Configuración

**Sequential vs Parallel:**

- **Sequential:** Procesa instancias una a una. Recomendado para:
  - Ambientes con dependencias entre instancias
  - Debugging y troubleshooting
  - Límites de rate limiting estrictos

- **Parallel:** Procesa todas las instancias simultáneamente. Recomendado para:
  - Ambientes de gran escala (>10 instancias)
  - Minimizar tiempo total de ejecución
  - Instancias completamente independientes

**Error Handling:**

- `CONTINUE_ON_ERROR=true`: Procesa todas las instancias incluso si alguna falla
- `CONTINUE_ON_ERROR=false`: Detiene ejecución ante primer error

---

## Operaciones y Mantenimiento

### Monitoreo de Ejecuciones

**Desde Consola:**
1. **Jobs** → Seleccione job → **Job runs**
2. Visualice historial completo de ejecuciones
3. Filtre por estado: Success, Failed, Pending

**[IMAGEN: Historial de job runs - ce-jobrun-history.png]**

**Desde CLI:**
```bash
# Listar últimas 20 ejecuciones
ibmcloud ce jobrun list --job start-vsis-prod --limit 20

# Ver logs de ejecución específica
ibmcloud ce jobrun logs --name start-vsis-prod-run-abc123
```

### Métricas de Rendimiento

**KPIs a monitorear:**
- **Success Rate:** % de ejecuciones exitosas
- **Execution Time:** Tiempo promedio de ejecución
- **Failure Rate:** Tendencia de fallos
- **Cost per Execution:** vCPU-seconds consumidos

### Troubleshooting

#### Problema: Job falla con "IBM_API_KEY no está configurada"

**Causa:** Secret configurado como tipo `registry` en lugar de `generic`

**Solución:**
```bash
# Verificar formato del secret
ibmcloud ce secret get --name ibm-api-credentials

# Si Format=registry, eliminar y recrear
ibmcloud ce secret delete --name ibm-api-credentials --force
ibmcloud ce secret create --name ibm-api-credentials \
  --from-literal IBM_API_KEY=<api-key>
```

#### Problema: Instancias no cambian de estado

**Diagnóstico:**
1. Verificar permisos IAM de la API Key
2. Confirmar IDs de instancias correctos
3. Validar región configurada

```bash
# Verificar permisos
ibmcloud iam api-key-get vsi-automation-key

# Test manual de API
ibmcloud is instance-stop <instance-id>
```

#### Problema: Image pull failed

**Causa:** Permisos insuficientes en Container Registry

**Solución:**
```bash
# Verificar permisos en namespace
ibmcloud cr namespace-list

# Otorgar acceso si es necesario
ibmcloud iam service-policy-create codeengine \
  --roles Reader --service-name container-registry
```

---

## Consideraciones de Seguridad

### Principio de Mínimo Privilegio

La API Key debe limitarse estrictamente a las operaciones requeridas:

```json
{
  "roles": [
    {
      "role_id": "crn:v1:bluemix:public:iam::::role:Editor",
      "resources": [{
        "attributes": [{
          "name": "serviceName",
          "value": "is"
        }]
      }]
    }
  ]
}
```

### Rotación de Credenciales

Implemente rotación automática de API Keys:

```bash
# Crear nueva API Key
ibmcloud iam api-key-create vsi-automation-key-v2

# Actualizar secret en Code Engine
ibmcloud ce secret update ibm-api-credentials \
  --from-literal IBM_API_KEY=<nueva-key>

# Eliminar API Key anterior
ibmcloud iam api-key-delete vsi-automation-key
```

**Frecuencia recomendada:** Cada 90 días

### Auditoría

Habilite Activity Tracker para auditoría de operaciones:

```bash
ibmcloud resource service-instance-create \
  vsi-automation-tracker \
  logdnaat \
  7-day \
  us-south
```

---

## Optimización de Costos

### Análisis de Costos

**Componentes facturables:**

| Recurso | Modelo de Facturación | Costo Estimado |
|---------|----------------------|----------------|
| Code Engine Jobs | vCPU-seconds + GB-seconds | $0.125/vCPU-hour |
| Container Registry | GB-month storage | $0.50/GB-month |
| VPC API Calls | Por request | Sin costo adicional |

**Cálculo ejemplo (ambientes dev/test):**

```
Escenario: 10 VSIs, 2 jobs/día (start+stop), 22 días laborables/mes

Ejecución por job:
- vCPU: 0.25
- Memoria: 512 MB
- Duración: 30 segundos

Costo mensual Code Engine:
44 jobs × 30 seg × 0.25 vCPU = 0.09 vCPU-hours
0.09 × $0.125 = $0.01/mes

Ahorro en VSIs (12 horas/día apagadas):
10 VSIs × 12 horas × 22 días × $0.05/hora = $132/mes

ROI: 13,200% 🎯
```

### Rightsizing

**Recomendaciones por escala:**

| Instancias | CPU | Memoria | Max Execution Time |
|------------|-----|---------|-------------------|
| 1-5 | 0.125 | 256 MB | 300s |
| 6-20 | 0.25 | 512 MB | 600s |
| 21-50 | 0.5 | 1 GB | 900s |
| 51+ | 1.0 | 2 GB | 1200s |

---

## Conclusiones

Esta arquitectura demuestra cómo las capacidades serverless de IBM Cloud Code Engine permiten construir soluciones de automatización enterprise-grade con inversión mínima en infraestructura. La combinación de Event Subscriptions para orquestación temporal, contenedores para portabilidad, y VPC API para control de ciclo de vida resulta en una solución robusta, escalable y cost-effective.

**Ventajas clave:**
- ✅ **TCO reducido:** Eliminación de infraestructura always-on
- ✅ **Time-to-market:** Deployment en < 30 minutos
- ✅ **Escalabilidad:** Soporte para cientos de instancias sin cambios arquitectónicos
- ✅ **Observabilidad:** Logs y métricas integradas
- ✅ **Seguridad:** Secrets management y permisos granulares

### Próximos Pasos

**Extensiones recomendadas:**
1. **Notificaciones:** Integración con Event Notifications para alertas
2. **Dashboards:** Visualización de métricas en Grafana/Kibana
3. **GitOps:** Automatización de deployment con Terraform
4. **Multi-región:** Replicación de solución cross-region
5. **Policy-based:** Tagging de instancias para scheduling dinámico

---

## Referencias

- **IBM Cloud Code Engine:** https://cloud.ibm.com/docs/codeengine
- **IBM Container Registry:** https://cloud.ibm.com/docs/Registry
- **IBM VPC API Reference:** https://cloud.ibm.com/apidocs/vpc
- **Cron Expression Guide:** https://crontab.guru
- **Best Practices for Serverless:** https://12factor.net

---

**Repositorio:** https://github.com/your-org/vsi-automation  
**Contacto:** cesar.carrasco@ibm.com  
**LinkedIn:** https://linkedin.com/in/cesar-carrasco

---

*Esta documentación fue desarrollada siguiendo IBM Cloud Architecture Framework y Cloud Native Computing Foundation (CNCF) best practices.*
