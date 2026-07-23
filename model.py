"""
model.py
--------
Model layer in the MVVM architecture.
Handles raw image processing, folder scanning, file copying, tone mapping, 
and CLAHE enhancement routines without external object detection dependencies.
"""

import os
import shutil
import cv2
import numpy as np
import time


class LetterBoxStandalone:
    """
    Standalone implementation replicating ultralytics.data.augment.LetterBox functionality
    without requiring ultralytics library installation.
    Maintains aspect ratio and applies uniform padding for image resizing.

    Attributes:
        new_shape (tuple): Target image dimensions (height, width).
        color (tuple): Border padding color tuple in (B, G, R) format.
        auto (bool): Minimum rectangle padding flag.
        scaleFill (bool): Stretch image to fill shape without maintaining aspect ratio.
        scaleup (bool): Allow scaling up smaller images.
        stride (int): Padding alignment stride divisor.
        center (bool): Center alignment flag for padding distribution.
    """

    def __init__(self, new_shape=(640, 640), color=(114, 114, 114),
                 auto=False, scaleFill=False, scaleup=True, stride=32, center=True):
        """
        Initializes LetterBoxStandalone with target shape and padding configurations.

        Args:
            new_shape (tuple or int, optional): Target dimensions (height, width). Defaults to (640, 640).
            color (tuple or int, optional): Border fill color. Defaults to (114, 114, 114).
            auto (bool, optional): Minimum rectangular padding flag. Defaults to False.
            scaleFill (bool, optional): Scale to fill target grid without padding. Defaults to False.
            scaleup (bool, optional): Allow scaling images up. Defaults to True.
            stride (int, optional): Stride size for alignment. Defaults to 32.
            center (bool, optional): Center padding flag. Defaults to True.
        """
        self.new_shape = new_shape if isinstance(new_shape, tuple) else (new_shape, new_shape)
        self.color = color if isinstance(color, tuple) else (color, color, color)
        self.auto = auto
        self.scaleFill = scaleFill
        self.scaleup = scaleup
        self.stride = stride
        self.center = center

    def __call__(self, img):
        """
        Executes letterbox resizing and padding on input image matrix.

        Args:
            img (numpy.ndarray): Input image array (H, W, C).

        Returns:
            tuple[numpy.ndarray, tuple, tuple]: 
                - Processed letterboxed image matrix.
                - Scale ratios tuple (r_w, r_h).
                - Top-left offset tuple (left, top).
        """
        shape = img.shape[:2]  # Current shape (h, w)
        new_shape = self.new_shape

        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        if not self.scaleup:
            r = min(r, 1.0)

        ratio = r, r
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))  # (w, h)
        dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]

        if self.auto:
            dw, dh = np.mod(dw, self.stride), np.mod(dh, self.stride)
        elif self.scaleFill:
            dw, dh = 0.0, 0.0
            new_unpad = (new_shape[1], new_shape[0])
            ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]

        if self.center:
            dw /= 2
            dh /= 2

        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))

        img = cv2.copyMakeBorder(img, top, bottom, left, right,
                                   cv2.BORDER_CONSTANT, value=self.color)
        return img, ratio, (left, top)


class PhotoCopyModel:
    """
    Core data processing class for scanning, preprocessing, and writing image files.

    Attributes:
        letterbox (LetterBoxStandalone): Standalone LetterBox instance for image resizing.
        pad_color (int): Padding color value for letterboxing.
        target_mean (float): Target mean brightness value for tone adjustment.
        max_gamma_shift (float): Maximum allowed shift bound for gamma correction.
        clahe_clip (float): Clip limit for CLAHE algorithm.
        clahe_tile (tuple): Grid size for CLAHE calculation (e.g., (8, 8)).
        clahe (cv2.CLAHE): OpenCV CLAHE object instance.
    """

    def __init__(self, imgsz=640, pad_color=114, target_mean=128.0, 
                 max_gamma_shift=0.4, clahe_clip=1.5, clahe_tile=(8, 8)):
        """
        Initializes the PhotoCopyModel with specified image processing parameters.

        Args:
            imgsz (int, optional): Target letterbox dimensions. Defaults to 640.
            pad_color (int, optional): Fill color for letterboxing borders. Defaults to 114.
            target_mean (float, optional): Ideal average luminance value. Defaults to 128.0.
            max_gamma_shift (float, optional): Maximum gamma correction bounds limit. Defaults to 0.4.
            clahe_clip (float, optional): Initial CLAHE clip threshold limit. Defaults to 1.5.
            clahe_tile (tuple, optional): Initial CLAHE tile grid size dimensions. Defaults to (8, 8).
        """
        color_tuple = (pad_color, pad_color, pad_color) if isinstance(pad_color, int) else pad_color
        self.letterbox = LetterBoxStandalone(
            new_shape=(imgsz, imgsz), 
            color=color_tuple, 
            auto=False, 
            scaleup=True, 
            center=True, 
            stride=32
        )
        self.pad_color = pad_color
        self.target_mean = target_mean
        self.max_gamma_shift = max_gamma_shift
        self.update_clahe_config(clahe_clip, clahe_tile)

    def update_clahe_config(self, clahe_clip, clahe_tile):
        """
        Dynamically updates CLAHE configuration parameters.

        Args:
            clahe_clip (float or str): Clip threshold limit value for contrast limiting.
            clahe_tile (tuple or list): Dimensions of the grid for histogram equalization (height, width).
        """
        self.clahe_clip = float(clahe_clip)
        self.clahe_tile = tuple(clahe_tile)
        self.clahe = cv2.createCLAHE(clipLimit=self.clahe_clip, tileGridSize=self.clahe_tile)

    def scan_images(self, src_root, allowed_types, stop_checker, scan_all=False):
        """
        Recursively traverses directories and collects valid image file paths based on mode.

        Args:
            src_root (str): Source root directory path.
            allowed_types (list): List of allowed folder name strings (e.g., ['original', 'processed']).
            stop_checker (callable): Function returning a boolean indicating if execution was aborted.
            scan_all (bool, optional): If True, scans all images directly without subfolder filtering.
                Defaults to False.

        Returns:
            list[str]: Absolute file path strings of matched valid images.
        """
        files_to_copy = []
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')

        for root, dirs, files in os.walk(src_root):
            if stop_checker():
                break
            
            if scan_all:
                for file in files:
                    if file.lower().endswith(valid_extensions):
                        files_to_copy.append(os.path.join(root, file))
            else:
                current_folder_name = os.path.basename(root).lower()
                if current_folder_name in allowed_types:
                    for file in files:
                        if file.lower().endswith(valid_extensions):
                            files_to_copy.append(os.path.join(root, file))

        return files_to_copy

    # =========================================================================
    # PREPROCESSING MODULES
    # =========================================================================
    def _build_gamma_lut(self, gamma):
        """
        Generates a 256-element Look-Up Table (LUT) for fast non-linear gamma mapping.

        Args:
            gamma (float): Calculated gamma value exponent.

        Returns:
            numpy.ndarray: 8-bit lookup table array of shape (256,).
        """
        indices = np.arange(256, dtype=np.float32)
        lut = np.clip((indices / 255.0) ** gamma * 255.0, 0, 255).astype(np.uint8)
        return lut

    def _preprocess_tone_clahe(self, img, metrics):
        """
        Applies automatic gamma tone mapping followed by CLAHE contrast enhancement in LAB space.

        Args:
            img (numpy.ndarray): Input image matrix loaded in BGR format.
            metrics (dict): Performance metrics dictionary to append execution benchmarks.

        Returns:
            numpy.ndarray: Enhanced output image matrix in BGR format.
        """
        orig_h, orig_w = img.shape[:2]
        letterboxed, _, _ = self.letterbox(img)
        
        new_h, new_w = letterboxed.shape[:2]
        scale = min(new_h / orig_h, new_w / orig_w)
        resized_h, resized_w = round(orig_h * scale), round(orig_w * scale)
        pad_h, pad_w = (new_h - resized_h) / 2, (new_w - resized_w) / 2
        top, left = int(round(pad_h - 0.1)), int(round(pad_w - 0.1))

        t_tone = time.perf_counter()
        lab = cv2.cvtColor(letterboxed, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        l_content = l[top:top + resized_h, left:left + resized_w]
        current_mean = float(np.mean(l_content)) if l_content.size > 0 else float(np.mean(l))
        current_mean_clamped = np.clip(current_mean, 20, 235)

        ideal_gamma = np.log(self.target_mean / 255.0) / np.log(current_mean_clamped / 255.0)
        gamma = np.clip(ideal_gamma, 1.0 - self.max_gamma_shift, 1.0 + self.max_gamma_shift)

        lut = self._build_gamma_lut(gamma)
        l_toned = cv2.LUT(l, lut)
        metrics["tonemap_time"] = time.perf_counter() - t_tone
        
        t_clahe = time.perf_counter()
        l_final = self.clahe.apply(l_toned)
        final_lab = cv2.merge((l_final, a, b))
        result = cv2.cvtColor(final_lab, cv2.COLOR_LAB2BGR)

        metrics["clahe_time"] = time.perf_counter() - t_clahe
        return result

    # =========================================================================
    # SINGLE FILE PROCESSOR
    # =========================================================================
    def copy_single_file(self, file_path, dest_root, stop_checker, apply_preprocessing, overwrite_inplace=False):
        """
        Processes or copies a single image file to a destination path or overwrites it in-place.

        Args:
            file_path (str): Absolute source path of the target image file.
            dest_root (str): Output destination root folder directory.
            stop_checker (callable): Function returning True if execution should stop.
            apply_preprocessing (bool): Whether to apply tone mapping and CLAHE filters.
            overwrite_inplace (bool, optional): If True, overwrites source file directly at source path.
                Defaults to False.

        Returns:
            tuple[str, dict]: Status string ('success', 'error', or 'stopped') and a performance metrics dictionary.
        """
        metrics = {
            "filename": os.path.basename(file_path),
            "total_time": 0.0,
            "read_time": 0.0,
            "tonemap_time": 0.0,
            "clahe_time": 0.0,
            "write_time": 0.0,
            "detail": ""
        }

        if stop_checker():
            return "stopped", metrics

        t_start = time.perf_counter()
        try:
            filename = os.path.basename(file_path)

            if overwrite_inplace:
                dest_path = file_path
            else:
                dest_path = os.path.join(dest_root, filename)

            if apply_preprocessing:
                t_read = time.perf_counter()
                img = cv2.imread(file_path)
                metrics["read_time"] = time.perf_counter() - t_read

                if img is not None:
                    result = self._preprocess_tone_clahe(img, metrics)

                    t_write = time.perf_counter()
                    if dest_path.lower().endswith(('.jpg', '.jpeg')):
                        cv2.imwrite(dest_path, result, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    elif dest_path.lower().endswith('.png'):
                        cv2.imwrite(dest_path, result, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
                    else:
                        cv2.imwrite(dest_path, result)
                    metrics["write_time"] = time.perf_counter() - t_write

                    metrics["total_time"] = time.perf_counter() - t_start
                    metrics["detail"] = f"[Overwritten In-Place] {filename}" if overwrite_inplace else f"[Processed & Saved] {filename}"
                    return "success", metrics
                else:
                    metrics["total_time"] = time.perf_counter() - t_start
                    metrics["detail"] = f"[Failed] Could not read {filename}"
                    return "error", metrics
            else:
                metrics["total_time"] = time.perf_counter() - t_start
                metrics["detail"] = f"[Skipped] No preprocessing applied in overwrite mode"
                return "success", metrics

        except Exception as e:
            metrics["total_time"] = time.perf_counter() - t_start
            metrics["detail"] = f"{os.path.basename(file_path)} -> {str(e)}"
            return "error", metrics

    def delete_only_images(self, dest_root):
        """
        Deletes image files within a target output directory while leaving subfolders intact.

        Args:
            dest_root (str): Target directory containing images to delete.

        Returns:
            int: Total number of deleted image files.
        """
        deleted_count = 0
        image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')
        
        if not os.path.exists(dest_root):
            return 0
            
        for filename in os.listdir(dest_root):
            file_path = os.path.join(dest_root, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(image_extensions):
                os.unlink(file_path)
                deleted_count += 1
        return deleted_count