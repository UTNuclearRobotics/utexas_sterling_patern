"""
TR-98 Zhang "A flexible technique for.."
H - Homography
Hx = x'
Where x is in frame 1, and x' is the point in frame 2, or the homography point.
Often x is expressed as a "model point" for a frontal-parallel chessboard
x' is as imaged in a real image

How do I compute a homography?
Direct Linear Transformation -> DLT

[
H1 H2 H3
H4 H5 H6
H7 H8 H9
] *
[
X
Y
W
] =
[
H1 * X + H2 * X + H3 * X,
..Y
..W
]

cv.getPerspectiveTransform does all of this for us

Explicit representation of a calibrated homography

Camera Calibration
Intrinsic Parameters <-- Unique to the camera
Extrinsic Parameters <-- Position and orientation of the camera (actually, transformation about the camera)

Camera Intrinsic Matrix
K = [
    fx gamma u0
    0   fy   v0
    0   0   1
]

You can assume:
fx = fy
(u0, v0) is the center of the image
gamma = 0

SO, you really only need focal length

Camera Extrinsic Matrix <-- Projective, taking a 3D point down to 2D homogeneous coordinates
[
R1 R2 R3 Tx
R1 R2 R3 Ty
R1 R2 R3 Tz
]           ^- T

Rigid Transform about the camera
[
R R R Tx
R R R Ty
R R R Tz
0 0 0 1
]

Let's suppose that I'm projecting a 3D point into 2D

X = [X, Y, Z, W] = (X/W, Y/W, Z/W)
x = [X, Y, W] = (X/W, Y/W)

<X, Y, W> ~= 2 * <X, Y, W> = We don't know W, but Z is a valid W
<X, Y, 1> ~= <2X, 2Y, 2>
<X/Z, Y/Z>

Ideal Projection <-- Not subject to camera intrinsics
R R R Tx
R R R Ty
R R R Tz
]
We took Z from 3D we made it W for 2D (and dropped the 3D W)

Ideal Projection from a Rigid Transformation <-- Is the camera extrinsic matrix

Calibrated Homography
H_calibrated = K * [R R T]

H <-- Computed from a chessboard
H^-1 * H = [R1 R2 T]
Rigid Transform =
[R1 R2 R1xR2 T]

So, if we want to move the chessboard around with the vehicle.

Get

Rigid transform in frame i
Rigid transform from IMU data for i+1..n (up to 10, but not if the homography drifts off of the camera)

Formula becomes
RT_i <-- Homography to first frame, which just stays as computed from the initial homography chessboard
BEVi = from chessboard
BEVvideo_frame,0 <-- from chessboard
BEVvideo_frame,i..(n) <-- from IMU

RT_i^-1 * RT_imu ->> Turn this into R R T - H_ideal
H = K * h_ideal


class HomographyFromChessboard

class HomographyTransformed
    Use IMURTsByTimestamp to tranform homography into other video frames

class ImageDataForTraining
    BEV_ts,0 CUR_IMAGE * HomographyFromChessboard
    BEV_ts - 1..n IMAGE_ts-1..n * HomographyTransformed_ts - 1..n

    "Good" image for timestamp + n vicreg into past images (transformed by homography)
    for each timestamp

Training the representation input vector requires IMURTsByTimestamp, ImagesByTimestamp, HomographyFromChessboard
    HomographyTransformed, and puts it into ImageDataForTraining

How do we build a ground image for a bag? A BEV picture of the ground?

Images -> BEV (with Rigid Transform)
Use Rigid Transform to compute relative homographies onto a larger plane.
    The resultant homography is not constrained to the model (0,0),(64,64) model, but lives in coordinates
    on this larger plane

Costmap is just that computation after applying the scoring function neural net

Metric calibration
5 images of chessboard from different views
Cannot be coparallel


"""

import cv2
import numpy as np
import os
import torch

from camera_intrinsics import CameraIntrinsics


class Homography:
    def __init__(self, homography_tensor):
        self.homography_tensor = homography_tensor


class HomographyFromChessboardImage(Homography):
    def __init__(self, image, cb_rows, cb_cols):
        super().__init__(torch.eye(3))
        
        # Get image chessboard corners, cartesian NX2
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, (cb_cols, cb_rows), None)
        corners = corners.reshape(-1, 2)

        # Get model chessboard corners, cartesian NX2
        model_chessboard = self.compute_model_chessboard(cb_rows, cb_cols)

        self.H, mask = cv2.findHomography(model_chessboard, corners, cv2.RANSAC)
        K, K_inv = CameraIntrinsics().get_camera_intrinsics()
        self.H_calibrated = self.decompose_homography(self.H, K_inv)

        ### These 2 images should be the same
        # points_out = H @ self.cart_to_hom(model_chessboard.T)
        # cart_pts_out = self.hom_to_cart(points_out)
        # validate_pts = cart_pts_out.T.reshape(-1, 1, 2).astype(np.float32)
        # self.draw_corner_image(image, (cb_rows, cb_cols), validate_pts, ret)
        # self.draw_corner_image(image, (cb_rows, cb_cols), corners, ret)
        
    def get_homography(self):
        """
        Return the homography matrix from the chessboard image.
        """
        return self.H
        
    def get_calibrated_homography(self):
        """
        Return the calibrated homography matrix from the chessboard image.
        """
        return self.H_calibrated

    def draw_corner_image(self, image, chessboard_size, corners, ret):
        if ret:
            print("Chessboard corners found!")
            # Draw the corners on the image
            cv2.drawChessboardCorners(image, chessboard_size, corners, ret)
            cv2.imshow("Chessboard Corners", image)
        else:
            cv2.imshow("Loaded Image", image)
            print("Chessboard corners not found.")

        cv2.waitKey(0)  # Wait for a key press to close the window
        cv2.destroyAllWindows()

    def compute_model_chessboard(self, rows, cols):
        model_chessboard = np.zeros((rows * cols, 2), dtype=np.float32)
        midpoint_row = rows / 2
        midpoint_col = cols / 2
        for row in range(0, rows):
            for col in range(0, cols):
                model_chessboard[row * cols + col, 0] = (col + 0.5) - midpoint_col
                model_chessboard[row * cols + col, 1] = (row + 0.5) - midpoint_row
        return model_chessboard

    def cart_to_hom(self, points):
        row_of_ones = np.ones((1, points.shape[1]))
        return np.vstack((points, row_of_ones))

    def hom_to_cart(self, points):
        w = points[-1]
        cart_pts = points / w
        return cart_pts[:-1]

    def decompose_homography_return_rt(self, H, K_inv):
        H = np.transpose(H)
        h1 = H[0]
        h2 = H[1]
        h3 = H[2]

        L = 1 / np.linalg.norm(np.dot(K_inv, h1))

        r1 = L * np.dot(K_inv, h1)
        r2 = L * np.dot(K_inv, h2)
        r3 = np.cross(r1, r2)

        T = L * np.dot(K_inv, h3)

        R = np.array([[r1], [r2], [r3]])
        R = np.reshape(R, (3, 3))
        U, S, V = np.linalg.svd(R, full_matrices=True)

        U = np.matrix(U)
        V = np.matrix(V)
        R = U * V

        M = np.eye(4, dtype=np.float32)
        M[:3, :3] = R                  
        M[:3, 3] = T.ravel()
        return M

class RobotDataAtTimestep:
    def __init__(self, nTimeSteps):
        print("FILLER")
        self.nTimeSteps = nTimeSteps

    def getNTimeSteps(self):
        return self.nTimeSteps
    
    def getImageAtTimeStep(self, idx):
        print("FILLER")
        #return the image
    
    def getIMUAtTimeStep(self, idx):
        print("FILLER")
        #return the IMU as a 4x4 matrix
    
    def getOdomAtTimeStep(self, idx):
        print("FILLER")
        #return the Odom as a 4x4 matrix

'''
    Inertial frame "the tape x in the drone cage"
    Base link cur where the robot is
    Base link past where the robot was
    Base link to camera

    Inertial frame * base link * base link to camera -- Do some magic -- BEV image
    Inertial frame * base link past * base link to camera -- Do some magic -- BEV image in the past

    Transform from cur to past

    (Inertial frame * base link)^-1 <-- inverse * (Inertial frame * base link past) = cur_to_past
    Assume the inertial frame is identity
    base link^-1 * base link past = cur_to_past

    Assume that base link to camera is always the same..
    Meaning it was the same in the inertial frame
    And in the current frame
    And in the past frame

    Determining how the camera moved, is now just cur_to_past
    The past orientation of the camera with respect to the homography is just
    cur_to_past * rt_to_calibrated_homography = cool_tranform
    Turn cool_tranform into a calibrated homography
    [   R1 R2 R3   T
        0           1
    ]

    [R1 R2 T] = calibrated_hom_past

    Turn it into something you can use to get the same BEV image patch

    At the current frame it is cv2.warpImage(cur_image, H)
    In the past frame it is cv2.warpImage(past_image, K * calibrated_hom_past)
'''

class FramePlusHistory:
    def __init__(self, start_frame, frames):
        print("FILLER")
        self.start_frame = start_frame  #The frame at the current timestep
        self.frames = frames            #The history for n timesteps

def ComputeVicRegData(\
        synced_data, camera_calibration_matrix, \
        rt_to_calibrated_homography, robot_at_timestep, n_history = 10):
        
        n_timesteps = robot_at_timestep.getNTimeSteps()
        for timestep in range(0, n_timesteps):
            cur_image = robot_at_timestep.getImageAtTimeStep(timestep)
            cur_rt = robot_at_timestep.getOdomAtTimeStep(timestep)
            for past_hist in range(1, n_history):
                past_timestep = timestep - past_hist
                if past_timestep >= 0:
                    past_image = robot_at_timestep.getImageAtTimeStep(past_timestep)
                    past_rt = robot_at_timestep.getOdomAtTimeStep(past_timestep)
                    cur_to_past_rt = past_rt @ np.invert(cur_rt)
                



class InData:
    def __init__(self, synced_data):
        self.synced_data = synced_data
        
    ### Pseudocode
    # Use IMURTsByTimestamp to tranform homography into other video frames


if __name__ == "__main__":
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    image_dir = script_dir + "/homography/"
    path_to_image = image_dir + "raw_image.jpg"

    image = cv2.imread(path_to_image)
    chessboard_homography = HomographyFromChessboardImage(image, 8, 6)
    
    H = chessboard_homography.get_homography()
    H_calibrated = chessboard_homography.get_calibrated_homography()

    # if ret:
    #     criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
    #     corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
    #         criteria)
