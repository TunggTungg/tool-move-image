import os
import shutil
import cv2
import numpy as np
import time
from ultralytics.data.augment import LetterBox

class PhotoCopyModel:
    def __init__(self, imgsz=640, pad_color=114, target_mean=128.0, 
                 max_gamma_shift=0.4, clahe_clip=1.5, clahe_tile=(8, 8)):
        self.letterbox = LetterBox(new_shape=(imgsz, imgsz), auto=False, 
                                     scaleup=True, 
                                     center=True, stride=32)
        self.pad_color = pad_color
        self.target_mean = target_mean
        self.max_gamma_shift = max_gamma_shift
        self.update_clahe_config(clahe_clip, clahe_tile)

    def update_clahe_config(self, clahe_clip, clahe_tile):
        """Cập nhật thông số CLAHE động từ giao diện người dùng."""
        self.clahe_clip = float(clahe_clip)
        self.clahe_tile = tuple(clahe_tile)
        self.clahe = cv2.createCLAHE(clipLimit=self.clahe_clip, tileGridSize=self.clahe_tile)

    def scan_images(self, src_root, allowed_types, stop_checker):
        files_to_copy = []
        for root, dirs, files in os.walk(src_root):
            if stop_checker():
                break
            current_folder_name = os.path.basename(root).lower()
            if current_folder_name in allowed_types:
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')):
                        files_to_copy.append(os.path.join(root, file))
        return files_to_copy

    # =========================================================================
    # KHO CHỨA CÁC HÀM TIỀN XỬ LÝ (PREPROCESSING MODULES)
    # =========================================================================
    def _build_gamma_lut(self, gamma):
        """Build LUT 256 phần tử cho gamma correction."""
        indices = np.arange(256, dtype=np.float32)
        lut = np.clip((indices / 255.0) ** gamma * 255.0, 0, 255).astype(np.uint8)
        return lut

    def _preprocess_tone_clahe(self, img, metrics):
        """Hàm xử lý Tone Mapping + CLAHE."""
        # --- BƯỚC 1: LETTERBOX BẰNG ULTRALYTICS ---
        orig_h, orig_w = img.shape[:2]
        letterboxed = self.letterbox(image=img)
        
        new_h, new_w = letterboxed.shape[:2]
        scale = min(new_h / orig_h, new_w / orig_w)
        resized_h, resized_w = round(orig_h * scale), round(orig_w * scale)
        pad_h, pad_w = (new_h - resized_h) / 2, (new_w - resized_w) / 2
        top, left = int(round(pad_h - 0.1)), int(round(pad_w - 0.1))

        # --- BƯỚC 2: TONE MAPPING ADAPTIVE ---
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
        
        # --- BƯỚC 3: CLAHE ---
        t_clahe = time.perf_counter()
        l_final = self.clahe.apply(l_toned)
        final_lab = cv2.merge((l_final, a, b))
        result = cv2.cvtColor(final_lab, cv2.COLOR_LAB2BGR)

        metrics["clahe_time"] = time.perf_counter() - t_clahe
        return result

    def copy_single_file(self, file_path, dest_root, stop_checker, apply_preprocessing):
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
            dest_path = os.path.join(dest_root, filename)

            counter = 1
            base, extension = os.path.splitext(filename)
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_root, f"{base}_{counter}{extension}")
                counter += 1

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
                    metrics["detail"] = f"[Processed & Copied] {filename}"
                    return "success", metrics
                else:
                    t_write = time.perf_counter()
                    shutil.copy2(file_path, dest_path)
                    metrics["write_time"] = time.perf_counter() - t_write
                    metrics["total_time"] = time.perf_counter() - t_start
                    metrics["detail"] = f"[Backup Copied] {filename} (OpenCV Read Failed)"
                    return "success", metrics
            else:
                t_write = time.perf_counter()
                shutil.copy2(file_path, dest_path)
                metrics["write_time"] = time.perf_counter() - t_write
                metrics["total_time"] = time.perf_counter() - t_start
                metrics["detail"] = filename
                return "success", metrics

        except Exception as e:
            metrics["total_time"] = time.perf_counter() - t_start
            metrics["detail"] = f"{os.path.basename(file_path)} -> {str(e)}"
            return "error", metrics

    def delete_only_images(self, dest_root):
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