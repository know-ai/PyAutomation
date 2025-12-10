from ..utils.decorators import decorator
import numpy as np

class KalmanFilter:
    r"""
    Implements a standard Kalman Filter for single-variable estimation.

    The Kalman Filter estimates the state of a system from a series of incomplete and noisy measurements.
    """
    def __init__(
            self, 
            x, 
            A:np.array=np.array([[1]]), 
            B:np.array=np.array([[0]]), 
            H:np.array=np.array([[1]]), 
            P:np.array=np.array([[1]]), 
            Q:np.array=np.array([[1e-5]]), 
            R:np.array=np.array([[0.5]])
            ):
        r"""
        Initializes the Kalman Filter.

        **Parameters:**

        * **x**: Initial state estimate.
        * **A**: State transition model.
        * **B**: Control input model.
        * **H**: Observation model.
        * **P**: Estimate covariance.
        * **Q**: Process noise covariance.
        * **R**: Measurement noise covariance.
        """
        self.A = A
        self.B = B
        self.H = H
        self.Q = Q
        self.R = R
        self.P = P
        self.x = x
        self.previous_innov = None                      # Para guardar la innovación anterior

    def predict(self, u=0):
        r"""
        Predicts the next state of the system.

        **Parameters:**

        * **u**: Control input vector (optional).
        """
        self.x = np.dot(self.A, self.x) + np.dot(self.B, u)
        self.P = np.dot(np.dot(self.A, self.P), self.A.T) + self.Q

    def update(self, z, threshold:float=100, r_value:float=0.5):
        r"""
        Updates the state estimate with a new measurement.

        Includes adaptive logic to adjust measurement noise (R) based on innovation variance.

        **Parameters:**

        * **z**: Measurement value.
        * **threshold** (float): Threshold for innovation variance to adjust R.
        * **r_value** (float): Default R value.
        """
        
        innov = z - np.dot(self.H, self.x)  # Innovación
        if self.previous_innov is not None:
            innov_var = np.std([self.previous_innov, innov])  # Varianza de las innovaciones
            self.R = 0.0 if innov_var > threshold else r_value  # Ajustar R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(np.dot(np.dot(self.H, self.P), self.H.T) + self.R))
        self.x = self.x + np.dot(K, innov)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)
        self.previous_innov = innov


class GaussianFilter:
    r"""
    A wrapper for the Kalman Filter designed for simple scalar value filtering.
    
    It maintains the filter state between calls.
    """

    def __init__(self):

        self.kf = None

    def __call__(self, value:float, threshold:float=100, r_value:float=0.5):
        r"""
        Applies the filter to a new value.

        **Parameters:**

        * **value** (float): The noisy input value.
        * **threshold** (float): Threshold for adaptive filtering.
        * **r_value** (float): Measurement noise parameter.

        **Returns:**

        * **float**: The filtered value.
        """
        
        if self.kf is None:

            self.kf = KalmanFilter(value)

        self.kf.predict()
        self.kf.update(value, threshold=threshold, r_value=r_value)
        filtered_value = self.kf.x[0][0]
        return filtered_value
