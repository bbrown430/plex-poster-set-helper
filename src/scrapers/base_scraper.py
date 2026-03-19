"""Base scraper class with Playwright support and anti-detection measures."""

from abc import ABC, abstractmethod
from typing import List, Tuple
import random
import time
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser

from ..core.models import PosterInfo


class BaseScraper(ABC):
    """Base class for all scrapers with comprehensive anti-scraping measures."""
    
    # Default delay settings (can be overridden by config)
    DEFAULT_MIN_DELAY = 0.1
    DEFAULT_MAX_DELAY = 0.5
    DEFAULT_INITIAL_DELAY = 0.0
    DEFAULT_BATCH_DELAY = 2.0
    
    # Realistic user agents rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
    ]
    
    # Viewport sizes for variety
    VIEWPORTS = [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 2560, 'height': 1440},
        {'width': 1440, 'height': 900},
    ]
    
    def __init__(self, use_playwright: bool = True, config=None):
        """Initialize base scraper.
        
        Args:
            use_playwright: Whether to use Playwright for scraping (default True).
            config: Config object with scraper settings (optional).
        """
        self.use_playwright = use_playwright
        self._playwright = None
        self._browser: Browser = None
        self._page: Page = None
        self._request_count = 0
        self._last_request_time = 0
        
        # Load delay settings from config or use defaults
        if config:
            self._min_delay = getattr(config, 'scraper_min_delay', self.DEFAULT_MIN_DELAY)
            self._max_delay = getattr(config, 'scraper_max_delay', self.DEFAULT_MAX_DELAY)
            self._initial_delay = getattr(config, 'scraper_initial_delay', self.DEFAULT_INITIAL_DELAY)
            self._batch_delay = getattr(config, 'scraper_batch_delay', self.DEFAULT_BATCH_DELAY)
            self._page_wait_min = getattr(config, 'scraper_page_wait_min', 0.0)
            self._page_wait_max = getattr(config, 'scraper_page_wait_max', 0.5)
        else:
            self._min_delay = self.DEFAULT_MIN_DELAY
            self._max_delay = self.DEFAULT_MAX_DELAY
            self._initial_delay = self.DEFAULT_INITIAL_DELAY
            self._batch_delay = self.DEFAULT_BATCH_DELAY
            self._page_wait_min = 0.0
            self._page_wait_max = 0.5
    
    def __enter__(self):
        """Context manager entry."""
        if self.use_playwright:
            self._start_playwright()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.use_playwright:
            self._stop_playwright()
    
    def _apply_random_delay(self, min_delay: float = None, max_delay: float = None):
        """Apply random delay between requests to avoid detection.
        
        Args:
            min_delay: Minimum delay in seconds (uses config value if None).
            max_delay: Maximum delay in seconds (uses config value if None).
        """
        # Use configured delays if not specified
        if min_delay is None:
            min_delay = self._min_delay
        if max_delay is None:
            max_delay = self._max_delay
        
        # First request: use initial delay (typically 0 for speed)
        if self._request_count == 0:
            if self._initial_delay > 0:
                time.sleep(self._initial_delay)
        else:
            # Subsequent requests: apply normal delay
            delay = random.uniform(min_delay, max_delay)
            current_time = time.time()
            
            # Ensure we don't make requests too frequently
            if self._last_request_time > 0:
                time_since_last = current_time - self._last_request_time
                if time_since_last < min_delay:
                    additional_delay = min_delay - time_since_last
                    time.sleep(additional_delay)
            
            time.sleep(delay)
        
        self._last_request_time = time.time()
        self._request_count += 1
        
        # Add longer delay every 10 requests (if configured)
        if self._batch_delay > 0 and self._request_count % 10 == 0:
            time.sleep(random.uniform(self._batch_delay * 0.8, self._batch_delay * 1.2))
    
    def _simulate_human_mouse_movement(self):
        """Simulate realistic human mouse movement with curved paths."""
        try:
            # Get current viewport dimensions
            viewport = self._page.viewport_size
            width = viewport['width']
            height = viewport['height']
            
            # Random starting position (anywhere on screen)
            start_x = random.randint(50, width - 50)
            start_y = random.randint(50, height - 50)
            
            # Random end position
            end_x = random.randint(50, width - 50)
            end_y = random.randint(50, height - 50)
            
            # Calculate distance
            distance = ((end_x - start_x) ** 2 + (end_y - start_y) ** 2) ** 0.5
            
            # Number of steps based on distance (more steps for longer movements)
            steps = int(distance / 10) + random.randint(10, 20)
            
            # Create bezier curve control points for natural movement
            # Control point creates the curve
            ctrl_x = (start_x + end_x) / 2 + random.randint(-100, 100)
            ctrl_y = (start_y + end_y) / 2 + random.randint(-100, 100)
            
            # Move along bezier curve
            for i in range(steps):
                t = i / steps
                
                # Quadratic bezier curve formula
                x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * ctrl_x + t ** 2 * end_x
                y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * ctrl_y + t ** 2 * end_y
                
                # Add micro-jitter for realism (human hands aren't perfectly steady)
                jitter_x = random.uniform(-2, 2)
                jitter_y = random.uniform(-2, 2)
                
                self._page.mouse.move(x + jitter_x, y + jitter_y)
                
                # Variable speed - slower at start/end, faster in middle
                # This mimics human acceleration/deceleration
                if i < steps * 0.2 or i > steps * 0.8:
                    # Slow at start and end
                    time.sleep(random.uniform(0.005, 0.015))
                else:
                    # Faster in middle
                    time.sleep(random.uniform(0.001, 0.005))
            
            # Occasionally do a small random click (not on anything specific)
            # About 10% chance - humans sometimes misclick or click while reading
            if random.random() < 0.1:
                time.sleep(random.uniform(0.1, 0.3))
                # Random scroll instead of click to avoid triggering anything
                scroll_amount = random.randint(-100, 100)
                self._page.mouse.wheel(0, scroll_amount)
                time.sleep(random.uniform(0.1, 0.2))
                
        except Exception as e:
            # Silently fail - mouse movement is optional enhancement
            pass
    
    def _start_playwright(self):
        """Start Playwright browser with advanced anti-detection measures."""
        if not self._playwright:
            import os
            import sys
            import platform
            
            self._playwright = sync_playwright().start()
            
            # Advanced browser launch arguments for stealth
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-dev-tools',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
                '--window-position=0,0',
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--disable-backgrounding-occluded-windows',
            ]
            
            # Handle PyInstaller frozen executable
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                try:
                    system = platform.system()
                    channel = "chrome" if system in ["Windows", "Darwin"] else "chromium"
                    
                    self._browser = self._playwright.chromium.launch(
                        channel=channel,
                        headless=True,
                        args=browser_args
                    )
                except:
                    self._browser = self._playwright.chromium.launch(
                        headless=True,
                        args=browser_args
                    )
            else:
                # Running as script
                self._browser = self._playwright.chromium.launch(
                    headless=True,
                    args=browser_args
                )
            
            # Select random user agent and viewport for this session
            user_agent = random.choice(self.USER_AGENTS)
            viewport = random.choice(self.VIEWPORTS)
            
            # Create context with realistic browser fingerprint
            context = self._browser.new_context(
                viewport=viewport,
                user_agent=user_agent,
                locale='en-US',
                timezone_id='America/New_York',
                geolocation={'latitude': 40.7128, 'longitude': -74.0060},  # New York
                permissions=['geolocation'],
                color_scheme='light',
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False,
                accept_downloads=False,
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            )
            
            self._page = context.new_page()
            
            # Comprehensive anti-detection script
            self._page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override plugins to appear real
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Plugin"
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: ""},
                            description: "",
                            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                            length: 1,
                            name: "Chrome PDF Viewer"
                        },
                        {
                            0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                            1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                            description: "",
                            filename: "internal-nacl-plugin",
                            length: 2,
                            name: "Native Client"
                        }
                    ]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({state: Notification.permission}) :
                        originalQuery(parameters)
                );
                
                // Mock chrome object
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
                
                // Override automation-related properties
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });
                
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                
                // Override platform if needed
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });
                
                // Override vendor
                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.'
                });
                
                // Remove automation indicators
                delete navigator.__proto__.webdriver;
                
                // Mock battery API
                if (!navigator.getBattery) {
                    navigator.getBattery = () => Promise.resolve({
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1,
                        addEventListener: () => {},
                        removeEventListener: () => {},
                        dispatchEvent: () => true
                    });
                }
                
                // Mock connection API
                if (!navigator.connection) {
                    Object.defineProperty(navigator, 'connection', {
                        get: () => ({
                            effectiveType: '4g',
                            rtt: 50,
                            downlink: 10,
                            saveData: false
                        })
                    });
                }
                
                // Override canvas fingerprinting
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    if (type === 'image/png' && this.width === 280 && this.height === 60) {
                        return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
                    }
                    return originalToDataURL.apply(this, arguments);
                };
                
                // Override WebGL fingerprinting
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.call(this, parameter);
                };
            """)
            
            print("✓ Browser initialized with stealth mode active")
    
    def _stop_playwright(self):
        """Stop Playwright browser."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
    
    def fetch_page(self, url: str, wait_for_selector: str = None, extra_wait: int = 0) -> BeautifulSoup:
        """Fetch page content using Playwright with anti-detection.
        
        Args:
            url: URL to fetch.
            wait_for_selector: Optional CSS selector to wait for before returning.
            extra_wait: Additional milliseconds to wait after page load.
            
        Returns:
            BeautifulSoup object with page content.
            
        Raises:
            Exception: If Playwright fails to fetch the page.
        """
        if not self.use_playwright or not self._page:
            raise Exception("Playwright is required. Initialize scraper with use_playwright=True and use context manager.")
        
        # Show what we're fetching
        domain = url.split('/')[2] if len(url.split('/')) > 2 else url
        print(f"🌐 Navigating to {domain}...")
        
        # Apply random delay before request
        self._apply_random_delay()
        
        try:
                # Navigate to the page with random wait strategy
                wait_strategies = ["domcontentloaded", "networkidle"]
                wait_until = random.choice(wait_strategies)
                
                try:
                    self._page.goto(url, wait_until=wait_until, timeout=120000)
                except Exception as e:
                    print(f"Retrying with alternate wait strategy due to error: {str(e)}")
                    wait_until = wait_strategies[0] if wait_until == wait_strategies[1] else wait_strategies[1]
                    self._page.goto(url, wait_until=wait_until, timeout=120000)
                
                # Site-specific handling with configurable delays
                if "mediux.pro" in url:
                    try:
                        # Wait for the script tags that contain the data
                        self._page.wait_for_selector('script', timeout=5000)
                        # Additional wait for JavaScript execution (configurable)
                        if self._page_wait_max > 0:
                            wait_ms = int(random.uniform(self._page_wait_min, self._page_wait_max) * 1000)
                            self._page.wait_for_timeout(wait_ms)
                    except:
                        # Silently continue - script tags always exist, this rarely fails
                        pass
                elif "theposterdb.com" in url:
                    try:
                        # Wait for any poster-related content to load
                        self._page.wait_for_selector('script', timeout=5000)
                        # Configurable wait for content (was hardcoded 800-1500ms)
                        if self._page_wait_max > 0:
                            wait_ms = int(random.uniform(self._page_wait_min, self._page_wait_max) * 1000)
                            self._page.wait_for_timeout(wait_ms)
                    except:
                        # Silently continue - content usually loads anyway
                        pass
                else:
                    # Generic wait for dynamic content (configurable)
                    if self._page_wait_max > 0:
                        wait_ms = int(random.uniform(self._page_wait_min, self._page_wait_max) * 1000)
                        self._page.wait_for_timeout(wait_ms)
                
                # Wait for custom selector if provided
                if wait_for_selector:
                    try:
                        self._page.wait_for_selector(wait_for_selector, timeout=10000)
                    except:
                        print(f"Warning: Selector '{wait_for_selector}' not found")
                
                # Apply extra wait if specified
                if extra_wait > 0:
                    self._page.wait_for_timeout(extra_wait)
                
                # Simulate realistic human mouse movement with curved paths
                # Increased frequency - 60% chance for more natural browsing
                if random.random() < 0.6:
                    self._simulate_human_mouse_movement()
                
                # Occasionally scroll the page like a human reading
                if random.random() < 0.4:  # 40% chance
                    try:
                        # Scroll down a bit
                        scroll_amount = random.randint(100, 400)
                        self._page.mouse.wheel(0, scroll_amount)
                        time.sleep(random.uniform(0.2, 0.5))
                        
                        # Sometimes scroll back up (like re-reading)
                        if random.random() < 0.3:
                            scroll_back = random.randint(-200, -100)
                            self._page.mouse.wheel(0, scroll_back)
                            time.sleep(random.uniform(0.1, 0.3))
                    except:
                        pass
                
                html_content = self._page.content()
                
                # Debug: Check if we got content
                if len(html_content) < 1000:
                    print(f"Warning: Page content seems too short ({len(html_content)} bytes)")
                
                return BeautifulSoup(html_content, 'html.parser')
                
        except Exception as e:
            raise Exception(f"Failed to fetch page with Playwright: {str(e)}")
    
    @abstractmethod
    def scrape(self, url: str) -> Tuple[List[PosterInfo], List[PosterInfo], List[PosterInfo]]:
        """Scrape posters from URL.
        
        Args:
            url: URL to scrape.
            
        Returns:
            Tuple of (movie_posters, show_posters, collection_posters).
        """
        pass
