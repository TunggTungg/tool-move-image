"""
viewmodel.py
------------
ViewModel layer in the MVVM architecture.
Manages application state, multi-threaded worker pools, UI callbacks, hardware drive checks,
and persistent configuration caching.
"""

import os
import threading
import psutil
import json
from concurrent.futures import ThreadPoolExecutor
from model import PhotoCopyModel

# System cache file path for user settings persistence
HIDDEN_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".photocopy_tool_cache")


class PhotoCopyViewModel:
    """
    ViewModel class managing state logic, thread pools, UI callbacks, and configuration storage.

    Attributes:
        model (PhotoCopyModel): Model layer instance.
        is_running (bool): Execution lock state flag.
        stop_requested (bool): Flag indicating cancellation request.
        optimal_threads (int): Calculated optimal thread worker pool count.
        on_log_callback (callable): UI logging update function delegate.
        on_progress_callback (callable): UI progress bar update delegate.
        on_state_changed_callback (callable): UI state refresh delegate.
    """

    def __init__(self):
        """Initializes the ViewModel, worker pool limits, and UI callback delegates."""
        self.model = PhotoCopyModel()
        self.is_running = False
        self.stop_requested = False
        
        cpu_cores = os.cpu_count() or 4
        self.optimal_threads = min(cpu_cores * 2, 8)
        
        self.on_log_callback = None
        self.on_progress_callback = None
        self.on_state_changed_callback = None

    def set_callbacks(self, on_log, on_progress, on_state_changed):
        """
        Registers event callbacks connecting ViewModel notifications to View components.

        Args:
            on_log (callable): Function handling log message events.
            on_progress (callable): Function handling progress percentage updates.
            on_state_changed (callable): Function handling UI control state switches.
        """
        self.on_log_callback = on_log
        self.on_progress_callback = on_progress
        self.on_state_changed_callback = on_state_changed

    def log(self, message, level="info"):
        """
        Sends log messages to registered View UI log text widgets.

        Args:
            message (str): Text payload describing current state/event.
            level (str, optional): Message severity level ('info', 'warning', or 'error'). Defaults to "info".
        """
        if self.on_log_callback:
            self.on_log_callback(message, level)

    def check_stop(self):
        """
        Checks if a user cancellation signal was dispatched.

        Returns:
            bool: True if thread worker cancellation was requested.
        """
        return self.stop_requested

    def request_stop(self):
        """Triggers worker threads cancellation interrupt flag."""
        if self.is_running:
            self.stop_requested = True
            self.log("WARNING: Stop signal sent! Wrapping up active threads...", "warning")

    def save_config(self, input_dir, output_dir, clahe_clip, clahe_tile, scan_mode, overwrite_inplace):
        """
        Saves user settings parameters into a local JSON cache file.

        Args:
            input_dir (str): Path to current source directory.
            output_dir (str): Path to current output directory.
            clahe_clip (str): Current CLAHE clip setting string.
            clahe_tile (str): Current CLAHE grid dimension string.
            scan_mode (str): Directory scan mode option string.
            overwrite_inplace (bool): In-place direct overwrite flag.
        """
        try:
            config_data = {
                "input_dir": input_dir,
                "output_dir": output_dir,
                "clahe_clip": clahe_clip,
                "clahe_tile": clahe_tile,
                "scan_mode": scan_mode,
                "overwrite_inplace": overwrite_inplace
            }
            with open(HIDDEN_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def load_saved_config(self):
        """
        Loads user configuration settings from hidden system JSON cache file.

        Returns:
            dict: Persistent config dictionary or default fallback configuration values.
        """
        default_config = {
            "input_dir": "",
            "output_dir": "",
            "clahe_clip": "1.5",
            "clahe_tile": "8x8",
            "scan_mode": "all_in_folder",
            "overwrite_inplace": True
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
        """
        Triggers deletion of images inside the destination folder via Model layer.

        Args:
            dest_root (str): Target output directory path.

        Returns:
            bool: True if directory clear operation succeeded.
        """
        if not dest_root:
            self.log("ERROR: Please select a Destination Folder first!", "error")
            return False
        if self.is_running:
            self.log("ERROR: Cannot delete files while a process is running!", "error")
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
                            apply_preprocessing, clahe_clip, clahe_tile_str, scan_mode="all_in_folder", overwrite_inplace=True):
        """
        Validates parameters and launches asynchronous image batch processing worker thread.

        Args:
            src_root (str): Source directory path.
            dest_root (str): Output destination directory path.
            include_original (bool): Filter flag to scan 'Original' subfolders.
            include_processed (bool): Filter flag to scan 'Processed' subfolders.
            apply_preprocessing (bool): Toggle for tone mapping and CLAHE enhancements.
            clahe_clip (str): CLAHE clip input value string.
            clahe_tile_str (str): CLAHE tile selection string (e.g., '8x8').
            scan_mode (str, optional): Directory scan mode setting. Defaults to "all_in_folder".
            overwrite_inplace (bool, optional): Directly overwrite files at source location. Defaults to True.
        """
        if not src_root:
            self.log("ERROR: Please select an Input folder!", "error")
            return
        
        if not overwrite_inplace and not dest_root:
            self.log("ERROR: Please select a Destination (Output) folder!", "error")
            return
        
        scan_all = (scan_mode == "all_in_folder")
        if not scan_all and not include_original and not include_processed:
            self.log("ERROR: You must select at least one folder type (Original or Processed)!", "error")
            return

        try:
            clip_val = float(clahe_clip)
            tile_dim = int(clahe_tile_str.split('x')[0])
            tile_tuple = (tile_dim, tile_dim)
        except ValueError:
            self.log("ERROR: Invalid CLAHE parameters! Resetting to default (1.5, 8x8).", "error")
            clip_val = 1.5
            tile_tuple = (8, 8)

        self.model.update_clahe_config(clip_val, tile_tuple)

        self.is_running = True
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()

        if self.on_progress_callback:
            self.on_progress_callback(0, "Progress: Scanning directories...")

        threading.Thread(
            target=self._async_copy_worker, 
            args=(src_root, dest_root, include_original, include_processed, apply_preprocessing, scan_all, overwrite_inplace), 
            daemon=True
        ).start()

    def _is_usb_or_removable(self, path):
        """
        Detects if target path resides on a removable/USB volume to adapt thread limits.

        Args:
            path (str): Target directory file system path.

        Returns:
            bool: True if volume type is removable/USB drive.
        """
        if not path: return False
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

    def _async_copy_worker(self, src_root, dest_root, include_original, include_processed, apply_preprocessing, scan_all, overwrite_inplace):
        """
        Asynchronous thread worker executing parallel image processing tasks via ThreadPoolExecutor.

        Args:
            src_root (str): Source folder path.
            dest_root (str): Destination folder path.
            include_original (bool): Flag for 'original' subfolder scanning.
            include_processed (bool): Flag for 'processed' subfolder scanning.
            apply_preprocessing (bool): Preprocessing execution flag.
            scan_all (bool): Direct full-directory scan flag.
            overwrite_inplace (bool): Direct file overwrite flag.
        """
        allowed_types = []
        if include_original: allowed_types.append("original")
        if include_processed: allowed_types.append("processed")

        self.log("Scanning directories and counting files...")
        files_to_copy = self.model.scan_images(src_root, allowed_types, self.check_stop, scan_all=scan_all)
        
        total_files = len(files_to_copy)
        if total_files == 0 or self.stop_requested:
            if self.stop_requested:
                self.log("Process aborted during directory scan.", "warning")
            else:
                self.log("No valid images found matching the criteria.", "warning")
            self._terminate_process(0, 0, total_files)
            return

        is_usb = self._is_usb_or_removable(src_root if overwrite_inplace else dest_root)
        active_threads = 1 if is_usb else self.optimal_threads

        if is_usb:
            self.log("⚠️ DETECTED REMOVABLE DRIVE (USB): Thread count locked to 1 to maximize hardware write speed.", "warning")

        mode_desc = "Process In-Place (Overwrite Original)" if overwrite_inplace else "Save to Output Folder"
        prep_desc = f"CLAHE [Clip: {self.model.clahe_clip}, Tile: {self.model.clahe_tile[0]}x{self.model.clahe_tile[1]}]" if apply_preprocessing else "Pure Copy"
        self.log(f"Found {total_files} images. Spawning {active_threads} worker threads ({mode_desc} | {prep_desc})...")

        copied_count = 0
        success_count = 0

        with ThreadPoolExecutor(max_workers=active_threads) as executor:
            futures = [
                executor.submit(self.model.copy_single_file, path, dest_root, self.check_stop, apply_preprocessing, overwrite_inplace) 
                for path in files_to_copy
            ]
            
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
                        pure_log = f"[{copied_count}/{total_files}] {metrics['filename']} updated."
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
        """
        Cleans up pipeline state flags and updates UI logs upon batch completion or cancellation.

        Args:
            success_count (int): Successfully processed image file count.
            total_files (int): Total queued image file count.
            scanned_files (int): Total discovered file count.
        """
        if self.stop_requested:
            self.log(f"Process STOPPED by user. Only {success_count} files were processed.", "warning")
        else:
            self.log(f"Done! Successfully processed {success_count}/{scanned_files} images.")
            
        self.is_running = False
        self.stop_requested = False
        if self.on_state_changed_callback:
            self.on_state_changed_callback()