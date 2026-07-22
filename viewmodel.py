import os
import threading
import psutil
import json
from concurrent.futures import ThreadPoolExecutor
from model import PhotoCopyModel

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

    def save_config(self, input_dir, output_dir, clahe_clip, clahe_tile):
        """Lưu đường dẫn và thông số CLAHE vào file ẩn dạng JSON."""
        try:
            config_data = {
                "input_dir": input_dir,
                "output_dir": output_dir,
                "clahe_clip": clahe_clip,
                "clahe_tile": clahe_tile
            }
            with open(HIDDEN_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def load_saved_config(self):
        """Tải đường dẫn và cài đặt CLAHE từ file ẩn."""
        default_config = {
            "input_dir": "",
            "output_dir": "",
            "clahe_clip": "1.5",
            "clahe_tile": "8x8"
        }
        if os.path.exists(HIDDEN_CONFIG_PATH):
            try:
                with open(HIDDEN_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception:
                pass
        return default_config

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

    def start_copy_pipeline(self, src_root, dest_root, include_original, include_processed, 
                            apply_preprocessing, clahe_clip, clahe_tile_str):
        if not src_root or not dest_root:
            self.log("ERROR: Please select both Input and Output folders!", "error")
            return
        if not include_original and not include_processed:
            self.log("ERROR: You must select at least one folder type (Original or Processed)!", "error")
            return

        # Parse thông số CLAHE
        try:
            clip_val = float(clahe_clip)
            tile_dim = int(clahe_tile_str.split('x')[0])
            tile_tuple = (tile_dim, tile_dim)
        except ValueError:
            self.log("ERROR: Invalid CLAHE parameters! Resetting to default (1.5, 8x8).", "error")
            clip_val = 1.5
            tile_tuple = (8, 8)

        # Cập nhật thông số vào Model
        self.model.update_clahe_config(clip_val, tile_tuple)

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
        try:
            abs_path = os.path.abspath(path)
            partitions = psutil.disk_partitions(all=True)
            partitions.sort(key=lambda x: len(x.mountpoint), reverse=True)
            
            for p in partitions:
                if abs_path.startswith(p.mountpoint):
                    if 'removable' in p.opts or 'cdrom' in p.opts:
                        return True
                    if os.name == 'nt':
                        import win32file
                        drive_type = win32file.GetDriveType(p.mountpoint)
                        if drive_type == win32file.DRIVE_REMOVABLE:
                            return True
                    break
            return False
        except Exception:
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

        is_usb = self._is_usb_or_removable(dest_root)
        active_threads = 1 if is_usb else self.optimal_threads

        if is_usb:
            self.log("⚠️ DETECTED REMOVABLE DRIVE (USB): Thread count locked to 1 to maximize hardware write speed.", "warning")

        mode_str = f"Preprocessing [Clip: {self.model.clahe_clip}, Tile: {self.model.clahe_tile[0]}x{self.model.clahe_tile[1]}]" if apply_preprocessing else "pure copy mode"
        self.log(f"Found {total_files} images. Spawning {active_threads} worker threads ({mode_str})...")

        copied_count = 0
        success_count = 0

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
                            f"Write: {metrics['write_time']:.3f}s"
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