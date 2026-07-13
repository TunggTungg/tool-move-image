import os
import threading
from concurrent.futures import ThreadPoolExecutor
from model import PhotoCopyModel

class PhotoCopyViewModel:
    def __init__(self):
        self.model = PhotoCopyModel()
        
        # Trạng thái Logic (State)
        self.is_running = False
        self.stop_requested = False
        
        # Cấu hình phần cứng tối ưu
        cpu_cores = os.cpu_count() or 4
        self.optimal_threads = min(cpu_cores * 2, 8)
        
        # Các hàm callback dùng để thông báo cho View cập nhật giao diện
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

    def execute_delete(self, dest_root):
        """Xử lý logic xóa thư mục thông qua Model"""
        if not dest_root:
            self.log("ERROR: Please select a Destination Folder first!", "error")
            return False
        if self.is_running:
            self.log("ERROR: Cannot delete files while a copy process is running!", "error")
            return False
            
        try:
            count = self.model.delete_all_files(dest_root)
            self.log(f"Cleaned output folder. Removed {count} items successfully.")
            if self.on_progress_callback:
                self.on_progress_callback(0, "Progress: Output folder cleared.")
            return True
        except Exception as e:
            self.log(f"ERROR while cleaning directory: {str(e)}", "error")
            return False

    def start_copy_pipeline(self, src_root, dest_root, include_original, include_processed):
        """Kích hoạt luồng chạy ngầm để không làm đơ giao diện"""
        if not src_root or not dest_root:
            self.log("ERROR: Please select both Input and Output folders!", "error")
            return
        if not include_original and not include_processed:
            self.log("ERROR: You must select at least one folder type (Original or Processed)!", "error")
            return

        # Cập nhật trạng thái bắt đầu
        self.is_running = True
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()

        if self.on_progress_callback:
            self.on_progress_callback(0, "Progress: Scanning directories...")

        # Chạy tác vụ nặng trên một Thread riêng biệt
        threading.Thread(target=self._async_copy_worker, args=(src_root, dest_root, include_original, include_processed), daemon=True).start()

    def _async_copy_worker(self, src_root, dest_root, include_original, include_processed):
        """Luồng xử lý dữ liệu lõi"""
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

        self.log(f"Found {total_files} images. Spawning {self.optimal_threads} worker threads...")

        copied_count = 0
        success_count = 0

        with ThreadPoolExecutor(max_workers=self.optimal_threads) as executor:
            futures = [executor.submit(self.model.copy_single_file, path, dest_root, self.check_stop) for path in files_to_copy]
            
            for future in futures:
                status, detail = future.result()
                copied_count += 1
                
                if status == "success":
                    success_count += 1
                    self.log(f"Copied: {detail}")
                elif status == "error":
                    self.log(f"ERROR: {detail}", "error")
                elif status == "stopped":
                    continue
                
                # Bắn tiến trình cập nhật về cho View
                progress_val = copied_count / total_files
                percentage = int(progress_val * 100)
                msg = f"Progress: {copied_count}/{total_files} images ({percentage}%)"
                if self.on_progress_callback:
                    self.on_progress_callback(progress_val, msg)

        self._terminate_process(success_count, total_files, total_files)

    def _terminate_process(self, success_count, total_files, scanned_files):
        """Dọn dẹp trạng thái khi kết thúc tiến trình"""
        if self.stop_requested:
            self.log(f"Process STOPPED by user. Only {success_count} files were processed.", "warning")
        else:
            self.log(f"Done! Successfully processed {success_count}/{scanned_files} images.")
            
        self.is_running = False
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()