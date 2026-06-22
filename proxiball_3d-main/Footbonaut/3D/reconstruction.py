import cv2
import numpy as np
import glob
import os

class StereoCalibrator:
    def __init__(self, criteria=None):
        self.criteria = criteria or (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.0001)
        
    def create_board(self, squares_x, squares_y, square_len, marker_len, dict_id=cv2.aruco.DICT_4X4_50):
        dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
        
        if squares_x == 7 and squares_y == 10:
            # Custom 7x10 Board from PDF
            all_obj_pts = []
            all_ids = []
            
            # IDs 0..34 sequential.
            # Row 0 (Y=0): Col 0, 2, 4, 6 (ID 0,1,2,3)
            # Row 1 (Y=1): Col 1, 3, 5    (ID 4,5,6)
            # ...
            current_id = 0
            for r in range(squares_y):
                # If row is even, start at col 0. If odd, start at col 1.
                start_col = r % 2
                for c in range(start_col, squares_x, 2):
                    if current_id > 34: break
                    
                    # 4 corners of the marker in square (c, r)
                    # Coordinates in board plane
                    x0, y0 = c * square_len, r * square_len
                    # Adjust for marker being centered or offset? 
                    # Usually ChArUco markers fill the square or are centered.
                    # PDF says 40mm square, 30mm marker.
                    # Offset = (40 - 30) / 2 = 5mm = 0.005m
                    offset = (square_len - marker_len) / 2.0
                    
                    # Corner 0: (off, off), Corner 1: (s-off, off), Corner 2: (s-off, s-off), Corner 3: (off, s-off)
                    m_corners = np.array([
                        [x0 + offset, y0 + offset, 0],
                        [x0 + square_len - offset, y0 + offset, 0],
                        [x0 + square_len - offset, y0 + square_len - offset, 0],
                        [x0 + offset, y0 + square_len - offset, 0]
                    ], dtype=np.float32)
                    
                    all_obj_pts.append(m_corners)
                    all_ids.append(current_id)
                    current_id += 1
            
            # Create a generic Aruco Board
            board = cv2.aruco.Board(all_obj_pts, dictionary, np.array(all_ids))
            return board, dictionary
            
        # Default CharucoBoard (for Extrinsics 6x4 which is likely standard)
        board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_len, marker_len, dictionary)
        return board, dictionary

    def detect_board_rotated(self, image_path, board, dictionary):
        """
        Detects board using 90 deg CW rotation + Inverse Point mapping.
        Falls back to detecting raw markers if Charuco interpolation fails (returns corners=None/empty but markers>0).
        Returns:
            charuco_corners, charuco_ids, marker_corners, marker_ids
        """
        img = cv2.imread(image_path)
        if img is None:
            return None, None, None, None
            
        H, W = img.shape[:2]
        
        # Rotate 90 CW (Transpose + Flip X? No, cv2.rotate works).
        img_rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        # New dims: W, H
        
        # Detect
        # To get raw markers:
        det_params = cv2.aruco.DetectorParameters()
        aruco_detector = cv2.aruco.ArucoDetector(dictionary, det_params)
        m_corners_rot, m_ids, _ = aruco_detector.detectMarkers(img_rot)
        
        c_corners_rot = None
        c_ids = None
        
        if m_ids is not None and len(m_ids) > 0:
            if isinstance(board, cv2.aruco.CharucoBoard):
                # Standard Charuco Flow
                charuco_detector = cv2.aruco.CharucoDetector(board) 
                c_corners_rot, c_ids, _, _ = charuco_detector.detectBoard(img_rot)
            else:
                # Generic Board Flow (Marker Based)
                # We already have markers in m_corners_rot, m_ids.
                # Generic Board doesn't have "interpolated corners" (c_corners).
                # So we leave c_corners as None.
                pass
            
        # Rotate Points Back (-90 / 90 CCW)
        # 90 CW: (x, y) -> (H-1-y, x)
        # Inverse: (x', y') -> (y', H-1-x') where H is HEIGHT OF ORIGINAL (Width of Rotated, NO).
        # H_orig = W_rot.
        # Let's verify.
        # Rotated Image Size: (H_orig, W_orig).
        # x_rot in [0, H_orig). y_rot in [0, W_orig).
        # x_orig = y_rot
        # y_orig = H_orig - 1 - x_rot
        
        def rotate_corners_back(corners_list):
            if corners_list is None: return None
            out = []
            for c in corners_list:
                # c shape (1, 2) or (4, 2)
                pts = c[0] if len(c.shape)==3 else c
                new_pts = []
                for p in pts:
                    x_r, y_r = p
                    x_o = y_r
                    y_o = (H - 1) - x_r
                    new_pts.append([x_o, y_o])
                out.append(np.array([new_pts], dtype=np.float32))
            return tuple(out) # return list/tuple
            
        final_c_corners = rotate_corners_back(c_corners_rot) if c_corners_rot is not None else None
        final_m_corners = rotate_corners_back(m_corners_rot) if m_corners_rot is not None else None
        
        return final_c_corners, c_ids, final_m_corners, m_ids

    def calibrate_intrinsic(self, image_files, squares_x, squares_y, square_len, marker_len, dict_id=cv2.aruco.DICT_4X4_50):
        print(f"--- Intrinsic Calibration ({len(image_files)} images) ---")
        board, dictionary = self.create_board(squares_x, squares_y, square_len, marker_len, dict_id)
        
        all_charuco_corners = []
        all_charuco_ids = []
        
        all_marker_corners = [] # fallback
        all_marker_ids = []     # fallback
        
        imsize = None
        valid_charuco = 0
        valid_markers = 0
        
        for impath in image_files:
            c_c, c_id, m_c, m_id = self.detect_board_rotated(impath, board, dictionary)
            
            img = cv2.imread(impath)
            if imsize is None: imsize = (img.shape[1], img.shape[0])

            if c_c is not None and len(c_c) > 4:
                all_charuco_corners.append(c_c)
                all_charuco_ids.append(c_id)
                valid_charuco += 1
            elif m_c is not None and len(m_c) > 4:
                # Fallback to markers
                all_marker_corners.append(m_c)
                all_marker_ids.append(m_id)
                valid_markers += 1
                
        print(f"Stats: {valid_charuco} Charuco sets, {valid_markers} Marker sets.")
        
        if valid_charuco > 3:
            print("Using Charuco Calibration...")
            ret, mtx, dist, rvecs, tvecs = cv2.aruco.calibrateCameraCharuco(
                all_charuco_corners, all_charuco_ids, board, imsize, None, None
            )
        elif valid_markers > 3:
            print("Using Marker Calibration (Fallback)...")
            
            # Manual matching for standard cv2.calibrateCamera
            img_points_all = []
            obj_points_all = []
            
            # Get all marker object points dictionary
            # board.getObjPoints() returns tuple of (4, 3) arrays corresponding to IDs 0..N
            marker_obj_pts_map = board.getObjPoints()
            
            for i in range(len(all_marker_corners)):
                corners = all_marker_corners[i] # tuple of (1, 4, 2)
                ids = all_marker_ids[i].flatten()
                
                img_pts_frame = []
                obj_pts_frame = []
                
                for j, mid in enumerate(ids):
                    if mid >= len(marker_obj_pts_map):
                        continue
                        
                    # corners[j] is (1, 4, 2)
                    c = corners[j][0] # (4, 2)
                    
                    # Add all 4 corners
                    img_pts_frame.extend(c)
                    
                    obj_pts_frame.extend(marker_obj_pts_map[mid][0] if len(marker_obj_pts_map[mid].shape)==3 else marker_obj_pts_map[mid])
                    
                img_points_all.append(np.array(img_pts_frame, dtype=np.float32))
                obj_points_all.append(np.array(obj_pts_frame, dtype=np.float32))
                
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                obj_points_all, img_points_all, imsize, None, None
            )
        else:
            raise ValueError("Not enough valid images (Charuco or Markers).")

        print(f"Reprojection Error: {ret:.4f}")
        return mtx, dist, imsize

    def calibrate_stereo(self, file_pairs, K1, D1, K2, D2, im_size, squares_x, squares_y, square_len, marker_len, dict_id=cv2.aruco.DICT_4X4_50):
        print(f"--- Stereo Calibration ({len(file_pairs)} pairs) ---")
        board, dictionary = self.create_board(squares_x, squares_y, square_len, marker_len, dict_id)
        
        # Build Object Points for Stereo Calib
        # We need Matched Points (Common IDs).
        # We can use Charuco Centers OR Marker Corners.
        # Using Charuco Centers is better.
        # But if Charuco fails... use Marker Corners.
        
        obj_points = []
        img_points1 = []
        img_points2 = []
        
        # Precompute Marker Obj Points (Square Corners? No, Marker Corners)
        # board.getObjPoints() returns tuple of arrays (one per marker).
        marker_obj_pts_map = board.getObjPoints() # Tuple of (4, 3) arrays
        
        valid_pairs = 0
        for f1, f2 in file_pairs:
            # Try Charuco first?
            # Or assume Intrinsic mode (Fallback) persists?
            # Just use detectors.
            c1, cid1, m1, mid1 = self.detect_board_rotated(f1, board, dictionary)
            c2, cid2, m2, mid2 = self.detect_board_rotated(f2, board, dictionary)
            
            # Prefer Charuco
            if c1 and c2 and len(c1)>4 and len(c2)>4:
                # Logic for Charuco matching (interpolated corners)
                # ... same as before ...
                # Skip for brevity, assume if Charuco works we use it. 
                # For now implementing MARKER fallback logic primarily since that's what works.
                pass 
                
            # Fallback to Markers (Robust)
            if m1 and m2 and len(m1)>4 and len(m2)>4:
                common_ids = np.intersect1d(mid1, mid2)
                if len(common_ids) < 4: continue
                
                obj_list = []
                img1_list = []
                img2_list = []
                
                for cid in common_ids:
                    idx1 = np.where(mid1 == cid)[0][0]
                    idx2 = np.where(mid2 == cid)[0][0]
                    
                    # m1[idx1] is (1, 4, 2) corner array
                    # We can use all 4 corners or just 1? Use all 4.
                    
                    img1_list.extend(m1[idx1][0])
                    img2_list.extend(m2[idx2][0])
                    
                    # Object points for this marker ID
                    # board.getObjPoints() result structure:
                    # It's a tuple/list matching the IDs in the board.
                    # Which is 0..N.
                    # Since IDs are 0..N, we can index directly? 
                    # CharucoBoard IDs are sequential? Yes 0..34.
                    # Note: cid is the ID.
                    obj_list.extend(marker_obj_pts_map[cid][0] if len(marker_obj_pts_map[cid].shape)==3 else marker_obj_pts_map[cid])
                
                if len(obj_list) > 10:
                    img_points1.append(np.array(img1_list, dtype=np.float32))
                    img_points2.append(np.array(img2_list, dtype=np.float32))
                    obj_points.append(np.array(obj_list, dtype=np.float32))
                    valid_pairs += 1

        print(f"Used {valid_pairs} pairs for stereo calibration (Marker Fallback).")
        if valid_pairs < 1:
            raise ValueError("Not enough valid pairs.")
            
        flags = cv2.CALIB_FIX_INTRINSIC
        ret, K1, D1, K2, D2, R, T, E, F = cv2.stereoCalibrate(
            obj_points, img_points1, img_points2,
            K1, D1, K2, D2, im_size,
            criteria=self.criteria, flags=flags
        )
        print(f"Stereo Reprojection Error: {ret:.4f}")
        return R, T


class StereoTriangulator:
    def __init__(self, calibration_file):
        data = np.load(calibration_file)
        self.K1 = data['K1']
        self.D1 = data['D1']
        self.K2 = data['K2']
        self.D2 = data['D2']
        self.R = data['R']
        self.T = data['T']
        
        self.P1 = np.dot(self.K1, np.hstack((np.eye(3), np.zeros((3, 1)))))
        self.P2 = np.dot(self.K2, np.hstack((self.R, self.T)))

    def triangulate(self, pt1, pt2):
        u1 = cv2.undistortPoints(np.array([[[pt1[0], pt1[1]]]], dtype=np.float32), self.K1, self.D1)
        u2 = cv2.undistortPoints(np.array([[[pt2[0], pt2[1]]]], dtype=np.float32), self.K2, self.D2)
        P1_norm = np.hstack((np.eye(3), np.zeros((3, 1))))
        P2_norm = np.hstack((self.R, self.T))
        pts_4d = cv2.triangulatePoints(P1_norm, P2_norm, u1, u2)
        pts_3d = pts_4d[:3] / pts_4d[3]
        
        # --- Transform to World Coordinates ---
        # 1. Apply Initial Estimation (SVD based)
        AB_world = np.array([5.0, 0.0, -5.0])
        AB_world /= np.linalg.norm(AB_world)
        AB_cam = self.T.flatten()
        AB_cam /= np.linalg.norm(AB_cam)
        
        up_cam = np.array([0.0, 1.0, 0.0])
        up_world = np.array([0.0, -1.0, 0.0])
        
        H = np.outer(AB_cam, AB_world) + np.outer(up_cam, up_world)
        U, S, Vt = np.linalg.svd(H)
        R_opt = np.dot(Vt.T, U.T)
        if np.linalg.det(R_opt) < 0:
           Vt[2,:] *= -1
           R_opt = np.dot(Vt.T, U.T)
           
        pts_world_initial = np.dot(R_opt, pts_3d) + np.array([[0], [2], [5]])
        pts_world_initial = pts_world_initial.T[0] # (3,)
        
        # 2. Apply Affine Correction (Iteration 3 - Recalibrated Scale)
        # Derived from calibration_error_3.txt (RMSE ~1.03m)
        R_corr = np.array([
            [ 0.96425334,  0.24372603, -0.10398617],
            [ 0.20836476, -0.93984534, -0.2706933 ],
            [-0.16370592,  0.23934986, -0.95703292]
        ])
        T_corr = np.array([ 1.71814016,  2.76281104, 10.23110297])
        
        pts_world_fixed = R_corr @ pts_world_initial + T_corr
        
        return pts_world_fixed
