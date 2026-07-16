"""
BDA Investment Advisory Agent V2 - Enhanced for AgentCore
Specialized in investment recommendations, portfolio optimization, and risk assessment
Full AgentCore integration with advanced analytics
"""

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands_agents_v2.shared.agent_base import AgentCoreBaseAgent
from strands_agents_v2.shared.prompt_loader import PromptLoader
import boto3
import json
import os
import asyncio
from typing import Dict, Any, List, Union, Optional, Tuple
from decimal import Decimal
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
from scipy import optimize

# Configure logging
logger = logging.getLogger(__name__)

class EnhancedInvestmentAdvisoryAgent(AgentCoreBaseAgent):
    """
    Enhanced Investment Advisory Agent with AgentCore integration
    Provides sophisticated portfolio optimization and investment recommendations
    """
    
    def __init__(self):
        super().__init__(
            agent_name="BDA-Investment-Advisory-Agent-V2",
            agent_type="specialist_advisor",
            model_config={
                "model_id": "us.anthropic.claude-sonnet-4-5-20250514-v1:0"
            }
        )
        
        # Enhanced tools with async support
        self.tools = [
            self.assess_investment_risk,
            self.optimize_portfolio,
            self.evaluate_investment_opportunity,
            self.generate_portfolio_recommendations,
            self.perform_monte_carlo_simulation,
            self.calculate_efficient_frontier,
            self.analyze_real_estate_investment,
            self.generate_investment_report
        ]
        
        # Recreate agent with tools
        self.agent = self._create_strands_agent()
    
    def get_system_prompt(self) -> str:
        """Load prompt from assets/AgentPrompts.txt file"""
        return PromptLoader.get_prompt('investment_advisory')
    
    @tool
    async def assess_investment_risk(self, investment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform comprehensive multi-factor risk assessment
        
        Args:
            investment_data: Investment details including financials and market data
            
        Returns:
            Dict with detailed risk analysis and scoring
        """
        try:
            risk_assessment = {
                'timestamp': datetime.now().isoformat(),
                'investment_profile': investment_data,
                'risk_factors': {},
                'composite_risk_score': 0,
                'risk_rating': '',
                'mitigation_strategies': [],
                'stress_test_results': {}
            }
            
            # Initialize risk scoring
            risk_scores = []
            
            # 1. Market Risk Assessment
            market_risk = self._assess_market_risk(investment_data)
            risk_assessment['risk_factors']['market_risk'] = market_risk
            risk_scores.append(market_risk['score'])
            
            # 2. Credit Risk Assessment
            credit_risk = self._assess_credit_risk(investment_data)
            risk_assessment['risk_factors']['credit_risk'] = credit_risk
            risk_scores.append(credit_risk['score'])
            
            # 3. Liquidity Risk Assessment
            liquidity_risk = self._assess_liquidity_risk(investment_data)
            risk_assessment['risk_factors']['liquidity_risk'] = liquidity_risk
            risk_scores.append(liquidity_risk['score'])
            
            # 4. Operational Risk Assessment
            operational_risk = self._assess_operational_risk(investment_data)
            risk_assessment['risk_factors']['operational_risk'] = operational_risk
            risk_scores.append(operational_risk['score'])
            
            # 5. Real Estate Specific Risks
            if investment_data.get('asset_type', '').lower() == 'real_estate':
                re_risk = self._assess_real_estate_risk(investment_data)
                risk_assessment['risk_factors']['real_estate_risk'] = re_risk
                risk_scores.append(re_risk['score'])
            
            # Calculate composite risk score
            composite_score = np.mean(risk_scores)
            risk_assessment['composite_risk_score'] = float(composite_score)
            
            # Determine risk rating
            if composite_score <= 3:
                risk_assessment['risk_rating'] = 'Low Risk'
            elif composite_score <= 5:
                risk_assessment['risk_rating'] = 'Moderate Risk'
            elif composite_score <= 7:
                risk_assessment['risk_rating'] = 'High Risk'
            else:
                risk_assessment['risk_rating'] = 'Very High Risk'
            
            # Generate mitigation strategies
            risk_assessment['mitigation_strategies'] = self._generate_mitigation_strategies(
                risk_assessment['risk_factors']
            )
            
            # Stress testing
            if 'expected_return' in investment_data and 'volatility' in investment_data:
                risk_assessment['stress_test_results'] = self._perform_stress_test(investment_data)
            
            return risk_assessment
            
        except Exception as e:
            logger.error(f"Risk assessment error: {e}")
            return {'error': str(e)}
    
    @tool
    async def optimize_portfolio(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform advanced portfolio optimization using Modern Portfolio Theory
        
        Args:
            portfolio_data: Current holdings, constraints, and objectives
            
        Returns:
            Dict with optimal allocation and performance metrics
        """
        try:
            # Extract portfolio parameters
            assets = portfolio_data.get('assets', [])
            constraints = portfolio_data.get('constraints', {})
            objective = portfolio_data.get('objective', 'max_sharpe')
            
            if len(assets) < 2:
                return {'error': 'Need at least 2 assets for portfolio optimization'}
            
            # Prepare return and covariance matrices
            returns = np.array([asset.get('expected_return', 0) for asset in assets])
            
            # Create covariance matrix (simplified - in practice would use historical data)
            n_assets = len(assets)
            correlations = portfolio_data.get('correlations', np.eye(n_assets) * 0.5)
            volatilities = np.array([asset.get('volatility', 0.15) for asset in assets])
            cov_matrix = self._create_covariance_matrix(volatilities, correlations)
            
            # Define optimization constraints
            optimization_constraints = self._prepare_optimization_constraints(n_assets, constraints)
            
            # Perform optimization based on objective
            if objective == 'max_sharpe':
                optimal_weights = self._optimize_sharpe_ratio(returns, cov_matrix, optimization_constraints)
            elif objective == 'min_variance':
                optimal_weights = self._optimize_min_variance(cov_matrix, optimization_constraints)
            elif objective == 'target_return':
                target_return = constraints.get('target_return', 0.08)
                optimal_weights = self._optimize_target_return(returns, cov_matrix, target_return, optimization_constraints)
            else:
                optimal_weights = np.array([1/n_assets] * n_assets)  # Equal weight fallback
            
            # Calculate portfolio metrics
            portfolio_return = np.dot(optimal_weights, returns)
            portfolio_variance = np.dot(optimal_weights.T, np.dot(cov_matrix, optimal_weights))
            portfolio_volatility = np.sqrt(portfolio_variance)
            sharpe_ratio = (portfolio_return - 0.02) / portfolio_volatility if portfolio_volatility > 0 else 0
            
            # Prepare results
            optimization_results = {
                'optimal_allocation': {},
                'portfolio_metrics': {
                    'expected_return': float(portfolio_return),
                    'volatility': float(portfolio_volatility),
                    'sharpe_ratio': float(sharpe_ratio),
                    'var_95': float(-1.645 * portfolio_volatility + portfolio_return)
                },
                'allocation_changes': {},
                'implementation_plan': []
            }
            
            # Map weights to assets
            for i, asset in enumerate(assets):
                asset_name = asset.get('name', f'Asset_{i}')
                current_weight = asset.get('current_weight', 0)
                optimal_weight = float(optimal_weights[i])
                
                optimization_results['optimal_allocation'][asset_name] = {
                    'weight': optimal_weight,
                    'percentage': f"{optimal_weight * 100:.1f}%",
                    'value': optimal_weight * portfolio_data.get('total_value', 1000000)
                }
                
                # Calculate required changes
                weight_change = optimal_weight - current_weight
                if abs(weight_change) > 0.02:  # More than 2% change
                    optimization_results['allocation_changes'][asset_name] = {
                        'action': 'increase' if weight_change > 0 else 'decrease',
                        'amount': abs(weight_change),
                        'percentage_points': f"{abs(weight_change * 100):.1f}pp"
                    }
            
            # Generate implementation plan
            optimization_results['implementation_plan'] = self._generate_implementation_plan(
                optimization_results['allocation_changes'],
                portfolio_data
            )
            
            return optimization_results
            
        except Exception as e:
            logger.error(f"Portfolio optimization error: {e}")
            return {'error': str(e)}
    
    @tool
    async def evaluate_investment_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive evaluation of investment opportunities
        
        Args:
            opportunity: Investment opportunity details
            
        Returns:
            Dict with detailed evaluation and recommendation
        """
        try:
            evaluation = {
                'opportunity_summary': opportunity,
                'financial_analysis': {},
                'qualitative_assessment': {},
                'risk_return_profile': {},
                'recommendation': {},
                'due_diligence_checklist': []
            }
            
            # Financial Analysis
            evaluation['financial_analysis'] = self._perform_financial_analysis(opportunity)
            
            # Qualitative Assessment
            evaluation['qualitative_assessment'] = self._perform_qualitative_assessment(opportunity)
            
            # Risk-Return Profile
            evaluation['risk_return_profile'] = self._analyze_risk_return_profile(opportunity)
            
            # Generate recommendation
            scores = {
                'financial': self._score_financial_metrics(evaluation['financial_analysis']),
                'qualitative': self._score_qualitative_factors(evaluation['qualitative_assessment']),
                'risk_return': self._score_risk_return(evaluation['risk_return_profile'])
            }
            
            overall_score = np.mean(list(scores.values()))
            
            evaluation['recommendation'] = {
                'action': self._determine_recommendation_action(overall_score),
                'confidence': self._determine_confidence_level(scores),
                'score': float(overall_score),
                'rationale': self._generate_recommendation_rationale(evaluation, scores)
            }
            
            # Due diligence checklist
            evaluation['due_diligence_checklist'] = self._generate_due_diligence_checklist(opportunity)
            
            return evaluation
            
        except Exception as e:
            logger.error(f"Investment evaluation error: {e}")
            return {'error': str(e)}
    
    @tool
    async def perform_monte_carlo_simulation(self, simulation_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation for investment scenarios
        
        Args:
            simulation_params: Parameters for simulation including returns, volatility
            
        Returns:
            Dict with simulation results and probability distributions
        """
        try:
            # Extract parameters
            initial_investment = float(simulation_params.get('initial_investment', 1000000))
            expected_return = float(simulation_params.get('expected_return', 0.08))
            volatility = float(simulation_params.get('volatility', 0.15))
            time_horizon = int(simulation_params.get('years', 10))
            simulations = int(simulation_params.get('simulations', 10000))
            
            # Run Monte Carlo simulation
            np.random.seed(42)  # For reproducibility
            
            # Generate random returns
            annual_returns = np.random.normal(expected_return, volatility, (simulations, time_horizon))
            
            # Calculate portfolio values over time
            portfolio_values = np.zeros((simulations, time_horizon + 1))
            portfolio_values[:, 0] = initial_investment
            
            for t in range(time_horizon):
                portfolio_values[:, t + 1] = portfolio_values[:, t] * (1 + annual_returns[:, t])
            
            # Calculate statistics
            final_values = portfolio_values[:, -1]
            
            results = {
                'simulation_parameters': {
                    'initial_investment': initial_investment,
                    'expected_return': f"{expected_return:.1%}",
                    'volatility': f"{volatility:.1%}",
                    'time_horizon': time_horizon,
                    'simulations': simulations
                },
                'results': {
                    'mean_final_value': float(np.mean(final_values)),
                    'median_final_value': float(np.median(final_values)),
                    'std_dev': float(np.std(final_values)),
                    'min_value': float(np.min(final_values)),
                    'max_value': float(np.max(final_values))
                },
                'percentiles': {
                    '5th': float(np.percentile(final_values, 5)),
                    '25th': float(np.percentile(final_values, 25)),
                    '50th': float(np.percentile(final_values, 50)),
                    '75th': float(np.percentile(final_values, 75)),
                    '95th': float(np.percentile(final_values, 95))
                },
                'probability_analysis': {
                    'prob_gain': float(np.mean(final_values > initial_investment)),
                    'prob_double': float(np.mean(final_values > 2 * initial_investment)),
                    'prob_loss_10pct': float(np.mean(final_values < 0.9 * initial_investment)),
                    'prob_loss_25pct': float(np.mean(final_values < 0.75 * initial_investment))
                },
                'risk_metrics': {
                    'var_95': float(np.percentile(final_values - initial_investment, 5)),
                    'cvar_95': float(np.mean(final_values[final_values <= np.percentile(final_values, 5)] - initial_investment)),
                    'max_drawdown': self._calculate_max_drawdown_simulation(portfolio_values)
                }
            }
            
            # Generate insights
            results['insights'] = self._generate_monte_carlo_insights(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Monte Carlo simulation error: {e}")
            return {'error': str(e)}
    
    @tool
    async def calculate_efficient_frontier(self, assets_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate efficient frontier for portfolio optimization
        
        Args:
            assets_data: Asset returns, volatilities, and correlations
            
        Returns:
            Dict with efficient frontier points and optimal portfolios
        """
        try:
            assets = assets_data.get('assets', [])
            if len(assets) < 2:
                return {'error': 'Need at least 2 assets for efficient frontier'}
            
            # Extract data
            returns = np.array([asset['expected_return'] for asset in assets])
            volatilities = np.array([asset['volatility'] for asset in assets])
            correlations = np.array(assets_data.get('correlation_matrix', np.eye(len(assets))))
            
            # Create covariance matrix
            cov_matrix = self._create_covariance_matrix(volatilities, correlations)
            
            # Generate efficient frontier
            n_portfolios = 50
            target_returns = np.linspace(np.min(returns), np.max(returns), n_portfolios)
            
            efficient_frontier = {
                'portfolios': [],
                'tangency_portfolio': {},
                'minimum_variance_portfolio': {},
                'asset_details': {}
            }
            
            # Calculate portfolio for each target return
            for target_return in target_returns:
                weights = self._optimize_for_target_return(returns, cov_matrix, target_return)
                
                if weights is not None:
                    portfolio_return = np.dot(weights, returns)
                    portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                    sharpe = (portfolio_return - 0.02) / portfolio_vol if portfolio_vol > 0 else 0
                    
                    efficient_frontier['portfolios'].append({
                        'return': float(portfolio_return),
                        'volatility': float(portfolio_vol),
                        'sharpe_ratio': float(sharpe),
                        'weights': [float(w) for w in weights]
                    })
            
            # Find special portfolios
            if efficient_frontier['portfolios']:
                # Minimum variance portfolio
                min_var_idx = np.argmin([p['volatility'] for p in efficient_frontier['portfolios']])
                efficient_frontier['minimum_variance_portfolio'] = efficient_frontier['portfolios'][min_var_idx]
                
                # Tangency portfolio (max Sharpe)
                max_sharpe_idx = np.argmax([p['sharpe_ratio'] for p in efficient_frontier['portfolios']])
                efficient_frontier['tangency_portfolio'] = efficient_frontier['portfolios'][max_sharpe_idx]
            
            # Add asset details
            for i, asset in enumerate(assets):
                efficient_frontier['asset_details'][asset['name']] = {
                    'expected_return': float(returns[i]),
                    'volatility': float(volatilities[i]),
                    'tangency_weight': float(efficient_frontier['tangency_portfolio']['weights'][i])
                }
            
            return efficient_frontier
            
        except Exception as e:
            logger.error(f"Efficient frontier calculation error: {e}")
            return {'error': str(e)}
    
    @tool
    async def analyze_real_estate_investment(self, property_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Specialized analysis for real estate investments
        
        Args:
            property_data: Property details including financials and market data
            
        Returns:
            Dict with comprehensive real estate investment analysis
        """
        try:
            analysis = {
                'property_overview': property_data,
                'financial_metrics': {},
                'market_analysis': {},
                'cash_flow_projection': {},
                'investment_returns': {},
                'risks_and_opportunities': {}
            }
            
            # Calculate key real estate metrics
            purchase_price = float(property_data.get('purchase_price', 0))
            noi = float(property_data.get('net_operating_income', 0))
            annual_rent = float(property_data.get('annual_rent', 0))
            
            # Financial Metrics
            if purchase_price > 0:
                # Cap Rate
                cap_rate = (noi / purchase_price) * 100 if noi > 0 else 0
                analysis['financial_metrics']['cap_rate'] = {
                    'value': float(cap_rate),
                    'formatted': f"{cap_rate:.2f}%",
                    'interpretation': self._interpret_cap_rate(cap_rate)
                }
                
                # Gross Rent Multiplier
                grm = purchase_price / annual_rent if annual_rent > 0 else 0
                analysis['financial_metrics']['gross_rent_multiplier'] = {
                    'value': float(grm),
                    'interpretation': self._interpret_grm(grm)
                }
            
            # Cash-on-Cash Return
            down_payment = float(property_data.get('down_payment', purchase_price * 0.25))
            annual_cash_flow = float(property_data.get('annual_cash_flow', noi * 0.7))
            
            if down_payment > 0:
                coc_return = (annual_cash_flow / down_payment) * 100
                analysis['financial_metrics']['cash_on_cash_return'] = {
                    'value': float(coc_return),
                    'formatted': f"{coc_return:.2f}%",
                    'interpretation': self._interpret_coc_return(coc_return)
                }
            
            # DSCR
            annual_debt_service = float(property_data.get('annual_debt_service', 0))
            if annual_debt_service > 0:
                dscr = noi / annual_debt_service
                analysis['financial_metrics']['dscr'] = {
                    'value': float(dscr),
                    'formatted': f"{dscr:.2f}x",
                    'interpretation': self._interpret_dscr(dscr)
                }
            
            # Market Analysis
            analysis['market_analysis'] = self._analyze_real_estate_market(property_data)
            
            # Cash Flow Projection
            analysis['cash_flow_projection'] = self._project_real_estate_cash_flows(property_data)
            
            # Investment Returns
            analysis['investment_returns'] = self._calculate_real_estate_returns(
                property_data,
                analysis['cash_flow_projection']
            )
            
            # Risks and Opportunities
            analysis['risks_and_opportunities'] = self._assess_real_estate_risks_opportunities(
                property_data,
                analysis['financial_metrics'],
                analysis['market_analysis']
            )
            
            return analysis
            
        except Exception as e:
            logger.error(f"Real estate analysis error: {e}")
            return {'error': str(e)}
    
    @tool
    async def generate_portfolio_recommendations(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate personalized portfolio recommendations based on investor profile
        
        Args:
            portfolio_data: Current portfolio and investor preferences
            
        Returns:
            Dict with tailored recommendations and action plan
        """
        try:
            recommendations = {
                'portfolio_assessment': {},
                'strategic_recommendations': [],
                'tactical_recommendations': [],
                'rebalancing_plan': {},
                'new_investment_ideas': [],
                'action_plan': []
            }
            
            # Assess current portfolio
            recommendations['portfolio_assessment'] = self._assess_current_portfolio(portfolio_data)
            
            # Generate strategic recommendations (long-term)
            recommendations['strategic_recommendations'] = self._generate_strategic_recommendations(
                portfolio_data,
                recommendations['portfolio_assessment']
            )
            
            # Generate tactical recommendations (short-term)
            recommendations['tactical_recommendations'] = self._generate_tactical_recommendations(
                portfolio_data,
                recommendations['portfolio_assessment']
            )
            
            # Rebalancing plan
            if recommendations['portfolio_assessment'].get('rebalancing_needed', False):
                recommendations['rebalancing_plan'] = self._create_rebalancing_plan(portfolio_data)
            
            # New investment ideas
            recommendations['new_investment_ideas'] = self._generate_investment_ideas(portfolio_data)
            
            # Create action plan
            recommendations['action_plan'] = self._create_action_plan(recommendations)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Portfolio recommendations error: {e}")
            return {'error': str(e)}
    
    @tool
    async def generate_investment_report(self, report_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate comprehensive investment report
        
        Args:
            report_params: Parameters for report generation
            
        Returns:
            Dict with structured investment report
        """
        try:
            report_type = report_params.get('report_type', 'quarterly')
            portfolio_data = report_params.get('portfolio_data', {})
            
            report = {
                'report_metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'report_type': report_type,
                    'reporting_period': report_params.get('period', 'Q4 2024')
                },
                'executive_summary': {},
                'portfolio_performance': {},
                'market_commentary': {},
                'risk_analysis': {},
                'recommendations': {},
                'appendix': {}
            }
            
            # Executive Summary
            report['executive_summary'] = self._generate_executive_summary(portfolio_data)
            
            # Portfolio Performance
            report['portfolio_performance'] = self._analyze_portfolio_performance(portfolio_data)
            
            # Market Commentary
            report['market_commentary'] = self._generate_market_commentary(report_params)
            
            # Risk Analysis
            report['risk_analysis'] = self._generate_risk_analysis(portfolio_data)
            
            # Recommendations
            report['recommendations'] = self._generate_report_recommendations(
                portfolio_data,
                report['portfolio_performance'],
                report['risk_analysis']
            )
            
            # Appendix
            report['appendix'] = {
                'methodology': 'Analysis based on Modern Portfolio Theory and risk-adjusted returns',
                'disclaimers': [
                    'Past performance does not guarantee future results',
                    'All investments carry risk of loss',
                    'This report is for informational purposes only'
                ],
                'glossary': self._generate_glossary()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Investment report generation error: {e}")
            return {'error': str(e)}
    
    # Helper methods
    def _assess_market_risk(self, data: Dict) -> Dict:
        """Assess market risk factors using LLM analysis"""
        risk_prompt = f"""Analyze this market risk profile:
        {json.dumps(data, indent=2)}
        
        Provide a comprehensive market risk assessment considering:
        1. Volatility levels and market sensitivity
        2. Beta coefficient and market correlation
        3. Current market conditions
        4. Historical performance patterns
        5. Systematic risk factors
        
        Provide a risk score (1-10, where 10 is highest risk) and assessment.
        Format as JSON with keys: score, assessment, key_factors, recommendations
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(risk_prompt).strip()
            
            # Parse LLM response
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    'score': min(10, max(1, analysis.get('score', 5))),
                    'factors': data,
                    'assessment': analysis.get('assessment', 'Medium Risk'),
                    'key_factors': analysis.get('key_factors', []),
                    'recommendations': analysis.get('recommendations', [])
                }
        except Exception as e:
            logger.error(f"Failed to assess market risk: {e}")
        
        # Fallback assessment
        return {
            'score': 5,
            'factors': data,
            'assessment': 'Risk assessment unavailable',
            'message': 'LLM analysis required for detailed risk assessment'
        }
    
    def _assess_credit_risk(self, data: Dict) -> Dict:
        """Assess credit risk factors using LLM analysis"""
        credit_prompt = f"""Analyze this credit risk profile:
        {json.dumps(data, indent=2)}
        
        Provide a comprehensive credit risk assessment considering:
        1. Credit rating and creditworthiness
        2. Leverage ratios and debt capacity
        3. Financial stability indicators
        4. Industry and sector factors
        5. Economic environment impact
        
        Provide a risk score (1-10, where 10 is highest risk) and assessment.
        Format as JSON with keys: score, assessment, key_factors, recommendations
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(credit_prompt).strip()
            
            # Parse LLM response
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    'score': min(10, max(1, analysis.get('score', 5))),
                    'factors': data,
                    'assessment': analysis.get('assessment', 'Medium Risk'),
                    'key_factors': analysis.get('key_factors', []),
                    'recommendations': analysis.get('recommendations', [])
                }
        except Exception as e:
            logger.error(f"Failed to assess credit risk: {e}")
        
        # Fallback assessment
        return {
            'score': 5,
            'factors': data,
            'assessment': 'Risk assessment unavailable',
            'message': 'LLM analysis required for detailed credit risk assessment'
        }
    
    def _assess_liquidity_risk(self, data: Dict) -> Dict:
        """Assess liquidity risk factors using LLM analysis"""
        liquidity_prompt = f"""Analyze this liquidity risk profile:
        {json.dumps(data, indent=2)}
        
        Provide a comprehensive liquidity risk assessment considering:
        1. Asset type and market characteristics
        2. Trading volume and market depth
        3. Market conditions and volatility
        4. Time horizon for liquidation
        5. Transaction costs and bid-ask spreads
        
        Provide a risk score (1-10, where 10 is highest risk) and assessment.
        Format as JSON with keys: score, assessment, key_factors, recommendations
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(liquidity_prompt).strip()
            
            # Parse LLM response
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    'score': min(10, max(1, analysis.get('score', 5))),
                    'factors': data,
                    'assessment': analysis.get('assessment', 'Medium Risk'),
                    'key_factors': analysis.get('key_factors', []),
                    'recommendations': analysis.get('recommendations', [])
                }
        except Exception as e:
            logger.error(f"Failed to assess liquidity risk: {e}")
        
        # Fallback assessment
        return {
            'score': 5,
            'factors': data,
            'assessment': 'Risk assessment unavailable',
            'message': 'LLM analysis required for detailed liquidity risk assessment'
        }
    
    def _assess_operational_risk(self, data: Dict) -> Dict:
        """Assess operational risk factors using LLM analysis"""
        operational_prompt = f"""Analyze this operational risk profile:
        {json.dumps(data, indent=2)}
        
        Provide a comprehensive operational risk assessment considering:
        1. Management quality and experience
        2. Regulatory compliance and governance
        3. Operational efficiency and processes
        4. Technology and systems risks
        5. Human capital and key person risks
        
        Provide a risk score (1-10, where 10 is highest risk) and assessment.
        Format as JSON with keys: score, assessment, key_factors, recommendations
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(operational_prompt).strip()
            
            # Parse LLM response
            import re
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    'score': min(10, max(1, analysis.get('score', 5))),
                    'factors': data,
                    'assessment': analysis.get('assessment', 'Medium Risk'),
                    'key_factors': analysis.get('key_factors', []),
                    'recommendations': analysis.get('recommendations', [])
                }
        except Exception as e:
            logger.error(f"Failed to assess operational risk: {e}")
        
        # Fallback assessment
        return {
            'score': 5,
            'factors': data,
            'assessment': 'Risk assessment unavailable',
            'message': 'LLM analysis required for detailed operational risk assessment'
        }
    
    def _assess_real_estate_risk(self, data: Dict) -> Dict:
        """Assess real estate specific risks"""
        location_quality = data.get('location_quality', 'B')
        occupancy_rate = float(data.get('occupancy_rate', 0.9))
        tenant_quality = data.get('tenant_quality', 'average')
        
        score = 5
        
        # Location impact
        location_scores = {'A': -2, 'B': 0, 'C': 2, 'D': 4}
        score += location_scores.get(location_quality, 0)
        
        # Occupancy impact
        if occupancy_rate < 0.8:
            score += 2
        elif occupancy_rate > 0.95:
            score -= 1
        
        # Tenant quality impact
        tenant_scores = {'excellent': -1, 'good': 0, 'average': 1, 'poor': 3}
        score += tenant_scores.get(tenant_quality, 0)
        
        return {
            'score': min(10, max(1, score)),
            'factors': {
                'location_quality': location_quality,
                'occupancy_rate': occupancy_rate,
                'tenant_quality': tenant_quality
            },
            'assessment': self._categorize_risk(score)
        }
    
    def _categorize_risk(self, score: float) -> str:
        """Categorize risk based on score"""
        if score <= 3:
            return "Low Risk"
        elif score <= 5:
            return "Moderate Risk"
        elif score <= 7:
            return "High Risk"
        else:
            return "Very High Risk"
    
    def _generate_mitigation_strategies(self, risk_factors: Dict) -> List[str]:
        """Generate risk mitigation strategies"""
        strategies = []
        
        for risk_type, assessment in risk_factors.items():
            if assessment['score'] > 6:
                if risk_type == 'market_risk':
                    strategies.append("Consider hedging strategies or diversification to reduce market exposure")
                elif risk_type == 'credit_risk':
                    strategies.append("Monitor credit quality closely and consider credit default swaps")
                elif risk_type == 'liquidity_risk':
                    strategies.append("Maintain adequate cash reserves and stagger investment maturities")
                elif risk_type == 'operational_risk':
                    strategies.append("Enhance due diligence on management teams and operational processes")
                elif risk_type == 'real_estate_risk':
                    strategies.append("Diversify across geographies and property types")
        
        return strategies
    
    def _perform_stress_test(self, data: Dict) -> Dict:
        """Perform stress testing on investment"""
        expected_return = float(data.get('expected_return', 0.08))
        volatility = float(data.get('volatility', 0.15))
        
        scenarios = {
            'mild_recession': {
                'return_impact': -0.15,
                'volatility_multiplier': 1.5
            },
            'severe_recession': {
                'return_impact': -0.30,
                'volatility_multiplier': 2.0
            },
            'market_crash': {
                'return_impact': -0.50,
                'volatility_multiplier': 3.0
            }
        }
        
        results = {}
        
        for scenario, params in scenarios.items():
            stressed_return = expected_return + params['return_impact']
            stressed_volatility = volatility * params['volatility_multiplier']
            
            results[scenario] = {
                'expected_return': float(stressed_return),
                'volatility': float(stressed_volatility),
                'var_95': float(-1.645 * stressed_volatility + stressed_return)
            }
        
        return results
    
    def _create_covariance_matrix(self, volatilities: np.ndarray, correlations: np.ndarray) -> np.ndarray:
        """Create covariance matrix from volatilities and correlations"""
        n = len(volatilities)
        cov_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if isinstance(correlations, np.ndarray) and correlations.shape == (n, n):
                    correlation = correlations[i, j]
                else:
                    correlation = 0.5 if i != j else 1.0
                
                cov_matrix[i, j] = volatilities[i] * volatilities[j] * correlation
        
        return cov_matrix
    
    def _prepare_optimization_constraints(self, n_assets: int, constraints: Dict) -> List:
        """Prepare constraints for portfolio optimization"""
        optimization_constraints = []
        
        # Weights sum to 1
        optimization_constraints.append({
            'type': 'eq',
            'fun': lambda x: np.sum(x) - 1
        })
        
        # Bounds for each asset
        min_weight = constraints.get('min_weight', 0)
        max_weight = constraints.get('max_weight', 1)
        bounds = tuple((min_weight, max_weight) for _ in range(n_assets))
        
        return optimization_constraints, bounds
    
    def _optimize_sharpe_ratio(self, returns: np.ndarray, cov_matrix: np.ndarray, constraints: Tuple) -> np.ndarray:
        """Optimize portfolio for maximum Sharpe ratio"""
        n_assets = len(returns)
        
        def neg_sharpe(weights):
            portfolio_return = np.dot(weights, returns)
            portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            return -(portfolio_return - 0.02) / portfolio_vol if portfolio_vol > 0 else 0
        
        optimization_constraints, bounds = constraints
        initial_guess = np.array([1/n_assets] * n_assets)
        
        result = optimize.minimize(
            neg_sharpe,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=optimization_constraints
        )
        
        return result.x if result.success else initial_guess
    
    def _optimize_min_variance(self, cov_matrix: np.ndarray, constraints: Tuple) -> np.ndarray:
        """Optimize portfolio for minimum variance"""
        n_assets = cov_matrix.shape[0]
        
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        optimization_constraints, bounds = constraints
        initial_guess = np.array([1/n_assets] * n_assets)
        
        result = optimize.minimize(
            portfolio_variance,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=optimization_constraints
        )
        
        return result.x if result.success else initial_guess
    
    def _optimize_target_return(self, returns: np.ndarray, cov_matrix: np.ndarray, 
                              target_return: float, constraints: Tuple) -> np.ndarray:
        """Optimize portfolio for target return with minimum variance"""
        n_assets = len(returns)
        
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        optimization_constraints, bounds = constraints
        
        # Add target return constraint
        optimization_constraints.append({
            'type': 'eq',
            'fun': lambda x: np.dot(x, returns) - target_return
        })
        
        initial_guess = np.array([1/n_assets] * n_assets)
        
        result = optimize.minimize(
            portfolio_variance,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=optimization_constraints
        )
        
        return result.x if result.success else initial_guess
    
    def _optimize_for_target_return(self, returns: np.ndarray, cov_matrix: np.ndarray, 
                                   target_return: float) -> Optional[np.ndarray]:
        """Optimize portfolio for specific target return"""
        n_assets = len(returns)
        
        # Check if target return is achievable
        if target_return > np.max(returns) or target_return < np.min(returns):
            return None
        
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
            {'type': 'eq', 'fun': lambda x: np.dot(x, returns) - target_return}
        ]
        
        bounds = tuple((0, 1) for _ in range(n_assets))
        initial_guess = np.array([1/n_assets] * n_assets)
        
        def portfolio_variance(weights):
            return np.dot(weights.T, np.dot(cov_matrix, weights))
        
        result = optimize.minimize(
            portfolio_variance,
            initial_guess,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        return result.x if result.success else None
    
    def _generate_implementation_plan(self, changes: Dict, portfolio_data: Dict) -> List[Dict]:
        """Generate step-by-step implementation plan"""
        plan = []
        
        # Sort changes by magnitude
        sorted_changes = sorted(
            changes.items(),
            key=lambda x: x[1]['amount'],
            reverse=True
        )
        
        for i, (asset, change) in enumerate(sorted_changes):
            step = {
                'step': i + 1,
                'action': f"{change['action'].capitalize()} {asset} allocation by {change['percentage_points']}",
                'timing': f"Week {i + 1}",
                'considerations': []
            }
            
            # Add specific considerations
            if change['amount'] > 0.1:  # Large change
                step['considerations'].append("Consider phased implementation to minimize market impact")
            
            if 'real_estate' in asset.lower():
                step['considerations'].append("Allow extra time for property transactions")
            
            plan.append(step)
        
        return plan
    
    def _perform_financial_analysis(self, opportunity: Dict) -> Dict:
        """Perform detailed financial analysis"""
        analysis = {}
        
        # Revenue analysis
        if 'revenue' in opportunity:
            revenue = float(opportunity['revenue'])
            revenue_growth = float(opportunity.get('revenue_growth', 0))
            
            analysis['revenue'] = {
                'current': revenue,
                'growth_rate': revenue_growth,
                'trend': 'positive' if revenue_growth > 5 else 'stable' if revenue_growth > 0 else 'negative'
            }
        
        # Profitability analysis
        if 'net_income' in opportunity:
            net_income = float(opportunity['net_income'])
            revenue = float(opportunity.get('revenue', 1))
            
            profit_margin = (net_income / revenue * 100) if revenue > 0 else 0
            analysis['profitability'] = {
                'net_income': net_income,
                'profit_margin': profit_margin,
                'assessment': 'strong' if profit_margin > 15 else 'moderate' if profit_margin > 5 else 'weak'
            }
        
        # Valuation metrics
        if 'price' in opportunity and 'earnings' in opportunity:
            price = float(opportunity['price'])
            earnings = float(opportunity['earnings'])
            
            pe_ratio = price / earnings if earnings > 0 else 0
            analysis['valuation'] = {
                'pe_ratio': pe_ratio,
                'assessment': 'undervalued' if pe_ratio < 15 else 'fair' if pe_ratio < 25 else 'overvalued'
            }
        
        return analysis
    
    def _perform_qualitative_assessment(self, opportunity: Dict) -> Dict:
        """Perform qualitative assessment of opportunity"""
        assessment = {
            'strengths': [],
            'weaknesses': [],
            'opportunities': [],
            'threats': []
        }
        
        # Market position
        market_position = opportunity.get('market_position', '').lower()
        if market_position in ['leader', 'dominant']:
            assessment['strengths'].append("Strong market position")
        elif market_position in ['challenger', 'niche']:
            assessment['weaknesses'].append("Limited market share")
        
        # Management quality
        if opportunity.get('management_quality', '').lower() in ['excellent', 'strong']:
            assessment['strengths'].append("High-quality management team")
        
        # Growth potential
        if float(opportunity.get('market_growth_rate', 0)) > 10:
            assessment['opportunities'].append("High market growth potential")
        
        # Competition
        if opportunity.get('competitive_intensity', '').lower() == 'high':
            assessment['threats'].append("Intense competitive pressure")
        
        return assessment
    
    def _analyze_risk_return_profile(self, opportunity: Dict) -> Dict:
        """Analyze risk-return characteristics"""
        expected_return = float(opportunity.get('expected_return', 0))
        risk_level = opportunity.get('risk_level', 'medium')
        
        profile = {
            'expected_return': expected_return,
            'risk_level': risk_level,
            'risk_adjusted_return': expected_return / (2 if risk_level == 'low' else 3 if risk_level == 'medium' else 5),
            'suitable_for': []
        }
        
        # Determine suitability
        if risk_level == 'low' and expected_return > 5:
            profile['suitable_for'].append("Conservative investors")
        if risk_level == 'medium' and expected_return > 10:
            profile['suitable_for'].append("Balanced investors")
        if risk_level == 'high' and expected_return > 15:
            profile['suitable_for'].append("Aggressive investors")
        
        return profile
    
    def _score_financial_metrics(self, analysis: Dict) -> float:
        """Score financial metrics using LLM analysis (0-10)"""
        scoring_prompt = f"""Analyze these financial metrics and provide a score from 0-10:
        {json.dumps(analysis, indent=2)}
        
        Consider:
        1. Revenue trends and growth patterns
        2. Profitability margins and sustainability
        3. Valuation metrics and market comparison
        4. Cash flow generation and quality
        5. Financial stability and leverage
        
        Provide only a numerical score (0-10) where:
        - 0-3: Poor financial condition
        - 4-6: Average financial health
        - 7-10: Strong financial performance
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(scoring_prompt).strip()
            
            # Extract numerical score
            import re
            score_match = re.search(r'([0-9](?:\.[0-9])?)', result)
            if score_match:
                score = float(score_match.group(1))
                return min(10, max(0, score))
        except Exception as e:
            logger.error(f"Failed to score financial metrics: {e}")
        
        return 5.0  # Fallback to neutral score
    
    def _score_qualitative_factors(self, assessment: Dict) -> float:
        """Score qualitative factors using LLM analysis (0-10)"""
        scoring_prompt = f"""Analyze these qualitative factors and provide a score from 0-10:
        {json.dumps(assessment, indent=2)}
        
        Consider the balance of:
        1. Strengths vs Weaknesses
        2. Opportunities vs Threats
        3. Management quality and experience
        4. Competitive positioning
        5. Industry outlook and trends
        
        Provide only a numerical score (0-10) where:
        - 0-3: Significant qualitative concerns
        - 4-6: Balanced qualitative profile
        - 7-10: Strong qualitative advantages
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(scoring_prompt).strip()
            
            # Extract numerical score
            import re
            score_match = re.search(r'([0-9](?:\.[0-9])?)', result)
            if score_match:
                score = float(score_match.group(1))
                return min(10, max(0, score))
        except Exception as e:
            logger.error(f"Failed to score qualitative factors: {e}")
        
        return 5.0  # Fallback to neutral score
    
    def _score_risk_return(self, profile: Dict) -> float:
        """Score risk-return profile using LLM analysis (0-10)"""
        scoring_prompt = f"""Analyze this risk-return profile and provide a score from 0-10:
        {json.dumps(profile, indent=2)}
        
        Consider:
        1. Risk-adjusted return metrics (Sharpe ratio, etc.)
        2. Volatility relative to expected returns
        3. Downside protection characteristics
        4. Return consistency and reliability
        5. Risk concentration and diversification
        
        Provide only a numerical score (0-10) where:
        - 0-3: Poor risk-adjusted returns
        - 4-6: Adequate risk-return profile
        - 7-10: Excellent risk-adjusted returns
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(scoring_prompt).strip()
            
            # Extract numerical score
            import re
            score_match = re.search(r'([0-9](?:\.[0-9])?)', result)
            if score_match:
                score = float(score_match.group(1))
                return min(10, max(0, score))
        except Exception as e:
            logger.error(f"Failed to score risk-return profile: {e}")
        
        return 5.0  # Fallback to neutral score
    
    def _determine_recommendation_action(self, score: float) -> str:
        """Determine investment recommendation using LLM analysis"""
        recommendation_prompt = f"""Based on this overall investment score of {score:.1f} out of 10, provide a clear investment recommendation.
        
        Consider:
        1. Score represents comprehensive analysis of financials, qualitative factors, and risk-return
        2. Current market conditions and investment environment
        3. Appropriate risk management principles
        4. Professional investment standards
        
        Provide one of these recommendations: Strong Buy, Buy, Hold, Reduce, or Avoid
        Include a brief rationale (1-2 sentences).
        """
        
        try:
            from strands.models.bedrock import BedrockModel
            model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0")
            result = model.generate(recommendation_prompt).strip()
            
            # Extract recommendation
            recommendations = ["Strong Buy", "Buy", "Hold", "Reduce", "Avoid"]
            for rec in recommendations:
                if rec in result:
                    return rec
        except Exception as e:
            logger.error(f"Failed to determine recommendation: {e}")
        
        # Fallback to threshold-based recommendation
        if score >= 7:
            return "Strong Buy"
        elif score >= 6:
            return "Buy"
        elif score >= 5:
            return "Hold"
        elif score >= 4:
            return "Reduce"
        else:
            return "Avoid"
    
    def _determine_confidence_level(self, scores: Dict) -> str:
        """Determine confidence level based on score consistency"""
        score_values = list(scores.values())
        std_dev = np.std(score_values)
        
        if std_dev < 1:
            return "High"
        elif std_dev < 2:
            return "Medium"
        else:
            return "Low"
    
    def _generate_recommendation_rationale(self, evaluation: Dict, scores: Dict) -> str:
        """Generate rationale for recommendation"""
        rationales = []
        
        # Financial rationale
        if scores.get('financial', 0) > 7:
            rationales.append("Strong financial metrics support investment")
        elif scores.get('financial', 0) < 4:
            rationales.append("Weak financials raise concerns")
        
        # Risk-return rationale
        if scores.get('risk_return', 0) > 7:
            rationales.append("Attractive risk-adjusted returns")
        
        # Qualitative rationale
        if scores.get('qualitative', 0) > 7:
            rationales.append("Favorable qualitative factors")
        
        return ". ".join(rationales) if rationales else "Mixed signals require careful consideration"
    
    def _generate_due_diligence_checklist(self, opportunity: Dict) -> List[str]:
        """Generate due diligence checklist"""
        checklist = [
            "Verify all financial statements and projections",
            "Conduct management team background checks",
            "Review legal documents and contracts",
            "Assess regulatory compliance status",
            "Analyze competitive landscape",
            "Evaluate technology and intellectual property",
            "Review customer concentration and retention",
            "Examine supply chain and vendor relationships",
            "Assess environmental and social governance (ESG) factors",
            "Obtain independent valuation if needed"
        ]
        
        # Add specific items based on opportunity type
        if opportunity.get('asset_type', '').lower() == 'real_estate':
            checklist.extend([
                "Conduct property inspection and environmental assessment",
                "Review tenant leases and occupancy history",
                "Verify zoning and land use compliance",
                "Assess property management quality"
            ])
        
        return checklist
    
    def _calculate_max_drawdown_simulation(self, portfolio_values: np.ndarray) -> float:
        """Calculate maximum drawdown from simulation"""
        max_drawdowns = []
        
        for simulation in portfolio_values:
            cumulative_max = np.maximum.accumulate(simulation)
            drawdowns = (simulation - cumulative_max) / cumulative_max
            max_drawdowns.append(np.min(drawdowns))
        
        return float(np.mean(max_drawdowns) * 100)
    
    def _generate_monte_carlo_insights(self, results: Dict) -> List[str]:
        """Generate insights from Monte Carlo simulation"""
        insights = []
        
        # Probability insights
        prob_gain = results['probability_analysis']['prob_gain']
        if prob_gain > 0.9:
            insights.append(f"High probability ({prob_gain:.1%}) of positive returns")
        elif prob_gain < 0.7:
            insights.append(f"Significant risk of loss ({1-prob_gain:.1%})")
        
        # Risk insights
        var_95 = results['risk_metrics']['var_95']
        if var_95 < -0.2 * results['simulation_parameters']['initial_investment']:
            insights.append("Substantial downside risk - consider risk mitigation")
        
        # Return insights
        median_return = (results['percentiles']['50th'] / results['simulation_parameters']['initial_investment'] - 1) * 100
        insights.append(f"Median expected return: {median_return:.1f}%")
        
        return insights
    
    def _interpret_cap_rate(self, cap_rate: float) -> str:
        """Interpret cap rate for real estate"""
        if cap_rate < 4:
            return "Low cap rate - Premium property in prime location"
        elif cap_rate < 6:
            return "Moderate cap rate - Good location with stable returns"
        elif cap_rate < 8:
            return "Average cap rate - Standard market returns"
        elif cap_rate < 10:
            return "Above average cap rate - Higher risk/return profile"
        else:
            return "High cap rate - Value-add opportunity or higher risk"
    
    def _interpret_grm(self, grm: float) -> str:
        """Interpret gross rent multiplier"""
        if grm < 5:
            return "Excellent income relative to price"
        elif grm < 8:
            return "Good income generation"
        elif grm < 12:
            return "Average market standard"
        else:
            return "High price relative to income"
    
    def _interpret_coc_return(self, coc: float) -> str:
        """Interpret cash-on-cash return"""
        if coc < 6:
            return "Below average returns"
        elif coc < 10:
            return "Average returns"
        elif coc < 15:
            return "Good returns"
        else:
            return "Excellent returns"
    
    def _interpret_dscr(self, dscr: float) -> str:
        """Interpret debt service coverage ratio"""
        if dscr < 1.0:
            return "Insufficient income to cover debt - High risk"
        elif dscr < 1.25:
            return "Minimal coverage - Moderate risk"
        elif dscr < 1.5:
            return "Adequate coverage - Acceptable risk"
        else:
            return "Strong coverage - Low risk"
    
    def _analyze_real_estate_market(self, property_data: Dict) -> Dict:
        """Analyze real estate market conditions"""
        return {
            'market_phase': property_data.get('market_phase', 'expansion'),
            'supply_demand': property_data.get('supply_demand_balance', 'balanced'),
            'rent_growth_trend': property_data.get('rent_growth_trend', 'stable'),
            'vacancy_trend': property_data.get('vacancy_trend', 'stable'),
            'market_outlook': self._determine_market_outlook(property_data)
        }
    
    def _determine_market_outlook(self, data: Dict) -> str:
        """Determine market outlook"""
        positive_factors = 0
        
        if data.get('rent_growth_trend', '') == 'increasing':
            positive_factors += 1
        if data.get('vacancy_trend', '') == 'decreasing':
            positive_factors += 1
        if data.get('market_phase', '') in ['recovery', 'expansion']:
            positive_factors += 1
        
        if positive_factors >= 2:
            return "Positive - Strong fundamentals"
        elif positive_factors == 1:
            return "Neutral - Mixed signals"
        else:
            return "Cautious - Headwinds present"
    
    def _project_real_estate_cash_flows(self, property_data: Dict) -> Dict:
        """Project real estate cash flows"""
        initial_noi = float(property_data.get('net_operating_income', 0))
        growth_rate = float(property_data.get('noi_growth_rate', 0.03))
        years = 10
        
        projections = []
        for year in range(1, years + 1):
            noi = initial_noi * (1 + growth_rate) ** year
            projections.append({
                'year': year,
                'noi': float(noi),
                'cash_flow': float(noi * 0.7)  # Assuming 30% for debt service
            })
        
        return {
            'projection_period': years,
            'annual_projections': projections,
            'total_cash_flow': sum(p['cash_flow'] for p in projections)
        }
    
    def _calculate_real_estate_returns(self, property_data: Dict, cash_flows: Dict) -> Dict:
        """Calculate real estate investment returns"""
        purchase_price = float(property_data.get('purchase_price', 0))
        exit_cap_rate = float(property_data.get('exit_cap_rate', 0.07))
        
        # Calculate exit value
        final_noi = cash_flows['annual_projections'][-1]['noi']
        exit_value = final_noi / exit_cap_rate if exit_cap_rate > 0 else 0
        
        # Calculate IRR (simplified)
        cash_flow_series = [-purchase_price]
        cash_flow_series.extend([p['cash_flow'] for p in cash_flows['annual_projections'][:-1]])
        cash_flow_series.append(cash_flows['annual_projections'][-1]['cash_flow'] + exit_value)
        
        try:
            irr = np.irr(cash_flow_series) * 100
        except:
            irr = 0
        
        return {
            'projected_exit_value': float(exit_value),
            'total_return': float(exit_value + cash_flows['total_cash_flow'] - purchase_price),
            'irr': float(irr),
            'multiple_on_invested_capital': float((exit_value + cash_flows['total_cash_flow']) / purchase_price) if purchase_price > 0 else 0
        }
    
    def _assess_real_estate_risks_opportunities(self, property_data: Dict, 
                                              financial_metrics: Dict, 
                                              market_analysis: Dict) -> Dict:
        """Assess risks and opportunities for real estate"""
        risks = []
        opportunities = []
        
        # Risk assessment
        if financial_metrics.get('dscr', {}).get('value', 1.5) < 1.25:
            risks.append("Low debt service coverage ratio")
        if market_analysis.get('vacancy_trend') == 'increasing':
            risks.append("Rising vacancy rates in market")
        if property_data.get('property_age', 0) > 20:
            risks.append("Aging property may require significant CapEx")
        
        # Opportunity assessment
        if financial_metrics.get('cap_rate', {}).get('value', 0) > 8:
            opportunities.append("High cap rate suggests value-add potential")
        if market_analysis.get('rent_growth_trend') == 'increasing':
            opportunities.append("Strong rent growth environment")
        if property_data.get('renovation_potential', False):
            opportunities.append("Renovation opportunity to increase rents")
        
        return {
            'risks': risks,
            'opportunities': opportunities,
            'risk_mitigation_suggestions': self._generate_risk_mitigation_suggestions(risks),
            'opportunity_capture_strategies': self._generate_opportunity_strategies(opportunities)
        }
    
    def _generate_risk_mitigation_suggestions(self, risks: List[str]) -> List[str]:
        """Generate risk mitigation suggestions"""
        suggestions = []
        
        for risk in risks:
            if 'debt service' in risk.lower():
                suggestions.append("Consider refinancing or negotiating better loan terms")
            elif 'vacancy' in risk.lower():
                suggestions.append("Implement aggressive leasing strategies and tenant retention programs")
            elif 'capex' in risk.lower():
                suggestions.append("Conduct detailed property condition assessment and budget for upgrades")
        
        return suggestions
    
    def _generate_opportunity_strategies(self, opportunities: List[str]) -> List[str]:
        """Generate strategies to capture opportunities"""
        strategies = []
        
        for opportunity in opportunities:
            if 'value-add' in opportunity.lower():
                strategies.append("Develop comprehensive value-add business plan")
            elif 'rent growth' in opportunity.lower():
                strategies.append("Implement strategic rent increases at lease renewals")
            elif 'renovation' in opportunity.lower():
                strategies.append("Create phased renovation plan to minimize disruption")
        
        return strategies
    
    def _assess_current_portfolio(self, portfolio_data: Dict) -> Dict:
        """Assess current portfolio status"""
        holdings = portfolio_data.get('holdings', [])
        total_value = sum(h.get('value', 0) for h in holdings)
        
        assessment = {
            'total_value': total_value,
            'number_of_holdings': len(holdings),
            'diversification_score': self._calculate_diversification_score(holdings),
            'risk_profile': self._determine_portfolio_risk_profile(holdings),
            'performance_vs_benchmark': portfolio_data.get('performance_vs_benchmark', 0),
            'rebalancing_needed': False
        }
        
        # Check if rebalancing needed
        if assessment['diversification_score'] < 0.7:
            assessment['rebalancing_needed'] = True
        
        return assessment
    
    def _calculate_diversification_score(self, holdings: List[Dict]) -> float:
        """Calculate portfolio diversification score (0-1)"""
        if not holdings:
            return 0
        
        # Simple diversification based on number of holdings and concentration
        n_holdings = len(holdings)
        total_value = sum(h.get('value', 0) for h in holdings)
        
        if total_value == 0:
            return 0
        
        # Calculate Herfindahl index
        concentration = sum((h.get('value', 0) / total_value) ** 2 for h in holdings)
        
        # Diversification score (inverse of concentration)
        return 1 - concentration
    
    def _determine_portfolio_risk_profile(self, holdings: List[Dict]) -> str:
        """Determine overall portfolio risk profile"""
        if not holdings:
            return "Unknown"
        
        risk_scores = []
        for holding in holdings:
            asset_type = holding.get('asset_type', '').lower()
            if asset_type in ['stocks', 'equity']:
                risk_scores.append(7)
            elif asset_type in ['bonds', 'fixed_income']:
                risk_scores.append(3)
            elif asset_type == 'real_estate':
                risk_scores.append(5)
            elif asset_type == 'cash':
                risk_scores.append(1)
            else:
                risk_scores.append(5)
        
        avg_risk = np.mean(risk_scores)
        
        if avg_risk < 3:
            return "Conservative"
        elif avg_risk < 5:
            return "Moderate"
        elif avg_risk < 7:
            return "Aggressive"
        else:
            return "Very Aggressive"
    
    def _generate_strategic_recommendations(self, portfolio_data: Dict, assessment: Dict) -> List[str]:
        """Generate long-term strategic recommendations"""
        recommendations = []
        
        # Based on risk profile
        risk_profile = assessment.get('risk_profile', 'Moderate')
        age = portfolio_data.get('investor_age', 40)
        
        if age > 60 and risk_profile in ['Aggressive', 'Very Aggressive']:
            recommendations.append("Consider reducing equity allocation given age and risk profile")
        
        # Based on diversification
        if assessment.get('diversification_score', 0) < 0.7:
            recommendations.append("Increase diversification across asset classes and geographies")
        
        # Based on performance
        if assessment.get('performance_vs_benchmark', 0) < -5:
            recommendations.append("Review underperforming holdings and consider index strategies")
        
        return recommendations
    
    def _generate_tactical_recommendations(self, portfolio_data: Dict, assessment: Dict) -> List[str]:
        """Generate short-term tactical recommendations"""
        recommendations = []
        
        # Market timing considerations
        market_conditions = portfolio_data.get('market_conditions', {})
        
        if market_conditions.get('volatility', 'normal') == 'high':
            recommendations.append("Consider defensive positioning or hedging strategies")
        
        if market_conditions.get('interest_rates', 'stable') == 'rising':
            recommendations.append("Reduce duration in fixed income holdings")
        
        # Sector rotation
        if market_conditions.get('economic_phase', 'expansion') == 'late_cycle':
            recommendations.append("Rotate into defensive sectors and quality assets")
        
        return recommendations
    
    def _create_rebalancing_plan(self, portfolio_data: Dict) -> Dict:
        """Create detailed rebalancing plan"""
        current_allocation = {}
        target_allocation = portfolio_data.get('target_allocation', {})
        
        # Calculate current allocation
        holdings = portfolio_data.get('holdings', [])
        total_value = sum(h.get('value', 0) for h in holdings)
        
        for holding in holdings:
            asset_type = holding.get('asset_type', 'Other')
            value = holding.get('value', 0)
            current_allocation[asset_type] = current_allocation.get(asset_type, 0) + value / total_value * 100
        
        # Calculate required trades
        trades = []
        for asset_type, target_pct in target_allocation.items():
            current_pct = current_allocation.get(asset_type, 0)
            diff = target_pct - current_pct
            
            if abs(diff) > 2:  # Only rebalance if difference > 2%
                trades.append({
                    'asset_type': asset_type,
                    'action': 'buy' if diff > 0 else 'sell',
                    'percentage_points': abs(diff),
                    'dollar_amount': abs(diff) * total_value / 100
                })
        
        return {
            'current_allocation': current_allocation,
            'target_allocation': target_allocation,
            'required_trades': trades,
            'estimated_cost': sum(t['dollar_amount'] * 0.001 for t in trades)  # 0.1% transaction cost
        }
    
    def _generate_investment_ideas(self, portfolio_data: Dict) -> List[Dict]:
        """Generate new investment ideas based on portfolio gaps"""
        ideas = []
        
        current_allocation = self._calculate_current_allocation(portfolio_data)
        risk_tolerance = portfolio_data.get('risk_tolerance', 'moderate')
        
        # Check for allocation gaps
        if current_allocation.get('real_estate', 0) < 10:
            ideas.append({
                'asset_class': 'Real Estate',
                'recommendation': 'REITs or direct property investment',
                'rationale': 'Increase real estate exposure for diversification and inflation protection'
            })
        
        if current_allocation.get('international', 0) < 20:
            ideas.append({
                'asset_class': 'International Equity',
                'recommendation': 'Developed and emerging market funds',
                'rationale': 'Geographic diversification to reduce home bias'
            })
        
        if risk_tolerance == 'conservative' and current_allocation.get('bonds', 0) < 40:
            ideas.append({
                'asset_class': 'Fixed Income',
                'recommendation': 'Investment grade corporate bonds',
                'rationale': 'Increase income stability and reduce portfolio volatility'
            })
        
        return ideas
    
    def _calculate_current_allocation(self, portfolio_data: Dict) -> Dict:
        """Calculate current asset allocation"""
        allocation = {}
        holdings = portfolio_data.get('holdings', [])
        total_value = sum(h.get('value', 0) for h in holdings)
        
        if total_value == 0:
            return allocation
        
        for holding in holdings:
            asset_type = holding.get('asset_type', 'Other')
            value = holding.get('value', 0)
            allocation[asset_type] = allocation.get(asset_type, 0) + value / total_value * 100
        
        return allocation
    
    def _create_action_plan(self, recommendations: Dict) -> List[Dict]:
        """Create prioritized action plan"""
        action_plan = []
        priority = 1
        
        # High priority: Rebalancing if needed
        if recommendations.get('rebalancing_plan', {}).get('required_trades'):
            action_plan.append({
                'priority': priority,
                'action': 'Execute portfolio rebalancing',
                'timeline': 'Within 2 weeks',
                'details': recommendations['rebalancing_plan']
            })
            priority += 1
        
        # Medium priority: Strategic recommendations
        for rec in recommendations.get('strategic_recommendations', []):
            action_plan.append({
                'priority': priority,
                'action': rec,
                'timeline': 'Within 3 months',
                'details': 'Long-term portfolio adjustment'
            })
            priority += 1
        
        # Low priority: New investments
        for idea in recommendations.get('new_investment_ideas', []):
            action_plan.append({
                'priority': priority,
                'action': f"Research {idea['asset_class']} investments",
                'timeline': 'Within 6 months',
                'details': idea
            })
            priority += 1
        
        return action_plan
    
    def _generate_executive_summary(self, portfolio_data: Dict) -> Dict:
        """Generate executive summary for report"""
        return {
            'portfolio_value': portfolio_data.get('total_value', 0),
            'ytd_performance': portfolio_data.get('ytd_return', 0),
            'risk_level': portfolio_data.get('risk_profile', 'Moderate'),
            'key_highlights': [
                f"Portfolio value: ${portfolio_data.get('total_value', 0):,.0f}",
                f"YTD return: {portfolio_data.get('ytd_return', 0):.1f}%",
                f"Current risk profile: {portfolio_data.get('risk_profile', 'Moderate')}"
            ]
        }
    
    def _analyze_portfolio_performance(self, portfolio_data: Dict) -> Dict:
        """Analyze portfolio performance metrics"""
        return {
            'absolute_return': portfolio_data.get('absolute_return', 0),
            'benchmark_return': portfolio_data.get('benchmark_return', 0),
            'alpha': portfolio_data.get('absolute_return', 0) - portfolio_data.get('benchmark_return', 0),
            'volatility': portfolio_data.get('volatility', 0),
            'sharpe_ratio': portfolio_data.get('sharpe_ratio', 0),
            'max_drawdown': portfolio_data.get('max_drawdown', 0)
        }
    
    def _generate_market_commentary(self, report_params: Dict) -> Dict:
        """Generate market commentary section"""
        return {
            'economic_overview': "Current economic conditions show mixed signals with moderate growth",
            'market_trends': [
                "Equity markets showing resilience despite rate concerns",
                "Real estate markets adjusting to new interest rate environment",
                "Fixed income offering attractive yields after recent adjustments"
            ],
            'outlook': "Cautiously optimistic with focus on quality assets"
        }
    
    def _generate_risk_analysis(self, portfolio_data: Dict) -> Dict:
        """Generate risk analysis for report"""
        return {
            'current_risk_metrics': {
                'portfolio_volatility': portfolio_data.get('volatility', 0),
                'var_95': portfolio_data.get('var_95', 0),
                'beta': portfolio_data.get('beta', 1.0)
            },
            'risk_contributors': self._identify_risk_contributors(portfolio_data),
            'risk_mitigation': "Diversification across asset classes and regular rebalancing"
        }
    
    def _identify_risk_contributors(self, portfolio_data: Dict) -> List[str]:
        """Identify main risk contributors"""
        contributors = []
        
        holdings = portfolio_data.get('holdings', [])
        for holding in holdings:
            if holding.get('weight', 0) > 0.2:  # More than 20%
                contributors.append(f"High concentration in {holding.get('name', 'Unknown')}")
        
        return contributors
    
    def _generate_report_recommendations(self, portfolio_data: Dict, 
                                       performance: Dict, 
                                       risk_analysis: Dict) -> Dict:
        """Generate recommendations for report"""
        return {
            'immediate_actions': [
                "Review and rebalance portfolio allocations",
                "Consider tax-loss harvesting opportunities"
            ],
            'strategic_considerations': [
                "Evaluate alternative investments for diversification",
                "Review estate planning and tax strategies"
            ],
            'monitoring_points': [
                "Track Federal Reserve policy changes",
                "Monitor inflation indicators",
                "Watch for market volatility spikes"
            ]
        }
    
    def _generate_glossary(self) -> Dict[str, str]:
        """Generate glossary of terms"""
        return {
            'Cap Rate': 'Net Operating Income divided by property value',
            'DSCR': 'Debt Service Coverage Ratio - NOI divided by debt payments',
            'IRR': 'Internal Rate of Return - annualized return considering cash flows',
            'Sharpe Ratio': 'Risk-adjusted return metric',
            'VaR': 'Value at Risk - potential loss at confidence level'
        }

# Create singleton instance
investment_advisory_agent_v2 = EnhancedInvestmentAdvisoryAgent()
investment_advisory_agent = investment_advisory_agent_v2  # Backward compatibility alias
investment_advisor_agent = investment_advisory_agent_v2  # Alternative alias

# AgentCore handler
def agentcore_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    """AgentCore entry point"""
    return investment_advisory_agent_v2.agentcore_handler(event)

# For local testing
if __name__ == "__main__":
    import asyncio
    
    test_event = {
        'input': 'Analyze a $10M real estate investment with 7% cap rate and recommend portfolio allocation',
        'sessionId': 'test-advisory-v2-001'
    }
    
    result = agentcore_handler(test_event)
    print(json.dumps(result, indent=2))