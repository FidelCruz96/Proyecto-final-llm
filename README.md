# Proyecto-final-llm
1. Guía de Usuario

1.1. Objetivo del Sistema

El router recibe un texto, detecta su complejidad y selecciona automáticamente el modelo LLM más adecuado según costo, velocidad y capacidad de razonamiento.

1.2. Endpoint del sistema:

POST /route

1.3. Body:
{
  "user_id": "u1",
  "text": "Escribe aquí tu consulta"
}

1.4. Ejemplo práctico:

curl -X POST "https://llm-router.../route" \
 -H "Content-Type: application/json" \
 -d '{"user_id":"u1","text":"Define qué es una API"}'

1.5. Respuesta:

{
  "routing": {
    "tier": "simple",
    "model_used": "gemini-2.0-flash-lite",
    "tokens_est": 8,
    "latency_ms": 2336.86
  },
  "response": {
    "model": "gemini-2.0-flash-lite",
    "output": "..."
  }
}

2. Guía de Administrador

2.1. Despliegue en Cloud Run (GCP):

gcloud run deploy llm-classifier \                                                                                                                                     
  --image us-central1-docker.pkg.dev/llm-router-project-479922/llm-router-repo/llm-classifier \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated

gcloud run deploy llm-router \                                                                    llm-router-project
  --image us-central1-docker.pkg.dev/llm-router-project-479922/llm-router-repo/llm-router \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars CLASSIFIER_URL=https://llm-classifier-911161541488.us-central1.run.app/predict \
  --set-env-vars GEMINI_API_KEY="AIzaSyC64plEiU6rsBw0kfFj2iwWAY2GfTOHTVE"

2.2. Ver logs:

gcloud logging read \
 'resource.type="cloud_run_revision" AND resource.labels.service_name="llm-router"' \
 --limit 50 --format="value(textPayload)"


3. Caso de Uso
 	
El proyecto resuelve la necesidad de optimizar costos, latencia y calidad al utilizar modelos de lenguaje grandes (LLMs).
Dado que distintos tipos de consultas requieren distintos niveles de capacidad computacional, un router inteligente permite redirigir cada consulta al modelo más adecuado según complejidad.

Escenarios típicos:
Chatbots empresariales


Soporte técnico automatizado


Clasificación y análisis rápido


Generación de contenido según complejidad


Requisitos del caso:
Consultas simples usan un modelo económico


Consultas medianas usan un modelo equilibrado


Consultas complejas usan un modelo premium


Deben existir KPIs de rendimiento y costo
	 	 	 	
KPIs del Sistema
 	 	 	
Routing Accuracy: 100% en pruebas iniciales.
Cost Savings: 55.5% (baseline real de pruebas) y 77.5% para cargas normales.
Latencia por Tier: simple=2.3s / medium=5.6s / complex=10.2s
Throughput: ~35 req/s (estimado Cloud Run)
Costo por 1k requests: 0.27 USD (vs 1.20 USD sin router)


4. Diseño del Router

El router implementa:
análisis de tokens


consulta al classifier


asignación de un modelo LLM


logging avanzado


medición de latencia


resiliencia ante fallos


Algoritmo resumido:
Recibir input


Llamar al classifier


Identificar tier


Elegir modelo usando MODEL_MAP


Ejecutar inferencia


Medir latencia


Registrar log


Devolver resultado
Criterios Técnicos de Clasificación (Heurísticas)
El router utiliza un conjunto de reglas simples y efectivas para asignar una solicitud a un tier:
Conteo de tokens (tokens_est):


0–25 tokens → simple


26–100 tokens → medium


101+ tokens → complex


Presencia de keywords técnicas:
 Si la consulta contiene términos de alta complejidad como:
arquitectura, serverless, autoscaling, optimización,
latencia, carga distribuida, RAG, embeddings

automáticamente se fuerza el tier → complex.


    3. Propósito de la consulta:


definiciones, preguntas cortas → simple


explicaciones medianas → medium


diseño de sistemas, análisis técnico → complex


Estas heurísticas permiten lograr un Routing Accuracy del 100% en pruebas iniciales.

5. Modelos Utilizados

Por temas ajenos, se usaron los siguientes modelos para hacer el proyecto de rendimiento:

Tier
Modelo
Descripción
Costo 1k tokens (USD)
simple
gemini-2.0-flash-lite
veloz y barato
$0.0001
medium
gemini-2.5-flash
razonamiento intermedio
$0.0003
complex
gemini-2.5-pro
mayor capacidad y costo
$0.0012


flash-lite es el más eficiente para tareas simples y reduce el costo drásticamente.


2.5-flash ofrece equilibrio costo/razonamiento.


2.5-pro brinda la mayor calidad, reservada para tareas complejas.

6. Patrones LLM

Patrón Principal: Model Router Pattern
El router implementa el Model Router Pattern, cuyo objetivo es seleccionar dinámicamente el modelo LLM más adecuado según:
complejidad de la consulta,


costo por inferencia,


latencia esperada,


restricciones del servicio.


Este patrón permite:
asignar modelos pequeños para tareas simples,


usar modelos medianos para consultas analíticas,


escalar hacia modelos avanzados en solicitudes complejas.


El patrón es modular, extensible y separa claramente:
Clasificación de la consulta (classifier)


Selección del modelo (decision engine)


Ejecución del LLM (model executor)

Patrón: Small-to-Big Routing
modelos pequeños para solicitudes sencillas


modelos grandes solo cuando necesario


optimización de costo por decisión inteligente


Beneficios:
ahorro del 55% al 80%


menor latencia promedio


escalado más eficiente

7. Arquitectura
Componentes:
Router (Cloud Run)


Classifier (Cloud Run)


Gemini API (LLM Providers)


Cloud Logging


Autoscaling


Infraestructura 100% Serverless
 Sin VMs, sin administración de servidores.

8. Estrategias de Costo

Los LLM tienen costos diferentes.
Sin router → todo se ejecuta en gemini-2.5-pro (caro).


Tier
Modelo
Ahorro vs Pro
simple
2.0-flash-lite
91.6%
medium
2.5-flash
75%
complex
2.5-pro
0%


Si el 70% de consultas son simples o medias, los costos bajan entre 55% y 80%.


9. Resultados Experimentales


Tier
Modelo
Tokens
Latencia
simple
2.0-flash-lite
8
2336ms
medium
2.5-flash
29
5627ms
complex
2.5-pro
34
10267ms


10. Testing

Casos probados:

10.1. Prueba Simple:


✔ Tier correcto
✔ Modelo: flash-lite

10.2. Prueba medio:

✔ Tier correcto
✔ Modelo: 2.5-flash

10.3. Prueba compleja:


✔ Tier correcto
✔ Modelo: 2.5-pro

Routing Accuracy:

100% (3/3 correctos)

11. Diagrama Final



12. Lecciones Aprendidas

No todas las consultas requieren un modelo grande


Los modelos económicos ofrecen gran valor en tareas simples


La clasificación previa ahorra costos reales


La latencia aumenta proporcionalmente al razonamiento


Cloud Run simplifica la infraestructura


El logging es el corazón de FinOps


La modularidad facilita mantenimiento y escalabilidad

El autoscaling de Cloud Run mostró instancias frías con latencias iniciales mayores, mitigadas mediante min-instances.


La contenerización con imágenes livianas reduce el cold start de forma significativa.


Los timeouts y retries deben configurarse explícitamente para evitar fallos silenciosos en servicios LLM externos.


La separación entre classifier y router mejora la resiliencia y permite reemplazar el modelo de clasificación sin afectar el enrutamiento general.
