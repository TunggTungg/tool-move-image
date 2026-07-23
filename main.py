"""
main.py
-------
View layer in the MVVM architecture built with CustomTkinter GUI framework.
Handles user interface rendering, widget state toggles, user input events, and application entry point.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from datetime import datetime
from viewmodel import PhotoCopyViewModel

# Set GUI theme defaults
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PhotoCopyView(ctk.CTk):
    """
    Main GUI application window class rendering CustomTkinter interface controls.

    Attributes:
        vm (PhotoCopyViewModel): ViewModel layer instance.
        input_dir (tk.StringVar): Bound string variable for input folder path.
        output_dir (tk.StringVar): Bound string variable for output folder path.
        chk_original_var (tk.BooleanVar): Checkbox state for scanning 'original' subfolders.
        chk_processed_var (tk.BooleanVar): Checkbox state for scanning 'processed' subfolders.
        chk_preprocess_var (tk.BooleanVar): Checkbox state for enabling tone mapping & CLAHE.
        clahe_clip_var (tk.StringVar): String variable holding CLAHE clip input limit.
        clahe_tile_var (tk.StringVar): String variable holding CLAHE grid configuration.
        scan_mode_var (tk.StringVar): Radio button value string for directory scan mode.
        chk_overwrite_inplace_var (tk.BooleanVar): Checkbox state for in-place overwrite.
    """

    def __init__(self, viewModel):
        """
        Initializes view window layout, control variables, and ViewModel callbacks.

        Args:
            viewModel (PhotoCopyViewModel): Instance of the ViewModel handling application logic.
        """
        super().__init__()
        self.vm = viewModel

        self.title("Advanced Photo Processing & Copy Tool")
        self.geometry("800x820") 
        self.resizable(False, False)

        # Application window icon configuration
        if getattr(sys, 'frozen', False):
            self.wm_iconbitmap(sys.executable)
        else:
            icon_path = os.path.abspath("app_icon.ico")
            if os.path.exists(icon_path):
                self.wm_iconbitmap(icon_path)

        # Load saved configuration from cache
        saved_config = self.vm.load_saved_config()
        self.input_dir = tk.StringVar(value=saved_config["input_dir"])
        self.output_dir = tk.StringVar(value=saved_config["output_dir"])
        self.chk_original_var = tk.BooleanVar(value=True) 
        self.chk_processed_var = tk.BooleanVar(value=False)
        self.chk_preprocess_var = tk.BooleanVar(value=True) 
        
        self.clahe_clip_var = tk.StringVar(value=saved_config["clahe_clip"])
        self.clahe_tile_var = tk.StringVar(value=saved_config["clahe_tile"])
        self.scan_mode_var = tk.StringVar(value=saved_config["scan_mode"]) 
        self.chk_overwrite_inplace_var = tk.BooleanVar(value=saved_config["overwrite_inplace"])

        self.setup_ui()
        self.vm.set_callbacks(self.update_log_ui, self.update_progress_ui, self.update_controls_state_ui)
        
        self.update_log_ui(f"System optimization: Configured to run with {self.vm.optimal_threads} parallel threads.")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        """Constructs layout hierarchy and populates widgets on screen."""
        title_lbl = ctk.CTkLabel(self, text="PHOTO PROCESSING TOOL", font=ctk.CTkFont(size=22, weight="bold"))
        title_lbl.pack(pady=15)

        # --- FOLDER SELECTION FRAME ---
        input_frame = ctk.CTkFrame(self)
        input_frame.pack(fill="x", padx=20, pady=5)
        
        input_lbl = ctk.CTkLabel(input_frame, text="Source Folder (Input):", width=160, anchor="w")
        input_lbl.pack(side="left", padx=10, pady=8)
        
        self.input_entry = ctk.CTkEntry(input_frame, textvariable=self.input_dir, width=460)
        self.input_entry.pack(side="left", padx=5, pady=8)
        
        btn_browse_in = ctk.CTkButton(input_frame, text="Browse...", width=80, command=self.browse_input)
        btn_browse_in.pack(side="left", padx=10, pady=8)

        # Output Folder Frame
        self.output_frame = ctk.CTkFrame(self)
        self.output_frame.pack(fill="x", padx=20, pady=5)
        
        self.output_lbl = ctk.CTkLabel(self.output_frame, text="Destination Folder (Output):", width=160, anchor="w")
        self.output_lbl.pack(side="left", padx=10, pady=8)
        
        self.output_entry = ctk.CTkEntry(self.output_frame, textvariable=self.output_dir, width=460)
        self.output_entry.pack(side="left", padx=5, pady=8)
        
        self.btn_browse_out = ctk.CTkButton(self.output_frame, text="Browse...", width=80, command=self.browse_output)
        self.btn_browse_out.pack(side="left", padx=10, pady=8)

        # --- CONFIGURATION FRAME ---
        config_frame = ctk.CTkFrame(self)
        config_frame.pack(fill="x", padx=20, pady=8)

        option_title = ctk.CTkLabel(config_frame, text="Scan & Processing Options:", font=ctk.CTkFont(weight="bold"))
        option_title.pack(anchor="w", padx=15, pady=(8, 4))

        # Scan Mode Radio Buttons
        mode_container = ctk.CTkFrame(config_frame, fg_color="transparent")
        mode_container.pack(fill="x", padx=10, pady=(0, 5))

        self.rad_scan_all = ctk.CTkRadioButton(
            mode_container, 
            text="Process ALL Images in Input Folder", 
            variable=self.scan_mode_var, 
            value="all_in_folder",
            command=self.toggle_scan_mode_ui
        )
        self.rad_scan_all.pack(side="left", padx=10, pady=5)

        self.rad_scan_sub = ctk.CTkRadioButton(
            mode_container, 
            text="Filter Subfolders ('Original' / 'Processed')", 
            variable=self.scan_mode_var, 
            value="subfolder",
            command=self.toggle_scan_mode_ui
        )
        self.rad_scan_sub.pack(side="left", padx=15, pady=5)

        # Subfolder Filters Container
        self.subfolder_container = ctk.CTkFrame(config_frame, fg_color="transparent")
        self.subfolder_container.pack(fill="x", padx=30, pady=(0, 5))

        self.chk_original = ctk.CTkCheckBox(self.subfolder_container, text="Scan 'Original'", variable=self.chk_original_var)
        self.chk_original.pack(side="left", padx=10, pady=2)

        self.chk_processed = ctk.CTkCheckBox(self.subfolder_container, text="Scan 'Processed'", variable=self.chk_processed_var)
        self.chk_processed.pack(side="left", padx=15, pady=2)

        # UI Separator line
        ctk.CTkFrame(config_frame, height=1, fg_color="#3A3A3A").pack(fill="x", padx=15, pady=5)

        # Preprocessing & In-Place Overwrite Controls
        prep_container = ctk.CTkFrame(config_frame, fg_color="transparent")
        prep_container.pack(fill="x", padx=10, pady=(2, 5))

        self.chk_preprocess = ctk.CTkCheckBox(
            prep_container, 
            text="Apply Preprocessing (Tone Mapping + CLAHE)", 
            variable=self.chk_preprocess_var, 
            fg_color="#2B719E",
            command=self.toggle_clahe_inputs
        )
        self.chk_preprocess.pack(side="left", padx=10, pady=5)

        self.chk_overwrite_inplace = ctk.CTkCheckBox(
            prep_container, 
            text="Overwrite directly in Input Folder (No Output needed)", 
            variable=self.chk_overwrite_inplace_var, 
            fg_color="#A85A32",
            command=self.toggle_output_folder_ui
        )
        self.chk_overwrite_inplace.pack(side="left", padx=20, pady=5)

        # CLAHE Parameters Controls Frame
        self.clahe_frame = ctk.CTkFrame(config_frame, fg_color="#2B2B2B", corner_radius=6)
        self.clahe_frame.pack(fill="x", padx=20, pady=(0, 10))

        clip_lbl = ctk.CTkLabel(self.clahe_frame, text="CLAHE Clip Limit:", font=ctk.CTkFont(size=12))
        clip_lbl.pack(side="left", padx=(15, 5), pady=8)
        
        self.clip_entry = ctk.CTkEntry(self.clahe_frame, textvariable=self.clahe_clip_var, width=70, justify="center")
        self.clip_entry.pack(side="left", padx=(0, 25), pady=8)

        tile_lbl = ctk.CTkLabel(self.clahe_frame, text="CLAHE Tile Grid:", font=ctk.CTkFont(size=12))
        tile_lbl.pack(side="left", padx=(0, 5), pady=8)

        self.tile_menu = ctk.CTkOptionMenu(
            self.clahe_frame, 
            values=["4x4", "8x8", "16x16", "32x32"], 
            variable=self.clahe_tile_var, 
            width=90
        )
        self.tile_menu.pack(side="left", padx=(0, 15), pady=8)

        # --- ACTION BUTTONS FRAME ---
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=5)

        self.btn_delete = ctk.CTkButton(control_frame, text="DELETE OUTPUT", font=ctk.CTkFont(size=13, weight="bold"), width=150, height=40, fg_color="#555555", hover_color="#333333", command=self.on_delete_clicked)
        self.btn_delete.pack(side="left", pady=5)

        self.btn_stop = ctk.CTkButton(control_frame, text="STOP", font=ctk.CTkFont(size=13, weight="bold"), width=120, height=40, fg_color="#A83232", hover_color="#7A2424", command=self.vm.request_stop, state="disabled")
        self.btn_stop.pack(side="right", padx=5, pady=5)

        self.btn_run = ctk.CTkButton(control_frame, text="RUN PIPELINE", font=ctk.CTkFont(size=13, weight="bold"), width=150, height=40, fg_color="#1F6AA5", hover_color="#144871", command=self.on_run_clicked)
        self.btn_run.pack(side="right", padx=5, pady=5)

        # --- PROGRESS BAR FRAME ---
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.pack(fill="x", padx=20, pady=(5, 10))

        self.progress_lbl = ctk.CTkLabel(progress_frame, text="Progress: 0/0 images (0%)", font=ctk.CTkFont(size=12, weight="bold"))
        self.progress_lbl.pack(anchor="w", padx=5, pady=(0, 2))

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(fill="x", padx=5)
        self.progress_bar.set(0) 

        # --- ACTIVITY LOG UI FRAME ---
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        log_title = ctk.CTkLabel(log_frame, text="Activity Logs:", font=ctk.CTkFont(size=12))
        log_title.pack(anchor="w", padx=10, pady=(5, 0))

        self.log_text = ctk.CTkTextbox(log_frame, state="disabled", font=("Courier New", 12))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text.tag_config("warning", foreground="#E6B800") 
        self.log_text.tag_config("error", foreground="#FF4D4D")   

        # Refresh initial state
        self.toggle_scan_mode_ui()
        self.toggle_clahe_inputs()
        self.toggle_output_folder_ui()

    def toggle_output_folder_ui(self):
        """Enables or disables output destination widgets based on in-place overwrite state."""
        is_overwrite_inplace = self.chk_overwrite_inplace_var.get()
        state = "disabled" if is_overwrite_inplace else "normal"
        
        self.output_entry.configure(state=state)
        self.btn_browse_out.configure(state=state)
        self.btn_delete.configure(state=state)

    def toggle_scan_mode_ui(self):
        """Toggles subfolder selection check boxes state depending on selected scan mode."""
        is_subfolder_mode = (self.scan_mode_var.get() == "subfolder")
        state = "normal" if is_subfolder_mode else "disabled"
        self.chk_original.configure(state=state)
        self.chk_processed.configure(state=state)

    def toggle_clahe_inputs(self):
        """Enables or disables CLAHE setting input fields based on preprocessing toggle."""
        state = "normal" if self.chk_preprocess_var.get() else "disabled"
        self.clip_entry.configure(state=state)
        self.tile_menu.configure(state=state)

    def update_log_ui(self, message, level="info"):
        """
        Thread-safe callback appending new text messages to the activity log textbox.

        Args:
            message (str): Log payload string.
            level (str, optional): Message severity key ('info', 'warning', 'error'). Defaults to "info".
        """
        self.log_text.configure(state="normal")
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        level_tag = level.lower() if level.lower() in ["warning", "error"] else None
        self.log_text.insert("end", f"{timestamp}{message}\n", level_tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def update_progress_ui(self, value, text_message):
        """
        Thread-safe callback updating UI progress bar position and status text.

        Args:
            value (float): Progress ratio between 0.0 and 1.0.
            text_message (str): Status label text message string.
        """
        self.progress_bar.set(value)
        self.progress_lbl.configure(text=text_message)

    def update_controls_state_ui(self):
        """Enables or disables interactive UI controls during pipeline execution cycles."""
        if self.vm.is_running:
            self.btn_run.configure(state="disabled")
            self.btn_delete.configure(state="disabled")
            self.rad_scan_all.configure(state="disabled")
            self.rad_scan_sub.configure(state="disabled")
            self.chk_original.configure(state="disabled")
            self.chk_processed.configure(state="disabled")
            self.chk_preprocess.configure(state="disabled") 
            self.chk_overwrite_inplace.configure(state="disabled")
            self.output_entry.configure(state="disabled")
            self.btn_browse_out.configure(state="disabled")
            self.clip_entry.configure(state="disabled")
            self.tile_menu.configure(state="disabled")
            self.btn_stop.configure(state="normal" if not self.vm.stop_requested else "disabled")
        else:
            self.btn_run.configure(state="normal")
            self.rad_scan_all.configure(state="normal")
            self.rad_scan_sub.configure(state="normal")
            self.chk_preprocess.configure(state="normal") 
            self.chk_overwrite_inplace.configure(state="normal")
            self.toggle_scan_mode_ui()
            self.toggle_clahe_inputs()
            self.toggle_output_folder_ui()
            self.btn_stop.configure(state="disabled")

    def browse_input(self):
        """Opens directory picker dialog for input source folder selection."""
        if self.vm.is_running: return
        path = filedialog.askdirectory()
        if path: self.input_dir.set(path)

    def browse_output(self):
        """Opens directory picker dialog for output destination folder selection."""
        if self.vm.is_running: return
        path = filedialog.askdirectory()
        if path: self.output_dir.set(path)

    def on_run_clicked(self):
        """Triggers main execution pipeline action in ViewModel."""
        self.vm.start_copy_pipeline(
            self.input_dir.get(),
            self.output_dir.get(),
            self.chk_original_var.get(),
            self.chk_processed_var.get(),
            self.chk_preprocess_var.get(),
            self.clahe_clip_var.get(),
            self.clahe_tile_var.get(),
            scan_mode=self.scan_mode_var.get(),
            overwrite_inplace=self.chk_overwrite_inplace_var.get()
        )

    def on_delete_clicked(self):
        """Displays confirmation dialog and executes output folder image cleanup."""
        confirm = messagebox.askyesno(
            "Confirmation Required", 
            "Are you sure you want to delete ALL files inside the selected output directory?\nThis action cannot be undone."
        )
        if confirm:
            self.vm.execute_delete(self.output_dir.get())
    
    def on_closing(self):
        """Persists current user options to cache and destroys main window frame."""
        self.vm.save_config(
            self.input_dir.get(), 
            self.output_dir.get(),
            self.clahe_clip_var.get(),
            self.clahe_tile_var.get(),
            self.scan_mode_var.get(),
            self.chk_overwrite_inplace_var.get()
        )
        self.destroy()


if __name__ == "__main__":
    vm = PhotoCopyViewModel()
    app = PhotoCopyView(vm)
    app.mainloop()