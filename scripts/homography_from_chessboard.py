import cv2
import numpy as np

from camera_intrinsics import CameraIntrinsics
from homography_utils import *
from utils import *
import tkinter as tk
from scipy.spatial.transform import Rotation as R
from concurrent.futures import ThreadPoolExecutor


class HomographyFromChessboardImage:
    def __init__(self, image, cb_rows, cb_cols):
        # super().__init__(torch.eye(3))
        self.image = image
        self.cb_rows = cb_rows
        self.cb_cols = cb_cols
        self.chessboard_size = (cb_rows, cb_cols)

        # Get image chessboard corners, cartesian NX2
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, (cb_cols, cb_rows), None)
        self.corners = corners.reshape(-1, 2)
        self.cb_tile_width = int(self.chessboard_tile_width())

        # Get model chessboard corners, cartesian NX2
        model_chessboard_2d = compute_model_chessboard_2d(cb_rows, cb_cols, self.cb_tile_width, center_at_zero=True)

        self.H, mask = cv2.findHomography(model_chessboard_2d, self.corners, cv2.RANSAC)
        self.K, K_inv = CameraIntrinsics().get_camera_calibration_matrix()
        self.RT, self.plane_normal, self.plane_distance = decompose_homography(self.H, self.K)

        self.validate_chessboard_2d(model_chessboard_2d)

        # Transform model chessboard 3D points to image points
        model_chessboard_3d = compute_model_chessboard_3d(cb_rows, cb_cols, self.cb_tile_width, center_at_zero=True)
        self.validate_chessboard_3d(model_chessboard_3d)

    def validate_chessboard_2d(self, model_chessboard_2d):
        # Transform model chessboard 2D points to image points
        self.transformed_model_chessboard_2d = self.transform_points(model_chessboard_2d.T, self.H)
        self.transformed_model_chessboard_2d = self.transformed_model_chessboard_2d.T.reshape(-1, 2).astype(np.float32)

    def validate_chessboard_3d(self, model_chessboard_3d):
        RT = self.get_rigid_transform()
        K = self.get_camera_intrinsics()
        self.IEK = K @ RT[:3] @ model_chessboard_3d.T
        self.model_cb_3d_to_2d = hom_to_cart(self.IEK)
        return self.model_cb_3d_to_2d

    def get_rigid_transform(self):
        return self.RT

    def get_camera_intrinsics(self):
        return self.K

    def get_plane_norm(self):
        return self.plane_normal

    def get_plane_dist(self):
        return self.plane_distance

    def chessboard_tile_width(self):
        """Calculate the maximum distance between two consecutive corners in each row of the chessboard."""
        # Sort corners by y value to group them by rows
        sorted_corners = sorted(self.corners, key=lambda x: x[1])

        # Split sorted_corners into rows
        interval = self.cb_cols
        rows = [sorted_corners[i * interval : (i + 1) * interval] for i in range(len(sorted_corners) // interval)]

        # Calculate distances between consecutive points in each row
        cb_tile_width = 0
        for row in rows:
            row.sort(key=lambda x: x[0])
            for i in range(len(row) - 1):
                distance = np.linalg.norm(np.array(row[i]) - np.array(row[i + 1]))
                cb_tile_width = max(cb_tile_width, distance)

        return cb_tile_width

    def validate_homography(self):
        keepRunning = True
        counter = 0
        cv2.namedWindow("Chessboard")
        while keepRunning:
            match counter % 3:
                case 0:
                    rend_image = draw_points(self.image, self.corners, color=(255, 0, 0))
                    cv2.setWindowTitle("Chessboard", "Original corners")
                case 1:
                    rend_image = draw_points(self.image, self.transformed_model_chessboard_2d, color=(0, 255, 0))
                    cv2.setWindowTitle("Chessboard", "Transformed 2D model chessboard corners")
                case 2:
                    rend_image = draw_points(self.image, self.model_cb_3d_to_2d.T, color=(0, 0, 255))
                    cv2.setWindowTitle("Chessboard", "Transformed 3D model chessboard corners")
            counter += 1
            cv2.imshow("Chessboard", rend_image)
            key = cv2.waitKey(0)
            if key == 113:  # Hitting 'q' quits the program
                keepRunning = False
        exit(0)

    def transform_points(self, points, H):
        """Transform points using the homography matrix."""
        hom_points = cart_to_hom(points)
        transformed_points = H @ hom_points
        return hom_to_cart(transformed_points)

    def plot_BEV_chessboard(self):
        image = self.image.copy()
        model_chessboard_2d_centered = compute_model_chessboard_2d(
            self.cb_rows, self.cb_cols, self.cb_tile_width, center_at_zero=False
        )
        H, mask = cv2.findHomography(model_chessboard_2d_centered, self.corners, cv2.RANSAC)
        dimensions = (int(self.cb_tile_width * (self.cb_cols - 1)), int(self.cb_tile_width * (self.cb_rows - 1)))
        warped_image = cv2.warpPerspective(image, np.linalg.inv(H), dsize=dimensions)

        cv2.imshow("BEV", warped_image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        exit(0)

    def submit(self):
        print("OK")
        self.theta = float(self.entries[0].get())
        self.x0 = float(self.entries[1].get())
        self.x1 = float(self.entries[2].get())
        self.y0 = float(self.entries[3].get())
        self.y1 = float(self.entries[4].get())
        for i, field in enumerate(self.fields):
            print(field, ": ", self.entries[i].get())

    def BEVEditor(self):
        root = tk.Tk()
        root.title("BEV Editor")
        self.fields = ["Theta", "x0", "x1", "y0", "y1"]
        self.entries = []
        for i, field in enumerate(self.fields):
            label = tk.Label(root, text=field)
            label.grid(row=i, column=0, padx=10, pady=5, sticky="e")
            entry = tk.Entry(root)
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.entries.append(entry)
        submit_button = tk.Button(root, text="Submit", command=lambda: self.submit())
        submit_button.grid(row=len(self.fields), column=0, padx=10, pady=10)
        self.entries[0].delete(0, tk.END)
        self.entries[0].insert(0, "0.0")
        self.entries[1].delete(0, tk.END)
        self.entries[1].insert(0, "-10.0")
        self.entries[2].delete(0, tk.END)
        self.entries[2].insert(0, "10.0")
        self.entries[3].delete(0, tk.END)
        self.entries[3].insert(0, "-10.0")
        self.entries[4].delete(0, tk.END)
        self.entries[4].insert(0, "10.0")
        self.submit()

        while True:
            root.update_idletasks()  # Update "idle" tasks (like geometry management)
            root.update()

            RT = self.get_rigid_transform()
            print("RT:  ", RT)
            K = self.get_camera_intrinsics()
            model_rect_3d_hom = compute_model_rectangle_3d_hom(self.theta, self.x0, self.y0, self.x1, self.y1)
            model_rect_3d_applied_RT = K @ RT[:3] @ model_rect_3d_hom.T
            model_rect_2d = hom_to_cart(model_rect_3d_applied_RT)
            rend_image = draw_points(self.image, model_rect_2d.T, color=(255, 0, 255))
            cv2.imshow("Full BEV", rend_image)
            cv2.waitKey(1)

    def crop_bottom_to_content(self, img, threshold=1):
        """
        Crops the bottom of the image so that the last row containing
        any pixel value above the threshold becomes the new bottom.
        
        Parameters:
        img: A color image (NumPy array) in BGR or RGB.
        threshold: Pixel intensity threshold (default 1); 
                    rows with all pixel values <= threshold are considered black.
        
        Returns:
        Cropped image.
        """
        # Convert to grayscale for simplicity.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        
        h, w = gray.shape
        # Initialize the crop index to h (no crop if no black bottom is found).
        crop_row = h  
        # Iterate from the bottom row upward.
        for row in range(h - 1, -1, -1):
            # If at least one pixel in this row exceeds the threshold,
            # then this row is part of the actual image.
            if np.any(gray[row, :] > threshold):
                crop_row = row + 1  # +1 so that this row is included
                break
        return img[:crop_row, :]

    def plot_BEV_full(self, img, H, patch_size=(128, 128)):
        """
        Preprocesses the robot data to compute multiple viewpoints
        of the same patch for each timestep.
        Args:
            H: Homography matrix.
            patch_size: Size of the patch (width, height).
        Returns:
            stitched_image: Reconstructed bird's-eye view image.
        """
        # Define horizontal and vertical shifts
        num_patches_x = 6
        num_patches_y = 10
        shift_step = 128

        # Compute all shifts using vectorized NumPy operations
        shift_x = np.arange(-(num_patches_x), num_patches_x + 2) * shift_step  # -6 to 7 (14 steps)
        shift_y = np.arange(-2, num_patches_y) * shift_step                   # -2 to 9 (12 steps)

        # Sort shifts in descending order to match sorted(..., reverse=True)
        shift_x = sorted(shift_x, reverse=True)  # Largest negative to largest positive (left to right)
        shift_y = sorted(shift_y, reverse=True)  # Largest negative to largest positive (top to bottom)

        # Generate all possible (sx, sy) shift pairs with the correct order
        # Use explicit indexing to match the original reverse-sorted order
        shift_pairs = []
        for sy in shift_y:  # Top to bottom (largest negative to largest positive)
            for sx in shift_x:  # Left to right (largest negative to largest positive)
                shift_pairs.append([sx, sy])
        shift_pairs = np.array(shift_pairs)  # Shape: (168, 2)

        def process_patch(shift):
            """Applies homography and warps a patch."""
            sx, sy = shift

            # Create transformation matrix
            T_shift = np.array([[1, 0, sx],
                                [0, 1, sy],
                                [0, 0, 1]])
            H_shifted = T_shift @ H  # Matrix multiplication

            # Warp image using shifted homography
            cur_patch = cv2.warpPerspective(img, H_shifted, dsize=patch_size, flags=cv2.INTER_LINEAR)

            # Ensure patch size matches exactly
            if cur_patch.shape[:2] != patch_size:
                cur_patch = cv2.resize(cur_patch, patch_size, interpolation=cv2.INTER_LINEAR)

            return cur_patch

        # Use multi-threading to process patches in parallel
        with ThreadPoolExecutor(max_workers=min(8, len(shift_pairs))) as executor:
            patches = list(executor.map(process_patch, shift_pairs))

        # Reconstruct the grid (rows x cols)
        rows = len(shift_y)  # 12
        cols = len(shift_x)  # 14

        # Reshape patches into row-wise groups and concatenate efficiently
        patches_array = np.array(patches, dtype=np.uint8)  # Convert to numpy array for efficiency
        row_images = [cv2.hconcat(patches_array[i * cols:(i + 1) * cols]) for i in range(rows)]

        # No reversal needed since shift_y is already sorted reverse=True
        # Concatenate all rows to form the final stitched image
        stitched_image = cv2.vconcat(row_images)

        # Crop the bottom part if necessary
        stitched_image = self.crop_bottom_to_content(stitched_image)

        return stitched_image

"""
    def plot_BEV_full(self, image, plot_BEV_full=False):
        
        #Plots the bird's-eye view (BEV) image using optimized rectangle parameters.
        

        RT = self.get_rigid_transform()
        K = self.get_camera_intrinsics()

        # Get optimized parameters
        #theta, x1, y1, x2, y2 = optimize_rectangle_parameters(self.image, RT, K)
        theta = 0
        x1 = -530
        x2 = 540
        y1 = -1300
        y2 = 325

        # Generate optimized 3D rectangle
        model_rect_3d_hom = compute_model_rectangle_3d_hom(theta, x1, y1, x2, y2)
        model_rect_3d_applied_RT = K @ RT[:3] @ model_rect_3d_hom.T
        model_rect_2d = hom_to_cart(model_rect_3d_applied_RT)

        # Align rectangle with the bottom of the image
        #model_rect_2d[1] -= model_rect_2d[1].max() - (self.image.shape[0] - 1)

        x_dif = abs(x2) + abs(x1)
        y_dif = abs(y2) + abs(y1)
        aspect_ratio = y_dif/x_dif
        dsize = (1280,720)
        #dsize = (int(aspect_ratio*720),int(720))
        #dsize = (x_dif, y_dif)

        # Adjust rectangle for warp perspective
        src_points = np.array([
            model_rect_2d.T[0, :2],  # Top-left
            model_rect_2d.T[1, :2],  # Top-right
            model_rect_2d.T[2, :2],  # Bottom-right
            model_rect_2d.T[3, :2],  # Bottom-left
        ], dtype=np.float32)

        
        # Adjusted destination points for better rectification
        dst_points = np.array([
            [dsize[0] // 2 - 180, 0],           # Top-left
            [dsize[0] // 2 + 180, 0],           # Top-right
            [2 * dsize[0] // 3, dsize[1] - 1],  # Bottom-right
            [dsize[0] // 3, dsize[1] - 1]       # Bottom-left 
        ], dtype=np.float32)
        
        dst_points = np.array([
            [0, 0],   # Top-left
            [dsize[0], 0],  # Top-right
            [dsize[0], dsize[1]],  # Bottom-right
            [0, dsize[1]]  # Bottom-left 
        ], dtype=np.float32)

        H, _ = cv2.findHomography(src_points, dst_points, cv2.RANSAC)
        warped_image = cv2.warpPerspective(image, H, dsize)

        # Resize the warped image
        #warped_image = cv2.resize(warped_image, (int(dsize[0] / 2), int(dsize[1] / 2)))

        if plot_BEV_full:
            plot_BEV(image, model_rect_2d, warped_image)

        return H, dsize, warped_image
    """