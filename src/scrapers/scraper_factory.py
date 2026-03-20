"""Scraper factory for creating appropriate scraper instances."""

from typing import Tuple, List
from bs4 import BeautifulSoup
import threading

from ..core.models import PosterInfo
from ..core.config import Config
from .posterdb_scraper import PosterDBScraper
from .mediux_scraper import MediuxScraper


class ScraperFactory:
    """Factory for creating and managing scrapers."""
    
    def __init__(self, config: Config = None, use_playwright: bool = True):
        """Initialize scraper factory.
        
        Args:
            config: Configuration object.
            use_playwright: Whether to use Playwright for scraping.
        """
        self.config = config
        self.use_playwright = use_playwright
        self._lock = threading.Lock()
        self._posterdb_scraper = None
        self._mediux_scraper = None
    
    def scrape_url(self, url: str, should_process_item=None) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape URL using appropriate scraper.
        
        Args:
            url: URL to scrape.
            should_process_item: Optional callback to check content before scraping (used for MediUX).
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        # For concurrent scraping, disable Playwright to avoid browser session conflicts
        # Each thread will use requests-based scraping instead
        if "theposterdb.com" in url:
            return self._scrape_posterdb(url)
        elif "mediux.pro" in url and ("sets" in url or "user" in url):
            return self._scrape_mediux(url, should_process_item=should_process_item)
        elif ".html" in url:
            return self._scrape_local_html(url)
        else:
            raise ValueError("Unsupported URL. Must be ThePosterDB, MediUX, or local HTML file.")
    
    def _scrape_posterdb(self, url: str) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape ThePosterDB URL.
        
        Args:
            url: ThePosterDB URL.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        with PosterDBScraper(use_playwright=self.use_playwright, config=self.config) as scraper:
            if "/user/" in url:
                # User page - scrape all uploads
                return scraper.scrape_user_uploads(url)
            elif "/set/" in url:
                # Set URL - scrape the entire set
                return scraper.scrape(url)
            elif "/poster/" in url:
                # Single poster URL - scrape only that specific poster
                return scraper.scrape_single_poster(url)
            else:
                raise ValueError("Unsupported PosterDB URL format.")
    
    def _scrape_mediux(self, url: str, should_process_item=None) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape MediUX URL.
        
        Args:
            url: MediUX URL.
            should_process_item: Optional callback to check content before scraping.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        with MediuxScraper(use_playwright=self.use_playwright, config=self.config) as scraper:
            if "/user/" in url:
                # User page - scrape all uploads
                return scraper.scrape_user_uploads(url, should_process_item=should_process_item)
            elif "/sets/" in url:
                # Set URL - scrape the entire set
                return scraper.scrape(url, should_process_item=should_process_item)
            else:
                raise ValueError("Unsupported MediUX URL format.")
            
    
    def _scrape_local_html(self, file_path: str) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape local HTML file.
        
        Args:
            file_path: Path to HTML file.
            
        Returns:
            Tuple of poster lists.
        """
        with open(file_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # For local HTML files, we parse directly without Playwright
        # Create a temporary scraper just for parsing (no browser needed)
        from .posterdb_scraper import PosterDBScraper
        scraper = PosterDBScraper(use_playwright=False)
        return scraper._parse_posterdb(soup)
    
    def cleanup(self):
        """Clean up any open scraper resources."""
        # This method is called when the GUI closes
        if self._posterdb_scraper:
            try:
                self._posterdb_scraper.__exit__(None, None, None)
            except:
                pass
            self._posterdb_scraper = None
        
        if self._mediux_scraper:
            try:
                self._mediux_scraper.__exit__(None, None, None)
            except:
                pass
            self._mediux_scraper = None