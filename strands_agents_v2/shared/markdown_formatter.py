"""
Markdown Formatter with Chart Support
Converts financial data into markdown strings with embedded chart blocks for frontend rendering
"""

import json
from typing import Dict, Any, List, Union


class MarkdownChartFormatter:
    """Helper class to format financial data as markdown with chart blocks"""

    @staticmethod
    def format_chart(chart_type: str, data: List[Dict[str, Any]], title: str = "") -> str:
        """
        Format data as a chart block for markdown

        Args:
            chart_type: 'bar', 'pie', or 'line'
            data: List of dictionaries with 'name' and 'value' keys
            title: Optional chart title

        Returns:
            Markdown string with embedded chart block
        """
        chart_data = {
            "title": title,
            "data": data
        }

        return f"""```chart:{chart_type}
{json.dumps(chart_data, indent=2)}
```"""

    @staticmethod
    def format_bar_chart(data: List[Dict[str, Any]], title: str = "") -> str:
        """Format data as a bar chart"""
        return MarkdownChartFormatter.format_chart('bar', data, title)

    @staticmethod
    def format_pie_chart(data: List[Dict[str, Any]], title: str = "") -> str:
        """Format data as a pie chart"""
        return MarkdownChartFormatter.format_chart('pie', data, title)

    @staticmethod
    def format_line_chart(data: List[Dict[str, Any]], title: str = "") -> str:
        """Format data as a line chart"""
        return MarkdownChartFormatter.format_chart('line', data, title)

    @staticmethod
    def format_financial_metrics(metrics: Dict[str, Any], title: str = "Financial Metrics") -> str:
        """
        Format financial metrics as markdown with appropriate charts

        Args:
            metrics: Dictionary of financial metrics
            title: Section title

        Returns:
            Formatted markdown string
        """
        md = f"## {title}\n\n"

        # Extract real estate metrics if available
        if 'real_estate_metrics' in metrics:
            re_metrics = metrics['real_estate_metrics']
            md += "### Real Estate Metrics\n\n"

            # Create bar chart data
            chart_data = []
            for metric_name, metric_value in re_metrics.items():
                if isinstance(metric_value, dict) and 'value' in metric_value:
                    chart_data.append({
                        'name': metric_name.replace('_', ' ').title(),
                        'value': round(metric_value['value'], 2)
                    })

            if chart_data:
                md += MarkdownChartFormatter.format_bar_chart(chart_data, "Key Real Estate Metrics")
                md += "\n\n"

            # Add detailed metrics table
            md += "| Metric | Value | Interpretation |\n"
            md += "|--------|-------|----------------|\n"

            for metric_name, metric_value in re_metrics.items():
                if isinstance(metric_value, dict):
                    formatted = metric_value.get('formatted', str(metric_value.get('value', 'N/A')))
                    interpretation = metric_value.get('interpretation', '')
                    metric_display = metric_name.replace('_', ' ').title()
                    md += f"| **{metric_display}** | {formatted} | {interpretation} |\n"

            md += "\n"

        # Add insights if available
        if 'insights' in metrics and metrics['insights']:
            md += "### Key Insights\n\n"
            for insight in metrics['insights']:
                md += f"- {insight}\n"
            md += "\n"

        return md

    @staticmethod
    def format_market_trends(trend_data: Dict[str, Any]) -> str:
        """
        Format market trend analysis as markdown with charts

        Args:
            trend_data: Trend analysis results

        Returns:
            Formatted markdown string
        """
        md = "## Market Trend Analysis\n\n"

        # Statistical Summary
        if 'statistical_summary' in trend_data:
            stats = trend_data['statistical_summary']
            md += "### Statistical Summary\n\n"
            md += f"- **Mean**: ${stats.get('mean', 0):,.2f}\n"
            md += f"- **Median**: ${stats.get('median', 0):,.2f}\n"
            md += f"- **Std Dev**: ${stats.get('std_dev', 0):,.2f}\n"
            md += f"- **Range**: ${stats.get('min', 0):,.2f} - ${stats.get('max', 0):,.2f}\n\n"

        # Trend Analysis
        if 'trend_analysis' in trend_data:
            trend = trend_data['trend_analysis']
            md += "### Trend Analysis\n\n"
            md += f"- **Direction**: {trend.get('direction', 'N/A').title()}\n"
            md += f"- **Trend Strength**: {trend.get('trend_strength', 'N/A')}\n"
            md += f"- **Percentage Change**: {trend.get('percentage_change', 0):.2f}%\n"
            md += f"- **R²**: {trend.get('r_squared', 0):.3f}\n\n"

        # Predictions with line chart
        if 'predictions' in trend_data and 'next_values' in trend_data['predictions']:
            predictions = trend_data['predictions']['next_values']
            chart_data = [
                {'name': f'Period {i+1}', 'value': round(val, 2)}
                for i, val in enumerate(predictions)
            ]

            md += "### Future Projections\n\n"
            md += MarkdownChartFormatter.format_line_chart(chart_data, "Predicted Values")
            md += "\n\n"

        return md

    @staticmethod
    def format_portfolio_allocation(allocation: Dict[str, Any]) -> str:
        """
        Format portfolio allocation as markdown with pie chart

        Args:
            allocation: Portfolio allocation data

        Returns:
            Formatted markdown string
        """
        md = "## Portfolio Allocation\n\n"

        if 'optimal_allocation' in allocation:
            # Create pie chart data
            chart_data = [
                {'name': asset_name, 'value': round(asset_data['weight'] * 100, 1)}
                for asset_name, asset_data in allocation['optimal_allocation'].items()
            ]

            md += MarkdownChartFormatter.format_pie_chart(chart_data, "Optimal Portfolio Allocation")
            md += "\n\n"

            # Portfolio metrics
            if 'portfolio_metrics' in allocation:
                metrics = allocation['portfolio_metrics']
                md += "### Portfolio Metrics\n\n"
                md += f"- **Expected Return**: {metrics.get('expected_return', 0):.2%}\n"
                md += f"- **Volatility**: {metrics.get('volatility', 0):.2%}\n"
                md += f"- **Sharpe Ratio**: {metrics.get('sharpe_ratio', 0):.2f}\n"
                md += f"- **VaR (95%)**: {metrics.get('var_95', 0):.2%}\n\n"

            # Allocation changes
            if 'allocation_changes' in allocation and allocation['allocation_changes']:
                md += "### Required Changes\n\n"
                md += "| Asset | Action | Amount |\n"
                md += "|-------|--------|--------|\n"

                for asset_name, change in allocation['allocation_changes'].items():
                    action = change['action'].title()
                    amount = change['percentage_points']
                    md += f"| {asset_name} | {action} | {amount} |\n"

                md += "\n"

        return md

    @staticmethod
    def format_risk_assessment(risk_data: Dict[str, Any]) -> str:
        """
        Format risk assessment as markdown with charts

        Args:
            risk_data: Risk assessment results

        Returns:
            Formatted markdown string
        """
        md = "## Risk Assessment\n\n"

        # Composite risk score
        if 'composite_risk_score' in risk_data:
            score = risk_data['composite_risk_score']
            rating = risk_data.get('risk_rating', 'Unknown')
            md += f"### Overall Risk: **{rating}**\n"
            md += f"**Risk Score**: {score:.1f}/10\n\n"

        # Risk factors chart
        if 'risk_factors' in risk_data:
            chart_data = []
            for factor_name, factor_data in risk_data['risk_factors'].items():
                if isinstance(factor_data, dict) and 'score' in factor_data:
                    chart_data.append({
                        'name': factor_name.replace('_', ' ').title(),
                        'value': factor_data['score']
                    })

            if chart_data:
                md += MarkdownChartFormatter.format_bar_chart(chart_data, "Risk Factor Scores")
                md += "\n\n"

            # Detailed risk factors
            md += "### Risk Factors\n\n"
            for factor_name, factor_data in risk_data['risk_factors'].items():
                if isinstance(factor_data, dict):
                    md += f"**{factor_name.replace('_', ' ').title()}** "
                    md += f"(Score: {factor_data.get('score', 'N/A')}/10)\n"
                    md += f"- {factor_data.get('assessment', 'No assessment available')}\n\n"

        # Mitigation strategies
        if 'mitigation_strategies' in risk_data and risk_data['mitigation_strategies']:
            md += "### Risk Mitigation Strategies\n\n"
            for strategy in risk_data['mitigation_strategies']:
                md += f"- {strategy}\n"
            md += "\n"

        return md

    @staticmethod
    def format_monte_carlo_results(results: Dict[str, Any]) -> str:
        """
        Format Monte Carlo simulation results as markdown with charts

        Args:
            results: Monte Carlo simulation results

        Returns:
            Formatted markdown string
        """
        md = "## Monte Carlo Simulation Results\n\n"

        # Simulation parameters
        if 'simulation_parameters' in results:
            params = results['simulation_parameters']
            md += "### Simulation Parameters\n\n"
            md += f"- **Initial Investment**: ${params.get('initial_investment', 0):,.0f}\n"
            md += f"- **Expected Return**: {params.get('expected_return', 'N/A')}\n"
            md += f"- **Volatility**: {params.get('volatility', 'N/A')}\n"
            md += f"- **Time Horizon**: {params.get('time_horizon', 'N/A')} years\n"
            md += f"- **Simulations**: {params.get('simulations', 'N/A'):,}\n\n"

        # Results distribution (percentiles as bar chart)
        if 'percentiles' in results:
            percentiles = results['percentiles']
            chart_data = [
                {'name': '5th', 'value': round(percentiles['5th'], 0)},
                {'name': '25th', 'value': round(percentiles['25th'], 0)},
                {'name': '50th', 'value': round(percentiles['50th'], 0)},
                {'name': '75th', 'value': round(percentiles['75th'], 0)},
                {'name': '95th', 'value': round(percentiles['95th'], 0)}
            ]

            md += "### Portfolio Value Distribution\n\n"
            md += MarkdownChartFormatter.format_bar_chart(chart_data, "Final Portfolio Value by Percentile")
            md += "\n\n"

        # Probability analysis
        if 'probability_analysis' in results:
            prob = results['probability_analysis']
            md += "### Probability Analysis\n\n"
            md += f"- **Probability of Gain**: {prob.get('prob_gain', 0):.1%}\n"
            md += f"- **Probability of Doubling**: {prob.get('prob_double', 0):.1%}\n"
            md += f"- **Probability of 10% Loss**: {prob.get('prob_loss_10pct', 0):.1%}\n"
            md += f"- **Probability of 25% Loss**: {prob.get('prob_loss_25pct', 0):.1%}\n\n"

        # Insights
        if 'insights' in results and results['insights']:
            md += "### Key Insights\n\n"
            for insight in results['insights']:
                md += f"- {insight}\n"
            md += "\n"

        return md

    @staticmethod
    def format_comparison(comparison_data: Dict[str, Any]) -> str:
        """
        Format market/investment comparison as markdown with charts

        Args:
            comparison_data: Comparison results

        Returns:
            Formatted markdown string
        """
        md = "## Comparative Analysis\n\n"

        # Composite rankings
        if 'comparison_summary' in comparison_data and 'composite_rankings' in comparison_data['comparison_summary']:
            rankings = comparison_data['comparison_summary']['composite_rankings']

            chart_data = [
                {'name': item['market'], 'value': item['score']}
                for item in sorted(rankings, key=lambda x: x['rank'])[:10]  # Top 10
            ]

            md += "### Overall Rankings\n\n"
            md += MarkdownChartFormatter.format_bar_chart(chart_data, "Investment Attractiveness Score")
            md += "\n\n"

            # Detailed rankings table
            md += "| Rank | Market | Score | Rationale |\n"
            md += "|------|--------|-------|----------|\n"

            for item in sorted(rankings, key=lambda x: x['rank'])[:10]:
                md += f"| {item['rank']} | {item['market']} | {item['score']:.1f} | {item.get('rationale', 'N/A')} |\n"

            md += "\n"

        # Recommendations
        if 'investment_recommendations' in comparison_data and comparison_data['investment_recommendations']:
            md += "### Investment Recommendations\n\n"
            for rec in comparison_data['investment_recommendations']:
                md += f"- {rec}\n"
            md += "\n"

        return md
