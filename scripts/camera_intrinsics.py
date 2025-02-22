import numpy as np
import os
import yaml

class CameraIntrinsics:
    def __init__(self, \
        config_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "homography", "camera_config.yaml")):
        # Load the configuration from the YAML file
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)
            self.CAMERA_INTRINSICS = config["camera_intrinsics"]
            # self.CAMERA_IMU_TRANSFORM = config["camera_imu_transform"]

    def get_camera_calibration_matrix(self):
        """
        Get camera intrinsics and its inverse as a tensors.
        Returns:
            K: Camera intrinsic matrix.
            K_inv: Inverse of the camera intrinsic matrix.
        """

        fx = self.CAMERA_INTRINSICS["fx"]
        fy = self.CAMERA_INTRINSICS["fy"]
        cx = self.CAMERA_INTRINSICS["cx"]
        cy = self.CAMERA_INTRINSICS["cy"]

        K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float32)
        K_inv = np.linalg.inv(K)
        return K, K_inv