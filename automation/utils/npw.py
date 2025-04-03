import pywt
import numpy as np
from datetime import datetime

class Wavelet:
    
    def __init__(
        self, 
        pipeline_length:float, 
        speed_of_sound:float, 
        family:str="db2"
        ):

        # Constant definitions
        self.C = speed_of_sound                             # Sound speed constant, (m/s)
        self.L = pipeline_length                            # Pipeline length (m)
        self.FAMILY = family
        self.threshold_iqr = 95

    def set_speed_of_sound(self, value:float)->None:
        r"""
        Documentation here
        """
        self.C = value

    def get_speed_of_sound(self)->float:
        r"""
        Documentation here
        """
        return self.C

    def set_threshold_iqr(self, value:float):
        r"""
        Documentation here
        """
        if value < 0 or value > 100:
            raise ValueError("Threshold IQR must be between 0 and 100")
        self.threshold_iqr = value

    def get_threshold_iqr(self)->float:
        r"""
        Documentation here
        """
        return self.threshold_iqr

    def set_pipeline_length(self, value:float)->None:
        r"""
        Documentation here
        """
        self.L = value
    
    def get_pipeline_length(self)->float:
        r"""
        Documentation here
        """
        return self.L
    
    def set_family(self, value:str)->None:
        r"""
        Set Wavelet Family
        ['bior1.1', 'bior1.3', 'bior1.5', 'bior2.2', 'bior2.4', 'bior2.6', 'bior2.8', 'bior3.1', 'bior3.3', 
        'bior3.5', 'bior3.7', 'bior3.9', 'bior4.4', 'bior5.5', 'bior6.8', 'cgau1', 'cgau2', 'cgau3', 'cgau4', 
        'cgau5', 'cgau6', 'cgau7', 'cgau8', 'cmor', 'coif1', 'coif2', 'coif3', 'coif4', 'coif5', 'coif6', 
        'coif7', 'coif8', 'coif9', 'coif10', 'coif11', 'coif12', 'coif13', 'coif14', 'coif15', 'coif16', 
        'coif17', 'db1', 'db2', 'db3', 'db4', 'db5', 'db6', 'db7', 'db8', 'db9', 'db10', 'db11', 'db12', 
        'db13', 'db14', 'db15', 'db16', 'db17', 'db18', 'db19', 'db20', 'db21', 'db22', 'db23', 'db24', 
        'db25', 'db26', 'db27', 'db28', 'db29', 'db30', 'db31', 'db32', 'db33', 'db34', 'db35', 'db36', 
        'db37', 'db38', 'dmey', 'fbsp', 'gaus1', 'gaus2', 'gaus3', 'gaus4', 'gaus5', 'gaus6', 'gaus7', 
        'gaus8', 'haar', 'mexh', 'morl', 'rbio1.1', 'rbio1.3', 'rbio1.5', 'rbio2.2', 'rbio2.4', 'rbio2.6', 
        'rbio2.8', 'rbio3.1', 'rbio3.3', 'rbio3.5', 'rbio3.7', 'rbio3.9', 'rbio4.4', 'rbio5.5', 'rbio6.8', 
        'shan', 'sym2', 'sym3', 'sym4', 'sym5', 'sym6', 'sym7', 'sym8', 'sym9', 'sym10', 'sym11', 'sym12', 
        'sym13', 'sym14', 'sym15', 'sym16', 'sym17', 'sym18', 'sym19', 'sym20']
        """
        self.FAMILY = value

    def get_family(self)->str:
        r"""
        Get Wavelet Family
        """
        return self.FAMILY

    def detect_anomaly(self, data):
        r"""
        Documentation here
        """
        cA, cD = self.decomposition(data)
        lower_anomaly, probabilities = self.find_singular_points(cD)
        return lower_anomaly, probabilities
    
    def find_singular_points(self, cD):
        r"""
        Find singular points in the wavelet detail coefficients.
        """
        x = np.arange(len(cD))
        slope, _ = np.polyfit(x, cD, 1)

        # print(f"Slope: {slope}")
        threshold = np.percentile(cD, 100 - self.threshold_iqr)
        singular_points = np.where(cD < threshold)[0]
    
        # Calcular probabilidad basada en la magnitud de la caída
        if len(singular_points) > 0 and abs(slope) > 0.5:
            magnitudes = np.abs(cD[singular_points] - threshold)
            # Normalizar magnitudes a probabilidades entre 0 y 1
            probabilities = magnitudes / np.max(magnitudes)
            
            return singular_points, probabilities
        return [], []
    
    
    def map_to_original_position(self, anomaly, original_length, cD_length):
        r"""
        Map the indices of anomalies to the positions in the original data.
        """
        # Assuming level=1 for simplicity, adjust if using different levels
        original_position = None
        if anomaly:

            scaling_factor = anomaly / cD_length
            original_position = (scaling_factor * original_length).astype(int)

        return original_position

    def decomposition(self, data):
        r"""
        Documentation here
        """
        coeffs = pywt.wavedec(data, self.FAMILY, level=1)
        cA = coeffs[0]
        cD = coeffs[1]
        return cA, cD

    def wavedec(self, s, wavelet, mode='symmetric', level=None, axis=-1):
        r"""
        Multilevel 1D Discrete Wavelet Transform of signal $s$
        
        **Parameters**

        * **s:** (array_like) Input data
        * **wavelet:** (Wavelet object or name string) Wavelet to use
        * **mode:** (str) Signal extension mode.
        * **level:** (int) Decomposition level (must be >= 0). If level is None (default)
        then it will be calculated using the `dwt_max_level` function.
        * **axis:** (int) Axis over which to compute the DWT. If not given, the last axis 
        is used.

        **Returns**

        * **[cA_n, cD_n, cD_n-1, ..., cD2, cD1]:** (list) Ordered list of coefficients arrays where
        $n$ denotes the level of decomposition. The first element `(cA_n)` of the result is approximation
        coefficients array and the following elements `[cD_n - cD1]` are details coefficients arrays.

        ## Snippet code

        ```python
        >>> coeffs = wavedec([1,2,3,4,5,6,7,8], 'db1', level=2)
        >>> cA2, cD2, cD1 = coeffs
        >>> cD1
        array([-0.70710678, -0.70710678, -0.70710678, -0.70710678])
        >>> cD2
        array([-2., -2.])
        >>> cA2
        array([ 5., 13.])
        >>> s = np.array([[1,1], [2,2], [3,3], [4,4], [5, 5], [6, 6], [7, 7], [8, 8]])
        >>> coeffs = wavedec(s, 'db1', level=2, axis=0)
        >>> cA2, cD2, cD1 = coeffs
        >>> cD1
        array([[-0.70710678, -0.70710678],
               [-0.70710678, -0.70710678],
               [-0.70710678, -0.70710678],
               [-0.70710678, -0.70710678]])
        >>> cD2
        array([[-2., -2.],
               [-2., -2.]])
        >>> cA2
        array([[ 5.,  5.],
               [13., 13.]])

        ```
        """
        coeffs = pywt.wavedec(s, wavelet, mode=mode, level=level, axis=axis)

        return coeffs
    
    def time_flight(self, dt):
        """
        x = L/2 ± (C * dt)/2
        
        Donde:
        x: distancia desde el sensor de entrada hasta la fuga
        L: longitud total de la tubería
        C: velocidad del sonido en el fluido
        dt: tiempo entre detecciones (t2 - t1)
        El signo ± depende de qué sensor detectó primero la onda
        """
        if dt > 0:  # La onda llegó primero al sensor de entrada
            location = (self.L - self.C * abs(dt)) / 2
        else:  # La onda llegó primero al sensor de salida
            location = (self.L + self.C * abs(dt)) / 2

        return location

    def compute_mode(self, arr):
        unique_values, counts = np.unique(arr, return_counts=True)
        max_count = np.max(counts)
        modes = unique_values[counts == max_count]
        return modes


class NPW:
    r"""
    Documentation here
    """

    def __init__(self, pipeline_length: int, speed_of_sound: float=1180, family: str="db2"):
        
        self.wavelet = Wavelet(pipeline_length=pipeline_length, speed_of_sound=speed_of_sound, family=family)

    def detect_anomaly(self, *pressure_signals:list[np.ndarray]):
        r"""
        Documentation here
        """
        anomalies = list()
        probabilities = list()
        for signal in pressure_signals:
            anomaly, probability = self.wavelet.detect_anomaly(signal)
            
            if len(anomaly) >= 1:
                anomalies.append(True)
                probabilities.append(probability)
        return anomalies, probabilities
    
    def diagnose_anomaly(
            self, 
            inlet_pressure:list[float], 
            outlet_pressure:list[float],
            inlet_timestamps:list[datetime], 
            outlet_timestamps:list[datetime]
        ):
        r"""
        Documentation here
        """

        if not isinstance(inlet_timestamps, list) or not all(isinstance(x, datetime) for x in inlet_timestamps):
            
            raise ValueError("inlet_timestamps must be a list of datetime objects when diagnosing anomalies on NPW Algorithm")
        
        if not isinstance(outlet_timestamps, list) or not all(isinstance(x, datetime) for x in outlet_timestamps):
            
            raise ValueError("outlet_timestamps must be a list of datetime objects when diagnosing anomalies on NPW Algorithm")
        
        if not isinstance(inlet_pressure, list) or not all(isinstance(x, float) for x in inlet_pressure):
            
            raise ValueError("inlet_pressure must be a list of float objects when diagnosing anomalies on NPW Algorithm")
        
        if not isinstance(outlet_pressure, list) or not all(isinstance(x, float) for x in outlet_pressure):
            
            raise ValueError("outlet_pressure must be a list of float objects when diagnosing anomalies on NPW Algorithm")

        inlet_timestamp = None
        outlet_timestamp = None
        # Inlet Pressure
        _, cD = self.wavelet.decomposition(inlet_pressure)
        anomalies, _ = self.wavelet.find_singular_points(cD)
        if len(anomalies) >= 1:
            anomaly = anomalies[0]
            pos = self.wavelet.map_to_original_position(anomaly=anomaly, original_length=len(inlet_pressure), cD_length=len(cD))

            if pos:
                
                inlet_timestamp = inlet_timestamps[pos]

        # Outlet Pressure
        _, cD = self.wavelet.decomposition(outlet_pressure)
        anomalies, _ = self.wavelet.find_singular_points(cD)
        if len(anomalies) >= 1:
            anomaly = anomalies[0]
            pos = self.wavelet.map_to_original_position(anomaly=anomaly, original_length=len(outlet_pressure), cD_length=len(cD))
            if pos:
                outlet_timestamp = outlet_timestamps[pos]

        if inlet_timestamp and outlet_timestamp:
            
            dt = outlet_timestamp - inlet_timestamp
            location = self.wavelet.time_flight(dt=dt.total_seconds())
            if location < 0:
                
                return 0
            
            if location > self.wavelet.L:
                
                return self.wavelet.L
            
            return location
