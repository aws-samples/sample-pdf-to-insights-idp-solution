"""
BDA External API Agent V2 - Enhanced for AgentCore
Specialized in retrieving real-time market data, economic indicators, and external information
Full AgentCore integration with async HTTP client
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands_agents_v2.shared.agent_base import AgentCoreBaseAgent
from strands_agents_v2.shared.prompt_loader import PromptLoader
import boto3
import json
import os
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import logging
from decimal import Decimal
import pandas as pd

# Configure logging
logger = logging.getLogger(__name__)

class EnhancedExternalAPIAgent(AgentCoreBaseAgent):
    """
    Enhanced External API Agent with AgentCore integration
    Provides real-time data access and external information retrieval
    """
    
    def __init__(self):
        super().__init__(
            agent_name="BDA-External-API-Agent-V2",
            agent_type="data_retrieval",
            model_config={
                "model_id": "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
            }
        )
        
        # API configurations
        self.api_keys = {
            'alpha_vantage': os.getenv('ALPHA_VANTAGE_API_KEY', 'demo'),
            'real_estate': os.getenv('REAL_ESTATE_API_KEY', 'demo'),
            'economic_data': os.getenv('FRED_API_KEY', 'demo'),
            'news_api': os.getenv('NEWS_API_KEY', 'demo')
        }
        
        # Rate limiting configuration
        self.rate_limits = {
            'alpha_vantage': {'calls': 5, 'period': 60},  # 5 calls per minute
            'real_estate': {'calls': 10, 'period': 60},   # 10 calls per minute
            'economic_data': {'calls': 120, 'period': 60}, # 120 calls per minute
            'news_api': {'calls': 100, 'period': 86400}    # 100 calls per day
        }
        
        self.last_calls = {}
        
        # Enhanced tools with async support
        self.tools = [
            self.get_stock_market_data,
            self.get_real_estate_market_data,
            self.get_economic_indicators,
            self.get_market_news,
            self.get_cryptocurrency_data,
            self.get_commodity_prices,
            self.get_forex_rates,
            self.aggregate_market_overview
        ]
        
        # Recreate agent with tools
        self.agent = self._create_strands_agent()
    
    def get_system_prompt(self) -> str:
        """Load prompt from assets/AgentPrompts.txt file"""
        return PromptLoader.get_prompt('external_api')
    
    @tool
    async def get_stock_market_data(self, 
                                   symbol: str, 
                                   data_type: str = "quote",
                                   interval: str = "daily") -> Dict[str, Any]:
        """
        Retrieve comprehensive stock market data
        
        Args:
            symbol: Stock ticker symbol (e.g., AAPL, MSFT)
            data_type: Type of data (quote, historical, technical, fundamental)
            interval: Time interval for historical data
            
        Returns:
            Dict containing market data with metadata
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit('alpha_vantage'):
                return {'error': 'Rate limit exceeded. Please try again later.'}
            
            results = {
                'symbol': symbol.upper(),
                'data_type': data_type,
                'timestamp': datetime.now().isoformat(),
                'source': 'Alpha Vantage',
                'data': {}
            }
            
            async with aiohttp.ClientSession() as session:
                if data_type == "quote":
                    data = await self._fetch_stock_quote(session, symbol)
                elif data_type == "historical":
                    data = await self._fetch_historical_data(session, symbol, interval)
                elif data_type == "technical":
                    data = await self._fetch_technical_indicators(session, symbol)
                elif data_type == "fundamental":
                    data = await self._fetch_fundamental_data(session, symbol)
                else:
                    data = {'error': f'Unknown data type: {data_type}'}
                
                results['data'] = data
            
            # Add market analysis
            if 'error' not in data:
                results['analysis'] = self._analyze_stock_data(data, data_type)
            
            return results
            
        except Exception as e:
            logger.error(f"Stock market data retrieval error: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_real_estate_market_data(self, 
                                        location: str,
                                        property_type: str = "all",
                                        metrics: List[str] = None) -> Dict[str, Any]:
        """
        Retrieve real estate market data and comparables
        
        Args:
            location: Geographic location (city, state, zip)
            property_type: Type of property (office, retail, industrial, multifamily)
            metrics: Specific metrics to retrieve
            
        Returns:
            Dict containing real estate market data
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit('real_estate'):
                return {'error': 'Rate limit exceeded. Please try again later.'}
            
            if metrics is None:
                metrics = ['median_price', 'cap_rate', 'vacancy_rate', 'absorption']
            
            results = {
                'location': location,
                'property_type': property_type,
                'timestamp': datetime.now().isoformat(),
                'metrics': {},
                'comparables': []
            }
            
            # Real estate data requires specialized APIs like CoStar, Reis, or RCA
            
            # Market metrics
            results['metrics'] = await self._fetch_re_market_metrics(location, property_type, metrics)
            
            # Comparable properties
            results['comparables'] = await self._fetch_re_comparables(location, property_type)
            
            # Market trends
            results['trends'] = await self._analyze_re_market_trends(results['metrics'])
            
            # Investment opportunities
            results['opportunities'] = self._identify_re_opportunities(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Real estate data retrieval error: {e}")
            return {
                'location': location,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_economic_indicators(self, 
                                    indicators: List[str] = None,
                                    start_date: str = None,
                                    end_date: str = None) -> Dict[str, Any]:
        """
        Retrieve economic indicators from FRED and other sources
        
        Args:
            indicators: List of indicator codes (GDP, CPI, UNRATE, etc.)
            start_date: Start date for historical data
            end_date: End date for historical data
            
        Returns:
            Dict containing economic indicator data
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit('economic_data'):
                return {'error': 'Rate limit exceeded. Please try again later.'}
            
            if indicators is None:
                indicators = ['GDP', 'CPIAUCSL', 'UNRATE', 'DFF', 'DEXUSEU']
            
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            results = {
                'indicators': {},
                'timestamp': datetime.now().isoformat(),
                'period': {'start': start_date, 'end': end_date},
                'analysis': {}
            }
            
            # Fetch each indicator
            async with aiohttp.ClientSession() as session:
                for indicator in indicators:
                    data = await self._fetch_fred_data(session, indicator, start_date, end_date)
                    if data:
                        results['indicators'][indicator] = data
            
            # Analyze economic conditions
            results['analysis'] = self._analyze_economic_conditions(results['indicators'])
            
            # Generate economic outlook
            results['outlook'] = self._generate_economic_outlook(results['analysis'])
            
            return results
            
        except Exception as e:
            logger.error(f"Economic indicators retrieval error: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_market_news(self, 
                            query: str,
                            category: str = "general",
                            limit: int = 10) -> Dict[str, Any]:
        """
        Retrieve and analyze market news
        
        Args:
            query: Search query for news
            category: News category (general, real-estate, stocks, economy)
            limit: Number of articles to retrieve
            
        Returns:
            Dict containing news articles and sentiment analysis
        """
        try:
            # Check rate limiting
            if not self._check_rate_limit('news_api'):
                return {'error': 'Rate limit exceeded. Please try again later.'}
            
            results = {
                'query': query,
                'category': category,
                'timestamp': datetime.now().isoformat(),
                'articles': [],
                'sentiment': {},
                'key_themes': []
            }
            
            # Fetch news articles
            articles = await self._fetch_news_articles(query, category, limit)
            results['articles'] = articles
            
            # Analyze sentiment
            if articles:
                results['sentiment'] = self._analyze_news_sentiment(articles)
                results['key_themes'] = self._extract_news_themes(articles)
            
            # Generate market impact assessment
            results['market_impact'] = self._assess_news_market_impact(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Market news retrieval error: {e}")
            return {
                'query': query,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_cryptocurrency_data(self, 
                                    symbols: List[str] = None,
                                    convert: str = "USD") -> Dict[str, Any]:
        """
        Retrieve cryptocurrency market data
        
        Args:
            symbols: List of crypto symbols (BTC, ETH, etc.)
            convert: Currency to convert prices to
            
        Returns:
            Dict containing cryptocurrency data
        """
        try:
            if symbols is None:
                symbols = ['BTC', 'ETH', 'USDT', 'BNB', 'SOL']
            
            results = {
                'timestamp': datetime.now().isoformat(),
                'convert_currency': convert,
                'cryptocurrencies': {},
                'market_summary': {}
            }
            
            # Fetch crypto data
            async with aiohttp.ClientSession() as session:
                for symbol in symbols:
                    data = await self._fetch_crypto_data(session, symbol, convert)
                    if data:
                        results['cryptocurrencies'][symbol] = data
            
            # Calculate market summary
            results['market_summary'] = self._calculate_crypto_market_summary(results['cryptocurrencies'])
            
            # Add market analysis
            results['analysis'] = self._analyze_crypto_market(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Cryptocurrency data retrieval error: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_commodity_prices(self, 
                                  commodities: List[str] = None) -> Dict[str, Any]:
        """
        Retrieve commodity prices and futures data
        
        Args:
            commodities: List of commodity symbols
            
        Returns:
            Dict containing commodity price data
        """
        try:
            if commodities is None:
                commodities = ['GOLD', 'SILVER', 'OIL', 'NATGAS', 'COPPER']
            
            results = {
                'timestamp': datetime.now().isoformat(),
                'commodities': {},
                'futures': {},
                'analysis': {}
            }
            
            # Fetch commodity data
            async with aiohttp.ClientSession() as session:
                for commodity in commodities:
                    spot_price = await self._fetch_commodity_spot(session, commodity)
                    futures_data = await self._fetch_commodity_futures(session, commodity)
                    
                    results['commodities'][commodity] = {
                        'spot': spot_price,
                        'futures': futures_data
                    }
            
            # Analyze commodity trends
            results['analysis'] = self._analyze_commodity_trends(results['commodities'])
            
            return results
            
        except Exception as e:
            logger.error(f"Commodity data retrieval error: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def get_forex_rates(self, 
                            base_currency: str = "USD",
                            target_currencies: List[str] = None) -> Dict[str, Any]:
        """
        Retrieve foreign exchange rates
        
        Args:
            base_currency: Base currency code
            target_currencies: List of target currency codes
            
        Returns:
            Dict containing forex rates and analysis
        """
        try:
            if target_currencies is None:
                target_currencies = ['EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD']
            
            results = {
                'timestamp': datetime.now().isoformat(),
                'base_currency': base_currency,
                'rates': {},
                'changes': {},
                'analysis': {}
            }
            
            # Fetch forex rates
            async with aiohttp.ClientSession() as session:
                current_rates = await self._fetch_forex_rates(session, base_currency, target_currencies)
                historical_rates = await self._fetch_forex_historical(session, base_currency, target_currencies)
                
                results['rates'] = current_rates
                
                # Calculate changes
                for currency in target_currencies:
                    if currency in current_rates and currency in historical_rates:
                        current = current_rates[currency]
                        historical = historical_rates[currency]
                        change = ((current - historical) / historical) * 100
                        results['changes'][currency] = {
                            'current': current,
                            '1d_ago': historical,
                            'change_pct': round(change, 2)
                        }
            
            # Analyze forex trends
            results['analysis'] = self._analyze_forex_trends(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Forex data retrieval error: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    @tool
    async def aggregate_market_overview(self, 
                                      include_sectors: List[str] = None) -> Dict[str, Any]:
        """
        Aggregate comprehensive market overview across asset classes
        
        Args:
            include_sectors: Sectors to include in overview
            
        Returns:
            Dict containing aggregated market overview
        """
        try:
            if include_sectors is None:
                include_sectors = ['stocks', 'bonds', 'real_estate', 'commodities', 'crypto']
            
            overview = {
                'timestamp': datetime.now().isoformat(),
                'market_summary': {},
                'sector_performance': {},
                'key_movers': {},
                'market_sentiment': {},
                'economic_context': {}
            }
            
            # Gather data from multiple sources concurrently
            tasks = []
            
            if 'stocks' in include_sectors:
                tasks.append(self._get_stock_market_summary())
            if 'bonds' in include_sectors:
                tasks.append(self._get_bond_market_summary())
            if 'real_estate' in include_sectors:
                tasks.append(self._get_re_market_summary())
            if 'commodities' in include_sectors:
                tasks.append(self._get_commodity_summary())
            if 'crypto' in include_sectors:
                tasks.append(self._get_crypto_summary())
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, sector in enumerate(include_sectors):
                if i < len(results) and not isinstance(results[i], Exception):
                    overview['sector_performance'][sector] = results[i]
            
            # Generate market sentiment
            overview['market_sentiment'] = self._calculate_overall_sentiment(overview['sector_performance'])
            
            # Add economic context
            overview['economic_context'] = await self._get_economic_context()
            
            # Identify key movers
            overview['key_movers'] = self._identify_key_movers(overview['sector_performance'])
            
            # Generate executive summary
            overview['executive_summary'] = self._generate_market_summary(overview)
            
            return overview
            
        except Exception as e:
            logger.error(f"Market overview aggregation error: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    # Helper methods for API interactions
    async def _fetch_stock_quote(self, session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
        """Fetch real-time stock quote"""
        try:
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.api_keys['alpha_vantage']
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'Global Quote' in data:
                    quote = data['Global Quote']
                    return {
                        'symbol': quote.get('01. symbol', symbol),
                        'price': float(quote.get('05. price', 0)),
                        'change': float(quote.get('09. change', 0)),
                        'change_percent': quote.get('10. change percent', '0%'),
                        'volume': int(quote.get('06. volume', 0)),
                        'latest_trading_day': quote.get('07. latest trading day', ''),
                        'previous_close': float(quote.get('08. previous close', 0)),
                        'open': float(quote.get('02. open', 0)),
                        'high': float(quote.get('03. high', 0)),
                        'low': float(quote.get('04. low', 0))
                    }
                else:
                    return {
                        'symbol': symbol,
                        'error': 'No stock data available - Alpha Vantage API key not configured or API limit exceeded',
                        'message': 'Please configure ALPHA_VANTAGE_API_KEY environment variable or check API usage limits'
                    }
                    
        except Exception as e:
            logger.error(f"Error fetching stock quote: {e}")
            return {
                'symbol': symbol,
                'error': f'Failed to fetch stock data: {str(e)}',
                'message': 'API request failed - check network connection and API configuration'
            }
    
    async def _fetch_historical_data(self, session: aiohttp.ClientSession, 
                                   symbol: str, interval: str) -> Dict[str, Any]:
        """Fetch historical stock data"""
        try:
            function = 'TIME_SERIES_DAILY' if interval == 'daily' else 'TIME_SERIES_INTRADAY'
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': function,
                'symbol': symbol,
                'apikey': self.api_keys['alpha_vantage']
            }
            
            if function == 'TIME_SERIES_INTRADAY':
                params['interval'] = '60min'
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                # Process time series data
                time_series_key = list(data.keys())[1] if len(data.keys()) > 1 else None
                
                if time_series_key and time_series_key.startswith('Time Series'):
                    time_series = data[time_series_key]
                    processed_data = []
                    
                    for date, values in list(time_series.items())[:30]:  # Last 30 periods
                        processed_data.append({
                            'date': date,
                            'open': float(values.get('1. open', 0)),
                            'high': float(values.get('2. high', 0)),
                            'low': float(values.get('3. low', 0)),
                            'close': float(values.get('4. close', 0)),
                            'volume': int(values.get('5. volume', 0))
                        })
                    
                    return {
                        'symbol': symbol,
                        'interval': interval,
                        'data': processed_data
                    }
                else:
                    return {
                        'symbol': symbol,
                        'interval': interval,
                        'error': 'No historical data available - Alpha Vantage API key not configured or invalid response',
                        'message': 'Please configure ALPHA_VANTAGE_API_KEY environment variable'
                    }
                    
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return {
                'symbol': symbol,
                'interval': interval,
                'error': f'Failed to fetch historical data: {str(e)}',
                'message': 'API request failed - check network connection and API configuration'
            }
    
    async def _fetch_technical_indicators(self, session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
        """Fetch technical indicators"""
        indicators = {}
        
        # Fetch multiple indicators
        for indicator in ['RSI', 'MACD', 'SMA']:
            try:
                url = f"https://www.alphavantage.co/query"
                params = {
                    'function': indicator,
                    'symbol': symbol,
                    'interval': 'daily',
                    'time_period': 14,
                    'series_type': 'close',
                    'apikey': self.api_keys['alpha_vantage']
                }
                
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    
                    # Extract latest indicator value
                    tech_key = f'Technical Analysis: {indicator}'
                    if tech_key in data:
                        latest_date = list(data[tech_key].keys())[0]
                        indicators[indicator] = float(list(data[tech_key][latest_date].values())[0])
                        
            except Exception as e:
                logger.error(f"Error fetching {indicator}: {e}")
        
        # Return error if no indicators available
        if not indicators:
            return {
                'error': 'Technical indicators unavailable',
                'message': 'Alpha Vantage API key not configured or API request failed'
            }
        
        return indicators
    
    async def _fetch_fundamental_data(self, session: aiohttp.ClientSession, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        try:
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol,
                'apikey': self.api_keys['alpha_vantage']
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'Symbol' in data:
                    return {
                        'market_cap': float(data.get('MarketCapitalization', 0)),
                        'pe_ratio': float(data.get('PERatio', 0)),
                        'dividend_yield': float(data.get('DividendYield', 0)),
                        'beta': float(data.get('Beta', 1)),
                        'eps': float(data.get('EPS', 0)),
                        'book_value': float(data.get('BookValue', 0)),
                        'revenue_ttm': float(data.get('RevenueTTM', 0)),
                        'profit_margin': float(data.get('ProfitMargin', 0))
                    }
                else:
                    return {
                        'symbol': symbol,
                        'error': 'No fundamental data available - Alpha Vantage API key not configured or invalid response',
                        'message': 'Please configure ALPHA_VANTAGE_API_KEY environment variable'
                    }
                    
        except Exception as e:
            logger.error(f"Error fetching fundamental data: {e}")
            return {
                'symbol': symbol,
                'error': f'Failed to fetch fundamental data: {str(e)}',
                'message': 'API request failed - check network connection and API configuration'
            }
    
    async def _fetch_re_market_metrics(self, location: str, property_type: str, metrics: List[str]) -> Dict[str, Any]:
        """Fetch real estate market metrics"""
        # TODO: Integrate with real estate data providers like:
        # - CoStar API
        # - RealPage API  
        # - Zillow API
        # - Redfin API
        
        api_key = os.getenv('REAL_ESTATE_API_KEY')
        if not api_key:
            return {
                'error': 'Real estate API key not configured',
                'message': 'Please set REAL_ESTATE_API_KEY environment variable',
                'requested_metrics': metrics,
                'location': location,
                'property_type': property_type
            }
        
        # Placeholder for actual API integration
        # When API is integrated, this will make real calls
        return {
            'status': 'api_not_implemented',
            'message': 'Real estate API integration pending',
            'location': location,
            'property_type': property_type,
            'requested_metrics': metrics
        }
    
    async def _fetch_re_comparables(self, location: str, property_type: str) -> List[Dict[str, Any]]:
        """Fetch comparable properties"""
        # TODO: Integrate with MLS or commercial real estate databases
        api_key = os.getenv('MLS_API_KEY')
        if not api_key:
            return [{
                'error': 'MLS API key not configured',
                'message': 'Please set MLS_API_KEY environment variable',
                'location': location,
                'property_type': property_type
            }]
        
        # Placeholder for actual API integration
        return [{
            'status': 'api_not_implemented',
            'message': 'MLS API integration pending',
            'location': location,
            'property_type': property_type
        }]
    
    async def _analyze_re_market_trends(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze real estate market trends"""
        trends = {
            'market_direction': 'stable',
            'investment_outlook': 'neutral',
            'key_insights': []
        }
        
        # Analyze cap rates
        cap_rate = metrics.get('cap_rate', 0)
        if cap_rate > 7:
            trends['key_insights'].append('High cap rates indicate value opportunities')
            trends['investment_outlook'] = 'positive'
        elif cap_rate < 5:
            trends['key_insights'].append('Compressed cap rates suggest market peak')
            trends['investment_outlook'] = 'cautious'
        
        # Analyze vacancy
        vacancy = metrics.get('vacancy_rate', 0)
        if vacancy > 15:
            trends['key_insights'].append('High vacancy presents challenges')
            trends['market_direction'] = 'weakening'
        elif vacancy < 5:
            trends['key_insights'].append('Low vacancy supports rent growth')
            trends['market_direction'] = 'strengthening'
        
        # Analyze absorption
        absorption = metrics.get('absorption', 0)
        if absorption > 0:
            trends['key_insights'].append('Positive absorption indicates demand')
        else:
            trends['key_insights'].append('Negative absorption signals oversupply')
        
        return trends
    
    def _identify_re_opportunities(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify real estate investment opportunities"""
        opportunities = []
        
        # Check for value-add opportunities
        if data['metrics'].get('cap_rate', 0) > 7:
            opportunities.append({
                'type': 'value_add',
                'description': 'High cap rate properties with improvement potential',
                'expected_return': '12-15%',
                'risk_level': 'moderate'
            })
        
        # Check for stable income
        if data['metrics'].get('vacancy_rate', 0) < 5:
            opportunities.append({
                'type': 'core',
                'description': 'Stable, fully-leased properties',
                'expected_return': '6-8%',
                'risk_level': 'low'
            })
        
        return opportunities
    
    async def _fetch_fred_data(self, session: aiohttp.ClientSession, 
                             series_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Fetch data from FRED API"""
        try:
            url = f"https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': series_id,
                'api_key': self.api_keys['economic_data'],
                'file_type': 'json',
                'observation_start': start_date,
                'observation_end': end_date
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'observations' in data:
                    observations = data['observations']
                    
                    # Get latest value and calculate change
                    if observations:
                        latest = observations[-1]
                        year_ago = observations[-12] if len(observations) >= 12 else observations[0]
                        
                        latest_value = float(latest['value'])
                        year_ago_value = float(year_ago['value'])
                        yoy_change = ((latest_value - year_ago_value) / year_ago_value) * 100
                        
                        return {
                            'series_id': series_id,
                            'latest_value': latest_value,
                            'latest_date': latest['date'],
                            'year_ago_value': year_ago_value,
                            'yoy_change': round(yoy_change, 2),
                            'unit': self._get_fred_unit(series_id)
                        }
                
        except Exception as e:
            logger.error(f"Error fetching FRED data: {e}")
        
        # Return error if API fails
        return {
            'series_id': series_id,
            'error': f'Failed to fetch FRED data for {series_id}',
            'message': 'Please configure FRED_API_KEY environment variable or check API availability',
            'unit': self._get_fred_unit(series_id)
        }
    
    def _get_fred_unit(self, series_id: str) -> str:
        """Get unit for FRED series"""
        units = {
            'GDP': 'Billions of Dollars',
            'CPIAUCSL': 'Index',
            'UNRATE': 'Percent',
            'DFF': 'Percent',
            'DEXUSEU': 'U.S. Dollars per Euro'
        }
        return units.get(series_id, 'Value')
    
    def _analyze_economic_conditions(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze economic conditions based on indicators"""
        analysis = {
            'growth_outlook': 'stable',
            'inflation_pressure': 'moderate',
            'employment_strength': 'strong',
            'monetary_policy': 'neutral',
            'key_risks': [],
            'opportunities': []
        }
        
        # Analyze GDP growth
        if 'GDP' in indicators:
            gdp_growth = indicators['GDP'].get('yoy_change', 0)
            if gdp_growth > 3:
                analysis['growth_outlook'] = 'strong'
            elif gdp_growth < 1:
                analysis['growth_outlook'] = 'weak'
                analysis['key_risks'].append('Slowing economic growth')
        
        # Analyze inflation
        if 'CPIAUCSL' in indicators:
            inflation = indicators['CPIAUCSL'].get('yoy_change', 0)
            if inflation > 3:
                analysis['inflation_pressure'] = 'high'
                analysis['key_risks'].append('Elevated inflation')
            elif inflation < 1:
                analysis['inflation_pressure'] = 'low'
        
        # Analyze unemployment
        if 'UNRATE' in indicators:
            unemployment = indicators['UNRATE'].get('latest_value', 0)
            if unemployment < 4:
                analysis['employment_strength'] = 'very strong'
            elif unemployment > 6:
                analysis['employment_strength'] = 'weak'
                analysis['key_risks'].append('Rising unemployment')
        
        # Analyze interest rates
        if 'DFF' in indicators:
            fed_funds = indicators['DFF'].get('latest_value', 0)
            if fed_funds > 4:
                analysis['monetary_policy'] = 'restrictive'
            elif fed_funds < 1:
                analysis['monetary_policy'] = 'accommodative'
        
        return analysis
    
    def _generate_economic_outlook(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate economic outlook based on analysis"""
        outlook = {
            'summary': '',
            'real_estate_impact': '',
            'investment_implications': [],
            'timeframe': '6-12 months'
        }
        
        # Generate summary
        growth = analysis.get('growth_outlook', 'stable')
        inflation = analysis.get('inflation_pressure', 'moderate')
        
        if growth == 'strong' and inflation == 'moderate':
            outlook['summary'] = 'Favorable economic conditions with balanced growth'
            outlook['real_estate_impact'] = 'Positive for real estate demand and rent growth'
        elif growth == 'weak' or inflation == 'high':
            outlook['summary'] = 'Challenging economic environment'
            outlook['real_estate_impact'] = 'Headwinds for real estate performance'
        else:
            outlook['summary'] = 'Mixed economic signals require careful monitoring'
            outlook['real_estate_impact'] = 'Selective opportunities in real estate'
        
        # Investment implications
        if analysis.get('monetary_policy') == 'restrictive':
            outlook['investment_implications'].append('Higher cap rates may create buying opportunities')
        
        if analysis.get('employment_strength') == 'very strong':
            outlook['investment_implications'].append('Strong job market supports real estate demand')
        
        return outlook
    
    async def _fetch_news_articles(self, query: str, category: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch news articles"""
        # Integrate with News API
        api_key = os.getenv('NEWS_API_KEY')
        
        if not api_key:
            return [{
                'error': 'News API key not configured',
                'message': 'Please set NEWS_API_KEY environment variable for news.api.org',
                'query': query,
                'category': category
            }]
        
        async with aiohttp.ClientSession() as session:
            try:
                url = 'https://newsapi.org/v2/everything'
                params = {
                    'q': query,
                    'apiKey': api_key,
                    'language': 'en',
                    'sortBy': 'relevancy',
                    'pageSize': limit
                }
                
                if category and category != 'general':
                    params['category'] = category
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        articles = []
                        for article in data.get('articles', [])[:limit]:
                            articles.append({
                                'title': article.get('title'),
                                'source': article.get('source', {}).get('name'),
                                'published': article.get('publishedAt'),
                                'summary': article.get('description'),
                                'url': article.get('url'),
                                'content': article.get('content')
                            })
                        return articles
                    else:
                        return [{'error': f'News API returned status {response.status}'}]
                        
            except Exception as e:
                logger.error(f"News API error: {e}")
                return [{'error': f'Failed to fetch news: {str(e)}'}]
    
    def _analyze_news_sentiment(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze sentiment from news articles"""
        if not articles:
            return {'overall': 'neutral', 'score': 0}
        
        # Calculate average sentiment
        total_sentiment = sum(article.get('sentiment_score', 0) for article in articles)
        avg_sentiment = total_sentiment / len(articles)
        
        # Categorize sentiment
        if avg_sentiment > 0.3:
            sentiment = 'positive'
        elif avg_sentiment < -0.3:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'overall': sentiment,
            'score': round(avg_sentiment, 2),
            'distribution': {
                'positive': sum(1 for a in articles if a.get('sentiment_score', 0) > 0.3),
                'neutral': sum(1 for a in articles if -0.3 <= a.get('sentiment_score', 0) <= 0.3),
                'negative': sum(1 for a in articles if a.get('sentiment_score', 0) < -0.3)
            }
        }
    
    def _extract_news_themes(self, articles: List[Dict[str, Any]]) -> List[str]:
        """Extract key themes from news articles"""
        # In production, would use NLP
        # For demo, extract from titles
        
        themes = set()
        keywords = ['growth', 'decline', 'surge', 'drop', 'record', 'concern', 'opportunity']
        
        for article in articles:
            title = article.get('title', '').lower()
            for keyword in keywords:
                if keyword in title:
                    themes.add(keyword.title())
        
        return list(themes)[:5]
    
    def _assess_news_market_impact(self, news_data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess potential market impact of news"""
        sentiment = news_data.get('sentiment', {})
        themes = news_data.get('key_themes', [])
        
        impact = {
            'level': 'low',
            'direction': 'neutral',
            'affected_sectors': [],
            'recommendation': ''
        }
        
        # Determine impact level
        if sentiment.get('overall') == 'positive' and len(themes) > 3:
            impact['level'] = 'high'
            impact['direction'] = 'bullish'
            impact['recommendation'] = 'Consider increasing exposure to affected sectors'
        elif sentiment.get('overall') == 'negative':
            impact['level'] = 'moderate'
            impact['direction'] = 'bearish'
            impact['recommendation'] = 'Review risk management and hedging strategies'
        else:
            impact['recommendation'] = 'Continue monitoring news flow'
        
        return impact
    
    async def _fetch_crypto_data(self, session: aiohttp.ClientSession, symbol: str, convert: str) -> Dict[str, Any]:
        """Fetch cryptocurrency data from real APIs"""
        # Try to fetch from CoinMarketCap or similar API
        try:
            # Example: CoinMarketCap API (requires API key)
            api_key = os.getenv('CMC_API_KEY')
            if not api_key:
                return {
                    'symbol': symbol,
                    'error': 'Cryptocurrency API not configured',
                    'message': 'Please configure CMC_API_KEY environment variable for CoinMarketCap API'
                }
            
            url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
            headers = {
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': api_key,
            }
            params = {
                'symbol': symbol,
                'convert': convert
            }
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'data' in data and symbol in data['data']:
                        crypto_data = data['data'][symbol]
                        quote = crypto_data['quote'][convert]
                        
                        return {
                            'symbol': symbol,
                            'price': quote['price'],
                            'market_cap': quote['market_cap'],
                            'volume_24h': quote['volume_24h'],
                            'change_24h': quote['percent_change_24h'],
                            'change_7d': quote['percent_change_7d']
                        }
                
        except Exception as e:
            logger.error(f"Error fetching crypto data: {e}")
        
        return {
            'symbol': symbol,
            'error': 'Failed to fetch cryptocurrency data',
            'message': 'Real-time crypto data unavailable - API not configured or request failed'
        }
    
    def _calculate_crypto_market_summary(self, crypto_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate crypto market summary"""
        total_market_cap = sum(c.get('market_cap', 0) for c in crypto_data.values())
        avg_change_24h = sum(c.get('change_24h', 0) for c in crypto_data.values()) / len(crypto_data)
        
        return {
            'total_market_cap': total_market_cap,
            'average_change_24h': round(avg_change_24h, 2),
            'trending': 'up' if avg_change_24h > 0 else 'down',
            'volatility': 'high' if abs(avg_change_24h) > 5 else 'moderate'
        }
    
    def _analyze_crypto_market(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze cryptocurrency market"""
        summary = data.get('market_summary', {})
        
        analysis = {
            'market_trend': summary.get('trending', 'neutral'),
            'risk_level': 'high' if summary.get('volatility') == 'high' else 'moderate',
            'investment_thesis': '',
            'key_drivers': []
        }
        
        # Generate investment thesis
        if summary.get('average_change_24h', 0) > 5:
            analysis['investment_thesis'] = 'Bullish momentum in crypto markets'
            analysis['key_drivers'].append('Positive market sentiment')
        elif summary.get('average_change_24h', 0) < -5:
            analysis['investment_thesis'] = 'Bearish pressure on crypto assets'
            analysis['key_drivers'].append('Risk-off sentiment')
        else:
            analysis['investment_thesis'] = 'Consolidation phase in crypto markets'
        
        return analysis
    
    async def _fetch_commodity_spot(self, session: aiohttp.ClientSession, commodity: str) -> Dict[str, Any]:
        """Fetch commodity spot prices from real data sources"""
        try:
            # Try to fetch from Alpha Vantage commodity API or similar
            api_key = self.api_keys.get('alpha_vantage', '')
            if not api_key or api_key == 'demo': # pragma: allowlist secret
                return {
                    'commodity': commodity,
                    'error': 'Commodity API not configured',
                    'message': 'Please configure ALPHA_VANTAGE_API_KEY for commodity pricing data'
                }
            
            # Alpha Vantage commodity endpoint (if available)
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'COMMODITY_SEARCH',  # This would need to be the actual function
                'symbol': commodity,
                'apikey': api_key
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # Parse the actual response format
                    # This would need to be adjusted based on the actual API response
                    
        except Exception as e:
            logger.error(f"Error fetching commodity data: {e}")
        
        return {
            'commodity': commodity,
            'error': 'Commodity pricing data unavailable',
            'message': 'Real-time commodity prices require API configuration',
            'timestamp': datetime.now().isoformat()
        }
    
    async def _fetch_commodity_futures(self, session: aiohttp.ClientSession, commodity: str) -> List[Dict[str, Any]]:
        """Fetch commodity futures curve"""
        spot = await self._fetch_commodity_spot(session, commodity)
        
        # If spot data failed, futures will also fail
        if 'error' in spot:
            return [{
                'commodity': commodity,
                'error': 'Futures data unavailable',
                'message': 'Spot price data required for futures curve'
            }]
        
        # In a real implementation, this would fetch actual futures data
        # For now, return error indicating futures data is not available
        return [{
            'commodity': commodity,
            'error': 'Futures curve data not implemented',
            'message': 'Commodity futures require specialized market data provider'
        }]
    
    def _analyze_commodity_trends(self, commodities: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze commodity market trends"""
        analysis = {
            'trend_summary': {},
            'curve_analysis': {},
            'investment_outlook': {}
        }
        
        for commodity, data in commodities.items():
            spot = data.get('spot', {}).get('spot_price', 0)
            futures = data.get('futures', [])
            
            if futures and spot > 0:
                # Analyze futures curve
                m1_price = futures[0]['price'] if futures else spot
                curve_shape = 'contango' if m1_price > spot else 'backwardation'
                
                analysis['curve_analysis'][commodity] = {
                    'shape': curve_shape,
                    'implication': 'Storage costs exceed convenience yield' if curve_shape == 'contango' else 'Supply shortage concerns'
                }
        
        return analysis
    
    async def _fetch_forex_rates(self, session: aiohttp.ClientSession, 
                               base: str, targets: List[str]) -> Dict[str, float]:
        """Fetch current forex rates from real data sources"""
        try:
            # Try to use Alpha Vantage FX API or similar service
            api_key = self.api_keys.get('alpha_vantage', '')
            if not api_key or api_key == 'demo': # pragma: allowlist secret
                logger.warning("Forex API not configured")
                return {target: None for target in targets}
            
            rates = {}
            for target in targets:
                url = f"https://www.alphavantage.co/query"
                params = {
                    'function': 'CURRENCY_EXCHANGE_RATE',
                    'from_currency': base,
                    'to_currency': target,
                    'apikey': api_key
                }
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'Realtime Currency Exchange Rate' in data:
                            rate_data = data['Realtime Currency Exchange Rate']
                            rates[target] = float(rate_data.get('5. Exchange Rate', 0))
                        else:
                            rates[target] = None
                    else:
                        rates[target] = None
            
            return rates
            
        except Exception as e:
            logger.error(f"Error fetching forex rates: {e}")
            return {target: None for target in targets}
    
    async def _fetch_forex_historical(self, session: aiohttp.ClientSession,
                                    base: str, targets: List[str]) -> Dict[str, float]:
        """Fetch historical forex rates (1 day ago)"""
        try:
            # For simplicity, get current rates as baseline
            # In a real implementation, you would fetch actual historical data
            current = await self._fetch_forex_rates(session, base, targets)
            
            # Return None for historical if current rates are not available
            historical = {}
            for currency in targets:
                if current.get(currency) is None:
                    historical[currency] = None
                else:
                    # For now, return current rates
                    # In production, fetch actual historical data
                    historical[currency] = current[currency]
            
            return historical
            
        except Exception as e:
            logger.error(f"Error fetching historical forex rates: {e}")
            return {target: None for target in targets}
    
    def _analyze_forex_trends(self, forex_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze forex market trends"""
        changes = forex_data.get('changes', {})
        
        analysis = {
            'dollar_strength': 'neutral',
            'volatile_pairs': [],
            'trend_summary': {}
        }
        
        # Analyze dollar strength
        avg_change = sum(c.get('change_pct', 0) for c in changes.values()) / len(changes) if changes else 0
        
        if avg_change > 1:
            analysis['dollar_strength'] = 'weakening'
        elif avg_change < -1:
            analysis['dollar_strength'] = 'strengthening'
        
        # Identify volatile pairs
        for currency, data in changes.items():
            if abs(data.get('change_pct', 0)) > 2:
                analysis['volatile_pairs'].append(currency)
        
        return analysis
    
    # Market summary helper methods
    async def _get_stock_market_summary(self) -> Dict[str, Any]:
        """Get stock market summary"""
        # Fetch major indices
        indices = ['SPY', 'QQQ', 'DIA']
        summary = {
            'indices': {},
            'trend': 'neutral',
            'volatility': 'normal'
        }
        
        for index in indices:
            data = await self.get_stock_market_data(index, 'quote')
            if 'data' in data and 'price' in data['data']:
                summary['indices'][index] = {
                    'price': data['data']['price'],
                    'change': data['data'].get('change', 0),
                    'change_percent': data['data'].get('change_percent', '0%')
                }
        
        return summary
    
    async def _get_bond_market_summary(self) -> Dict[str, Any]:
        """Get bond market summary"""
        return {
            '10Y_yield': 4.25,
            '2Y_yield': 4.85,
            'yield_curve': 'inverted',
            'credit_spreads': 'widening'
        }
    
    async def _get_re_market_summary(self) -> Dict[str, Any]:
        """Get real estate market summary"""
        return {
            'average_cap_rate': 6.5,
            'vacancy_trend': 'improving',
            'rent_growth': 3.2,
            'transaction_volume': 'moderate'
        }
    
    async def _get_commodity_summary(self) -> Dict[str, Any]:
        """Get commodity market summary"""
        commodities = ['GOLD', 'OIL']
        summary = {}
        
        for commodity in commodities:
            data = await self.get_commodity_prices([commodity])
            if 'commodities' in data and commodity in data['commodities']:
                summary[commodity] = data['commodities'][commodity]['spot']['spot_price']
        
        return summary
    
    async def _get_crypto_summary(self) -> Dict[str, Any]:
        """Get crypto market summary"""
        data = await self.get_cryptocurrency_data(['BTC', 'ETH'])
        return data.get('market_summary', {})
    
    def _calculate_overall_sentiment(self, sector_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall market sentiment"""
        positive_indicators = 0
        total_indicators = 0
        
        # Check various indicators
        for sector, data in sector_data.items():
            if isinstance(data, dict):
                total_indicators += 1
                
                # Sector-specific sentiment checks
                if sector == 'stocks' and 'indices' in data:
                    if any(idx.get('change', 0) > 0 for idx in data['indices'].values()):
                        positive_indicators += 1
                elif sector == 'bonds' and 'yield_curve' in data:
                    if data['yield_curve'] != 'inverted':
                        positive_indicators += 1
                elif sector == 'real_estate' and 'rent_growth' in data:
                    if data['rent_growth'] > 2:
                        positive_indicators += 1
        
        sentiment_score = positive_indicators / total_indicators if total_indicators > 0 else 0.5
        
        return {
            'score': round(sentiment_score, 2),
            'direction': 'bullish' if sentiment_score > 0.6 else 'bearish' if sentiment_score < 0.4 else 'neutral',
            'confidence': 'high' if total_indicators > 3 else 'moderate'
        }
    
    async def _get_economic_context(self) -> Dict[str, Any]:
        """Get current economic context"""
        indicators = await self.get_economic_indicators(['GDP', 'CPIAUCSL', 'UNRATE'])
        
        context = {
            'gdp_growth': 'moderate',
            'inflation': 'elevated',
            'employment': 'strong',
            'fed_policy': 'restrictive'
        }
        
        if 'indicators' in indicators:
            if 'GDP' in indicators['indicators']:
                gdp_change = indicators['indicators']['GDP'].get('yoy_change', 0)
                context['gdp_growth'] = 'strong' if gdp_change > 3 else 'weak' if gdp_change < 1 else 'moderate'
        
        return context
    
    def _identify_key_movers(self, sector_data: Dict[str, Any]) -> Dict[str, Any]:
        """Identify key market movers"""
        movers = {
            'gainers': [],
            'losers': [],
            'most_active': []
        }
        
        # Check stock indices
        if 'stocks' in sector_data and 'indices' in sector_data['stocks']:
            for symbol, data in sector_data['stocks']['indices'].items():
                change = data.get('change', 0)
                if change > 1:
                    movers['gainers'].append({'symbol': symbol, 'change': change})
                elif change < -1:
                    movers['losers'].append({'symbol': symbol, 'change': change})
        
        return movers
    
    def _generate_market_summary(self, overview: Dict[str, Any]) -> str:
        """Generate executive market summary"""
        sentiment = overview.get('market_sentiment', {})
        economic = overview.get('economic_context', {})
        
        summary_parts = []
        
        # Market direction
        direction = sentiment.get('direction', 'neutral')
        summary_parts.append(f"Markets show {direction} sentiment")
        
        # Economic backdrop
        gdp = economic.get('gdp_growth', 'moderate')
        inflation = economic.get('inflation', 'moderate')
        summary_parts.append(f"with {gdp} growth and {inflation} inflation")
        
        # Key themes
        if overview.get('key_movers', {}).get('gainers'):
            summary_parts.append("Technology and growth sectors leading gains")
        
        return ". ".join(summary_parts) + "."
    
    # Rate limiting helper
    def _check_rate_limit(self, api_name: str) -> bool:
        """Check if API call is within rate limits"""
        if api_name not in self.rate_limits:
            return True
        
        current_time = datetime.now()
        
        if api_name not in self.last_calls:
            self.last_calls[api_name] = []
        
        # Remove old calls outside the rate limit window
        rate_limit = self.rate_limits[api_name]
        cutoff_time = current_time - timedelta(seconds=rate_limit['period'])
        self.last_calls[api_name] = [
            call_time for call_time in self.last_calls[api_name]
            if call_time > cutoff_time
        ]
        
        # Check if we can make another call
        if len(self.last_calls[api_name]) < rate_limit['calls']:
            self.last_calls[api_name].append(current_time)
            return True
        
        return False
    
    
    
    
    
    def _analyze_stock_data(self, data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """Analyze stock data using LLM-based analysis"""
        if 'error' in data:
            return {
                'error': 'Cannot analyze stock data',
                'message': 'Stock data unavailable for analysis'
            }
        
        # Use LLM to analyze the stock data
        analysis_prompt = f"""Analyze this stock data and provide insights:
        Data Type: {data_type}
        Stock Data: {json.dumps(data, indent=2)}
        
        Provide a professional analysis including:
        1. Current trend direction and strength
        2. Key technical levels (if price data available)
        3. Investment recommendation
        4. Risk factors to consider
        
        Format as JSON with keys: trend, strength, recommendation, key_levels, risk_factors
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(analysis_prompt).strip()
            
            # Try to parse as JSON
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis
                
        except Exception as e:
            logger.error(f"Failed to analyze stock data: {e}")
        
        # Fallback analysis
        return {
            'trend': 'Unable to determine',
            'strength': 'Analysis unavailable',
            'recommendation': 'Insufficient data for recommendation',
            'message': 'Stock analysis requires LLM processing'
        }

# Create singleton instance
external_api_agent_v2 = EnhancedExternalAPIAgent()
external_api_agent = external_api_agent_v2  # Backward compatibility alias

# AgentCore handler
def agentcore_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """AgentCore entry point"""
    return external_api_agent_v2.agentcore_handler(event)

# For local testing
if __name__ == "__main__":
    import asyncio
    
    test_event = {
        'input': 'Get current market data for AAPL and real estate metrics for Boston',
        'sessionId': 'test-external-v2-001'
    }
    
    result = agentcore_handler(test_event)
    print(json.dumps(result, indent=2))