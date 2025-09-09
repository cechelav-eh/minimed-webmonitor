from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import threading
import time
import datetime
import requests
import json
import signal
import sys
import logging as log
import os
import subprocess
import socket

# import carelink_client2_proxy - se importará dinámicamente para evitar ejecución automática
import carelink_client2

# Definir estados
STATUS_INIT = "STATUS_INIT"
STATUS_DO_LOGIN = "STATUS_DO_LOGIN" 
STATUS_LOGIN_OK = "STATUS_LOGIN_OK"
STATUS_NEED_TKN = "STATUS_NEED_TKN"

# Función eliminada - ahora usamos subprocess para el servidor proxy

app = Flask(__name__)
app.secret_key = 'minimed_secret_key_2024'  # Necesario para flash messages

# Default configuration parameters
DEFAULT_NTP_SERVER = "pool.ntp.org"
DEFAULT_TIME_ZONE  = "0"
DEFAULT_PROXY_PORT = "8081"

# API
API_URL = "carelink/nohistory"
API_GRAPH_URL = "carelink"
proxyaddr = "localhost"  # Replace with your Carelink Python Client IP address
proxyport = 8081

# Global variables
last_pump_data = {}
last_update_time = None
last_pump_graph_data = {}
last_update_graph_time = None
dst_delta = 0

# Variables globales para carelink proxy
g_status = STATUS_INIT
recentData = None
wait_for_params = True
TOKENFILE = "data/logindata.json"
UPDATE_INTERVAL = 300
RETRY_INTERVAL = 120

# Variable global para el proceso proxy
proxy_process = None

#################################################
# The signal handler for the TERM signal
#################################################
def on_sigterm(signum, frame):
   # TODO: cleanup (if any)
   log.debug("Exiting in sigterm")
   sys.exit()

#################################################
# Funciones para gestión del proceso proxy
#################################################
def is_proxy_running():
    """Verifica si el servidor proxy está ejecutándose en el puerto 8081"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 8081))
        sock.close()
        return result == 0
    except Exception:
        return False

def stop_proxy():
    """Detiene el proceso proxy si está ejecutándose"""
    global proxy_process
    
    try:
        # Intentar terminar el proceso si tenemos referencia a él
        if proxy_process and proxy_process.poll() is None:
            log.info("Terminando proceso proxy existente...")
            proxy_process.terminate()
            proxy_process.wait(timeout=10)
            log.info("Proceso proxy terminado exitosamente")
        
        # Verificar si hay otros procesos proxy ejecutándose
        if is_proxy_running():
            log.info("Intentando terminar proceso proxy por puerto...")
            # Buscar y terminar el proceso que está usando el puerto 8081
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and 'carelink_client2_proxy.py' in ' '.join(cmdline):
                        log.info(f"Terminando proceso proxy PID: {proc.info['pid']}")
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass
    except Exception as e:
        log.warning(f"Error al terminar proceso proxy: {e}")
    
    proxy_process = None

def start_proxy():
    """Inicia el servidor proxy"""
    global proxy_process
    
    try:
        log.info("Iniciando servidor proxy...")
        proxy_process = subprocess.Popen([
            'python3', 'carelink_client2_proxy.py'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Esperar a que se inicie
        for i in range(10):  # Intentar hasta 10 segundos
            time.sleep(1)
            if is_proxy_running():
                log.info("Servidor proxy iniciado correctamente")
                return True
        
        log.warning("El servidor proxy no pudo iniciarse en el tiempo esperado")
        return False
        
    except Exception as e:
        log.error(f"Error al iniciar servidor proxy: {e}")
        return False

def restart_proxy():
    """Reinicia el servidor proxy"""
    log.info("Reiniciando servidor proxy...")
    stop_proxy()
    time.sleep(2)  # Esperar un poco antes de reiniciar
    return start_proxy()

#################################################
# Función para ejecutar el cliente Carelink en segundo plano
#################################################
def carelink_client_thread():
    global g_status, recentData, wait_for_params
    
    # Note: signal handlers only work in main thread, skipping in daemon thread
    
    # Main process loop
    while True:
       # Init Carelink client
       client = carelink_client2.CareLinkClient(tokenFile=TOKENFILE)
       g_status = STATUS_DO_LOGIN
       
       # Login to Carelink server
       if client.init():
          g_status = STATUS_LOGIN_OK

          # Infinite loop requesting Carelink data periodically
          i = 0
          while True:
             i += 1
             log.debug("Starting download %d" % i)

             try:
                recentData = client.getRecentData()
                if recentData != None and client.getLastResponseCode() == 200:  # HTTPStatus.OK
                   log.debug("New data received")
                elif client.getLastResponseCode() == 403 or client.getLastResponseCode() == 401:  # HTTPStatus.FORBIDDEN or HTTPStatus.UNAUTHORIZED
                   # Authorization error occured
                   log.error("ERROR: failed to get data (Authotization error, response code %d)" % client.getLastResponseCode())
                   break
                else:
                   # Connection error occured
                   log.error("ERROR: failed to get data (Connection error, response code %d)" % client.getLastResponseCode())
                   time.sleep(60)
                   continue
             except Exception as e:
                log.error(e)
                recentData = None
                time.sleep(60)
                continue
                
             # Calculate time until next reading
             try:
                nextReading = int(recentData["lastConduitUpdateServerTime"]/1000) + UPDATE_INTERVAL
                tmoSeconds  = int(nextReading - time.time())
                log.debug("Next reading at {0}, {1} seconds from now\n".format(nextReading,tmoSeconds))
                if tmoSeconds < 0:
                   tmoSeconds = RETRY_INTERVAL
             except KeyError:
                tmoSeconds = RETRY_INTERVAL

             log.debug("Waiting " + str(tmoSeconds) + " seconds before next download")
             time.sleep(tmoSeconds+10)

       # Wait for new token
       log.info(STATUS_NEED_TKN)
       g_status = STATUS_NEED_TKN
       wait_for_params = True
       while wait_for_params:
          time.sleep(0.1)

def get_time_ago(timestamp):
    if not timestamp:
        return "-- min ago"
    now = time.time()
    diff = now - time.mktime(timestamp)
    minutes = int(diff / 60)
    if minutes < 1:
        return "Just now"
    elif minutes == 1:
        return "1 min ago"
    elif minutes < 60:
        return f"{minutes} min ago"
    else:
        return "Over 1 hour ago"

def get_pump_data():
    global last_pump_data, last_update_time, last_pump_graph_data, last_update_graph_time
    while True:
        try:
            proxy_url = f"http://{proxyaddr}:{proxyport}/{API_URL}"
            response = requests.get(proxy_url)
            if response.status_code == 200 and response.json():
                last_pump_data = response.json()
                last_update_time = time.localtime(int(last_pump_data["lastConduitUpdateServerDateTime"]/1000))
        except Exception as e:
            print(f"Error fetching pump data: {e}")
        try:
            proxy_graph_url = f"http://{proxyaddr}:{proxyport}/{API_GRAPH_URL}"
            response = requests.get(proxy_graph_url)
            if response.status_code == 200 and response.json():
                last_pump_graph_data = response.json()
                last_update_graph_time = time.localtime(int(last_pump_graph_data["patientData"]["lastConduitUpdateServerDateTime"]/1000))
        except Exception as e:
            print(f"Error fetching pump graph data: {e}")
        time.sleep(60)  # Update every 60 seconds

def format_pump_data():
    if not last_pump_data:
        return {
            "glucose": "--",
            "battery": "unk",
            "reservoir": "unk",
            "active_insulin": "-- U",
            "sensor_connection": False,
            "last_update": "--:--",
            "time_ago": "-- min ago",
            "sensor_age": "",
            "calibration_status": "unknown",
            "trend": "none",
            "banner_state": None
        }

    data = last_pump_data
    have_data = data["conduitInRange"] and data["conduitMedicalDeviceInRange"]

    # print("data -> ", data) 
    
    formatted_data = {
        "glucose": str(data["lastSG"]["sg"]) if data["lastSG"]["sg"] > 0 else "--",
        "battery": str(data["pumpBatteryLevelPercent"]) if have_data else "unk",
        "reservoir": str(data["reservoirRemainingUnits"]) if have_data else "unk",
        "active_insulin": f"{round(data['activeInsulin']['amount'], 1)} U" if have_data else "-- U",
        "sensor_connection": data["conduitSensorInRange"],
        "last_update": time.strftime("%H:%M", last_update_time) if last_update_time else "--:--",
        "time_ago": get_time_ago(last_update_time),
        "sensor_age": str(round(data["sensorDurationHours"]/24)) if data["sensorDurationHours"] != 255 and have_data else "",
        "calibration_status": data["calibStatus"],
        "trend": data["lastSGTrend"].lower() if "lastSGTrend" in data else "none",
        "time_to_calib": data["timeToNextCalibHours"] if "timeToNextCalibHours" in data else 255,
        "sensor_status": data["sensorState"],
        "banner_state": data["pumpBannerState"][0]["type"].lower() if "pumpBannerState" in data and data["pumpBannerState"] else None
    }
    return formatted_data

def format_pump_graph_data():
    if not last_pump_graph_data:
        return {
            "glucose_history": [],
            "time_range": {
                "below": 0,
                "in_range": 0,
                "above": 0
            },
            "average_sg": 0,
            "markers": []
        }

    data = last_pump_graph_data["patientData"]
    # print("Datos completos del paciente:", json.dumps(data, indent=2))
    
    # Procesar datos del gráfico
    glucose_history = []
    if "sgs" in data:
        # Ordenar los datos por timestamp
        sorted_sgs = sorted(data["sgs"], key=lambda x: x["timestamp"])
        
        for sg in sorted_sgs:
            if sg["sg"] > 0:  # Solo valores válidos
                try:
                    timestamp = datetime.datetime.strptime(sg["timestamp"], "%Y-%m-%dT%H:%M:%S")
                    time_str = timestamp.strftime("%H:%M")
                    glucose_history.append({
                        "time": time_str,
                        "value": sg["sg"]
                    })
                except (ValueError, KeyError) as e:
                    print(f"Error processing timestamp: {e}")
                    continue
    
    # Procesar marcadores
    markers = []
    if "markers" in data:
        # print("Marcadores encontrados:", json.dumps(data["markers"], indent=2))
        for marker in data["markers"]:
            try:
                timestamp = datetime.datetime.strptime(marker["timestamp"], "%Y-%m-%dT%H:%M:%S")
                time_str = timestamp.strftime("%H:%M")
                marker_type = marker.get("type", "unknown")
                
                marker_data = {
                    "time": time_str,
                    "type": marker_type
                }
                
                # Procesar específicamente los marcadores AUTO_BASAL_DELIVERY
                if marker_type == "AUTO_BASAL_DELIVERY":
                    marker_data.update({
                        "value": 250,  # Valor fijo en la parte superior
                        "color": "#9370DB",  # Color lila
                        "radius": float(marker.get("data", {}).get("dataValues", {}).get("bolusAmount","4")) * 80,  # Tamaño basado en bolusAmount convertido a float
                        "borderWidth": 0  # Sin borde
                    })
                elif marker_type == "CALIBRATION":
                    marker_data.update({
                        "value": float(marker.get("data", {}).get("dataValues", {}).get("unitValue", "0")),  # Usar el valor de bolusAmount
                        "color": "#FF0000",  # Color rojo
                        "radius": 4,  # Radio fijo
                        "borderWidth": 0  # Sin borde
                    })
                elif marker_type == "INSULIN" and marker.get("data", {}).get("dataValues", {}).get("activationType", "0") == "AUTOCORRECTION":
                    print("marker_data insulin 1 -> ", marker.get("data", {}).get("dataValues", {}).get("deliveredFastAmount","4"))
                    marker_data.update({
                        "value": 240,  # Usar el valor de bolusAmount
                        "color": "#0000FF",  # Color azul
                        "radius": float(marker.get("data", {}).get("dataValues", {}).get("deliveredFastAmount","4")) * 40,  # Tamaño basado en bolusAmount convertido a float
                        "borderWidth": 0  # Sin borde
                    })
                elif marker_type == "INSULIN" and marker.get("data", {}).get("dataValues", {}).get("activationType", "0") == "RECOMMENDED":
                    print("marker_data insulin 2 -> ", marker.get("data", {}).get("dataValues", {}).get("deliveredFastAmount","4"))
                    marker_data.update({
                        "value": 250,  # Usar el valor de bolusAmount
                        "color": "#00FF00",  # Color verde
                        "radius": float(marker.get("data", {}).get("dataValues", {}).get("deliveredFastAmount","4")) * 6,  # Tamaño basado en bolusAmount convertido a float
                        # "radius": 3,
                        "borderWidth": 0,  # Sin borde
                        # "pointStyle": "star"  # Usar asterisco en lugar de círculo
                    })
                elif marker_type == "MEAL":
                    print("marker_data MEAL -> ", marker.get("data", {}).get("dataValues", {}).get("amount","-"), " -> ", marker.get("timestamp", "---"))
                    marker_data.update({
                        "value": 40,  # Usar el valor de bolusAmount
                        "color": "#FFFF00",  # Color amarillo
                        "radius": float(marker.get("data", {}).get("dataValues", {}).get("amount","4")) * 0.4,  # Tamaño basado en bolusAmount convertido a float
                        "borderWidth": 0,  # Sin borde
                    })
                else:
                    # Configuración por defecto para otros tipos de marcadores
                    marker_data.update({
                        "value": marker.get("value", 0),
                        "color": "#FF0000",
                        "radius": 4
                    })
                
                markers.append(marker_data)
            except (ValueError, KeyError) as e:
                print(f"Error processing marker: {e}")
                continue
    else:
        print("No se encontraron marcadores en los datos")
    
    # Obtener estadísticas y marcadores
    formatted_data = {
        "glucose_history": glucose_history,
        "time_range": {
            "below": data.get("belowHypoLimit", 0),
            "in_range": data.get("timeInRange", 0),
            "above": data.get("aboveHyperLimit", 0)
        },
        "average_sg": data.get("averageSG", 0),
        "markers": markers
    }
    
    # print("Datos formateados:", json.dumps(formatted_data, indent=2))
    return formatted_data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/pump-data')
def get_current_pump_data():
    return jsonify(format_pump_data())

@app.route('/api/pump-graph-data')
def get_current_pump_graph_data():
    return jsonify(format_pump_graph_data())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            # Obtener el contenido del formulario
            logindata_content = request.form.get('logindata', '').strip()
            
            # Validar que sea JSON válido
            try:
                json_data = json.loads(logindata_content)
            except json.JSONDecodeError as e:
                flash(f'Error: El contenido no es un JSON válido. {str(e)}', 'error')
                return render_template('login.html', 
                                     logindata_content=logindata_content,
                                     message=f'Error: El contenido no es un JSON válido. {str(e)}',
                                     message_type='error')
            
            # Crear el directorio data si no existe
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            # Ruta completa al archivo logindata.json
            logindata_path = os.path.join(data_dir, 'logindata.json')
            
            # Hacer backup del archivo existente si existe
            if os.path.exists(logindata_path):
                backup_path = logindata_path + '.backup'
                with open(logindata_path, 'r') as original:
                    with open(backup_path, 'w') as backup:
                        backup.write(original.read())
            
            # Guardar el nuevo contenido
            with open(logindata_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)
            
            # Reiniciar el servidor proxy para que use los nuevos datos
            log.info("Reiniciando servidor proxy debido a cambios en logindata.json...")
            restart_success = restart_proxy()
            
            if restart_success:
                message = 'Los datos de login se han guardado correctamente y el servidor proxy se ha reiniciado.'
                log.info("Servidor proxy reiniciado exitosamente")
            else:
                message = 'Los datos de login se han guardado correctamente, pero hubo un problema al reiniciar el servidor proxy.'
                log.warning("Error al reiniciar el servidor proxy")
            
            flash(message, 'success')
            return render_template('login.html', 
                                 logindata_content=json.dumps(json_data, indent=4, ensure_ascii=False),
                                 message=message,
                                 message_type='success')
            
        except Exception as e:
            log.error(f"Error al guardar logindata.json: {e}")
            flash(f'Error al guardar el archivo: {str(e)}', 'error')
            return render_template('login.html', 
                                 logindata_content=request.form.get('logindata', ''),
                                 message=f'Error al guardar el archivo: {str(e)}',
                                 message_type='error')
    
    # Método GET - mostrar el formulario
    try:
        # Leer el archivo actual
        logindata_path = os.path.join(os.path.dirname(__file__), 'data', 'logindata.json')
        if os.path.exists(logindata_path):
            with open(logindata_path, 'r', encoding='utf-8') as f:
                logindata_content = json.dumps(json.load(f), indent=4, ensure_ascii=False)
        else:
            # Contenido por defecto si el archivo no existe
            logindata_content = json.dumps({
                "access_token": "",
                "refresh_token": "",
                "scope": "profile openid roles country msso msso_register msso_client_register",
                "resource": [
                    "https://mdtsts-ocl.medtronic.com/*"
                ],
                "client_id": "",
                "client_secret": "",
                "mag-identifier": ""
            }, indent=4, ensure_ascii=False)
    except Exception as e:
        log.error(f"Error al leer logindata.json: {e}")
        logindata_content = "{}"
    
    return render_template('login.html', logindata_content=logindata_content)

if __name__ == '__main__':
    # Configurar logging
    FORMAT = '[%(asctime)s:%(levelname)s] %(message)s'
    log.basicConfig(format=FORMAT, datefmt='%Y-%m-%d %H:%M:%S', level=log.INFO)
    
    log.info("Starting MiniMed Monitor Web with Carelink Client Proxy integration")
    
    # Check if proxy server is already running
    if is_proxy_running():
        log.info("Servidor proxy ya está ejecutándose en puerto 8081")
    else:
        log.info("No se detectó servidor proxy. Iniciando proceso independiente...")
        if not start_proxy():
            log.info("Continuando sin servidor proxy...")
    
    # Start the Carelink client thread
    log.info("Iniciando cliente Carelink...")
    carelink_thread = threading.Thread(target=carelink_client_thread, daemon=True)
    carelink_thread.start()
    
    # Start the background thread for data collection
    log.info("Iniciando recolección de datos...")
    data_thread = threading.Thread(target=get_pump_data, daemon=True)
    data_thread.start()
    
    # Run the Flask app
    log.info("Iniciando servidor Flask en puerto 5001...")
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False) 
    