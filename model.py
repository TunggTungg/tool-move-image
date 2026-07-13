import os
import shutil
import cv2
import numpy as np
import time

class PhotoCopyModel:
    def __init__(self):
        pass

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

    def _preprocess_tone_clahe(self, img, metrics):
        """
        Hàm xử lý số 1: Tone Mapping + CLAHE
        Nhận vào ảnh gốc và dict metrics để cập nhật thời gian chi tiết của từng bước.
        Trả về: Ảnh sau xử lý.
        """

        # --- BƯỚC 1: TONE MAPPING ---
        t_tone = time.perf_counter()
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_float = l.astype(np.float32) / 255.0
        l_tonemapped = l_float / (l_float + 0.2)
        l_gamma = np.power(l_tonemapped, 1.0 / 1.2)

        # Khôi phục lại định dạng 8-bit chuẩn
        l_toned_8bit = np.clip(l_gamma * 255.0, 0, 255).astype(np.uint8)
        metrics["tonemap_time"] = time.perf_counter() - t_tone
        
        # --- BƯỚC 2: LAB + CLAHE ---
        t_clahe = time.perf_counter()
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(32, 32))
        l_final = clahe.apply(l_toned_8bit)
        final_lab = cv2.merge((l_final, a, b))
        result = cv2.cvtColor(final_lab, cv2.COLOR_LAB2BGR)

        metrics["clahe_time"] = time.perf_counter() - t_clahe

        return result

    def _preprocess_future_style(self, img, metrics):
        """
        [Ví dụ] Hàm xử lý số 2: Sau này bạn muốn thêm bộ lọc khác (Ví dụ: chuyển ảnh xám, làm nét...)
        Chỉ cần viết ở đây và gọi nó trong hàm copy_single_file.
        """
        # t_start = time.perf_counter()
        # logic xử lý của bạn...
        # metrics["future_process_time"] = time.perf_counter() - t_start
        return img

    # =========================================================================
    # HÀM QUẢN LÝ ĐIỀU PHỐI I/O VÀ LOGIC COPY
    # =========================================================================

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

            # Xử lý trùng tên file
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_root, f"{base}_{counter}{extension}")
                counter += 1

            # NẾU CÓ TIỀN XỬ LÝ
            if apply_preprocessing:
                t_read = time.perf_counter()
                img = cv2.imread(file_path)
                metrics["read_time"] = time.perf_counter() - t_read

                if img is not None:
                    # >>> GỌI HÀM TIỀN XỬ LÝ ĐÃ ĐƯỢC TÁCH RIÊNG Ở ĐÂY <<<
                    # Sau này nếu có nhiều option, bạn có thể truyền tham số `preprocess_type` 
                    # để dùng câu lệnh if-else chọn hàm xử lý tương ứng cực kỳ linh hoạt.
                    result = self._preprocess_tone_clahe(img, metrics)

                    # Ghi file xuống đĩa (đã tối ưu nén để tăng tốc cho USB)
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
                    # Nếu OpenCV lỗi không đọc được, hạ cấp xuống copy thuần
                    t_write = time.perf_counter()
                    shutil.copy2(file_path, dest_path)
                    metrics["write_time"] = time.perf_counter() - t_write
                    metrics["total_time"] = time.perf_counter() - t_start
                    metrics["detail"] = f"[Backup Copied] {filename} (OpenCV Read Failed)"
                    return "success", metrics
            
            # NẾU KHÔNG CÓ TIỀN XỬ LÝ (Pure Copy)
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