import unittest, os, csv
from datetime import datetime, timedelta
from ..utils.npw import NPW as NPWAlgorithm
import numpy as np

threshold_iqr = 70
# Agregar ruido gaussiano (0.1% de error)
noise_factor = 0.001  # 0.1%
csv_path = os.path.join(os.path.dirname(__file__), 'SA_L1L_D_WL_SS_V2_01.csv')
# Leer el CSV usando la biblioteca csv
with open(csv_path, 'r') as file:
    csv_reader = csv.DictReader(file)
    rows = list(csv_reader)  # Convertir el reader a lista para poder usar índices

# Crear instancia de NPWAlgorithm
npw = NPWAlgorithm(pipeline_length=2070, speed_of_sound=1380, family="db2")
npw.wavelet.set_threshold_iqr(threshold_iqr)

class TestNPW(unittest.TestCase):

    def setUp(self) -> None:
        
        return super().setUp()

    def tearDown(self) -> None:
        
        return super().tearDown()
    
    def test_npw_algorithm_detection_no_leak_outlet_pressure(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[9:49]:
            pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [])

    def test_npw_algorithm_detection_with_leak_outlet_pressure(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[1189:1229]:
            pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [True])

    def test_npw_algorithm_detection_no_leak_inlet_pressure(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[9:49]:
            pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [])

    def test_npw_algorithm_detection_with_leak_inlet_pressure(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[1189:1229]:
            pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [True])

    def test_npw_algorithm_detection_no_leak_inlet_outlet_pressure(self):
        # Inicializar listas para almacenar los datos
        inlet_pressure = []
        outlet_pressure = []
        for row in rows[9:49]:
            inlet_pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
            outlet_pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(inlet_pressure, outlet_pressure)
        self.assertListEqual(anomalies, [])

    def test_npw_algorithm_detection_with_leak_inlet_outlet_pressure(self):
        # Inicializar listas para almacenar los datos
        inlet_pressure = []
        outlet_pressure = []
        for row in rows[1189:1229]:
            inlet_pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
            outlet_pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(inlet_pressure, outlet_pressure)
        self.assertListEqual(anomalies, [True, True])

    def test_npw_algorithm_diagnose_anomaly(self):
        # Inicializar listas para almacenar los datos
        inlet_pressure = []
        outlet_pressure = []
        location = None
        for row in rows[1189:1229]:
            inlet_pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
            outlet_pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        # Crear timestamps para cada valor
        base_time = datetime.now()
        inlet_timestamps = [base_time + timedelta(seconds=i*0.5) for i in range(40)]
        outlet_timestamps = [base_time + timedelta(seconds=i*0.5) for i in range(40)]
        # Ejecutar diagnóstico
        anomalies, _ = npw.detect_anomaly(inlet_pressure, outlet_pressure)
        if anomalies:
            location = npw.diagnose_anomaly(inlet_pressure, outlet_pressure, inlet_timestamps, outlet_timestamps)  

        self.assertEqual(location, 345)

    # PRUEBAS CON RUIDO
    def test_npw_algorithm_detection_no_leak_outlet_pressure_with_noise(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[9:49]:
            pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        
        pressure = [p + np.random.normal(0, p * noise_factor) for p in pressure]
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [])

    def test_npw_algorithm_detection_with_leak_outlet_pressure_with_noise(self):
        # Inicializar listas para almacenar los datos
        pressure = []
        for row in rows[1189:1229]:
            pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
        
        pressure = [p + np.random.normal(0, p * noise_factor) for p in pressure]
        # Ejecutar detección de anomalías
        anomalies, _ = npw.detect_anomaly(pressure)
        self.assertListEqual(anomalies, [True])


    # def test_npw_algorithm_diagnose_anomaly_with_noise(self):
    #     # Inicializar listas para almacenar los datos
    #     inlet_pressure = []
    #     outlet_pressure = []
    #     location = None
        
    #     # Obtener datos base
    #     for row in rows[1189:1229]:
    #         inlet_pressure.append(float(row['FIRST_TRANSMITTER_PRESSURE']))
    #         outlet_pressure.append(float(row['LAST_TRANSMITTER_PRESSURE']))
            
    #     inlet_pressure = [p + np.random.normal(0, p * noise_factor) for p in inlet_pressure]
    #     outlet_pressure = [p + np.random.normal(0, p * noise_factor) for p in outlet_pressure]
        
    #     # Crear timestamps para cada valor
    #     base_time = datetime.now()
    #     inlet_timestamps = [base_time + timedelta(seconds=i*0.5) for i in range(40)]
    #     outlet_timestamps = [base_time + timedelta(seconds=i*0.5) for i in range(40)]
        
    #     # Ejecutar diagnóstico
    #     anomalies, _ = npw.detect_anomaly(inlet_pressure, outlet_pressure)
    #     if anomalies:
    #         location = npw.diagnose_anomaly(inlet_pressure, outlet_pressure, inlet_timestamps, outlet_timestamps)
            
    #     # Verificar que la ubicación esté dentro de un rango aceptable (por ejemplo, ±5% de la ubicación real)
    #     expected_location = 345  # ubicación real
    #     tolerance = expected_location * 0.05  # 5% de tolerancia
    #     self.assertGreaterEqual(location, expected_location - tolerance)
    #     self.assertLessEqual(location, expected_location + tolerance)