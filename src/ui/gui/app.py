"""Main GUI application for Plex Poster Set Helper - Refactored Architecture."""

import os
import sys
import threading
import webbrowser
import tkinter as tk
import customtkinter as ctk
from PIL import Image
from typing import List

from ...core.config import ConfigManager, Config
from ...core.logger import get_logger
from ...services.plex_service import PlexService
from ...services.poster_upload_service import PosterUploadService
from ...scrapers.scraper_factory import ScraperFactory
from ...utils.helpers import resource_path, get_exe_dir
from ...utils.text_utils import parse_urls

from .widgets import UIHelpers
from .handlers import ScrapeHandler, LabelHandler
from .tabs import (
    PosterScrapeTab,
    BulkImportTab,
    TitleMappingsTab,
    ManageLabelsTab,
    SettingsTab
)


class PlexPosterGUI:
    """Main GUI application with modular architecture."""
    
    def __init__(self):
        """Initialize the GUI application."""
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        
        # Initialize logger
        self.logger = get_logger()
        self.logger.configure(log_file=self.config.log_file)
        self.logger.info("GUI Application initializing...")
        
        # Services
        self.plex_service: PlexService = None
        self.upload_service: PosterUploadService = None
        self.scraper_factory: ScraperFactory = None
        
        # Main window
        self.app = None
        
        # Status and progress
        self.status_label = None
        self.progress_bar = None
        self.progress_label = None
        self.cancel_button = None
        self.is_cancelled = False
        
        # Bulk import state
        self.current_bulk_file = None
        
        # Helpers and handlers (initialized after UI creation)
        self.ui_helpers = None
        self.scrape_handler = None
        self.label_handler = None
        
        # Tab instances
        self.poster_scrape_tab = None
        self.bulk_import_tab = None
        self.title_mappings_tab = None
        self.manage_labels_tab = None
        self.settings_tab = None
        
        # Expose settings tab variables for backwards compatibility
        self.base_url_entry = None
        self.token_entry = None
        self.max_workers_var = None
        self.initial_delay_var = None
        self.min_delay_var = None
        self.max_delay_var = None
        self.batch_delay_var = None
        self.page_wait_min_var = None
        self.page_wait_max_var = None
        
        # Expose manage labels variables for backwards compatibility
        self.labeled_items_scroll = None
        self.labeled_count_label = None
        self.labeled_library_label = None
        self.labeled_source_label = None
        self.labeled_search_var = None
        self.labeled_filter_mediux = None
        self.labeled_filter_posterdb = None
        self.labeled_filter_movies = None
        self.labeled_filter_tv = None
    
    def run(self):
        """Run the GUI application."""
        self._create_ui()
        self.app.mainloop()
    
    def _create_ui(self):
        """Create the main UI window."""
        self.app = ctk.CTk()
        ctk.set_appearance_mode("dark")
        
        self.app.title("Plex Poster Upload Helper")
        self.app.geometry("660x815")
        
        try:
            self.app.iconbitmap(resource_path("icons/Plex.ico"))
        except:
            pass
        
        self.app.configure(fg_color="#2A2B2B")
        self.app.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Initialize helpers
        self.ui_helpers = UIHelpers(self.app)
        
        # Initialize handlers (before tabs, since tabs use them)
        self.scrape_handler = ScrapeHandler(self)
        self.label_handler = LabelHandler(self)
        
        # Create UI components
        self._create_link_bar()
        self._create_tabview()
        self._create_status_bar()
        
        # Load configuration into UI
        self._load_and_update_ui()
    
    def _create_link_bar(self):
        """Create the link bar at the top."""
        link_bar = ctk.CTkFrame(self.app, fg_color="transparent")
        link_bar.pack(fill="x", pady=5, padx=10)
        
        base_url = self.config.base_url if self.config.base_url else "https://www.plex.tv"
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            display_url = parsed.netloc if parsed.netloc else base_url
        except:
            display_url = base_url
        
        url_text = self.config.base_url if self.config.base_url else "Plex Media Server"
        url_label = ctk.CTkLabel(
            link_bar,
            text=url_text,
            anchor="w",
            font=("Roboto", 14, "bold"),
            text_color="#CECECE"
        )
        url_label.pack(side="left", padx=(5, 10))
        
        # External links
        mediux_button = self.ui_helpers.create_button(
            link_bar,
            text="MediUX.pro",
            command=lambda: webbrowser.open("https://mediux.pro"),
            color="#945af2",
            height=30
        )
        mediux_button.pack(side="right", padx=5)
        
        posterdb_button = self.ui_helpers.create_button(
            link_bar,
            text="ThePosterDB",
            command=lambda: webbrowser.open("https://theposterdb.com"),
            color="#FA6940",
            height=30
        )
        posterdb_button.pack(side="right", padx=5)
    
    def _create_tabview(self):
        """Create the tabbed interface."""
        tabview = ctk.CTkTabview(self.app)
        tabview.pack(fill="both", expand=True, padx=10, pady=0)
        
        tabview.configure(
            fg_color="#2A2B2B",
            segmented_button_fg_color="#1C1E1E",
            segmented_button_selected_color="#2A2B2B",
            segmented_button_selected_hover_color="#2A2B2B",
            segmented_button_unselected_color="#1C1E1E",
            segmented_button_unselected_hover_color="#1C1E1E",
            text_color="#CECECE",
            text_color_disabled="#777777",
            border_color="#484848",
            border_width=1,
        )
        
        # Create all tabs
        self.poster_scrape_tab = PosterScrapeTab(tabview, self)
        self.bulk_import_tab = BulkImportTab(tabview, self)
        self.title_mappings_tab = TitleMappingsTab(tabview, self)
        self.manage_labels_tab = ManageLabelsTab(tabview, self)
        self.settings_tab = SettingsTab(tabview, self)
        
        # Set default tab
        tabview.set("Poster Scrape")
        
        # Expose settings variables
        self.base_url_entry = self.settings_tab.base_url_entry
        self.token_entry = self.settings_tab.token_entry
        self.max_workers_var = self.settings_tab.max_workers_var
        self.initial_delay_var = self.settings_tab.initial_delay_var
        self.min_delay_var = self.settings_tab.min_delay_var
        self.max_delay_var = self.settings_tab.max_delay_var
        self.batch_delay_var = self.settings_tab.batch_delay_var
        self.page_wait_min_var = self.settings_tab.page_wait_min_var
        self.page_wait_max_var = self.settings_tab.page_wait_max_var
        
        # Expose manage labels variables
        self.labeled_items_scroll = self.manage_labels_tab.scroll_frame
        self.labeled_count_label = self.manage_labels_tab.count_label
        self.labeled_library_label = self.manage_labels_tab.library_label
        self.labeled_source_label = self.manage_labels_tab.source_label
        self.labeled_search_var = self.manage_labels_tab.search_var
        self.labeled_filter_mediux = self.manage_labels_tab.filter_mediux
        self.labeled_filter_posterdb = self.manage_labels_tab.filter_posterdb
        self.labeled_filter_movies = self.manage_labels_tab.filter_movies
        self.labeled_filter_tv = self.manage_labels_tab.filter_tv
    
    def _create_status_bar(self):
        """Create status label and progress bar at bottom."""
        status_frame = ctk.CTkFrame(self.app, fg_color="transparent")
        status_frame.pack(side="bottom", fill="x", pady=5, padx=10)
        
        self.progress_bar = ctk.CTkProgressBar(
            status_frame,
            height=8,
            fg_color="#1C1E1E",
            progress_color="#E5A00D"
        )
        self.progress_bar.pack(fill="x", padx=0, pady=(0, 3))
        self.progress_bar.set(0)
        self.progress_bar.pack_forget()
        
        self.progress_label = ctk.CTkLabel(status_frame, text="", text_color="#696969", font=("Roboto", 11))
        self.progress_label.pack(fill="x", pady=(0, 2))
        self.progress_label.pack_forget()
        
        self.cancel_button = ctk.CTkButton(
            status_frame,
            text="Cancel",
            command=self._cancel_operation,
            fg_color="#8B0000",
            hover_color="#A00000",
            height=28,
            width=100
        )
        self.cancel_button.pack(pady=(0, 5))
        self.cancel_button.pack_forget()
        
        self.status_label = ctk.CTkLabel(status_frame, text="", text_color="#E5A00D", font=("Roboto", 12))
        self.status_label.pack(fill="x")
    
    def _on_closing(self):
        """Handle window close event with proper cleanup."""
        self.is_cancelled = True
        
        if self.scrape_handler:
            self.scrape_handler.cancel()
        
        if self.scraper_factory:
            try:
                self.scraper_factory.cleanup()
            except:
                pass
        
        self.app.destroy()
    
    def _load_and_update_ui(self):
        """Load configuration and update UI fields."""
        self.config = self.config_manager.load()
        
        # Load settings tab
        if self.base_url_entry:
            self.base_url_entry.delete(0, ctk.END)
            self.base_url_entry.insert(0, self.config.base_url or "")
        
        if self.token_entry:
            self.token_entry.delete(0, ctk.END)
            self.token_entry.insert(0, self.config.token or "")
        
        # Load TV libraries
        for row in self.settings_tab.tv_library_rows:
            row['frame'].destroy()
        self.settings_tab.tv_library_rows.clear()
        
        for lib in self.config.tv_library:
            self.settings_tab.add_library_item('tv', lib)
        
        # Load Movie libraries
        for row in self.settings_tab.movie_library_rows:
            row['frame'].destroy()
        self.settings_tab.movie_library_rows.clear()
        
        for lib in self.config.movie_library:
            self.settings_tab.add_library_item('movie', lib)
        
        # Load Mediux filters
        for row in self.settings_tab.mediux_filters_rows:
            row['frame'].destroy()
        self.settings_tab.mediux_filters_rows.clear()
        
        for filter_val in self.config.mediux_filters:
            self.settings_tab.add_library_item('mediux', filter_val)
        
        # Load worker count
        if self.max_workers_var:
            self.max_workers_var.set(self.config.max_workers)
        
        # Load scraper delay settings
        if self.initial_delay_var:
            self.initial_delay_var.set(self.config.scraper_initial_delay)
        if self.min_delay_var:
            self.min_delay_var.set(self.config.scraper_min_delay)
        if self.max_delay_var:
            self.max_delay_var.set(self.config.scraper_max_delay)
        if self.batch_delay_var:
            self.batch_delay_var.set(self.config.scraper_batch_delay)
        if self.page_wait_min_var:
            self.page_wait_min_var.set(self.config.scraper_page_wait_min)
        if self.page_wait_max_var:
            self.page_wait_max_var.set(self.config.scraper_page_wait_max)
        
        # Update preset button highlighting
        self.settings_tab.update_preset_buttons()
        
        # Load log file path
        if self.settings_tab.log_file_entry:
            self.settings_tab.log_file_entry.delete(0, ctk.END)
            self.settings_tab.log_file_entry.insert(0, self.config.log_file or "debug.log")
        
        # Load bulk import file
        self.bulk_import_tab.load_file()
        
        # Load title mappings
        self.title_mappings_tab.load_mappings()
        
        # Initialize poster scrape with one empty row if needed
        if len(self.poster_scrape_tab.rows) == 0:
            self.poster_scrape_tab.add_url_row()
    
    def _save_config(self):
        """Save configuration from UI fields."""
        # Save basic settings
        self.config.base_url = self.base_url_entry.get().strip()
        self.config.token = self.token_entry.get().strip()
        
        # Save TV libraries
        tv_libs = []
        for row in self.settings_tab.tv_library_rows:
            lib_name = row['entry'].get().strip()
            if lib_name:
                tv_libs.append(lib_name)
        self.config.tv_library = tv_libs
        
        # Save Movie libraries
        movie_libs = []
        for row in self.settings_tab.movie_library_rows:
            lib_name = row['entry'].get().strip()
            if lib_name:
                movie_libs.append(lib_name)
        self.config.movie_library = movie_libs
        
        # Save Mediux filters
        mediux_filters = []
        for row in self.settings_tab.mediux_filters_rows:
            filter_val = row['entry'].get().strip()
            if filter_val:
                mediux_filters.append(filter_val)
        self.config.mediux_filters = mediux_filters
        
        # Save worker count
        if self.max_workers_var:
            self.config.max_workers = self.max_workers_var.get()
        
        # Save scraper delay settings
        if self.initial_delay_var:
            self.config.scraper_initial_delay = self.initial_delay_var.get()
        if self.min_delay_var:
            self.config.scraper_min_delay = self.min_delay_var.get()
        if self.max_delay_var:
            self.config.scraper_max_delay = self.max_delay_var.get()
        if self.batch_delay_var:
            self.config.scraper_batch_delay = self.batch_delay_var.get()
        if self.page_wait_min_var:
            self.config.scraper_page_wait_min = self.page_wait_min_var.get()
        if self.page_wait_max_var:
            self.config.scraper_page_wait_max = self.page_wait_max_var.get()
        
        # Save log file path
        if self.settings_tab.log_file_entry:
            self.config.log_file = self.settings_tab.log_file_entry.get().strip() or "debug.log"
        
        # Save to file
        self.config_manager.save(self.config)
        
        # Update logger with new log file
        self.logger.configure(log_file=self.config.log_file)
        
        # Reinitialize Plex service with new credentials
        self.plex_service = PlexService(self.config)
        tv_libs, movie_libs = self.plex_service.setup(gui_mode=True)
        
        # Reinitialize upload service with updated Plex service
        if self.plex_service:
            self.upload_service = PosterUploadService(self.plex_service)
        
        # Reinitialize scraper factory with updated config
        self.scraper_factory = ScraperFactory(config=self.config)
        
        self._update_status("Configuration saved successfully!", color="#E5A00D")
        
        # Refresh the Reset Posters tab if Plex setup was successful
        if tv_libs or movie_libs:
            self.app.after(100, lambda: self.label_handler.refresh_labeled_items())
    
    def _setup_services(self):
        """Initialize Plex and upload services."""
        if not self.plex_service:
            self.plex_service = PlexService(self.config)
            self.plex_service.setup(gui_mode=True)
        elif not self.plex_service.tv_libraries and not self.plex_service.movie_libraries:
            # Plex service exists but libraries aren't loaded - try setting up again
            self.plex_service.setup(gui_mode=True)
        
        if not self.upload_service and self.plex_service:
            self.upload_service = PosterUploadService(self.plex_service)
        
        if not self.scraper_factory:
            self.scraper_factory = ScraperFactory(
                config=self.config
            )
    
    def _run_url_scrape_thread(self):
        """Run URL scraping in a separate thread."""
        urls = self.poster_scrape_tab.get_urls()
        
        if not urls:
            self._update_status("No URLs to scrape", color="orange")
            return
        
        self._disable_buttons()
        threading.Thread(
            target=self.scrape_handler.process_scrape_urls,
            args=(urls, self.poster_scrape_rows),
            daemon=True
        ).start()
    
    def _run_bulk_import_thread(self):
        """Run bulk import in a separate thread."""
        urls = self.bulk_import_tab.get_urls()
        
        if not urls:
            self._update_status("No URLs in bulk file", color="orange")
            return
        
        self._disable_buttons()
        threading.Thread(
            target=self.scrape_handler.process_scrape_urls,
            args=(urls, self.bulk_import_rows),
            daemon=True
        ).start()
    
    def _disable_buttons(self):
        """Disable action buttons during operations."""
        if self.poster_scrape_tab.scrape_button:
            self.poster_scrape_tab.scrape_button.configure(state="disabled")
        if self.bulk_import_tab.import_button:
            self.bulk_import_tab.import_button.configure(state="disabled")
    
    def _enable_buttons(self):
        """Enable action buttons after operations."""
        if self.poster_scrape_tab.scrape_button:
            self.poster_scrape_tab.scrape_button.configure(state="normal")
        if self.bulk_import_tab.import_button:
            self.bulk_import_tab.import_button.configure(state="normal")
    
    def _update_status(self, message: str, color: str = "white"):
        """Update status label."""
        if color == "red":
            self.logger.error(message)
        elif color in ["orange", "#FF6B6B"]:
            self.logger.warning(message)
        else:
            self.logger.info(message)
        
        self.app.after(0, lambda: self.status_label.configure(text=message, text_color=color))
    
    def _update_progress(self, current: int, total: int, url: str = "", active_count: int = 0):
        """Update progress bar and label."""
        def update():
            if total > 0:
                progress = current / total
                self.progress_bar.set(progress)
                self.progress_bar.pack(fill="x", padx=0, pady=(0, 3))
                
                if active_count > 0:
                    progress_text = f"Processing {current}/{total} URLs ({active_count} active workers)"
                else:
                    progress_text = f"Processing {current}/{total} URLs"
                
                if url:
                    progress_text += f"\nCurrent: {url[:80]}..."
                
                self.progress_label.configure(text=progress_text)
                self.progress_label.pack(fill="x", pady=(0, 2))
        
        self.app.after(0, update)
    
    def _hide_progress(self):
        """Hide progress bar and label."""
        def hide():
            self.progress_bar.pack_forget()
            self.progress_label.pack_forget()
            if self.cancel_button:
                self.cancel_button.pack_forget()
        
        self.app.after(0, hide)
    
    def _show_cancel_button(self):
        """Show cancel button."""
        def show():
            if self.cancel_button:
                self.cancel_button.pack(pady=(0, 5))
        
        self.app.after(0, show)
    
    def _cancel_operation(self):
        """Cancel the current operation."""
        self.is_cancelled = True
        self.scrape_handler.cancel()
        self._update_status("Cancelling operation...", color="#FF6B6B")
        if self.cancel_button:
            self.cancel_button.configure(state="disabled")
    
    def _set_url_row_status(self, url: str, status: str, row_list: list):
        """Set visual status for a URL row."""
        def update():
            for row in row_list:
                if row.get('entry') and row['entry'].get().strip() == url:
                    if status == 'processing':
                        # Yellow border for processing
                        row['entry'].configure(border_width=2, border_color="#E5A00D")
                    elif status == 'completed':
                        # Green border for completed
                        row['entry'].configure(border_width=2, border_color="#4CAF50")
                    elif status == 'error':
                        # Red border for error
                        row['entry'].configure(border_width=2, border_color="#FF6B6B")
                    else:
                        # Reset to default
                        row['entry'].configure(border_width=1, border_color="#484848")
                    break
        
        self.app.after(0, update)
    
    def _start_plex_oauth(self):
        """Start the Plex OAuth sign-in flow."""
        from plexapi.myplex import MyPlexPinLogin

        self._update_oauth_status("Opening Plex sign-in page...", color="#E5A00D")
        try:
            pin_login = MyPlexPinLogin(oauth=True)
            oauth_url = pin_login.oauthUrl()
            webbrowser.open(oauth_url)
            self._update_oauth_status("Waiting for sign-in...", color="#E5A00D")
            threading.Thread(target=self._poll_plex_oauth, args=(pin_login,), daemon=True).start()
        except Exception as e:
            self._update_oauth_status(f"OAuth error: {e}", color="red")

    def _poll_plex_oauth(self, pin_login):
        """Poll for Plex OAuth completion in a background thread."""
        import time
        for _ in range(150):  # 5 minute timeout
            time.sleep(2)
            if pin_login.checkLogin():
                token = pin_login.token
                if token:
                    try:
                        from plexapi.myplex import MyPlexAccount
                        account = MyPlexAccount(token=token)
                        resources = [r for r in account.resources() if 'server' in r.provides]
                        base_url = ""
                        if resources:
                            server = resources[0]
                            try:
                                plex_server = server.connect()
                                base_url = plex_server._baseurl
                            except Exception:
                                if server.connections:
                                    base_url = server.connections[0].uri
                        self.app.after(0, lambda bu=base_url, t=token, u=account.username: self._finish_plex_oauth(bu, t, u))
                    except Exception as e:
                        self.app.after(0, lambda err=e: self._update_oauth_status(f"OAuth error: {err}", color="red"))
                    return
        self.app.after(0, lambda: self._update_oauth_status("Sign-in timed out", color="red"))

    def _finish_plex_oauth(self, base_url, token, username):
        """Complete the OAuth flow by populating UI fields and saving config."""
        self.base_url_entry.delete(0, ctk.END)
        self.base_url_entry.insert(0, base_url)
        self.token_entry.delete(0, ctk.END)
        self.token_entry.insert(0, token)
        self._update_oauth_status(f"Signed in as {username}!", color="#4CAF50")
        self._save_config()

    def _update_oauth_status(self, message, color="#696969"):
        """Update the OAuth status label on the settings tab."""
        def update():
            if self.settings_tab and hasattr(self.settings_tab, 'oauth_status_label'):
                self.settings_tab.oauth_status_label.configure(text=message, text_color=color)
        self.app.after(0, update)

    @property
    def poster_scrape_rows(self):
        """Get current poster scrape rows dynamically."""
        if self.poster_scrape_tab:
            return self.poster_scrape_tab.rows
        return []
    
    @property
    def bulk_import_rows(self):
        """Get current bulk import rows dynamically."""
        if self.bulk_import_tab:
            return self.bulk_import_tab.rows
        return []
    
    @property
    def title_mappings_rows(self):
        """Get current title mappings rows dynamically."""
        if self.title_mappings_tab:
            return self.title_mappings_tab.rows
        return []
