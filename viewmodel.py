import os
import threading
import psutil
from concurrent.futures import ThreadPoolExecutor
from model import PhotoCopyModel
import json 
HIDDEN_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".photocopy_tool_cache")

class PhotoCopyViewModel:
    def __init__(self):
        self.model = PhotoCopyModel()
        self.is_running = False
        self.stop_requested = False
        
        cpu_cores = os.cpu_count() or 4
        self.optimal_threads = min(cpu_cores * 2, 8)
        
        self.on_log_callback = None
        self.on_progress_callback = None
        self.on_state_changed_callback = None

    def set_callbacks(self, on_log, on_progress, on_state_changed):
        self.on_log_callback = on_log
        self.on_progress_callback = on_progress
        self.on_state_changed_callback = on_state_changed

    def log(self, message, level="info"):
        if self.on_log_callback:
            self.on_log_callback(message, level)

    def check_stop(self):
        return self.stop_requested

    def request_stop(self):
        if self.is_running:
            self.stop_requested = True
            self.log("WARNING: Stop signal sent! Wrapping up active threads...", "warning")

    def save_paths(self, input_dir, output_dir):
        """Lưu đường dẫn vào file ẩn của hệ thống, không sinh file rác tại thư mục app"""
        try:
            # Tạo dictionary chứa dữ liệu cần lưu
            config_data = {
                "input_dir": input_dir,
                "output_dir": output_dir
            }
            # Ghi đè vào file ẩn dưới dạng JSON
            with open(HIDDEN_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            pass

    def load_saved_paths(self):
        """Tải đường dẫn từ thư mục ẩn hệ thống"""
        if os.path.exists(HIDDEN_CONFIG_PATH):
            try:
                with open(HIDDEN_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("input_dir", ""), data.get("output_dir", "")
            except Exception:
                pass
        return "", ""

    def execute_delete(self, dest_root):
        if not dest_root:
            self.log("ERROR: Please select a Destination Folder first!", "error")
            return False
        if self.is_running:
            self.log("ERROR: Cannot delete files while a copy process is running!", "error")
            return False
            
        try:
            count = self.model.delete_only_images(dest_root)
            self.log(f"Cleaned output folder. Removed {count} items successfully.")
            if self.on_progress_callback:
                self.on_progress_callback(0, "Progress: Output folder cleared.")
            return True
        except Exception as e:
            self.log(f"ERROR while cleaning directory: {str(e)}", "error")
            return False

    def start_copy_pipeline(self, src_root, dest_root, include_original, include_processed, apply_preprocessing):
        if not src_root or not dest_root:
            self.log("ERROR: Please select both Input and Output folders!", "error")
            return
        if not include_original and not include_processed:
            self.log("ERROR: You must select at least one folder type (Original or Processed)!", "error")
            return

        self.is_running = True
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()

        if self.on_progress_callback:
            self.on_progress_callback(0, "Progress: Scanning directories...")

        threading.Thread(
            target=self._async_copy_worker, 
            args=(src_root, dest_root, include_original, include_processed, apply_preprocessing), 
            daemon=True
        ).start()

    def _is_usb_or_removable(self, path):
        """
        A function that checks whether a path is located on a USB drive or a removable drive.
        """
        try:
            # Lấy đường dẫn tuyệt đối chuẩn hóa
            abs_path = os.path.abspath(path)
            
            # Quét qua toàn bộ các ổ đĩa/phân vùng đang kết nối vào máy tính
            partitions = psutil.disk_partitions(all=True)
            
            # Sắp xếp các phân vùng theo độ dài ký tự giảm dần để khớp chính xác nhất (VD: F:\\ trước F:\\Folder)
            partitions.sort(key=lambda x: len(x.mountpoint), reverse=True)
            
            for p in partitions:
                # Kiểm tra xem đường dẫn đích có bắt đầu bằng tên ổ đĩa này không
                if abs_path.startswith(p.mountpoint):
                    # 'removable' đại diện cho USB, Thẻ nhớ, Ổ đĩa di động cắm ngoài
                    if 'removable' in p.opts or 'cdrom' in p.opts:
                        return True
                    
                    # Backup check cho Windows: Ổ USB thường không có tùy chọn 'removable' trong p.opts ở một số bản cập nhật
                    # nhưng nó sẽ chứa thuộc tính hệ thống hoặc nằm ngoài phân vùng mặc định (C, D nội bộ)
                    if os.name == 'nt': # Nếu là Windows
                        import win32file # Thư viện đi kèm mặc định nếu dùng môi trường chuẩn
                        drive_type = win32file.GetDriveType(p.mountpoint)
                        if drive_type == win32file.DRIVE_REMOVABLE:
                            return True
                    break
            return False
        except Exception:
            # Nếu có lỗi (hoặc không có thư viện win32file), dùng giải pháp loại trừ an toàn:
            # Trên Mac/Linux, USB thường nằm trong thư mục /Volumes hoặc /media
            if "/Volumes/" in abs_path or "/media/" in abs_path:
                return True
            return False

    def _async_copy_worker(self, src_root, dest_root, include_original, include_processed, apply_preprocessing):
        allowed_types = []
        if include_original: allowed_types.append("original")
        if include_processed: allowed_types.append("processed")

        self.log("Scanning directories and counting files...")
        files_to_copy = self.model.scan_images(src_root, allowed_types, self.check_stop)
        
        total_files = len(files_to_copy)
        if total_files == 0 or self.stop_requested:
            if self.stop_requested:
                self.log("Process aborted during directory scan.", "warning")
            else:
                self.log("No valid images found matching the folder structure criteria.", "warning")
            self._terminate_process(0, 0, total_files)
            return

        # --- 🚀 Cải tiến: TỰ ĐỘNG ĐIỀU CHỈNH LUỒNG (WORKERS) DỰA TRÊN THIẾT BỊ ĐÍCH ---
        is_usb = self._is_usb_or_removable(dest_root)
        
        if is_usb:
            # Nếu ghi vào USB: Ép xuống 1 hoặc tối đa 2 luồng để tránh nghẽn I/O làm đứng hệ thống
            active_threads = 1 
            self.log("⚠️ DETECTED REMOVABLE DRIVE (USB): Thread count locked to 1 to maximize hardware write speed.", "warning")
        else:
            # Nếu ghi vào SSD/HDD nội bộ (C:, D:): Giữ nguyên số luồng tối ưu (4-8 luồng)
            active_threads = self.optimal_threads

        mode_str = "with Advanced Preprocessing" if apply_preprocessing else "pure copy mode"
        self.log(f"Found {total_files} images. Spawning {active_threads} worker threads running in {mode_str}...")

        copied_count = 0
        success_count = 0

        # Thay thế self.optimal_threads bằng biến active_threads vừa tính toán
        with ThreadPoolExecutor(max_workers=active_threads) as executor:
            futures = [executor.submit(self.model.copy_single_file, path, dest_root, self.check_stop, apply_preprocessing) for path in files_to_copy]
            
            for future in futures:
                status, metrics = future.result()
                copied_count += 1
                
                if status == "success":
                    success_count += 1
                    if apply_preprocessing and metrics["tonemap_time"] > 0:
                        perf_log = (
                            f"[{copied_count}/{total_files}] {metrics['filename']} processed in {metrics['total_time']:.3f}s | "
                            f"Read: {metrics['read_time']:.3f}s | "
                            f"CLAHE: {metrics['clahe_time']:.3f}s | "
                            f"ToneMap: {metrics['tonemap_time']:.3f}s | "
                            f"Write: {metrics['write_time']:.3f}s"
                        )
                        self.log(perf_log, "info")
                    else:
                        pure_log = (
                            f"[{copied_count}/{total_files}] {metrics['filename']} copied in {metrics['total_time']:.3f}s | "
                            f"Read/Prep: 0.000s | CLAHE: 0.000s | ToneMap: 0.000s | Write: {metrics['write_time']:.3f}s"
                        )
                        self.log(pure_log, "info")
                        
                elif status == "error":
                    self.log(f"ERROR: {metrics['detail']}", "error")
                elif status == "stopped":
                    continue
                
                progress_val = copied_count / total_files
                percentage = int(progress_val * 100)
                msg = f"Progress: {copied_count}/{total_files} images ({percentage}%)"
                if self.on_progress_callback:
                    self.on_progress_callback(progress_val, msg)

        self._terminate_process(success_count, total_files, total_files)

    def _terminate_process(self, success_count, total_files, scanned_files):
        if self.stop_requested:
            self.log(f"Process STOPPED by user. Only {success_count} files were processed.", "warning")
        else:
            self.log(f"Done! Successfully processed {success_count}/{scanned_files} images.")
            
        self.is_running = False
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()