"""
BDA Market Analyst Agent V2 - Enhanced for AgentCore
Specialized in numerical analysis, calculations, and market trend identification
Full AgentCore integration with async support and enhanced tools
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands_agents_v2.shared.agent_base import AgentCoreBaseAgent
from strands_agents_v2.shared.prompt_loader import PromptLoader
import boto3
import json
import os
import asyncio
from typing import Dict, Any, List, Union, Optional
from decimal import Decimal, InvalidOperation
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
# Knowledge base integration
from ..shared.knowledge_base_wrapper import search_bda_knowledge_base, get_market_documents, get_investment_insights

# Configure logging
logger = logging.getLogger(__name__)

class EnhancedMarketAnalystAgent(AgentCoreBaseAgent):
    """
    Enhanced Market Analyst Agent with AgentCore integration
    Provides advanced financial calculations and market analysis
    """
    
    def __init__(self):
        super().__init__(
            agent_name="BDA-Market-Analyst-Agent-V2",
            agent_type="specialist_analyst",
            model_config={
                "model_id": "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
            }
        )
        
        # Enhanced tools with async support
        self.tools = [
            self.calculate_financial_metrics,
            self.analyze_market_trends,
            self.compare_market_performance,
            self.calculate_investment_returns,
            self.perform_dcf_analysis,
            self.calculate_risk_metrics,
            self.generate_market_report,
            # Knowledge base tools
            search_bda_knowledge_base,
            get_market_documents,
            get_investment_insights
        ]
        
        # Recreate agent with tools
        self.agent = self._create_strands_agent()
    
    def get_system_prompt(self) -> str:
        """Load prompt from assets/AgentPrompts.txt file"""
        return PromptLoader.get_prompt('market_analyst')
    
    @tool
    async def calculate_financial_metrics(self, data: Dict[str, Union[float, int, str]]) -> Dict[str, Any]:
        """
        Calculate comprehensive financial metrics with enhanced accuracy
        
        Args:
            data: Financial data including prices, income, expenses
            
        Returns:
            Dict with calculated metrics, ratios, and insights
        """
        try:
            results = {
                'timestamp': datetime.now().isoformat(),
                'input_data': data,
                'calculated_metrics': {},
                'ratios': {},
                'real_estate_metrics': {},
                'insights': []
            }
            
            # Helper for safe decimal conversion
            def to_decimal(value):
                if value is None:
                    return None
                if isinstance(value, str):
                    value = value.replace('$', '').replace(',', '').strip()
                try:
                    return Decimal(str(value))
                except:
                    return None
            
            # Real Estate Specific Metrics
            
            # Cap Rate
            noi = to_decimal(data.get('net_operating_income', data.get('noi')))
            property_value = to_decimal(data.get('property_value', data.get('purchase_price')))
            
            if noi and property_value and property_value > 0:
                cap_rate = (noi / property_value) * 100
                results['real_estate_metrics']['cap_rate'] = {
                    'value': float(cap_rate),
                    'formatted': f"{cap_rate:.2f}%",
                    'interpretation': self._interpret_cap_rate(float(cap_rate))
                }
            
            # Cash-on-Cash Return
            annual_cash_flow = to_decimal(data.get('annual_cash_flow'))
            cash_invested = to_decimal(data.get('cash_invested', data.get('down_payment')))
            
            if annual_cash_flow and cash_invested and cash_invested > 0:
                coc_return = (annual_cash_flow / cash_invested) * 100
                results['real_estate_metrics']['cash_on_cash_return'] = {
                    'value': float(coc_return),
                    'formatted': f"{coc_return:.2f}%",
                    'interpretation': self._interpret_coc_return(float(coc_return))
                }
            
            # Debt Service Coverage Ratio (DSCR)
            annual_debt_service = to_decimal(data.get('annual_debt_service'))
            
            if noi and annual_debt_service and annual_debt_service > 0:
                dscr = noi / annual_debt_service
                results['real_estate_metrics']['dscr'] = {
                    'value': float(dscr),
                    'formatted': f"{dscr:.2f}x",
                    'interpretation': self._interpret_dscr(float(dscr))
                }
            
            # Gross Rent Multiplier (GRM)
            gross_annual_rent = to_decimal(data.get('gross_annual_rent'))
            
            if property_value and gross_annual_rent and gross_annual_rent > 0:
                grm = property_value / gross_annual_rent
                results['real_estate_metrics']['gross_rent_multiplier'] = {
                    'value': float(grm),
                    'formatted': f"{grm:.2f}",
                    'interpretation': self._interpret_grm(float(grm))
                }
            
            # Operating Expense Ratio
            operating_expenses = to_decimal(data.get('operating_expenses'))
            gross_income = to_decimal(data.get('gross_income', gross_annual_rent))
            
            if operating_expenses and gross_income and gross_income > 0:
                oer = (operating_expenses / gross_income) * 100
                results['real_estate_metrics']['operating_expense_ratio'] = {
                    'value': float(oer),
                    'formatted': f"{oer:.2f}%",
                    'interpretation': self._interpret_oer(float(oer))
                }
            
            # Generate insights
            self._generate_financial_insights(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Financial metrics calculation error: {e}")
            return {
                'error': str(e),
                'input_data': data
            }
    
    @tool
    async def analyze_market_trends(self, 
                                  time_series_data: List[Dict[str, Any]], 
                                  analysis_type: str = "comprehensive") -> Dict[str, Any]:
        """
        Perform advanced market trend analysis with statistical methods
        
        Args:
            time_series_data: Historical data points
            analysis_type: Type of analysis (basic, comprehensive, predictive)
            
        Returns:
            Dict with trend analysis, statistics, and predictions
        """
        try:
            if not time_series_data or len(time_series_data) < 3:
                return {'error': 'Insufficient data for trend analysis (need at least 3 points)'}
            
            # Convert to pandas DataFrame for easier analysis
            df = pd.DataFrame(time_series_data)
            
            # Ensure we have proper date parsing
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.sort_values('date', inplace=True)
            
            # Extract numerical values
            value_column = 'value' if 'value' in df.columns else df.select_dtypes(include=[np.number]).columns[0]
            values = df[value_column].astype(float).values
            
            results = {
                'analysis_type': analysis_type,
                'data_points': len(values),
                'date_range': {
                    'start': str(df['date'].min()) if 'date' in df.columns else 'N/A',
                    'end': str(df['date'].max()) if 'date' in df.columns else 'N/A'
                },
                'statistical_summary': {},
                'trend_analysis': {},
                'volatility_metrics': {},
                'predictions': {}
            }
            
            # Statistical Summary
            results['statistical_summary'] = {
                'mean': float(np.mean(values)),
                'median': float(np.median(values)),
                'std_dev': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'range': float(np.max(values) - np.min(values))
            }
            
            # Trend Analysis
            x = np.arange(len(values))
            coefficients = np.polyfit(x, values, 1)
            slope = coefficients[0]
            
            # Calculate R-squared
            y_pred = np.polyval(coefficients, x)
            ss_res = np.sum((values - y_pred) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            
            # Percentage change
            pct_change = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
            
            results['trend_analysis'] = {
                'direction': 'upward' if slope > 0 else 'downward',
                'slope': float(slope),
                'r_squared': float(r_squared),
                'trend_strength': self._categorize_trend_strength(r_squared, pct_change),
                'percentage_change': float(pct_change),
                'annualized_growth': self._calculate_annualized_growth(values, df)
            }
            
            # Volatility Metrics
            returns = np.diff(values) / values[:-1]
            results['volatility_metrics'] = {
                'volatility': float(np.std(returns) * np.sqrt(252)),  # Annualized
                'sharpe_ratio': float(np.mean(returns) / np.std(returns)) if np.std(returns) != 0 else 0,
                'max_drawdown': self._calculate_max_drawdown(values)
            }
            
            # Simple prediction if requested
            if analysis_type in ['comprehensive', 'predictive']:
                next_periods = 3
                future_x = np.arange(len(values), len(values) + next_periods)
                predictions = np.polyval(coefficients, future_x)
                
                results['predictions'] = {
                    'method': 'linear_regression',
                    'next_values': [float(p) for p in predictions],
                    'confidence_interval': {
                        'lower': [float(p - 1.96 * np.std(values)) for p in predictions],
                        'upper': [float(p + 1.96 * np.std(values)) for p in predictions]
                    }
                }
            
            return results
            
        except Exception as e:
            logger.error(f"Market trend analysis error: {e}")
            return {'error': str(e)}
    
    @tool
    async def perform_dcf_analysis(self, cash_flow_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform Discounted Cash Flow analysis for property valuation
        
        Args:
            cash_flow_data: Dict with cash flows, growth rate, discount rate
            
        Returns:
            Dict with NPV, IRR, and valuation metrics
        """
        try:
            # Extract parameters
            initial_investment = float(cash_flow_data.get('initial_investment', 0))
            annual_cash_flows = cash_flow_data.get('annual_cash_flows', [])
            discount_rate = float(cash_flow_data.get('discount_rate', 0.08))
            terminal_growth_rate = float(cash_flow_data.get('terminal_growth_rate', 0.02))
            holding_period = len(annual_cash_flows)
            
            if not annual_cash_flows:
                return {'error': 'No cash flows provided'}
            
            # Convert to numpy array
            cash_flows = np.array([float(cf) for cf in annual_cash_flows])
            
            # Calculate NPV
            discount_factors = [(1 + discount_rate) ** -i for i in range(1, holding_period + 1)]
            pv_cash_flows = cash_flows * discount_factors
            
            # Terminal value (if applicable)
            terminal_value = 0
            if terminal_growth_rate > 0 and discount_rate > terminal_growth_rate:
                terminal_cash_flow = cash_flows[-1] * (1 + terminal_growth_rate)
                terminal_value = terminal_cash_flow / (discount_rate - terminal_growth_rate)
                terminal_value_pv = terminal_value * discount_factors[-1]
            else:
                terminal_value_pv = 0
            
            npv = np.sum(pv_cash_flows) + terminal_value_pv - initial_investment
            
            # Calculate IRR
            cash_flow_series = np.concatenate([[-initial_investment], cash_flows])
            irr = np.irr(cash_flow_series) if len(cash_flow_series) > 0 else 0
            
            # Calculate other metrics
            total_return = np.sum(cash_flows) - initial_investment
            roi = (total_return / initial_investment * 100) if initial_investment != 0 else 0
            
            results = {
                'valuation_metrics': {
                    'npv': float(npv),
                    'formatted_npv': f"${npv:,.2f}",
                    'irr': float(irr * 100),
                    'formatted_irr': f"{irr * 100:.2f}%",
                    'total_return': float(total_return),
                    'roi': float(roi),
                    'formatted_roi': f"{roi:.2f}%"
                },
                'dcf_components': {
                    'present_value_cash_flows': float(np.sum(pv_cash_flows)),
                    'terminal_value': float(terminal_value),
                    'terminal_value_pv': float(terminal_value_pv),
                    'discount_rate_used': f"{discount_rate * 100:.2f}%"
                },
                'investment_decision': {
                    'recommendation': 'Accept' if npv > 0 else 'Reject',
                    'reasoning': self._generate_dcf_reasoning(npv, irr, discount_rate)
                }
            }
            
            return results
            
        except Exception as e:
            logger.error(f"DCF analysis error: {e}")
            return {'error': str(e)}
    
    @tool
    async def calculate_risk_metrics(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive risk metrics for real estate portfolio
        
        Args:
            portfolio_data: Portfolio returns and property data
            
        Returns:
            Dict with VaR, CVaR, beta, and other risk metrics
        """
        try:
            returns = np.array(portfolio_data.get('returns', []))
            market_returns = np.array(portfolio_data.get('market_returns', []))
            confidence_level = portfolio_data.get('confidence_level', 0.95)
            
            if len(returns) < 10:
                return {'error': 'Insufficient return data for risk analysis'}
            
            results = {
                'risk_metrics': {},
                'risk_adjusted_returns': {},
                'risk_assessment': {}
            }
            
            # Basic risk metrics
            results['risk_metrics']['volatility'] = {
                'daily': float(np.std(returns)),
                'annualized': float(np.std(returns) * np.sqrt(252))
            }
            
            # Value at Risk (VaR)
            var_percentile = (1 - confidence_level) * 100
            var = np.percentile(returns, var_percentile)
            results['risk_metrics']['var'] = {
                'value': float(var),
                'confidence_level': f"{confidence_level * 100}%",
                'interpretation': f"There is a {confidence_level * 100}% probability that losses will not exceed {abs(var):.2%}"
            }
            
            # Conditional VaR (CVaR)
            cvar = np.mean(returns[returns <= var])
            results['risk_metrics']['cvar'] = {
                'value': float(cvar),
                'interpretation': f"Expected loss given that loss exceeds VaR is {abs(cvar):.2%}"
            }
            
            # Beta (if market returns provided)
            if len(market_returns) == len(returns):
                covariance = np.cov(returns, market_returns)[0, 1]
                market_variance = np.var(market_returns)
                beta = covariance / market_variance if market_variance != 0 else 1
                
                results['risk_metrics']['beta'] = {
                    'value': float(beta),
                    'interpretation': self._interpret_beta(beta)
                }
            
            # Sharpe Ratio
            risk_free_rate = portfolio_data.get('risk_free_rate', 0.02) / 252  # Daily
            excess_returns = returns - risk_free_rate
            sharpe = np.mean(excess_returns) / np.std(returns) if np.std(returns) != 0 else 0
            sharpe_annualized = sharpe * np.sqrt(252)
            
            results['risk_adjusted_returns']['sharpe_ratio'] = {
                'value': float(sharpe_annualized),
                'interpretation': self._interpret_sharpe(sharpe_annualized)
            }
            
            # Risk assessment
            risk_score = self._calculate_risk_score(results['risk_metrics'])
            results['risk_assessment'] = {
                'risk_level': risk_score['level'],
                'risk_score': risk_score['score'],
                'recommendations': risk_score['recommendations']
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Risk metrics calculation error: {e}")
            return {'error': str(e)}
    
    @tool
    async def compare_market_performance(self, markets_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Enhanced market comparison with statistical significance testing
        
        Args:
            markets_data: Dict of market names to their performance data
            
        Returns:
            Dict with detailed comparative analysis
        """
        try:
            if len(markets_data) < 2:
                return {'error': 'Need at least two markets to compare'}
            
            results = {
                'comparison_summary': {},
                'market_rankings': {},
                'statistical_analysis': {},
                'investment_recommendations': []
            }
            
            # Standardize metrics across markets
            all_metrics = {}
            for market, data in markets_data.items():
                for metric, value in data.items():
                    if metric not in all_metrics:
                        all_metrics[metric] = {}
                    try:
                        all_metrics[metric][market] = float(value)
                    except:
                        continue
            
            # Rank markets by each metric
            for metric, values in all_metrics.items():
                if len(values) >= 2:
                    sorted_markets = sorted(values.items(), key=lambda x: x[1], reverse=True)
                    results['market_rankings'][metric] = [
                        {'rank': i+1, 'market': market, 'value': value}
                        for i, (market, value) in enumerate(sorted_markets)
                    ]
            
            # Calculate composite scores
            composite_scores = self._calculate_composite_scores(markets_data)
            results['comparison_summary']['composite_rankings'] = composite_scores
            
            # Statistical analysis
            if len(markets_data) > 2:
                results['statistical_analysis'] = self._perform_statistical_tests(all_metrics)
            
            # Generate recommendations
            results['investment_recommendations'] = self._generate_market_recommendations(
                results['market_rankings'], 
                composite_scores
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Market comparison error: {e}")
            return {'error': str(e)}
    
    @tool
    async def calculate_investment_returns(self, investment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive investment returns with multiple methodologies
        
        Args:
            investment_data: Investment details including cash flows
            
        Returns:
            Dict with various return calculations
        """
        try:
            results = {
                'return_metrics': {},
                'time_weighted_returns': {},
                'money_weighted_returns': {},
                'risk_adjusted_returns': {}
            }
            
            # Extract data
            initial = float(investment_data.get('initial_investment', 0))
            current = float(investment_data.get('current_value', 0))
            cash_flows = investment_data.get('cash_flows', [])
            time_period = float(investment_data.get('years', 1))
            
            if initial == 0:
                return {'error': 'Initial investment cannot be zero'}
            
            # Simple returns
            total_return = ((current - initial) / initial) * 100
            results['return_metrics']['total_return'] = {
                'value': float(total_return),
                'formatted': f"{total_return:.2f}%"
            }
            
            # CAGR
            if time_period > 0:
                cagr = (((current / initial) ** (1/time_period)) - 1) * 100
                results['return_metrics']['cagr'] = {
                    'value': float(cagr),
                    'formatted': f"{cagr:.2f}%"
                }
            
            # IRR if cash flows provided
            if cash_flows:
                cf_series = [-initial] + [float(cf) for cf in cash_flows] + [current]
                try:
                    irr = np.irr(cf_series) * 100
                    results['money_weighted_returns']['irr'] = {
                        'value': float(irr),
                        'formatted': f"{irr:.2f}%"
                    }
                except:
                    results['money_weighted_returns']['irr'] = {'error': 'IRR calculation failed'}
            
            # Multiple on Invested Capital (MOIC)
            total_distributions = sum([float(cf) for cf in cash_flows]) + current
            moic = total_distributions / initial
            results['return_metrics']['moic'] = {
                'value': float(moic),
                'formatted': f"{moic:.2f}x"
            }
            
            # Real estate specific metrics
            if 'rental_income' in investment_data:
                annual_rental = float(investment_data['rental_income'])
                rental_yield = (annual_rental / initial) * 100
                results['return_metrics']['rental_yield'] = {
                    'value': float(rental_yield),
                    'formatted': f"{rental_yield:.2f}%"
                }
            
            return results
            
        except Exception as e:
            logger.error(f"Investment return calculation error: {e}")
            return {'error': str(e)}
    
    @tool
    async def generate_market_report(self, analysis_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive market analysis report
        
        Args:
            analysis_request: Parameters for report generation
            
        Returns:
            Dict with structured market report
        """
        try:
            report_type = analysis_request.get('report_type', 'standard')
            market_name = analysis_request.get('market', 'General Market')
            metrics = analysis_request.get('metrics', {})
            
            report = {
                'report_metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'report_type': report_type,
                    'market': market_name
                },
                'executive_summary': {},
                'market_metrics': {},
                'trend_analysis': {},
                'risk_assessment': {},
                'recommendations': []
            }
            
            # Executive Summary
            report['executive_summary'] = self._generate_executive_summary(metrics)
            
            # Market Metrics Section
            report['market_metrics'] = self._format_market_metrics(metrics)
            
            # Generate insights and recommendations
            report['recommendations'] = self._generate_recommendations(metrics, market_name)
            
            return report
            
        except Exception as e:
            logger.error(f"Market report generation error: {e}")
            return {'error': str(e)}
    
    # Helper methods
    def _interpret_cap_rate(self, cap_rate: float) -> str:
        """Use LLM knowledge for cap rate interpretation based on current market conditions"""
        # Let the LLM interpret cap rates based on its training data and current market knowledge
        interpretation_prompt = f"""Analyze this cap rate: {cap_rate:.2f}%
        Provide a professional interpretation considering:
        1. Current commercial real estate market conditions
        2. Property type and location factors
        3. Risk/return profile implications
        4. Market positioning (premium, average, value-add)
        
        Provide a concise, factual interpretation."""
        
        # Use the agent's model for interpretation
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get LLM interpretation: {e}")
            return f"Cap rate: {cap_rate:.2f}% - Unable to provide interpretation (LLM unavailable)"
    
    def _interpret_coc_return(self, coc: float) -> str:
        """Use LLM knowledge for cash-on-cash return interpretation"""
        interpretation_prompt = f"""Analyze this cash-on-cash return: {coc:.2f}%
        Provide a professional interpretation considering:
        1. Current real estate investment benchmarks
        2. Risk-adjusted return expectations
        3. Market context and interest rate environment
        4. Relative performance vs other investment options
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get LLM interpretation: {e}")
            return f"Cash-on-Cash Return: {coc:.2f}% - Unable to provide interpretation (LLM unavailable)"
    
    def _interpret_dscr(self, dscr: float) -> str:
        """Use LLM knowledge for DSCR interpretation"""
        interpretation_prompt = f"""Analyze this Debt Service Coverage Ratio (DSCR): {dscr:.2f}x
        Provide a professional interpretation considering:
        1. Lender requirements and market standards
        2. Risk implications for debt service
        3. Financial stability indicators
        4. Refinancing and financing prospects
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get LLM interpretation: {e}")
            return f"DSCR: {dscr:.2f}x - Unable to provide interpretation (LLM unavailable)"
    
    def _interpret_grm(self, grm: float) -> str:
        """Use LLM knowledge for GRM interpretation"""
        interpretation_prompt = f"""Analyze this Gross Rent Multiplier (GRM): {grm:.2f}
        Provide a professional interpretation considering:
        1. Current market standards for property type
        2. Income generation efficiency
        3. Price-to-income relationship
        4. Investment attractiveness indicators
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get LLM interpretation: {e}")
            return f"GRM: {grm:.2f} - Unable to provide interpretation (LLM unavailable)"
    
    def _interpret_oer(self, oer: float) -> str:
        """Use LLM knowledge for Operating Expense Ratio interpretation"""
        interpretation_prompt = f"""Analyze this Operating Expense Ratio (OER): {oer:.2f}%
        Provide a professional interpretation considering:
        1. Industry benchmarks for property type
        2. Operational efficiency indicators
        3. Cost management effectiveness
        4. Areas for potential improvement
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get LLM interpretation: {e}")
            return f"OER: {oer:.2f}% - Unable to provide interpretation (LLM unavailable)"
    
    def _categorize_trend_strength(self, r_squared: float, pct_change: float) -> str:
        """Use statistical analysis and LLM knowledge for trend strength assessment"""
        interpretation_prompt = f"""Analyze this trend analysis:
        - R-squared: {r_squared:.3f}
        - Percentage change: {pct_change:.2f}%
        
        Provide a professional assessment of trend strength considering:
        1. Statistical significance (R-squared interpretation)
        2. Magnitude of change
        3. Reliability of the trend
        4. Investment implications
        
        Return one word: "Strong", "Moderate", or "Weak"""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(interpretation_prompt).strip()
            # Extract the strength rating
            if "Strong" in result:
                return "Strong"
            elif "Moderate" in result:
                return "Moderate"
            else:
                return "Weak"
        except Exception as e:
            logger.error(f"Failed to get trend strength assessment: {e}")
            # Fallback to basic statistical interpretation
            if r_squared > 0.7 and abs(pct_change) > 15:
                return "Strong"
            elif r_squared > 0.5 and abs(pct_change) > 5:
                return "Moderate"
            else:
                return "Weak"
    
    def _calculate_annualized_growth(self, values: np.ndarray, df: pd.DataFrame) -> float:
        if 'date' in df.columns and len(values) > 1:
            days = (df['date'].max() - df['date'].min()).days
            if days > 0:
                years = days / 365.25
                return float(((values[-1] / values[0]) ** (1/years) - 1) * 100)
        return 0.0
    
    def _calculate_max_drawdown(self, values: np.ndarray) -> float:
        cumulative = np.maximum.accumulate(values)
        drawdowns = (values - cumulative) / cumulative
        return float(np.min(drawdowns) * 100)
    
    def _interpret_beta(self, beta: float) -> str:
        """Use LLM knowledge for beta interpretation"""
        interpretation_prompt = f"""Analyze this beta coefficient: {beta:.2f}
        Provide a professional interpretation considering:
        1. Market sensitivity and correlation
        2. Risk profile implications
        3. Portfolio diversification impact
        4. Current market conditions
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get beta interpretation: {e}")
            return f"Beta: {beta:.2f} - Unable to provide interpretation (LLM unavailable)"
    
    def _interpret_sharpe(self, sharpe: float) -> str:
        """Use LLM knowledge for Sharpe ratio interpretation"""
        interpretation_prompt = f"""Analyze this Sharpe ratio: {sharpe:.2f}
        Provide a professional interpretation considering:
        1. Risk-adjusted return quality
        2. Current market benchmarks
        3. Investment attractiveness
        4. Comparison with market standards
        
        Provide a concise, factual assessment."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(interpretation_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to get Sharpe ratio interpretation: {e}")
            return f"Sharpe Ratio: {sharpe:.2f} - Unable to provide interpretation (LLM unavailable)"
    
    def _calculate_risk_score(self, risk_metrics: Dict) -> Dict:
        """Use comprehensive risk analysis with LLM interpretation"""
        # Use LLM to analyze the complete risk profile
        metrics_summary = json.dumps(risk_metrics, indent=2)
        
        risk_prompt = f"""Analyze this comprehensive risk profile:
        {metrics_summary}
        
        Provide a risk assessment with:
        1. Overall risk level (Low/Medium/High)
        2. Key risk factors identified
        3. Specific recommendations for risk mitigation
        4. Risk score (0-100 scale)
        
        Consider current market conditions and best practices in risk management.
        Format as JSON with keys: score, level, recommendations"""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(risk_prompt).strip()
            
            # Try to parse as JSON
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                parsed_result = json.loads(json_match.group())
                return {
                    'score': parsed_result.get('score', 50),
                    'level': parsed_result.get('level', 'Medium'),
                    'recommendations': parsed_result.get('recommendations', ['Unable to generate specific recommendations'])
                }
        except Exception as e:
            logger.error(f"Failed to get risk analysis: {e}")
        
        # Fallback to basic analysis if LLM fails
        return {
            'score': 50,
            'level': 'Medium',
            'recommendations': ['Unable to provide detailed risk analysis - LLM unavailable']
        }
    
    def _generate_financial_insights(self, results: Dict) -> None:
        """Generate insights using LLM analysis of calculated metrics"""
        # Prepare metrics summary for LLM analysis
        metrics_summary = {
            'real_estate_metrics': results.get('real_estate_metrics', {}),
            'calculated_metrics': results.get('calculated_metrics', {}),
            'ratios': results.get('ratios', {})
        }
        
        insight_prompt = f"""Analyze these financial metrics and generate 3-5 key insights:
        {json.dumps(metrics_summary, indent=2)}
        
        Provide professional insights considering:
        1. Investment attractiveness
        2. Risk factors
        3. Market positioning
        4. Areas of concern or opportunity
        5. Comparison to market standards
        
        Return as a JSON array of strings."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(insight_prompt).strip()
            
            # Parse insights from LLM response
            import re
            array_match = re.search(r'\[.*\]', result, re.DOTALL)
            if array_match:
                insights = json.loads(array_match.group())
                results['insights'] = insights
            else:
                # Fallback if JSON parsing fails
                insights = [line.strip() for line in result.split('\n') if line.strip() and not line.startswith('```')]
                results['insights'] = insights[:5]  # Limit to 5 insights
                
        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")
            results['insights'] = ["Unable to generate detailed insights - Analysis unavailable"]
    
    def _generate_dcf_reasoning(self, npv: float, irr: float, discount_rate: float) -> str:
        """Generate DCF reasoning using LLM analysis"""
        reasoning_prompt = f"""Analyze this DCF analysis:
        - NPV: ${npv:,.0f}
        - IRR: {irr:.1f}%
        - Discount Rate: {discount_rate*100:.1f}%
        
        Provide a professional investment recommendation considering:
        1. Value creation/destruction analysis
        2. Return adequacy vs required rate
        3. Investment decision rationale
        4. Risk-return assessment
        
        Keep response concise and actionable."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(reasoning_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to generate DCF reasoning: {e}")
            # Basic fallback reasoning
            if npv > 0 and irr > discount_rate:
                return f"Positive NPV (${npv:,.0f}) and IRR ({irr:.1f}%) exceed required return ({discount_rate*100:.1f}%) - Investment creates value"
            else:
                return f"Investment analysis suggests caution - NPV: ${npv:,.0f}, IRR: {irr:.1f}% vs required {discount_rate*100:.1f}%"
    
    def _calculate_composite_scores(self, markets_data: Dict) -> List[Dict]:
        """Calculate composite scores using LLM-driven market analysis"""
        ranking_prompt = f"""Analyze and rank these markets based on investment attractiveness:
        {json.dumps(markets_data, indent=2)}
        
        Consider all available metrics and provide:
        1. Ranking of markets from best to worst investment opportunity
        2. Composite score (0-100) for each market
        3. Brief rationale for ranking
        
        Return as JSON array with format: [{"rank": 1, "market": "name", "score": 85, "rationale": "..."}]"""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(ranking_prompt).strip()
            
            # Parse the ranking from LLM response
            import re
            array_match = re.search(r'\[.*\]', result, re.DOTALL)
            if array_match:
                rankings = json.loads(array_match.group())
                return rankings
                
        except Exception as e:
            logger.error(f"Failed to generate market rankings: {e}")
        
        # Fallback to simple scoring if LLM fails
        scores = {}
        for market, data in markets_data.items():
            # Basic scoring using available numerical metrics
            score = 50  # Base score
            if 'cap_rate' in data:
                try:
                    cap_rate = float(data['cap_rate'])
                    score += min(20, max(-20, (cap_rate - 6) * 2))  # Normalize around 6%
                except:
                    pass
            scores[market] = score
        
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [
            {'rank': i+1, 'market': market, 'score': score, 'rationale': 'Basic scoring due to analysis limitations'}
            for i, (market, score) in enumerate(sorted_scores)
        ]
    
    def _perform_statistical_tests(self, metrics: Dict) -> Dict:
        """Perform basic statistical tests on market metrics"""
        results = {}
        
        for metric, values in metrics.items():
            if len(values) >= 3:
                metric_values = list(values.values())
                results[metric] = {
                    'mean': float(np.mean(metric_values)),
                    'std_dev': float(np.std(metric_values)),
                    'cv': float(np.std(metric_values) / np.mean(metric_values)) if np.mean(metric_values) != 0 else 0
                }
        
        return results
    
    def _determine_market_outlook(self, metrics: Dict) -> str:
        """Determine market outlook using LLM analysis of all available metrics"""
        outlook_prompt = f"""Analyze these market metrics and determine overall outlook:
        {json.dumps(metrics, indent=2)}
        
        Consider:
        1. Current market fundamentals
        2. Economic indicators
        3. Investment opportunities and risks
        4. Market trends and momentum
        5. External factors affecting the market
        
        Provide a concise outlook statement (2-3 sentences) that summarizes the investment climate."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(outlook_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to generate market outlook: {e}")
            return "Market outlook analysis unavailable - Unable to assess current conditions"
    
    def _generate_executive_summary(self, metrics: Dict) -> Dict:
        """Generate executive summary for market report"""
        return {
            'market_outlook': self._determine_market_outlook(metrics),
            'key_metrics': self._extract_key_metrics(metrics),
            'risk_profile': self._assess_risk_profile(metrics)
        }
    
    
    def _extract_key_metrics(self, metrics: Dict) -> List[Dict]:
        """Extract and format key metrics using data-driven approach"""
        key_metrics = []
        
        # Dynamically identify the most relevant metrics from available data
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)) and metric_name not in ['timestamp', 'id']:
                # Format based on metric type
                if 'rate' in metric_name.lower() or 'percent' in metric_name.lower():
                    formatted = f"{metric_value:.1f}%"
                elif 'price' in metric_name.lower() or 'value' in metric_name.lower():
                    formatted = f"${metric_value:,.0f}"
                else:
                    formatted = f"{metric_value:.2f}"
                    
                key_metrics.append({
                    'name': metric_name.replace('_', ' ').title(),
                    'value': metric_value,
                    'formatted': formatted
                })
        
        # Sort by importance (rates and percentages first)
        key_metrics.sort(key=lambda x: ('rate' in x['name'].lower() or 'percent' in x['name'].lower()), reverse=True)
        return key_metrics[:6]  # Return top 6 metrics
    
    def _assess_risk_profile(self, metrics: Dict) -> str:
        """Assess risk profile using LLM analysis of all available metrics"""
        risk_prompt = f"""Assess the overall risk profile of this investment based on these metrics:
        {json.dumps(metrics, indent=2)}
        
        Consider:
        1. Market indicators and volatility
        2. Financial performance metrics
        3. Operational risk factors
        4. Market conditions and trends
        5. Comparative risk levels
        
        Provide a concise risk assessment: "Low Risk", "Moderate Risk", or "High Risk" with brief justification."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            return model.generate(risk_prompt).strip()
        except Exception as e:
            logger.error(f"Failed to assess risk profile: {e}")
            return "Risk assessment unavailable - Analysis system unavailable"
    
    def _format_market_metrics(self, metrics: Dict) -> Dict:
        """Format market metrics with intelligent type detection"""
        formatted = {}
        
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                # Smart formatting based on metric name and value
                key_lower = key.lower()
                if 'rate' in key_lower or 'yield' in key_lower or 'return' in key_lower or 'percent' in key_lower:
                    formatted[key] = f"{value:.2f}%"
                elif 'price' in key_lower or 'value' in key_lower or 'cost' in key_lower:
                    if value >= 1000:
                        formatted[key] = f"${value:,.0f}"
                    else:
                        formatted[key] = f"${value:.2f}"
                elif 'ratio' in key_lower or 'multiple' in key_lower:
                    formatted[key] = f"{value:.2f}x"
                else:
                    # Auto-detect formatting based on value magnitude
                    if value >= 1000:
                        formatted[key] = f"{value:,.0f}"
                    else:
                        formatted[key] = f"{value:.2f}"
            elif isinstance(value, dict):
                # Recursively format nested dictionaries
                formatted[key] = self._format_market_metrics(value)
            else:
                formatted[key] = str(value)
        
        return formatted
    
    def _generate_recommendations(self, metrics: Dict, market_name: str) -> List[str]:
        """Generate investment recommendations using LLM analysis"""
        recommendation_prompt = f"""Generate specific, actionable investment recommendations for {market_name} based on these metrics:
        {json.dumps(metrics, indent=2)}
        
        Provide 3-5 specific recommendations considering:
        1. Current market conditions and opportunities
        2. Risk factors and mitigation strategies
        3. Investment timing and strategy
        4. Portfolio allocation suggestions
        5. Market-specific advantages or concerns
        
        Return as a JSON array of specific recommendation strings."""
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(recommendation_prompt).strip()
            
            # Parse recommendations from LLM response
            import re
            array_match = re.search(r'\[.*\]', result, re.DOTALL)
            if array_match:
                recommendations = json.loads(array_match.group())
                return recommendations
                
        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
        
        # Fallback recommendations if LLM fails
        return [
            f"Conduct thorough due diligence on {market_name} investment opportunities",
            "Monitor local market conditions and regulatory changes",
            "Consider professional property management for optimal returns"
        ]

# Create singleton instance
market_analyst_agent_v2 = EnhancedMarketAnalystAgent()
market_analyst_agent = market_analyst_agent_v2  # Backward compatibility alias

# AgentCore handler
def agentcore_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """AgentCore entry point"""
    return market_analyst_agent_v2.agentcore_handler(event)

# For local testing
if __name__ == "__main__":
    import asyncio
    
    test_event = {
        'input': 'Calculate the cap rate for a property with $1M NOI and $15M value',
        'sessionId': 'test-market-v2-001'
    }
    
    result = agentcore_handler(test_event)
    print(json.dumps(result, indent=2))