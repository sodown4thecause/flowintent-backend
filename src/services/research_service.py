"""Deep research service with multi-agent approach inspired by Skywork.ai."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import re
from urllib.parse import quote_plus

from src.services.scraping_service import ScrapingService, ScrapingConfig, ScrapingResult
from src.services.rag_service import RAGService
from src.services.vector_store import VectorStoreService
from src.errors import IntegrationError, handle_errors
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ResearchQuery:
    """A research query with context and requirements."""
    query: str
    context: Optional[str] = None
    depth: str = "medium"  # shallow, medium, deep
    sources: List[str] = None  # specific sources to search
    time_range: Optional[str] = None  # "1d", "1w", "1m", "1y"
    language: str = "en"
    max_sources: int = 10
    include_academic: bool = False
    include_news: bool = True
    include_social: bool = False
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = []


@dataclass
class ResearchSource:
    """A source of information for research."""
    url: str
    title: str
    content: str
    relevance_score: float
    credibility_score: float
    timestamp: Optional[datetime] = None
    source_type: str = "web"  # web, academic, news, social
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ResearchResult:
    """Result of a research operation."""
    query: str
    summary: str
    key_findings: List[str]
    sources: List[ResearchSource]
    confidence_score: float
    research_depth: str
    timestamp: datetime
    follow_up_questions: List[str] = None
    related_topics: List[str] = None
    
    def __post_init__(self):
        if self.follow_up_questions is None:
            self.follow_up_questions = []
        if self.related_topics is None:
            self.related_topics = []


class ResearchService:
    """Advanced research service with multi-agent approach."""
    
    def __init__(
        self,
        scraping_service: ScrapingService,
        rag_service: RAGService,
        vector_store: VectorStoreService
    ):
        self.scraping_service = scraping_service
        self.rag_service = rag_service
        self.vector_store = vector_store
        
        # Search engines and APIs
        self.search_engines = {
            'google': self._search_google,
            'bing': self._search_bing,
            'duckduckgo': self._search_duckduckgo,
            'academic': self._search_academic,
            'news': self._search_news
        }
        
        # Research agents
        self.agents = {
            'query_planner': self._plan_research_queries,
            'source_finder': self._find_sources,
            'content_extractor': self._extract_content,
            'fact_checker': self._verify_facts,
            'synthesizer': self._synthesize_findings
        }
    
    @handle_errors
    async def conduct_research(self, query: ResearchQuery) -> ResearchResult:
        """Conduct comprehensive research on a topic."""
        logger.info(f"Starting research for: {query.query}")
        
        # Phase 1: Query Planning
        research_plan = await self.agents['query_planner'](query)
        
        # Phase 2: Source Discovery
        sources = await self.agents['source_finder'](research_plan)
        
        # Phase 3: Content Extraction
        extracted_sources = await self.agents['content_extractor'](sources)
        
        # Phase 4: Fact Verification
        verified_sources = await self.agents['fact_checker'](extracted_sources)
        
        # Phase 5: Synthesis
        result = await self.agents['synthesizer'](query, verified_sources)
        
        # Store research in vector database for future reference
        await self._store_research_result(result)
        
        logger.info(f"Research completed with {len(result.sources)} sources")
        return result
    
    async def _plan_research_queries(self, query: ResearchQuery) -> Dict[str, Any]:
        """Plan the research approach and generate sub-queries."""
        # Generate related queries and search strategies
        sub_queries = await self._generate_sub_queries(query.query)
        
        # Determine search strategies based on query type
        strategies = self._determine_search_strategies(query)
        
        return {
            'main_query': query.query,
            'sub_queries': sub_queries,
            'strategies': strategies,
            'depth': query.depth,
            'max_sources': query.max_sources
        }
    
    async def _find_sources(self, research_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find relevant sources using multiple search engines."""
        all_sources = []
        
        # Search with main query
        main_query = research_plan['main_query']
        
        # Use different search engines based on strategies
        for strategy in research_plan['strategies']:
            if strategy == 'web_search':
                sources = await self._search_web(main_query)
                all_sources.extend(sources)
            elif strategy == 'academic_search':
                sources = await self._search_academic(main_query)
                all_sources.extend(sources)
            elif strategy == 'news_search':
                sources = await self._search_news(main_query)
                all_sources.extend(sources)
        
        # Search with sub-queries
        for sub_query in research_plan['sub_queries']:
            sources = await self._search_web(sub_query)
            all_sources.extend(sources[:3])  # Limit sub-query results
        
        # Remove duplicates and rank by relevance
        unique_sources = self._deduplicate_sources(all_sources)
        ranked_sources = self._rank_sources(unique_sources, main_query)
        
        # Limit to max sources
        return ranked_sources[:research_plan['max_sources']]
    
    async def _extract_content(self, sources: List[Dict[str, Any]]) -> List[ResearchSource]:
        """Extract content from sources."""
        extracted_sources = []
        
        # Configure scraping for research
        config = ScrapingConfig(
            javascript_enabled=True,
            extract_structured_data=True,
            timeout=30,
            max_retries=2
        )
        
        # Extract content from each source
        for source in sources:
            try:
                scraping_result = await self.scraping_service.scrape_url(
                    source['url'], config
                )
                
                # Create research source
                research_source = ResearchSource(
                    url=source['url'],
                    title=scraping_result.title or source.get('title', ''),
                    content=scraping_result.content,
                    relevance_score=source.get('relevance_score', 0.5),
                    credibility_score=self._assess_credibility(scraping_result),
                    timestamp=scraping_result.timestamp,
                    source_type=source.get('type', 'web'),
                    metadata=scraping_result.metadata
                )
                
                extracted_sources.append(research_source)
                
            except Exception as e:
                logger.warning(f"Failed to extract content from {source['url']}: {e}")
                continue
        
        return extracted_sources
    
    async def _verify_facts(self, sources: List[ResearchSource]) -> List[ResearchSource]:
        """Verify facts and assess source reliability."""
        verified_sources = []
        
        for source in sources:
            # Cross-reference with other sources
            verification_score = await self._cross_reference_facts(source, sources)
            
            # Adjust credibility based on verification
            source.credibility_score = (source.credibility_score + verification_score) / 2
            
            # Only include sources above credibility threshold
            if source.credibility_score > 0.3:
                verified_sources.append(source)
        
        return verified_sources
    
    async def _synthesize_findings(
        self,
        query: ResearchQuery,
        sources: List[ResearchSource]
    ) -> ResearchResult:
        """Synthesize findings into a comprehensive research result."""
        # Extract key information from sources
        all_content = "\n\n".join([
            f"Source: {source.title}\n{source.content[:1000]}..."
            for source in sources
        ])
        
        # Generate summary using RAG
        summary_prompt = f"""
        Based on the following research sources, provide a comprehensive summary for the query: "{query.query}"
        
        Sources:
        {all_content}
        
        Please provide:
        1. A clear, concise summary
        2. Key findings (3-5 bullet points)
        3. Follow-up questions for deeper research
        4. Related topics worth exploring
        """
        
        summary_response = await self.rag_service.query(
            summary_prompt,
            context=all_content,
            max_tokens=1000
        )
        
        # Parse the response to extract structured information
        summary, key_findings, follow_ups, related = self._parse_synthesis_response(
            summary_response
        )
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(sources)
        
        return ResearchResult(
            query=query.query,
            summary=summary,
            key_findings=key_findings,
            sources=sources,
            confidence_score=confidence_score,
            research_depth=query.depth,
            timestamp=datetime.now(),
            follow_up_questions=follow_ups,
            related_topics=related
        )
    
    async def _generate_sub_queries(self, main_query: str) -> List[str]:
        """Generate related sub-queries for comprehensive research."""
        # Use RAG to generate related queries
        prompt = f"""
        For the research topic "{main_query}", generate 3-5 related sub-queries that would help 
        provide comprehensive coverage of the topic. Focus on different aspects, perspectives, 
        and related concepts.
        
        Format as a simple list, one query per line.
        """
        
        response = await self.rag_service.query(prompt, max_tokens=200)
        
        # Parse sub-queries from response
        sub_queries = [
            line.strip().lstrip('- ').lstrip('• ')
            for line in response.split('\n')
            if line.strip() and not line.strip().startswith('For the research')
        ]
        
        return sub_queries[:5]  # Limit to 5 sub-queries
    
    def _determine_search_strategies(self, query: ResearchQuery) -> List[str]:
        """Determine appropriate search strategies based on query."""
        strategies = ['web_search']
        
        if query.include_academic:
            strategies.append('academic_search')
        
        if query.include_news:
            strategies.append('news_search')
        
        if query.include_social:
            strategies.append('social_search')
        
        return strategies
    
    async def _search_web(self, query: str) -> List[Dict[str, Any]]:
        """Search the web using multiple search engines."""
        results = []
        
        # Try different search engines
        for engine_name, search_func in self.search_engines.items():
            if engine_name in ['google', 'bing', 'duckduckgo']:
                try:
                    engine_results = await search_func(query)
                    results.extend(engine_results)
                except Exception as e:
                    logger.warning(f"Search engine {engine_name} failed: {e}")
        
        return results
    
    async def _search_google(self, query: str) -> List[Dict[str, Any]]:
        """Search using Google (via scraping or API)."""
        # Note: In production, use Google Custom Search API
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        
        config = ScrapingConfig(
            user_agent="Mozilla/5.0 (compatible; ResearchBot/1.0)",
            javascript_enabled=False
        )
        
        try:
            result = await self.scraping_service.scrape_url(search_url, config)
            return self._parse_google_results(result.content)
        except Exception as e:
            logger.error(f"Google search failed: {e}")
            return []
    
    async def _search_bing(self, query: str) -> List[Dict[str, Any]]:
        """Search using Bing."""
        # Similar implementation to Google
        return []
    
    async def _search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo."""
        # DuckDuckGo has an API that's more research-friendly
        return []
    
    async def _search_academic(self, query: str) -> List[Dict[str, Any]]:
        """Search academic sources."""
        # Could integrate with arXiv, Google Scholar, etc.
        return []
    
    async def _search_news(self, query: str) -> List[Dict[str, Any]]:
        """Search news sources."""
        # Could integrate with news APIs
        return []
    
    def _parse_google_results(self, html_content: str) -> List[Dict[str, Any]]:
        """Parse Google search results from HTML."""
        # This is a simplified parser - in production, use proper HTML parsing
        results = []
        
        # Extract search result patterns
        # This would need proper implementation with BeautifulSoup
        
        return results
    
    def _deduplicate_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate sources."""
        seen_urls = set()
        unique_sources = []
        
        for source in sources:
            url = source.get('url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(source)
        
        return unique_sources
    
    def _rank_sources(self, sources: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Rank sources by relevance to query."""
        # Simple relevance scoring based on title/description matching
        for source in sources:
            title = source.get('title', '').lower()
            description = source.get('description', '').lower()
            query_lower = query.lower()
            
            # Calculate relevance score
            title_matches = len([word for word in query_lower.split() if word in title])
            desc_matches = len([word for word in query_lower.split() if word in description])
            
            relevance_score = (title_matches * 2 + desc_matches) / len(query_lower.split())
            source['relevance_score'] = min(relevance_score, 1.0)
        
        # Sort by relevance score
        return sorted(sources, key=lambda x: x.get('relevance_score', 0), reverse=True)
    
    def _assess_credibility(self, scraping_result: ScrapingResult) -> float:
        """Assess the credibility of a source."""
        credibility_score = 0.5  # Base score
        
        # Check domain reputation (simplified)
        domain = scraping_result.url.split('/')[2].lower()
        
        # High credibility domains
        high_credibility = [
            'wikipedia.org', 'britannica.com', 'nature.com', 'science.org',
            'arxiv.org', 'pubmed.ncbi.nlm.nih.gov', 'scholar.google.com',
            'reuters.com', 'bbc.com', 'npr.org', 'apnews.com'
        ]
        
        # Medium credibility domains
        medium_credibility = [
            'cnn.com', 'nytimes.com', 'washingtonpost.com', 'theguardian.com',
            'wsj.com', 'forbes.com', 'bloomberg.com'
        ]
        
        if any(domain.endswith(d) for d in high_credibility):
            credibility_score = 0.9
        elif any(domain.endswith(d) for d in medium_credibility):
            credibility_score = 0.7
        
        # Check for structured data (indicates quality)
        if scraping_result.structured_data:
            credibility_score += 0.1
        
        # Check for author information
        if scraping_result.metadata.get('author'):
            credibility_score += 0.1
        
        # Check for publication date
        if scraping_result.metadata.get('datePublished'):
            credibility_score += 0.1
        
        return min(credibility_score, 1.0)
    
    async def _cross_reference_facts(
        self,
        source: ResearchSource,
        all_sources: List[ResearchSource]
    ) -> float:
        """Cross-reference facts across sources."""
        # Simplified fact verification
        verification_score = 0.5
        
        # Check if key facts appear in multiple sources
        source_content = source.content.lower()
        
        for other_source in all_sources:
            if other_source.url == source.url:
                continue
            
            other_content = other_source.content.lower()
            
            # Simple overlap check (in production, use more sophisticated NLP)
            common_phrases = self._find_common_phrases(source_content, other_content)
            if len(common_phrases) > 2:
                verification_score += 0.1
        
        return min(verification_score, 1.0)
    
    def _find_common_phrases(self, text1: str, text2: str) -> List[str]:
        """Find common phrases between two texts."""
        # Simplified phrase matching
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        common_words = words1.intersection(words2)
        return list(common_words)
    
    def _calculate_confidence_score(self, sources: List[ResearchSource]) -> float:
        """Calculate overall confidence score for research."""
        if not sources:
            return 0.0
        
        # Average credibility and relevance scores
        avg_credibility = sum(s.credibility_score for s in sources) / len(sources)
        avg_relevance = sum(s.relevance_score for s in sources) / len(sources)
        
        # Factor in number of sources
        source_factor = min(len(sources) / 5, 1.0)  # Optimal around 5 sources
        
        confidence = (avg_credibility * 0.4 + avg_relevance * 0.4 + source_factor * 0.2)
        return min(confidence, 1.0)
    
    def _parse_synthesis_response(self, response: str) -> Tuple[str, List[str], List[str], List[str]]:
        """Parse the synthesis response into structured components."""
        lines = response.split('\n')
        
        summary = ""
        key_findings = []
        follow_ups = []
        related = []
        
        current_section = "summary"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if "key findings" in line.lower():
                current_section = "findings"
            elif "follow-up" in line.lower():
                current_section = "follow_ups"
            elif "related topics" in line.lower():
                current_section = "related"
            elif line.startswith(('•', '-', '*')):
                item = line.lstrip('•-* ').strip()
                if current_section == "findings":
                    key_findings.append(item)
                elif current_section == "follow_ups":
                    follow_ups.append(item)
                elif current_section == "related":
                    related.append(item)
            elif current_section == "summary":
                summary += line + " "
        
        return summary.strip(), key_findings, follow_ups, related
    
    async def _store_research_result(self, result: ResearchResult):
        """Store research result in vector database for future reference."""
        try:
            await self.vector_store.store(
                id=f"research_{hash(result.query)}_{int(result.timestamp.timestamp())}",
                content={
                    "query": result.query,
                    "summary": result.summary,
                    "key_findings": result.key_findings,
                    "confidence_score": result.confidence_score,
                    "source_count": len(result.sources),
                    "timestamp": result.timestamp.isoformat()
                },
                collection_type="research"
            )
        except Exception as e:
            logger.error(f"Failed to store research result: {e}")


# Global research service instance
research_service = None

async def get_research_service() -> ResearchService:
    """Get research service instance."""
    global research_service
    if research_service is None:
        from src.services.scraping_service import scraping_service
        from src.services.rag_service import rag_service
        from src.services.vector_store import get_vector_store
        
        vector_store = await get_vector_store()
        research_service = ResearchService(scraping_service, rag_service, vector_store)
    
    return research_service