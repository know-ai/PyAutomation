from ..utils.decorators import decorator
import numpy as np

class KalmanFilter:
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
        self.A = A
        self.B = B
        self.H = H
        self.Q = Q
        self.R = R
        self.P = P
        self.x = x
        self.previous_innov = None                      # Para guardar la innovación anterior

    def predict(self, u=0):
        self.x = np.dot(self.A, self.x) + np.dot(self.B, u)
        self.P = np.dot(np.dot(self.A, self.P), self.A.T) + self.Q

    def update(self, z, threshold:float=100, r_value:float=0.5):
        
        innov = z - np.dot(self.H, self.x)  # Innovación
        if self.previous_innov is not None:
            innov_var = np.std([self.previous_innov, innov])  # Varianza de las innovaciones
            self.R = 0.0 if innov_var > threshold else r_value  # Ajustar R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(np.dot(np.dot(self.H, self.P), self.H.T) + self.R))
        self.x = self.x + np.dot(K, innov)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)
        self.previous_innov = innov


class GaussianFilter:

    def __init__(self):

        self.kf = None

    def __call__(self, value:float, threshold:float=100, r_value:float=0.5):
        
        if self.kf is None:

            self.kf = KalmanFilter(value)

        self.kf.predict()
        self.kf.update(value, threshold=threshold, r_value=r_value)
        filtered_value = self.kf.x[0][0]
        return filtered_value
