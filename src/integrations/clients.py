"""API clients for external service integrations."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import httpx

from .config import RateLimitConfig
from ..errors import IntegrationError

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API requests."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.requests: List[float] = []
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to make a request."""
        async with self.lock:
            now = time.time()
            
            # Clean old requests
            self._clean_old_requests(now)
            
            # Check rate limits
            if self._should_wait(now):
                wait_time = self._calculate_wait_time(now)
                if wait_time > 0:
                    logger.info(f"Rate limit hit, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self._clean_old_requests(now)
            
            # Record this request
            self.requests.append(now)
    
    def _clean_old_requests(self, now: float):
        """Remove old requests from tracking."""
        # Keep requests from last hour
        cutoff = now - 3600
        self.requests = [req_time for req_time in self.requests if req_time > cutoff]
    
    def _should_wait(self, now: float) -> bool:
        """Check if we should wait before making a request."""
        if not self.requests:
            return False
        
        # Check per-minute limit
        if self.config.requests_per_minute:
            minute_ago = now - 60
            recent_requests = [req for req in self.requests if req > minute_ago]
            if len(recent_requests) >= self.config.requests_per_minute:
                return True
        
        # Check per-hour limit
        if self.config.requests_per_hour:
            hour_ago = now - 3600
            recent_requests = [req for req in self.requests if req > hour_ago]
            if len(recent_requests) >= self.config.requests_per_hour:
                return True
        
        # Check burst limit
        if self.config.burst_limit:
            last_10_seconds = now - 10
            recent_requests = [req for req in self.requests if req > last_10_seconds]
            if len(recent_requests) >= self.config.burst_limit:
                return True
        
        return False
    
    def _calculate_wait_time(self, now: float) -> float:
        """Calculate how long to wait before next request."""
        wait_times = []
        
        # Wait time for per-minute limit
        if self.config.requests_per_minute:
            minute_ago = now - 60
            recent_requests = [req for req in self.requests if req > minute_ago]
            if len(recent_requests) >= self.config.requests_per_minute:
                oldest_in_minute = min(recent_requests)
                wait_times.append(oldest_in_minute + 60 - now)
        
        # Wait time for per-hour limit
        if self.config.requests_per_hour:
            hour_ago = now - 3600
            recent_requests = [req for req in self.requests if req > hour_ago]
            if len(recent_requests) >= self.config.requests_per_hour:
                oldest_in_hour = min(recent_requests)
                wait_times.append(oldest_in_hour + 3600 - now)
        
        return max(wait_times) if wait_times else 0


class BaseAPIClient(ABC):
    """Base class for API clients."""
    
    def __init__(
        self,
        base_url: str,
        auth: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        rate_limit: Optional[RateLimitConfig] = None
    ):
        self.base_url = base_url.rstrip('/')
        self.auth = auth or {}
        self.default_headers = headers or {}
        self.timeout = timeout
        self.rate_limiter = RateLimiter(rate_limit) if rate_limit else None
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if not self.client:
            # Prepare headers
            headers = self.default_headers.copy()
            if 'headers' in self.auth:
                headers.update(self.auth['headers'])
            
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout
            )
    
    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """Make an HTTP request with rate limiting and error handling."""
        await self._ensure_client()
        
        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        # Prepare request parameters
        url = f"{self.base_url}{path}" if path.startswith('/') else f"{self.base_url}/{path}"
        
        # Add auth parameters
        if 'params' in self.auth:
            params = kwargs.get('params', {})
            params.update(self.auth['params'])
            kwargs['params'] = params
        
        if 'data' in self.auth:
            data = kwargs.get('data', {})
            data.update(self.auth['data'])
            kwargs['data'] = data
        
        try:
            response = await self.client.request(method, url, **kwargs)
            
            # Handle common HTTP errors
            if response.status_code >= 400:
                await self._handle_error_response(response)
            
            return response
        
        except httpx.TimeoutException:
            raise IntegrationError(
                "Request timeout",
                service=self.__class__.__name__,
                operation=method.upper()
            )
        except httpx.NetworkError as e:
            raise IntegrationError(
                f"Network error: {str(e)}",
                service=self.__class__.__name__,
                operation=method.upper()
            )
    
    async def _handle_error_response(self, response: httpx.Response):
        """Handle HTTP error responses."""
        error_message = f"HTTP {response.status_code}"
        
        try:
            error_data = response.json()
            if isinstance(error_data, dict):
                error_message = error_data.get('error', error_data.get('message', error_message))
        except:
            error_message = response.text or error_message
        
        if response.status_code == 401:
            raise IntegrationError(
                f"Authentication failed: {error_message}",
                service=self.__class__.__name__,
                status_code=response.status_code
            )
        elif response.status_code == 403:
            raise IntegrationError(
                f"Permission denied: {error_message}",
                service=self.__class__.__name__,
                status_code=response.status_code
            )
        elif response.status_code == 429:
            # Rate limit exceeded
            retry_after = response.headers.get('Retry-After', '60')
            raise IntegrationError(
                f"Rate limit exceeded: {error_message}",
                service=self.__class__.__name__,
                status_code=response.status_code,
                retry_after=int(retry_after)
            )
        else:
            raise IntegrationError(
                f"API error: {error_message}",
                service=self.__class__.__name__,
                status_code=response.status_code
            )
    
    @abstractmethod
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make a GET request."""
        pass
    
    @abstractmethod
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make a POST request."""
        pass
    
    @abstractmethod
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """Make a PUT request."""
        pass
    
    @abstractmethod
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """Make a DELETE request."""
        pass


class HTTPClient(BaseAPIClient):
    """Generic HTTP client for REST APIs."""
    
    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make a GET request."""
        return await self._make_request('GET', path, **kwargs)
    
    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make a POST request."""
        return await self._make_request('POST', path, **kwargs)
    
    async def put(self, path: str, **kwargs) -> httpx.Response:
        """Make a PUT request."""
        return await self._make_request('PUT', path, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """Make a DELETE request."""
        return await self._make_request('DELETE', path, **kwargs)
    
    async def patch(self, path: str, **kwargs) -> httpx.Response:
        """Make a PATCH request."""
        return await self._make_request('PATCH', path, **kwargs)


class OpenAIClient(HTTPClient):
    """Specialized client for OpenAI API."""
    
    async def create_completion(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a text completion."""
        response = await self.post('/completions', json={
            'model': model,
            'prompt': prompt,
            'max_tokens': max_tokens,
            'temperature': temperature,
            **kwargs
        })
        return response.json()
    
    async def create_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a chat completion."""
        response = await self.post('/chat/completions', json={
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            **kwargs
        })
        return response.json()


class SlackClient(HTTPClient):
    """Specialized client for Slack API."""
    
    async def send_message(
        self,
        channel: str,
        text: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Send a message to a Slack channel."""
        response = await self.post('/chat.postMessage', json={
            'channel': channel,
            'text': text,
            **kwargs
        })
        return response.json()
    
    async def get_channels(self) -> Dict[str, Any]:
        """Get list of channels."""
        response = await self.get('/conversations.list')
        return response.json()


class GoogleDriveClient(HTTPClient):
    """Specialized client for Google Drive API."""
    
    async def list_files(
        self,
        query: Optional[str] = None,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """List files in Google Drive."""
        params = {'pageSize': page_size}
        if query:
            params['q'] = query
        
        response = await self.get('/files', params=params)
        return response.json()
    
    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
        parent_folder_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload a file to Google Drive."""
        metadata = {'name': filename}
        if parent_folder_id:
            metadata['parents'] = [parent_folder_id]
        
        files = {
            'metadata': (None, json.dumps(metadata), 'application/json'),
            'media': (filename, file_content, mime_type)
        }
        
        response = await self.post('/upload/drive/v3/files', files=files)
        return response.json()


# Client factory
CLIENT_CLASSES = {
    'openai': OpenAIClient,
    'slack': SlackClient,
    'google_drive': GoogleDriveClient,
    'default': HTTPClient
}


def create_client(
    service_name: str,
    base_url: str,
    auth: Optional[Dict[str, Any]] = None,
    **kwargs
) -> BaseAPIClient:
    """Create an appropriate client for a service."""
    client_class = CLIENT_CLASSES.get(service_name, HTTPClient)
    return client_class(base_url=base_url, auth=auth, **kwargs)