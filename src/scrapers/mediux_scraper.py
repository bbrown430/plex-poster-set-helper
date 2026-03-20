"""MediUX scraper implementation."""

import math
import re
from typing import List, Tuple

from ..core.models import PosterInfo
from ..core.config import Config
from ..utils.helpers import parse_string_to_dict
from .base_scraper import BaseScraper


class MediuxScraper(BaseScraper):
    """Scraper for MediUX website."""
    
    def __init__(self, config: Config = None, use_playwright: bool = True):
        """Initialize MediUX scraper.
        
        Args:
            config: Configuration object for filter settings.
            use_playwright: Whether to use Playwright.
        """
        super().__init__(use_playwright, config)
        self.config = config
    
    def scrape(self, url: str, should_process_item=None) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape posters from MediUX.
        
        Args:
            url: MediUX set URL.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        
        soup = self.fetch_page(url)
        return self._parse_mediux(soup, should_process_item=should_process_item)
    
    def scrape_user_uploads(self, url: str, should_process_item=None) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape all uploads from a user's page.
        
        Args:
            url: User profile URL.
            should_process_item: Optional callback to check content before scraping.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        soup = self.fetch_page(url)
        pages = self._get_user_page_count(soup)
        
        if not pages:
            print(f"Could not determine the number of pages for {url}")
            return [], [], []
        
        # Clean URL
        if "?" in url:
            url = url.split("?")[0]
        
        all_movie_posters = []
        all_show_posters = []
        all_collection_posters = []
        
        base_url = url.removesuffix('/sets')
        
        for page in range(pages):
            print(f"Scraping page {page + 1} of {pages}.")
            page_url = f"{base_url}/sets?page={page + 1}"
            
            grid_soup = self.fetch_page(page_url)
            set_links = self.scrape_sets_from_page(grid_soup)
            
            for set_link in set_links:
                movie_posters, show_posters, collection_posters = self.scrape(set_link, should_process_item=should_process_item)
                all_movie_posters.extend(movie_posters)
                all_show_posters.extend(show_posters)
                all_collection_posters.extend(collection_posters)
        
        return all_movie_posters, all_show_posters, all_collection_posters
    
    def _get_user_page_count(self, soup) -> int:
        """Get number of pages for user uploads.
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            Number of pages or None.
        """
        try:
            set_link = soup.find('a', href=lambda href: href and href.endswith('/sets'))
            if set_link:
                raw_text = set_link.get_text(strip=True)
                number_str = re.sub(r'\D', '', raw_text)
                upload_count = int(number_str)
                pages = math.ceil(upload_count / 12)
                
                return pages
        except:
            return None
        
    def scrape_sets_from_page(self, soup) -> List[str]:
        """Extract all set links from a user sets page.
        
        Args:
            soup: BeautifulSoup object.
            
        Returns:
            List of set URLs.
        """
        set_links = []
        try:
            headings = soup.select('h3 a')
            
            for link in headings:
                href = link.get('href')
                if href and '/sets/' in href:
                    full_url = f"https://mediux.pro{href}" if href.startswith('/') else href
                    set_links.append(full_url)
            
            return set_links
            
        except Exception as e:
            print(f"Error scraping set links: {e}")
            return []
    
    def _parse_mediux(self, soup, should_process_item=None) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Parse MediUX page for posters.
        
        Args:
            soup: BeautifulSoup object.
            should_process_item: Optional callback to check content before scraping.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        # Use direct API URL for original quality images instead of Next.js proxy
        base_url = "https://api.mediux.pro/assets/"
        quality_suffix = ""
        
        movie_posters = []
        show_posters = []
        collection_posters = []
        
        scripts = soup.find_all('script')
        poster_data = None
        data_dict = None
        
        print(f"Found {len(scripts)} script tags on page")
        
        # Extract poster data from scripts
        for i, script in enumerate(scripts):
            script_text = script.text if script.text else ""
            
            # Look for the JSON data in __NEXT_DATA__ or inline scripts
            if 'files' in script_text and 'set' in script_text:
                if 'Set Link\\' not in script_text:
                    try:
                        print(f"Attempting to parse script tag {i+1}...")
                        data_dict = parse_string_to_dict(script_text)
                        
                        if "set" in data_dict and "files" in data_dict["set"]:
                            poster_data = data_dict["set"]["files"]
                            print(f"Successfully parsed poster data: {len(poster_data)} posters found")
                            break
                    except Exception as e:
                        print(f"Error parsing MediUX data from script {i+1}: {str(e)}")
                        continue
        
        if not poster_data:
            print("ERROR: No poster data found in page!")
            print("This may be due to:")
            print("  1. MediUX changed their page structure")
            print("  2. JavaScript didn't load properly")
            print("  3. Page requires authentication or has anti-scraping")
            return movie_posters, show_posters, collection_posters
        
        if should_process_item and data_dict and "set" in data_dict:
            should_skip = False
            check_title = "Unknown"
            
            # If you don't own the show, you don't need any posters from it.
            if data_dict["set"].get("show"):
                check_title = data_dict["set"]["show"]["name"]
                try:
                    check_year = int(data_dict["set"]["show"]["first_air_date"][:4])
                except:
                    check_year = None
                    
                if not should_process_item(check_title, check_year):
                    should_skip = True

            # If the set is for ONE movie and you don't own it, skip it.
            elif data_dict["set"].get("movie"):
                check_title = data_dict["set"]["movie"]["title"]
                try:
                    check_year = int(data_dict["set"]["movie"]["release_date"][:4])
                except:
                    check_year = None
                    
                if not should_process_item(check_title, check_year):
                    should_skip = True

            if should_skip:
                return [], [], []
        
        # Determine media type
        media_type = self._determine_media_type(poster_data)
        
        # Parse each poster
        for data in poster_data:
            try:
                if media_type == "Show":
                    poster_info = self._parse_show_data(data, data_dict, base_url, quality_suffix)
                    if poster_info:
                        show_posters.append(poster_info)
                elif media_type == "Movie":
                    poster_info = self._parse_movie_data(data, data_dict, base_url, quality_suffix)
                    if poster_info:
                        if poster_info.is_collection():
                            collection_posters.append(poster_info)
                        else:
                            movie_posters.append(poster_info)
            except Exception as e:
                print(f"Error parsing MediUX poster data: {str(e)}")
        
        return movie_posters, show_posters, collection_posters
    
    def _determine_media_type(self, poster_data: list) -> str:
        """Determine if set is for TV shows or movies.
        
        Args:
            poster_data: List of poster data dictionaries.
            
        Returns:
            "Show" or "Movie".
        """
        for data in poster_data:
            if (data.get("show_id") is not None or 
                data.get("show_id_backdrop") is not None or 
                data.get("episode_id") is not None or 
                data.get("season_id") is not None):
                return "Show"
        return "Movie"
    
    def _parse_show_data(self, data: dict, data_dict: dict, base_url: str, quality_suffix: str) -> PosterInfo:
        """Parse TV show poster data from MediUX.
        
        Args:
            data: Individual poster data.
            data_dict: Full data dictionary.
            base_url: Base URL for images.
            quality_suffix: Quality suffix for images.
            
        Returns:
            PosterInfo object or None.
        """
        show_name = data_dict["set"]["show"]["name"]
        
        try:
            year = int(data_dict["set"]["show"]["first_air_date"][:4])
        except:
            year = None
        
        file_type = data.get("fileType")
        season = None
        episode = None
        
        # Determine poster type and target
        if file_type == "title_card":
            episode_id = data["episode_id"]["id"]
            season = data["episode_id"]["season_id"]["season_number"]
            title = data.get("title", "")
            try:
                episode = int(title.rsplit(" E", 1)[1])
            except:
                print(f"Error getting episode number for {title}.")
                episode = None
        elif file_type == "backdrop":
            season = "Backdrop"
            episode = None
        elif data.get("season_id") is not None:
            season_id = data["season_id"]["id"]
            episodes = data_dict["set"]["show"]["seasons"]
            season_data = [ep for ep in episodes if ep["id"] == season_id][0]
            season = season_data["season_number"]
            episode = "Cover"
        elif data.get("show_id") is not None:
            season = "Cover"
            episode = None
        
        # Check filters
        if not self._check_filter(file_type):
            print(f"{show_name} - skipping. '{file_type}' is not in 'mediux_filters'")
            return None
        
        image_stub = data["id"]
        poster_url = f"{base_url}{image_stub}{quality_suffix}"
        
        return PosterInfo(
            title=show_name,
            season=season,
            episode=episode,
            url=poster_url,
            year=year,
            source="mediux"
        )
    
    def _parse_movie_data(self, data: dict, data_dict: dict, base_url: str, quality_suffix: str) -> PosterInfo:
        """Parse movie poster data from MediUX.
        
        Args:
            data: Individual poster data.
            data_dict: Full data dictionary.
            base_url: Base URL for images.
            quality_suffix: Quality suffix for images.
            
        Returns:
            PosterInfo object or None.
        """
        title = "Untitled"
        year = None
        
        if data.get("movie_id"):
            if data_dict["set"].get("movie"):
                title = data_dict["set"]["movie"]["title"]
                year = int(data_dict["set"]["movie"]["release_date"][:4])
            elif data_dict["set"].get("collection"):
                movie_id = data["movie_id"]["id"]
                movies = data_dict["set"]["collection"]["movies"]
                movie_data = [movie for movie in movies if movie["id"] == movie_id][0]
                title = movie_data["title"]
                year = int(movie_data["release_date"][:4])
        elif data.get("collection_id"):
            title = data_dict["set"]["collection"]["collection_name"]
            year = None  # Collections don't have years
        
        image_stub = data["id"]
        poster_url = f"{base_url}{image_stub}{quality_suffix}"
        
        return PosterInfo(
            title=title,
            year=year,
            url=poster_url,
            source="mediux"
        )
    
    def _check_filter(self, file_type: str) -> bool:
        """Check if file type passes filters.
        
        Args:
            file_type: Type of file (title_card, backdrop, etc.).
            
        Returns:
            True if allowed, False otherwise.
        """
        if not self.config or not self.config.mediux_filters:
            return True
        
        return file_type in self.config.mediux_filters