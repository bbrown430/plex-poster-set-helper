"""Settings tab for application configuration."""

import os
import tkinter as tk
import customtkinter as ctk
import subprocess
import platform
from ....utils.helpers import get_exe_dir


class SettingsTab:
    """Manages the Settings tab interface."""
    
    def __init__(self, parent, app):
        """Initialize Settings tab.
        
        Args:
            parent: Parent tab view widget.
            app: Main application instance.
        """
        self.app = app
        self.tab = parent.add("Settings")
        
        # UI variables
        self.base_url_entry = None
        self.token_entry = None
        self.log_file_entry = None
        self.tv_library_container = None
        self.tv_library_rows = []
        self.movie_library_container = None
        self.movie_library_rows = []
        self.mediux_filters_container = None
        self.mediux_filters_rows = []
        
        # Scraper settings
        self.max_workers_var = None
        self.initial_delay_var = None
        self.min_delay_var = None
        self.max_delay_var = None
        self.batch_delay_var = None
        self.page_wait_min_var = None
        self.page_wait_max_var = None
        self.fast_preset_btn = None
        self.balanced_preset_btn = None
        self.safe_preset_btn = None
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the tab UI."""
        self.tab.grid_columnconfigure(0, weight=1)
        self.tab.grid_rowconfigure(0, weight=1, minsize=560)
        
        # Create main scrollable container
        main_scroll = self.app.ui_helpers.create_scrollable_frame(
            self.tab, fg_color="transparent")
        main_scroll.grid(row=0, column=0, padx=0, pady=(0, 5), sticky="nsew")
        main_scroll.grid_columnconfigure(0, weight=1)
        
        row = 0
        
        # Plex Base URL
        base_url_label = ctk.CTkLabel(main_scroll, text="Plex Base URL", text_color="#696969", font=("Roboto", 15))
        base_url_label.grid(row=row, column=0, pady=(10, 5), padx=10, sticky="w")
        row += 1
        
        self.base_url_entry = ctk.CTkEntry(
            main_scroll,
            placeholder_text="Enter Plex Base URL",
            fg_color="#1C1E1E",
            text_color="#A1A1A1",
            border_width=0,
            height=40
        )
        self.base_url_entry.grid(row=row, column=0, pady=(0, 10), padx=10, sticky="ew")
        self.app.ui_helpers.bind_context_menu(self.base_url_entry)
        row += 1
        
        # Plex Token
        token_label = ctk.CTkLabel(main_scroll, text="Plex Token", text_color="#696969", font=("Roboto", 15))
        token_label.grid(row=row, column=0, pady=5, padx=10, sticky="w")
        row += 1
        
        self.token_entry = ctk.CTkEntry(
            main_scroll,
            placeholder_text="Enter Plex Token",
            fg_color="#1C1E1E",
            text_color="#A1A1A1",
            border_width=0,
            height=40
        )
        self.token_entry.grid(row=row, column=0, pady=(0, 10), padx=10, sticky="ew")
        self.app.ui_helpers.bind_context_menu(self.token_entry)
        row += 1

        # Sign in with Plex OAuth
        oauth_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        oauth_frame.grid(row=row, column=0, pady=(0, 10), padx=10, sticky="ew")
        oauth_frame.grid_columnconfigure(0, weight=1)

        divider_label = ctk.CTkLabel(
            oauth_frame,
            text="-- or sign in with Plex --",
            text_color="#696969",
            font=("Roboto", 12)
        )
        divider_label.grid(row=0, column=0, pady=(0, 5), sticky="ew")

        self.oauth_button = ctk.CTkButton(
            oauth_frame,
            text="Sign in with Plex",
            command=self.app._start_plex_oauth,
            fg_color="#E5A00D",
            hover_color="#FFA500",
            text_color="#000000",
            font=("Roboto", 14, "bold"),
            height=40
        )
        self.oauth_button.grid(row=1, column=0, pady=(0, 5), sticky="ew")

        self.oauth_status_label = ctk.CTkLabel(
            oauth_frame,
            text="",
            text_color="#696969",
            font=("Roboto", 12)
        )
        self.oauth_status_label.grid(row=2, column=0, pady=0, sticky="ew")
        row += 1

        # TV Library Names
        tv_header_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        tv_header_frame.grid(row=row, column=0, pady=(5, 5), padx=10, sticky="ew")
        tv_header_frame.grid_columnconfigure(0, weight=1)
        
        tv_label = ctk.CTkLabel(tv_header_frame, text="TV Library Names", text_color="#696969", font=("Roboto", 14))
        tv_label.grid(row=0, column=0, sticky="w")
        
        tv_add_button = self.app.ui_helpers.create_button(
            tv_header_frame, text="+ Add", command=lambda: self.add_library_item('tv'), height=26)
        tv_add_button.grid(row=0, column=1, padx=5, ipadx=8, sticky="e")
        row += 1
        
        self.tv_library_container = ctk.CTkFrame(main_scroll, fg_color="#1C1E1E", corner_radius=5)
        self.tv_library_container.grid(row=row, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.tv_library_container.grid_columnconfigure(0, weight=1)
        self.tv_library_container.configure(border_width=0)
        row += 1
        
        # Movie Library Names
        movie_header_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        movie_header_frame.grid(row=row, column=0, pady=(5, 5), padx=10, sticky="ew")
        movie_header_frame.grid_columnconfigure(0, weight=1)
        
        movie_label = ctk.CTkLabel(movie_header_frame, text="Movie Library Names", text_color="#696969", font=("Roboto", 14))
        movie_label.grid(row=0, column=0, sticky="w")
        
        movie_add_button = self.app.ui_helpers.create_button(
            movie_header_frame, text="+ Add", command=lambda: self.add_library_item('movie'), height=26)
        movie_add_button.grid(row=0, column=1, padx=5, ipadx=8, sticky="e")
        row += 1
        
        self.movie_library_container = ctk.CTkFrame(main_scroll, fg_color="#1C1E1E", corner_radius=5)
        self.movie_library_container.grid(row=row, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.movie_library_container.grid_columnconfigure(0, weight=1)
        self.movie_library_container.configure(border_width=0)
        row += 1
        
        # Mediux Filters
        mediux_header_frame = ctk.CTkFrame(main_scroll, fg_color="transparent")
        mediux_header_frame.grid(row=row, column=0, pady=(5, 5), padx=10, sticky="ew")
        mediux_header_frame.grid_columnconfigure(0, weight=1)
        
        mediux_label = ctk.CTkLabel(mediux_header_frame, text="Mediux Filters", text_color="#696969", font=("Roboto", 14))
        mediux_label.grid(row=0, column=0, sticky="w")
        
        mediux_add_button = self.app.ui_helpers.create_button(
            mediux_header_frame, text="+ Add", command=lambda: self.add_library_item('mediux'), height=26)
        mediux_add_button.grid(row=0, column=1, padx=5, ipadx=8, sticky="e")
        row += 1
        
        self.mediux_filters_container = ctk.CTkFrame(main_scroll, fg_color="#1C1E1E", corner_radius=5)
        self.mediux_filters_container.grid(row=row, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.mediux_filters_container.grid_columnconfigure(0, weight=1)
        self.mediux_filters_container.configure(border_width=0)
        row += 1
        
        # Application Settings Section
        app_settings_label = ctk.CTkLabel(
            main_scroll,
            text="Application Settings",
            text_color="#E5A00D",
            font=("Roboto", 16, "bold")
        )
        app_settings_label.grid(row=row, column=0, pady=(15, 10), padx=10, sticky="w")
        row += 1
        
        # Max Concurrent Workers
        row = self._create_max_workers_control(main_scroll, row)
        
        # Log File Path
        row = self._create_log_file_control(main_scroll, row)
        
        # Scraper Performance Settings Section
        row = self._create_scraper_settings(main_scroll, row)
        
        # Buttons fixed at bottom
        button_frame = ctk.CTkFrame(self.tab, fg_color="transparent")
        button_frame.grid(row=1, column=0, pady=5, padx=10, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        reload_button = self.app.ui_helpers.create_button(
            button_frame, text="Reload", command=self.app._load_and_update_ui)
        reload_button.grid(row=0, column=0, pady=0, padx=(0, 5), sticky="ew")
        
        save_button = self.app.ui_helpers.create_button(
            button_frame, text="Save", command=self.app._save_config, primary=True)
        save_button.grid(row=0, column=1, pady=0, padx=(5, 0), sticky="ew")
    
    def _create_max_workers_control(self, parent, row):
        """Create max workers slider control."""
        max_workers_frame = ctk.CTkFrame(parent, fg_color="transparent")
        max_workers_frame.grid(row=row, column=0, pady=(0, 8), padx=10, sticky="ew")
        max_workers_frame.grid_columnconfigure(1, weight=1)
        
        cpu_count = os.cpu_count() or 4
        default_workers = min(3, cpu_count)
        
        max_workers_label = ctk.CTkLabel(
            max_workers_frame,
            text="Max Concurrent Workers",
            text_color="#696969",
            font=("Roboto", 13)
        )
        max_workers_label.grid(row=0, column=0, pady=0, padx=(0, 10), sticky="w")
        
        self.max_workers_var = tk.IntVar(value=default_workers)
        max_workers_slider = ctk.CTkSlider(
            max_workers_frame,
            from_=1,
            to=cpu_count,
            number_of_steps=cpu_count - 1,
            variable=self.max_workers_var,
            fg_color="#1C1E1E",
            progress_color="#E5A00D",
            button_color="#E5A00D",
            button_hover_color="#FFA500"
        )
        max_workers_slider.grid(row=0, column=1, pady=0, padx=0, sticky="ew")
        
        max_workers_value_label = ctk.CTkLabel(
            max_workers_frame,
            textvariable=self.max_workers_var,
            text_color="#E5A00D",
            font=("Roboto", 13, "bold"),
            width=50
        )
        max_workers_value_label.grid(row=0, column=2, pady=0, padx=(10, 0), sticky="e")
        
        return row + 1
    
    def _create_log_file_control(self, parent, row):
        """Create log file path control."""
        log_file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        log_file_frame.grid(row=row, column=0, pady=(0, 8), padx=10, sticky="ew")
        log_file_frame.grid_columnconfigure(1, weight=1)
        
        log_file_label = ctk.CTkLabel(
            log_file_frame,
            text="Log File Path",
            text_color="#696969",
            font=("Roboto", 13)
        )
        log_file_label.grid(row=0, column=0, pady=0, padx=(0, 10), sticky="w")
        
        self.log_file_entry = ctk.CTkEntry(
            log_file_frame,
            placeholder_text="debug.log",
            fg_color="#1C1E1E",
            border_width=0
        )
        self.log_file_entry.grid(row=0, column=1, pady=0, padx=(0, 5), sticky="ew")
        
        open_log_button = self.app.ui_helpers.create_button(
            log_file_frame, text="Open Log", command=self._open_log_file, height=32)
        open_log_button.grid(row=0, column=2, pady=0, padx=0, ipadx=10, sticky="e")
        
        return row + 1
    
    def _create_scraper_settings(self, parent, row):
        """Create scraper performance settings section."""
        scraper_section_label = ctk.CTkLabel(
            parent,
            text="Scraper Performance Settings",
            text_color="#E5A00D",
            font=("Roboto", 16, "bold")
        )
        scraper_section_label.grid(row=row, column=0, pady=(15, 5), padx=10, sticky="w")
        row += 1
        
        scraper_info_label = ctk.CTkLabel(
            parent,
            text="Configure delays between web scraping requests. Lower values = faster scraping but higher detection risk.",
            text_color="#696969",
            font=("Roboto", 11),
            wraplength=600,
            justify="left"
        )
        scraper_info_label.grid(row=row, column=0, pady=(0, 5), padx=10, sticky="w")
        row += 1
        
        # Quick preset buttons
        row = self._create_preset_buttons(parent, row)
        
        # Request Delays subsection
        request_delays_label = ctk.CTkLabel(
            parent,
            text="Request Delays",
            text_color="#A1A1A1",
            font=("Roboto", 14, "bold")
        )
        request_delays_label.grid(row=row, column=0, pady=(5, 8), padx=10, sticky="w")
        row += 1
        
        # Create all delay sliders
        row = self._create_delay_slider(parent, row, "Initial Delay (first request)", 
                                        "initial_delay_var", 0.0, 0.0, 5.0, 50)
        row = self._create_delay_slider(parent, row, "Min Delay (between requests)", 
                                        "min_delay_var", 0.1, 0.0, 5.0, 50)
        row = self._create_delay_slider(parent, row, "Max Delay (between requests)", 
                                        "max_delay_var", 0.5, 0.0, 5.0, 50)
        row = self._create_delay_slider(parent, row, "Batch Delay (every 10 requests)", 
                                        "batch_delay_var", 2.0, 0.0, 10.0, 100)
        
        # Page Load Delays subsection
        page_wait_label = ctk.CTkLabel(
            parent,
            text="Page Load Delays",
            text_color="#A1A1A1",
            font=("Roboto", 14, "bold")
        )
        page_wait_label.grid(row=row, column=0, pady=(15, 3), padx=10, sticky="w")
        row += 1
        
        page_wait_desc = ctk.CTkLabel(
            parent,
            text="Wait time after page navigation for JavaScript execution",
            text_color="#696969",
            font=("Roboto", 11),
            wraplength=600,
            justify="left"
        )
        page_wait_desc.grid(row=row, column=0, pady=(0, 8), padx=10, sticky="w")
        row += 1
        
        row = self._create_delay_slider(parent, row, "Min Page Wait", 
                                        "page_wait_min_var", 0.0, 0.0, 3.0, 30)
        row = self._create_delay_slider(parent, row, "Max Page Wait", 
                                        "page_wait_max_var", 0.5, 0.0, 3.0, 30)
        
        return row
    
    def _create_preset_buttons(self, parent, row):
        """Create preset button controls."""
        preset_frame = ctk.CTkFrame(parent, fg_color="#1C1E1E", corner_radius=5)
        preset_frame.grid(row=row, column=0, pady=(5, 15), padx=10, sticky="ew")
        preset_frame.grid_columnconfigure(0, weight=0)
        preset_frame.grid_columnconfigure(1, weight=1)
        preset_frame.grid_columnconfigure(2, weight=1)
        preset_frame.grid_columnconfigure(3, weight=1)
        
        preset_label = ctk.CTkLabel(
            preset_frame,
            text="Quick Presets:",
            text_color="#A1A1A1",
            font=("Roboto", 13, "bold")
        )
        preset_label.grid(row=0, column=0, pady=10, padx=(15, 10), sticky="w")
        
        # Common button style for presets
        btn_style = {
            "border_width": 1,
            "text_color": "#696969",
            "fg_color": "#1C1E1E", 
            "border_color": "#484848",
            "hover_color": "#333333",
            "width": 80,
            "height": 32,
            "font": ("Segoe UI", 13, "bold")  # Using Segoe UI for consistent emoji support
        }

        self.fast_preset_btn = ctk.CTkButton(
            preset_frame,
            text="⚡ Fast",
            command=lambda: self.apply_scraper_preset('fast'),
            **btn_style
        )
        self.fast_preset_btn.grid(row=0, column=1, pady=10, padx=5, sticky="ew")
        
        self.balanced_preset_btn = ctk.CTkButton(
            preset_frame,
            text="⚖️ Balanced",
            command=lambda: self.apply_scraper_preset('balanced'),
            **btn_style
        )
        self.balanced_preset_btn.grid(row=0, column=2, pady=10, padx=5, sticky="ew")
        
        self.safe_preset_btn = ctk.CTkButton(
            preset_frame,
            text="🛡 Safe",
            command=lambda: self.apply_scraper_preset('safe'),
            **btn_style
        )
        self.safe_preset_btn.grid(row=0, column=3, pady=10, padx=(5, 15), sticky="ew")
        
        return row + 1
    
    def _create_delay_slider(self, parent, row, label_text, var_name, default, min_val, max_val, steps):
        """Create a delay slider control."""
        slider_frame = ctk.CTkFrame(parent, fg_color="transparent")
        slider_frame.grid(row=row, column=0, pady=(5, 5), padx=10, sticky="ew")
        slider_frame.grid_columnconfigure(1, weight=1)
        
        label = ctk.CTkLabel(
            slider_frame,
            text=label_text,
            text_color="#696969",
            font=("Roboto", 13)
        )
        label.grid(row=0, column=0, pady=0, padx=(0, 10), sticky="w")
        
        var = tk.DoubleVar(value=default)
        setattr(self, var_name, var)
        
        slider = ctk.CTkSlider(
            slider_frame,
            from_=min_val,
            to=max_val,
            number_of_steps=steps,
            variable=var,
            fg_color="#1C1E1E",
            progress_color="#E5A00D",
            button_color="#E5A00D",
            button_hover_color="#FFA500"
        )
        slider.grid(row=0, column=1, pady=0, padx=0, sticky="ew")
        
        value_label = ctk.CTkLabel(
            slider_frame,
            textvariable=var,
            text_color="#E5A00D",
            font=("Roboto", 13, "bold"),
            width=50
        )
        value_label.grid(row=0, column=2, pady=0, padx=(10, 0), sticky="e")
        
        unit_label = ctk.CTkLabel(
            slider_frame,
            text="sec",
            text_color="#696969",
            font=("Roboto", 11)
        )
        unit_label.grid(row=0, column=3, pady=0, padx=(2, 0), sticky="w")
        
        return row + 1
    
    def apply_scraper_preset(self, preset: str):
        """Apply a scraper delay preset."""
        presets = {
            'fast': {
                'initial': 0.0, 'min': 0.0, 'max': 0.2, 'batch': 0.0,
                'page_min': 0.0, 'page_max': 0.0
            },
            'balanced': {
                'initial': 0.0, 'min': 0.1, 'max': 0.5, 'batch': 2.0,
                'page_min': 0.0, 'page_max': 0.5
            },
            'safe': {
                'initial': 1.0, 'min': 0.5, 'max': 2.0, 'batch': 5.0,
                'page_min': 0.5, 'page_max': 1.5
            }
        }
        
        values = presets.get(preset, presets['balanced'])
        
        self.initial_delay_var.set(values['initial'])
        self.min_delay_var.set(values['min'])
        self.max_delay_var.set(values['max'])
        self.batch_delay_var.set(values['batch'])
        self.page_wait_min_var.set(values['page_min'])
        self.page_wait_max_var.set(values['page_max'])
        
        self.update_preset_buttons(preset)
    
    def update_preset_buttons(self, active_preset: str = None):
        """Update preset button highlighting."""
        if not all([self.fast_preset_btn, self.balanced_preset_btn, self.safe_preset_btn]):
            return
        
        if active_preset is None:
            active_preset = self.detect_active_preset()
        
        plex_orange = "#E5A00D"
        default_color = "#1C1E1E"
        hover_orange = "#FFA500"
        default_hover = "#484848"
        active_text = "#000000"
        default_text = "#CECECE"
        
        # Update each button
        buttons = {
            'fast': self.fast_preset_btn,
            'balanced': self.balanced_preset_btn,
            'safe': self.safe_preset_btn
        }
        
        for preset_name, button in buttons.items():
            if preset_name == active_preset:
                button.configure(fg_color=plex_orange, hover_color=hover_orange, text_color=active_text)
            else:
                button.configure(fg_color=default_color, hover_color=default_hover, text_color=default_text)
    
    def detect_active_preset(self) -> str:
        """Detect which preset matches current values."""
        if not all([self.initial_delay_var, self.min_delay_var, self.max_delay_var, 
                   self.batch_delay_var, self.page_wait_min_var, self.page_wait_max_var]):
            return None
        
        current = {
            'initial': round(self.initial_delay_var.get(), 1),
            'min': round(self.min_delay_var.get(), 1),
            'max': round(self.max_delay_var.get(), 1),
            'batch': round(self.batch_delay_var.get(), 1),
            'page_min': round(self.page_wait_min_var.get(), 1),
            'page_max': round(self.page_wait_max_var.get(), 1)
        }
        
        # Check Fast preset
        if (current['initial'] == 0.0 and current['min'] == 0.0 and current['max'] == 0.2 and 
            current['batch'] == 0.0 and current['page_min'] == 0.0 and current['page_max'] == 0.0):
            return 'fast'
        
        # Check Balanced preset
        if (current['initial'] == 0.0 and current['min'] == 0.1 and current['max'] == 0.5 and 
            current['batch'] == 2.0 and current['page_min'] == 0.0 and current['page_max'] == 0.5):
            return 'balanced'
        
        # Check Safe preset
        if (current['initial'] == 1.0 and current['min'] == 0.5 and current['max'] == 2.0 and 
            current['batch'] == 5.0 and current['page_min'] == 0.5 and current['page_max'] == 1.5):
            return 'safe'
        
        return None
    
    def add_library_item(self, list_type: str, value: str = ""):
        """Add a library item row."""
        if list_type == 'tv':
            container = self.tv_library_container
            rows = self.tv_library_rows
        elif list_type == 'movie':
            container = self.movie_library_container
            rows = self.movie_library_rows
        else:  # mediux
            container = self.mediux_filters_container
            rows = self.mediux_filters_rows
        
        row_num = len(rows)
        
        # Add top padding to first row
        pady_value = (5, 2) if row_num == 0 else 2
        padx_value = 8
        
        row_frame = ctk.CTkFrame(container, fg_color="transparent")
        row_frame.grid(row=row_num, column=0, padx=padx_value, pady=pady_value, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)
        
        entry = ctk.CTkEntry(
            row_frame,
            fg_color="#2A2B2B",
            border_width=0,
            text_color="#CECECE",
            height=30
        )
        entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.app.ui_helpers.bind_context_menu(entry)
        
        if value:
            entry.insert(0, value)
        
        delete_button = ctk.CTkButton(
            row_frame,
            text="✕",
            command=lambda t=list_type, r=row_num: self.remove_library_item(t, r),
            fg_color="#8B0000",
            hover_color="#A52A2A",
            border_width=1,
            border_color="#484848",
            text_color="#FFFFFF",
            width=30,
            height=30,
            font=("Roboto", 13, "bold")
        )
        delete_button.grid(row=0, column=1, padx=0, sticky="e")
        
        rows.append({
            'frame': row_frame,
            'entry': entry,
            'button': delete_button
        })
        
        # Add bottom padding spacer if this is the last row
        self._update_container_padding(container, len(rows))
    
    def remove_library_item(self, list_type: str, row_num: int):
        """Remove a library item row."""
        if list_type == 'tv':
            rows = self.tv_library_rows
        elif list_type == 'movie':
            rows = self.movie_library_rows
        else:  # mediux
            rows = self.mediux_filters_rows
        
        if 0 <= row_num < len(rows):
            row = rows[row_num]
            row['frame'].destroy()
            rows.pop(row_num)
            
            for idx, remaining_row in enumerate(rows):
                remaining_row['button'].configure(
                    command=lambda t=list_type, r=idx: self.remove_library_item(t, r))
            
            # Update padding after removal
            if list_type == 'tv':
                self._update_container_padding(self.tv_library_container, len(rows))
            elif list_type == 'movie':
                self._update_container_padding(self.movie_library_container, len(rows))
            else:
                self._update_container_padding(self.mediux_filters_container, len(rows))
    
    def _update_container_padding(self, container, num_rows):
        """Update container bottom padding based on number of rows.
        
        Args:
            container: The container widget.
            num_rows: Number of rows in the container.
        """
        # Remove existing padding spacer if it exists
        for child in container.winfo_children():
            if isinstance(child, ctk.CTkFrame) and child.cget('height') == 5:
                child.destroy()
        
        # Add padding spacer at the bottom
        if num_rows > 0:
            spacer = ctk.CTkFrame(container, fg_color="transparent", height=5)
            spacer.grid(row=num_rows, column=0, sticky="ew")
    
    def _open_log_file(self):
        """Open the log file in the default text editor."""
        try:
            log_path = os.path.join(get_exe_dir(), self.app.config.log_file)
            
            if not os.path.exists(log_path):
                self.app._update_status(f"Log file not found: {log_path}", color="orange")
                return
            
            if platform.system() == 'Windows':
                os.startfile(log_path)
            elif platform.system() == 'Darwin':
                subprocess.run(['open', log_path])
            else:
                subprocess.run(['xdg-open', log_path])
            
            self.app._update_status("Opened log file", color="#E5A00D")
        except Exception as e:
            self.app._update_status(f"Error opening log file: {str(e)}", color="red")
