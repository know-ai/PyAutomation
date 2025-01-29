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
            R:np.array=np.array([[0.05]]), 
            threshold_var:np.array=np.array([[100]])
            ):
        self.A = A
        self.B = B
        self.H = H
        self.Q = Q
        self.__R = R
        self.R = R
        self.P = P
        self.x = x
        self.threshold_var = threshold_var              # Varianza de variables en unidades de ingenieria
        self.previous_innov = None                      # Para guardar la innovación anterior

    def predict(self, u=0):
        self.x = np.dot(self.A, self.x) + np.dot(self.B, u)
        self.P = np.dot(np.dot(self.A, self.P), self.A.T) + self.Q

    def update(self, z):
        innov = z - np.dot(self.H, self.x)  # Innovación
        if self.previous_innov is not None:
            innov_var = np.var([self.previous_innov, innov])  # Varianza de las innovaciones
            self.R = 0.0 if innov_var > self.threshold_var else self.__R  # Ajustar R

        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(np.dot(np.dot(self.H, self.P), self.H.T) + self.R))
        self.x = self.x + np.dot(K, innov)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)
        self.previous_innov = innov


class GaussianFilter:

    def __init__(self):

        self.kf = None

    def __call__(self, value:float):
        
        if self.kf is None:

            self.kf = KalmanFilter(value)

        self.kf.predict()
        self.kf.update(value)
        return self.kf.x[0][0]


__filter = GaussianFilter()   


@decorator
def gaussian_noise_filter(func, args, kwargs):
    r"""
    Documentation here
    """
    cvt = args[0]
    tag_id = kwargs["id"]
    value = kwargs["value"]
    tag = cvt.get_tag(id=tag_id)
    if tag.gaussian_filter:
        
        kwargs["value"] = __filter(value)

        return func(*args, **kwargs)
    
    return func(*args, **kwargs)