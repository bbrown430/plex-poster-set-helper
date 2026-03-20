from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base_handler import BaseHandler
from ....utils.helpers import get_exe_dir
from ....utils.text_utils import is_comment
import os

class URLHandler(BaseHandler):
    """Handler for URL processing operations."""
    
    def handle_single_url(self):
        """Handle single URL input."""
        url = input("Enter the URL: ").strip()
        if url:
            self.process_url(url)
        else:
            print("No URL provided.")
            
    def handle_bulk_import(self):
        """Handle bulk import from file."""
        # Show available bulk files
        if self.config.bulk_files and len(self.config.bulk_files) > 1:
            print("\nAvailable bulk import files:")
            for i, filename in enumerate(self.config.bulk_files, 1):
                print(f"  {i}. {filename}")
            print(f"  {len(self.config.bulk_files) + 1}. Enter custom path")
            
            choice = input(f"\nSelect a file (1-{len(self.config.bulk_files) + 1}) or press [Enter] for default: ").strip()
            
            if not choice:
                file_path = self.config.bulk_files[0]
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.config.bulk_files):
                    file_path = self.config.bulk_files[idx]
                elif idx == len(self.config.bulk_files):
                    file_path = input("Enter custom file path: ").strip()
                else:
                    print("Invalid selection.")
                    return
            else:
                file_path = choice
        else:
            file_path = input(f"Enter the path to the bulk import file, or press [Enter] to use '{self.config.bulk_files[0] if self.config.bulk_files else 'bulk_import.txt'}': ").strip()
            if not file_path:
                file_path = self.config.bulk_files[0] if self.config.bulk_files else "bulk_import.txt"
        
        self.process_bulk_file(file_path)
    
    def process_url(self, url: str):
        """Process a single URL.
        
        Args:
            url: URL to process.
        """
        self.app._setup_services()
        
        if not self._check_libraries():
            return
        
        try:
            self.logger.info(f"Processing URL: {url}")
            print(f"\nScraping: {url}")
            movie_posters, show_posters, collection_posters = self.scraper_factory.scrape_url(url)
            
            self.logger.debug(f"Scraped {len(collection_posters)} collections, {len(movie_posters)} movies, {len(show_posters)} shows")
            print(f"Found {len(collection_posters)} collection posters, {len(movie_posters)} movie posters, {len(show_posters)} show posters.")
            
            # Process all posters
            all_posters = collection_posters + movie_posters + show_posters
            for poster in all_posters:
                self.upload_service.process_poster(poster)
            
            self.logger.info(f"Successfully completed processing: {url}")
            print(f"\nCompleted processing: {url}")
        
        except Exception as e:
            self.logger.exception(f"Error processing URL {url}: {str(e)}")
            print(f"Error processing URL: {str(e)}")
            
    def process_bulk_file(self, file_path: str, concurrent: bool = True):
        """Process bulk import file.
        
        Args:
            file_path: Path to bulk import file.
            concurrent: Whether to use concurrent processing (default True).
        """
        # Convert relative path to absolute for cross-platform compatibility
        if not os.path.isabs(file_path):
            file_path = os.path.join(get_exe_dir(), file_path)
        
        self.app._setup_services()
        
        if not self._check_libraries():
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                urls = file.readlines()
            
            valid_urls = []
            for url in urls:
                url = url.strip()
                if not is_comment(url):
                    valid_urls.append(url)
            
            if not valid_urls:
                print("No valid URLs found in file.")
                return
            
            total_urls = len(valid_urls)
            max_workers = getattr(self.config, 'max_workers', 3)
            
            print(f"\nProcessing {total_urls} URLs from {file_path}...")
            
            if concurrent and total_urls > 1:
                print(f"Using {max_workers} concurrent workers for parallel processing\n")
                self._process_urls_concurrent(valid_urls, max_workers)
            else:
                print("Using sequential processing\n")
                self._process_urls_sequential(valid_urls)
            
            print("\nBulk import completed.")
        
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error reading file: {str(e)}")
            
    def should_process_item(self, title, year=None):
        """Callback function to check if a title is in the library.
        If the title is not found, we can skip the entire MediUX set to save time.
        
        Args:
            title: Title to check.
            year: Optional year to check.
        """
        plex_service = self.app.plex_service
        all_libraries = plex_service.movie_libraries + plex_service.tv_libraries
        
        results = plex_service.find_in_library(all_libraries, title, year)
        return results is not None
            
    def _process_urls_sequential(self, urls: List[str]):
        """Process URLs sequentially.
        
        Args:
            urls: List of URLs to process.
        """
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] Processing: {url}")
            
            try:
                movie_posters, show_posters, collection_posters = self.scraper_factory.scrape_url(url, should_process_item=self.should_process_item)
                
                # Process all posters
                all_posters = collection_posters + movie_posters + show_posters
                for poster in all_posters:
                    self.upload_service.process_poster(poster)
                
                print(f"✓ Completed: {url}")
            
            except Exception as e:
                print(f"✗ Error processing {url}: {str(e)}")
                
    def _process_urls_concurrent(self, urls: List[str], max_workers: int):
        """Process URLs concurrently using thread pool.
        
        Args:
            urls: List of URLs to process.
            max_workers: Maximum number of concurrent workers.
        """
        total_urls = len(urls)
        completed = 0
        total_posters = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self._scrape_and_upload_url, url, should_process_item=self.should_process_item): url 
                for url in urls
            }
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                completed += 1
                
                try:
                    poster_count, error = future.result()
                    
                    if error:
                        print(f"✗ [{completed}/{total_urls}] Error: {error}")
                    else:
                        total_posters += poster_count
                        print(f"✓ [{completed}/{total_urls}] Completed {url} - Uploaded {poster_count} posters")
                
                except Exception as e:
                    print(f"✗ [{completed}/{total_urls}] Exception processing {url}: {str(e)}")
        
        print(f"\n📊 Total: {total_posters} posters uploaded from {total_urls} URLs")
        
    def _scrape_and_upload_url(self, url: str, should_process_item=None):
        """Scrape and upload posters from a single URL (thread-safe).
        
        Args:
            url: URL to process.
            
        Returns:
            Tuple of (poster_count, error_message or None)
        """
        try:
            movie_posters, show_posters, collection_posters = self.scraper_factory.scrape_url(url, should_process_item=should_process_item)
            
            # Process all posters
            all_posters = collection_posters + movie_posters + show_posters
            for poster in all_posters:
                self.upload_service.process_poster(poster)
            
            return (len(all_posters), None)
        
        except Exception as e:
            return (0, f"{url} - {str(e)}")