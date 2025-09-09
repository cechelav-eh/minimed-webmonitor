# MiniMed Monitor Web

Un monitor web para bombas de insulina MiniMed que permite visualizar datos en tiempo real de glucosa, estado de la bomba y gráficos históricos a través de una interfaz web moderna.

> **Nota**: Este proyecto es un fork del repositorio [carelink-python-client](https://github.com/ondrej1024/carelink-python-client) al que se le ha agregado un visualizador web moderno y una interfaz de usuario mejorada.

## 🚀 Características

- **Monitoreo en tiempo real**: Visualización de niveles de glucosa, batería, reservorio y insulina activa
- **Gráficos históricos**: Historial de glucosa con marcadores de eventos (comidas, insulina, calibraciones)
- **Interfaz web responsive**: Diseño optimizado para dispositivos móviles y desktop
- **Integración con CareLink**: Conexión directa con los servidores de Medtronic CareLink
- **Docker support**: Fácil despliegue con Docker y Docker Compose
- **Autenticación automática**: Script automatizado para obtener credenciales de CareLink

## 📋 Requisitos

- Python 3.9+
- Firefox (necesario para el proceso de autenticación)
- Acceso a internet para conectar con CareLink
- Credenciales válidas de Medtronic CareLink

## 🛠️ Instalación

### Instalación Local

1. **Clonar el repositorio**:

```bash
git clone <repository-url>
cd minimed-webmonitor
```

2. **Instalar dependencias**:

```bash
pip install -r requirements.txt
```

3. **Configurar credenciales (OBLIGATORIO)**:

```bash
python carelink_carepartner_api_login.py
```

- Este paso es **obligatorio** antes de ejecutar la aplicación
- El script abrirá Firefox para autenticarte con CareLink
- Las credenciales se guardarán automáticamente en `data/logindata.json`

4. **Ejecutar la aplicación**:

```bash
python minimed-mon-web.py
```

La aplicación estará disponible en `http://localhost:5001`

### Instalación con Docker

0. **Configurar credenciales (OBLIGATORIO)**:

```bash
python carelink_carepartner_api_login.py
```

- Este paso es **obligatorio** antes de ejecutar con Docker
- El script abrirá Firefox para autenticarte con CareLink
- Las credenciales se guardarán automáticamente en `data/logindata.json`

1. **Usar Docker Compose** (recomendado):

```bash
docker-compose up -d
```

2. **O construir manualmente**:

```bash
docker build -t minimed-web .
docker run -p 5001:5001 -p 8081:8081 -v $(pwd)/data:/app/data minimed-web
```

## 🔧 Configuración

### Credenciales de CareLink

Las credenciales se obtienen automáticamente ejecutando:

```bash
python carelink_carepartner_api_login.py
```

Este script:

1. Abrirá Firefox automáticamente
2. Te guiará a través del proceso de login de CareLink
3. Guardará las credenciales en `data/logindata.json`

El archivo generado contendrá tus tokens de acceso en el formato requerido.

### Variables de Entorno

- `TZ`: Zona horaria (por defecto: Chile/Santiago)

## 📊 Uso

### Interfaz Principal

- **Nivel de glucosa**: Muestra el valor actual y tendencia
- **Estado de la bomba**: Batería, reservorio, insulina activa
- **Conexión del sensor**: Estado de conexión y edad del sensor
- **Gráfico histórico**: Visualización de las últimas 24 horas con marcadores de eventos

### Marcadores en el Gráfico

- 🔵 **Azul**: Insulina automática (AUTOCORRECTION)
- 🟢 **Verde**: Insulina recomendada (RECOMMENDED)
- 🟣 **Lila**: Entrega de basal automática
- 🔴 **Rojo**: Calibraciones
- 🟡 **Amarillo**: Comidas

### API Endpoints

- `GET /api/pump-data`: Datos actuales de la bomba
- `GET /api/pump-graph-data`: Datos históricos y gráficos
- `GET /login`: Interfaz de configuración de credenciales
- `POST /login`: Guardar nuevas credenciales

## 🏗️ Arquitectura

El proyecto consta de varios componentes:

- **`minimed-mon-web.py`**: Aplicación Flask principal
- **`carelink_client2.py`**: Cliente para conectar con CareLink
- **`carelink_client2_proxy.py`**: Servidor proxy para datos
- **`templates/`**: Plantillas HTML
- **`static/`**: Recursos estáticos (imágenes, sonidos)

### Flujo de Datos

1. El cliente CareLink se conecta a los servidores de Medtronic
2. Los datos se obtienen cada 5 minutos (configurable)
3. Un servidor proxy local (puerto 8081) expone los datos
4. La aplicación web (puerto 5001) consume estos datos
5. La interfaz se actualiza automáticamente cada minuto

## 🔒 Seguridad

- Las credenciales se almacenan localmente en `data/logindata.json`
- El archivo de credenciales se respalda automáticamente antes de cambios
- La aplicación no almacena datos médicos permanentemente

## 🐛 Solución de Problemas

### El servidor proxy no inicia

```bash
# Verificar si el puerto 8081 está en uso
netstat -tulpn | grep 8081

# Reiniciar manualmente
python carelink_client2_proxy.py
```

### Error de autenticación

1. Verificar que las credenciales en `logindata.json` sean correctas
2. Re-ejecutar el script de login: `python carelink_carepartner_api_login.py`
3. Asegurarse de que Firefox esté instalado y funcional
4. El servidor proxy se reiniciará automáticamente

### Datos no se actualizan

1. Verificar conexión a internet
2. Comprobar logs de la aplicación
3. Verificar que el sensor esté en rango

## 📝 Logs

Los logs se muestran en la consola con el siguiente formato:

```
[2024-01-01 12:00:00:INFO] Starting MiniMed Monitor Web
[2024-01-01 12:00:01:INFO] Servidor proxy iniciado correctamente
[2024-01-01 12:00:02:INFO] Iniciando cliente Carelink...
```

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit tus cambios (`git commit -am 'Agregar nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es para uso personal y educativo. Por favor, respeta los términos de servicio de Medtronic CareLink.

## ⚠️ Disclaimer

Este software no está afiliado con Medtronic. Úsalo bajo tu propia responsabilidad. Siempre consulta con tu médico sobre el manejo de tu diabetes.

## 📞 Soporte

Para reportar bugs o solicitar features, por favor abre un issue en el repositorio.

## 🙏 Créditos

Este proyecto está basado en el excelente trabajo de [ondrej1024/carelink-python-client](https://github.com/ondrej1024/carelink-python-client), que proporciona la funcionalidad base para conectarse con Medtronic CareLink.

### Créditos del proyecto original:

- **ondrej1024** - Autor del cliente Python de CareLink
- **Pal Marci** - Por revertir la comunicación de la API de CareLink Cloud
- **Bence Szász** - Por la implementación Java de xDrip Carelink Follower

### Mejoras agregadas en este fork:

- Interfaz web moderna y responsive
- Visualización en tiempo real de datos
- Gráficos históricos con marcadores de eventos
- Integración con Docker para fácil despliegue
- Gestión automática de credenciales

---

**Nota**: Este proyecto requiere credenciales válidas de Medtronic CareLink. Asegúrate de tener acceso autorizado antes de usar esta aplicación.
