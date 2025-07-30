"""Advanced web scraping service with MCP integration."""

import asyncio
import logging
import json
import re
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.errors import handle_errors, IntegrationError
from src.config import settings

logger = logging.getLogger(__name__)


class ScrapingResult(BaseModel):
    """Result of a web scraping operation."""
    url: str = Field(..., description="URL that was scraped")
    title: Optional[str] = Field(None, description="Page title")
    content: str = Field(..., description="Extracted content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Page metadata")
    links: List[str] = Field(default_factory=list, description="Links found on the page")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the page was scraped")
    success: bool = Field(..., description="Whether scraping was successful")
    error: Optional[str] = Field(None, description="Error message if scraping failed")


class ScrapingConfig(BaseModel):
    """Configuration for web scraping."""
    selector: Optional[str] = Field(None, description="CSS selector for content extraction")
    include_images: bool = Field(False, description="Whether to include image descriptions")
    extract_metadata: bool = Field(True, description="Whether to extract metadata")
    follow_links: bool = Field(False, description="Whether to follow links")
    max_links: int = Field(0, description="Maximum number of links to follow")
    max_depth: int = Field(1, description="Maximum depth for link following")
    timeout: int = Field(30, description="Request timeout in seconds")
    user_agent: Optional[str] = Field(None, description="Custom user agent")
    use_mcp: bool = Field(True, description="Whether to use MCP for enhanced scraping")


class ScrapingService:
    """Service for advanced web scraping with MCP integration."""
    
    def __init__(self):
        self.client = None
        self.rate_limiters: Dict[str, float] = {}
        self.cache: Dict[str, ScrapingResult] = {}
        self.cache_expiry: Dict[str, float] = {}
        self.cache_ttl = 3600  # 1 hour
    
    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
            )
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    @handle_errors
    async def scrape_url(
        self,
        url: str,
        config: Optional[ScrapingConfig] = None
    ) -> ScrapingResult:
        """Scrape content from a URL."""
        config = config or ScrapingConfig()
        
        # Check cache
        if url in self.cache and time.time() < self.cache_expiry.get(url, 0):
            logger.info(f"Using cached result for {url}")
            return self.cache[url]
        
        # Apply rate limiting
        await self._apply_rate_limiting(url)
        
        # Use MCP if enabled
        if config.use_mcp:
            try:
                return await self._scrape_with_mcp(url, config)
            except Exception as e:
                logger.warning(f"MCP scraping failed, falling back to direct: {e}")
                # Fall back to direct scraping
        
        # Direct scraping
        return await self._scrape_direct(url, config)
    
    async def _scrape_with_mcp(self, url: str, config: ScrapingConfig) -> ScrapingResult:
        """Scrape using MCP fetch tool."""
        from src.mcp.fetch import fetch_url
        
        try:
            # Use MCP fetch tool
            result = await fetch_url(
                url=url,
                max_length=50000,
                raw=False
            )
            
            # Parse the result
            title = self._extract_title_from_content(result)
            
            # Extract links if needed
            links = []
            if config.follow_links:
                links = self._extract_links_from_content(result, url)
                if config.max_links > 0:
                    links = links[:config.max_links]
            
            # Create result
            scraping_result = ScrapingResult(
                url=url,
                title=title,
                content=result,
                links=links,
                success=True,
                metadata={"source": "mcp"}
            )
            
            # Cache the result
            self._cache_result(url, scraping_result)
            
            return scraping_result
            
        except Exception as e:
            logger.error(f"MCP scraping failed: {e}")
            raise IntegrationError(
                f"MCP scraping failed: {str(e)}",
                service="mcp_fetch",
                operation="fetch_url"
            )
    
    async def _scrape_direct(self, url: str, config: ScrapingConfig) -> ScrapingResult:
        """Scrape directly using httpx."""
        await self._ensure_client()
        
        try:
            # Set custom user agent if provided
            headers = {}
            if config.user_agent:
                headers["User-Agent"] = config.user_agent
            
            # Make the request
            response = await self.client.get(url, headers=headers, timeout=config.timeout)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract title
            title = soup.title.text.strip() if soup.title else None
            
            # Extract content based on selector or default to body
            if config.selector:
                content_elements = soup.select(config.selector)
                content = "\\n".join([elem.get_text(strip=True) for elem in content_elements])
            else:
                # Remove script, style, and other non-content elements
                for element in soup(["script", "style", "meta", "link", "noscript"]):
                    element.decompose()
                content = soup.body.get_text("\\n", strip=True) if soup.body else soup.get_text("\\n", strip=True)
            
            # Extract metadata
            metadata = {}
            if config.extract_metadata:
                metadata = self._extract_metadata(soup)
            
            # Extract links
            links = []
            if config.follow_links:
                links = self._extract_links(soup, url)
                if config.max_links > 0:
                    links = links[:config.max_links]
            
            # Create result
            scraping_result = ScrapingResult(
                url=url,
                title=title,
                content=content,
                metadata=metadata,
                links=links,
                success=True
            )
            
            # Cache the result
            self._cache_result(url, scraping_result)
            
            return scraping_result
            
        except httpx.HTTPStatusError as e:
            return ScrapingResult(
                url=url,
                content="",
                success=False,
                error=f"HTTP error: {e.response.status_code}"
            )
        except httpx.RequestError as e:
            return ScrapingResult(
                url=url,
                content="",
                success=False,
                error=f"Request error: {str(e)}"
            )
        except Exception as e:
            return ScrapingResult(
                url=url,
                content="",
                success=False,
                error=f"Scraping error: {str(e)}"
            )
    
    async def scrape_multiple(
        self,
        urls: List[str],
        config: Optional[ScrapingConfig] = None
    ) -> List[ScrapingResult]:
        """Scrape multiple URLs in parallel."""
        config = config or ScrapingConfig()
        
        tasks = [self.scrape_url(url, config) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ScrapingResult(
                    url=urls[i],
                    content="",
                    success=False,
                    error=f"Error: {str(result)}"
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def deep_scrape(
        self,
        start_url: str,
        config: Optional[ScrapingConfig] = None
    ) -> List[ScrapingResult]:
        """Perform deep scraping by following links."""
        config = config or ScrapingConfig(follow_links=True, max_depth=2, max_links=5)
        
        # Ensure follow_links is enabled
        config.follow_links = True
        
        visited = set()
        to_visit = [(start_url, 0)]  # (url, depth)
        results = []
        
        while to_visit:
            url, depth = to_visit.pop(0)
            
            if url in visited or depth > config.max_depth:
                continue
            
            visited.add(url)
            
            # Scrape the URL
            result = await self.scrape_url(url, config)
            results.append(result)
            
            # Add links to visit queue if within depth limit
            if depth < config.max_depth and result.success:
                for link in result.links:
                    if link not in visited:
                        to_visit.append((link, depth + 1))
                        
                        # Limit the number of URLs to visit
                        if len(to_visit) + len(visited) >= 50:  # Safety limit
                            break
        
        return results
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract metadata from HTML."""
        metadata = {}
        
        # Extract Open Graph metadata
        for meta in soup.find_all("meta"):
            if meta.get("property") and meta["property"].startswith("og:"):
                key = meta["property"][3:]
                metadata[key] = meta.get("content")
            elif meta.get("name"):
                metadata[meta["name"]] = meta.get("content")
        
        # Extract JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                json_ld = json.loads(script.string)
                metadata["json_ld"] = json_ld
                break
            except:
                pass
        
        return metadata
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract links from HTML."""
        links = []
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            
            # Skip empty links, anchors, and javascript
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            
            # Convert relative URLs to absolute
            if not href.startswith(("http://", "https://")):
                href = urljoin(base_url, href)
            
            # Only include http/https links
            if href.startswith(("http://", "https://")):
                links.append(href)
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(links))
    
    def _extract_links_from_content(self, content: str, base_url: str) -> List[str]:
        """Extract links from text content."""
        # Simple regex to find URLs
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        urls = re.findall(url_pattern, content)
        
        # Convert relative URLs to absolute
        processed_urls = []
        for url in urls:
            if not url.startswith(("http://", "https://")):
                if url.startswith("www."):
                    url = "https://" + url
                else:
                    url = urljoin(base_url, url)
            
            processed_urls.append(url)
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(processed_urls))
    
    def _extract_title_from_content(self, content: str) -> Optional[str]:
        """Extract title from text content."""
        # Try to find a title in the content
        title_match = re.search(r'(?:Title:|#)\s*([^\n]+)', content)
        if title_match:
            return title_match.group(1).strip()
        
        # Otherwise use the first non-empty line
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                return line[:100]  # Limit title length
        
        return None
    
    async def _apply_rate_limiting(self, url: str):
        """Apply rate limiting for a domain."""
        domain = urlparse(url).netloc
        
        # Check if we need to wait
        now = time.time()
        if domain in self.rate_limiters:
            wait_until = self.rate_limiters[domain]
            if now < wait_until:
                wait_time = wait_until - now
                logger.info(f"Rate limiting {domain}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        # Update rate limiter (1 request per 2 seconds per domain)
        self.rate_limiters[domain] = now + 2.0
    
    def _cache_result(self, url: str, result: ScrapingResult):
        """Cache a scraping result."""
        self.cache[url] = result
        self.cache_expiry[url] = time.time() + self.cache_ttl
        
        # Limit cache size
        if len(self.cache) > 1000:
            # Remove oldest entries
            oldest_url = min(self.cache_expiry.items(), key=lambda x: x[1])[0]
            del self.cache[oldest_url]
            del self.cache_expiry[oldest_url]


# Global scraping service instance
scraping_service = ScrapingService()