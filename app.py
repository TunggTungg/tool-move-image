import os
import shutil
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Global theme configuration for Dark Mode
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class AdvancedPhotoCopyTool(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Advanced Photo Copy Tool")
        self.geometry("750x660") 
        self.resizable(False, False)

        icon_path = "icon.ico"
        if os.path.exists(icon_path):
            self.wm_iconbitmap(icon_path)

        # Variables to store paths and options
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.chk_original_var = tk.BooleanVar(value=True) 
        self.chk_processed_var = tk.BooleanVar(value=False)

        # Optimization: Cap at 8 threads to prevent disk I/O bottlenecks
        cpu_cores = os.cpu_count() or 4
        self.optimal_threads = min(cpu_cores * 2, 8)

        # Control flags for stopping/canceling tasks
        self.is_running = False
        self.stop_requested = False

        self.setup_ui()

    def setup_ui(self):
        # --- HEADER TITLE ---
        title_lbl = ctk.CTkLabel(self, text="PHOTO COPY TOOL", font=ctk.CTkFont(size=22, weight="bold"))
        title_lbl.pack(pady=15)

        # --- INPUT FOLDER SECTION ---
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", padx=20, pady=5)
        
        input_lbl = ctk.CTkLabel(input_frame, text="Source Folder (Input):", width=150, anchor="w")
        input_lbl.pack(side="left", padx=10, pady=10)
        
        self.input_entry = ctk.CTkEntry(input_frame, textvariable=self.input_dir, width=420)
        self.input_entry.pack(side="left", padx=5, pady=10)
        
        btn_browse_in = ctk.CTkButton(input_frame, text="Browse...", width=80, command=self.browse_input)
        btn_browse_in.pack(side="left", padx=10, pady=10)

        # --- OUTPUT FOLDER SECTION ---
        output_frame = ctk.CTkFrame(self)
        output_frame.pack(fill="x", padx=20, pady=5)
        
        output_lbl = ctk.CTkLabel(output_frame, text="Destination Folder (Output):", width=150, anchor="w")
        output_lbl.pack(side="left", padx=10, pady=10)
        
        self.output_entry = ctk.CTkEntry(output_frame, textvariable=self.output_dir, width=420)
        self.output_entry.pack(side="left", padx=5, pady=10)
        
        btn_browse_out = ctk.CTkButton(output_frame, text="Browse...", width=80, command=self.browse_output)
        btn_browse_out.pack(side="left", padx=10, pady=10)

        # --- CONFIGURATION & CONTROLS SECTION ---
        action_frame = ctk.CTkFrame(self)
        action_frame.pack(fill="x", padx=20, pady=10)

        checkbox_subframe = ctk.CTkFrame(action_frame, fg_color="transparent")
        checkbox_subframe.pack(side="left", fill="both", expand=True, padx=10, pady=5)

        option_title = ctk.CTkLabel(checkbox_subframe, text="Target Folder Type:", font=ctk.CTkFont(weight="bold"))
        option_title.pack(anchor="w", padx=10, pady=(2, 5))

        self.chk_original = ctk.CTkCheckBox(checkbox_subframe, text="Original", variable=self.chk_original_var)
        self.chk_original.pack(side="left", padx=10, pady=5)
        
        self.chk_processed = ctk.CTkCheckBox(checkbox_subframe, text="Processed", variable=self.chk_processed_var)
        self.chk_processed.pack(side="left", padx=20, pady=5)

        # Control Buttons Right Side
        self.btn_run = ctk.CTkButton(action_frame, text="RUN", font=ctk.CTkFont(size=14, weight="bold"), width=80, height=35, command=self.start_process)
        self.btn_run.pack(side="right", padx=5, pady=10)

        self.btn_stop = ctk.CTkButton(action_frame, text="STOP", font=ctk.CTkFont(size=14, weight="bold"), width=80, height=35, fg_color="#A83232", hover_color="#7A2424", command=self.stop_process, state="disabled")
        self.btn_stop.pack(side="right", padx=5, pady=10)

        self.btn_delete = ctk.CTkButton(action_frame, text="DELETE", font=ctk.CTkFont(size=14, weight="bold"), width=80, height=35, fg_color="#555555", hover_color="#333333", command=self.clear_output_folder)
        self.btn_delete.pack(side="right", padx=5, pady=10)

        # --- PROGRESS BAR ---
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.progress_lbl = ctk.CTkLabel(progress_frame, text="Progress: 0/0 images (0%)", font=ctk.CTkFont(size=12, weight="bold"))
        self.progress_lbl.pack(anchor="w", padx=5, pady=(0, 2))

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(fill="x", padx=5)
        self.progress_bar.set(0) 

        # --- LOGS WINDOW ---
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        log_title = ctk.CTkLabel(log_frame, text="Activity Logs:", font=ctk.CTkFont(size=12))
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.log_text = ctk.CTkTextbox(log_frame, state="disabled", font=("Courier New", 12))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        # Define color tags for specific logs inside Textbox
        self.log_text.tag_config("warning", foreground="#E6B800") # Dark Yellow/Gold for readability on dark background
        self.log_text.tag_config("error", foreground="#FF4D4D")   # Bright Red
        
        self.log(f"System optimization: Configured to run with {self.optimal_threads} parallel threads.")

    def log(self, message, level="info"):
        """Color-coded logging helper"""
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        
        # Determine log level tag styling
        level_tag = level.lower() if level.lower() in ["warning", "error"] else None
        
        self.log_text.insert("end", f"{timestamp}{message}\n", level_tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def browse_input(self):
        if self.is_running: return
        path = filedialog.askdirectory()
        if path: self.input_dir.set(path)

    def browse_output(self):
        if self.is_running: return
        path = filedialog.askdirectory()
        if path: self.output_dir.set(path)

    def stop_process(self):
        if self.is_running:
            self.stop_requested = True
            self.log("WARNING: Stop signal sent! Wrapping up active threads...", "warning")
            self.btn_stop.configure(state="disabled")

    def clear_output_folder(self):
        dest_root = self.output_dir.get()
        if not dest_root:
            self.log("ERROR: Please select a Destination Folder first!", "error")
            return
        
        if self.is_running:
            self.log("ERROR: Cannot delete files while a copy process is running!", "error")
            return

        # Confirmation box
        confirm = messagebox.askyesno(
            "Confirmation Required", 
            "Are you sure you want to delete ALL files inside the selected output directory?\nThis action cannot be undone."
        )
        
        if confirm:
            try:
                deleted_count = 0
                for filename in os.listdir(dest_root):
                    file_path = os.path.join(dest_root, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                        deleted_count += 1
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        deleted_count += 1
                
                self.log(f"Cleaned output folder. Removed {deleted_count} items successfully.")
                self.progress_lbl.configure(text="Progress: Output folder cleared.")
                self.progress_bar.set(0)
            except Exception as e:
                self.log(f"ERROR while cleaning directory: {str(e)}", "error")

    def start_process(self):
        if not self.input_dir.get() or not self.output_dir.get():
            self.log("ERROR: Please select both Input and Output folders!", "error")
            return
        
        if not self.chk_original_var.get() and not self.chk_processed_var.get():
            self.log("ERROR: You must select at least one folder type (Original or Processed)!", "error")
            return

        # Lock UI components
        self.is_running = True
        self.stop_requested = False
        self.btn_run.configure(state="disabled")
        self.btn_delete.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress_bar.set(0)
        self.progress_lbl.configure(text="Progress: Scanning directories...")
        
        threading.Thread(target=self.start_threaded_copy, daemon=True).start()

    def single_file_copy(self, file_path, dest_root):
        # Immediate break out if global stop flag is triggered
        if self.stop_requested:
            return "stopped", ""

        try:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(dest_root, filename)

            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_root, f"{base}_{counter}{extension}")
                counter += 1

            shutil.copy2(file_path, dest_path)
            return "success", filename
        except Exception as e:
            return "error", f"{os.path.basename(file_path)} -> {str(e)}"

    def start_threaded_copy(self):
        src_root = self.input_dir.get()
        dest_root = self.output_dir.get()

        allowed_types = []
        if self.chk_original_var.get(): allowed_types.append("original")
        if self.chk_processed_var.get(): allowed_types.append("processed")

        self.log("Scanning directories and counting files...")
        
        files_to_copy = []
        for root, dirs, files in os.walk(src_root):
            if self.stop_requested: break
            current_folder_name = os.path.basename(root).lower()
            if current_folder_name in allowed_types:
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')):
                        files_to_copy.append(os.path.join(root, file))

        total_files = len(files_to_copy)
        if total_files == 0 or self.stop_requested:
            if self.stop_requested:
                self.log("Process aborted during directory scan.", "warning")
            else:
                self.log("No valid images found matching the folder structure criteria.", "warning")
            self.reset_ui_state()
            return

        self.log(f"Found {total_files} images. Spawning worker thread pipeline...")

        copied_count = 0
        success_count = 0
        
        # ThreadPoolExecutor execution block
        with ThreadPoolExecutor(max_workers=self.optimal_threads) as executor:
            # Distribute tasks
            futures = [executor.submit(self.single_file_copy, path, dest_root) for path in files_to_copy]
            
            for future in futures:
                # Read dynamic completion tokens
                status, detail = future.result()
                copied_count += 1
                
                if status == "success":
                    success_count += 1
                    self.log(f"Copied: {detail}")
                elif status == "error":
                    self.log(f"ERROR: {detail}", "error")
                elif status == "stopped":
                    # Drop updates for threads skipped due to cancelation token
                    continue
                
                # Tqdm calculation outputs
                progress_value = copied_count / total_files
                percentage = int(progress_value * 100)
                self.progress_lbl.configure(text=f"Progress: {copied_count}/{total_files} images ({percentage}%)")
                self.progress_bar.set(progress_value)

        # Final logging checks based on execution termination
        if self.stop_requested:
            self.log(f"Process STOPPED by user. Only {success_count} files were processed.", "warning")
        else:
            self.log(f"Done! Successfully processed {success_count}/{total_files} images.")
            
        self.reset_ui_state()

    def reset_ui_state(self):
        """Unlocks control layout safely at execution completion"""
        self.is_running = False
        self.stop_requested = False
        self.btn_run.configure(state="normal")
        self.btn_delete.configure(state="normal")
        self.btn_stop.configure(state="disabled")

if __name__ == "__main__":
    app = AdvancedPhotoCopyTool()
    app.mainloop()


    