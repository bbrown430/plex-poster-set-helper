"""CLI interface for Plex Poster Set Helper."""

import sys
from ...core.config import ConfigManager
from ...core.logger import get_logger
from ...services.plex_service import PlexService
from ...services.poster_upload_service import PosterUploadService
from ...scrapers.scraper_factory import ScraperFactory

# Import handlers
from .handlers.url_handler import URLHandler
from .handlers.mapping_handler import MappingHandler
from .handlers.reset_handler import ResetHandler
from .handlers.stats_handler import StatsHandler

class PlexPosterCLI:
    """Command-line interface for the application."""
    
    def __init__(self):
        """Initialize the CLI."""
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        
        # Initialize logger with config
        self.logger = get_logger()
        self.logger.configure(log_file=self.config.log_file)
        self.logger.info("CLI Application initializing...")
        
        self.plex_service: PlexService = None
        self.upload_service: PosterUploadService = None
        self.scraper_factory: ScraperFactory = None
        
        # Initialize handlers
        self.url_handler = URLHandler(self)
        self.mapping_handler = MappingHandler(self)
        self.reset_handler = ResetHandler(self)
        self.stats_handler = StatsHandler(self)
    
    def run(self):
        """Run the interactive CLI loop."""
        sys.stdout.reconfigure(encoding='utf-8')
        
        while True:
            self._display_main_menu()
            
            choice = input("\nSelect an option (1-7): ").strip()
            
            if choice == '1':
                self.url_handler.handle_single_url()
            elif choice == '2':
                self.url_handler.handle_bulk_import()
            elif choice == '3':
                self.mapping_handler.handle_menu()
            elif choice == '4':
                self.reset_handler.handle_menu()
            elif choice == '5':
                self.stats_handler.handle_view_stats()
            elif choice == '6':
                self._launch_gui()
                break
            elif choice == '7':
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please select an option between 1 and 7.")
                
    def process_bulk_file(self, file_path: str):
        """Process a bulk file."""
        self.url_handler.process_bulk_file(file_path)
        
    def process_url(self, url: str):
        """Process a single URL."""
        self.url_handler.process_url(url)
    
    def _display_main_menu(self):
        """Display the main menu with stats."""
        print("\n" + "="*60)
        print("         Plex Poster Set Helper - Main Menu")
        print("="*60)
        
        # Try to show quick stats if Plex is connected
        try:
            if not self.plex_service:
                self.plex_service = PlexService(self.config)
                self.plex_service.setup(gui_mode=False)
            
            if self.plex_service:
                # Get labeled items count quickly
                labeled_items = self.plex_service.get_items_by_label("Plex_poster_set_helper")
                if labeled_items:
                    print(f"\n📊 Quick Stats: {len(labeled_items)} items with custom posters")
        except:
            pass  # Silently skip stats if Plex not connected
        
        print("\n1. Enter a URL (ThePosterDB/MediUX set or user URL)")
        print("2. Run Bulk Import from file")
        print("3. Manage Title Mappings")
        print("4. Reset Posters to Default")
        print("5. View Detailed Stats")
        print("6. Launch GUI")
        print("7. Exit")
        
    def _launch_gui(self):
        """Launch the GUI."""
        print("Launching GUI...")
        # Local import to avoid circular dependency
        from ..gui import PlexPosterGUI
        gui = PlexPosterGUI()
        gui.run()
        
    def _setup_services(self):
        """Setup Plex and scraper services."""
        if not self.plex_service:
            self.plex_service = PlexService(self.config)
            tv, movies = self.plex_service.setup(gui_mode=False)
            
            if not tv and not movies:
                print("\nError: Unable to setup Plex connection.")
                print("Please check your config.json file and ensure base_url and token are correct.")
                sys.exit(1)
        
        if not self.upload_service:
            self.upload_service = PosterUploadService(self.plex_service)
        
        if not self.scraper_factory:
            self.scraper_factory = ScraperFactory(self.config, use_playwright=True)
            
    def _check_libraries(self) -> bool:
        """Check if libraries are initialized.
        
        Returns:
            True if libraries are initialized, False otherwise.
        """
        if not self.plex_service.tv_libraries:
            print("Warning: No TV libraries initialized. Verify 'tv_library' in config.json.")
        
        if not self.plex_service.movie_libraries:
            print("Warning: No movie libraries initialized. Verify 'movie_library' in config.json.")
        
        return bool(self.plex_service.tv_libraries or self.plex_service.movie_libraries)
