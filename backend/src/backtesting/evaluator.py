from src.backtesting.metrics import BacktestMetrics
from src.core.config import settings
from src.llm.providers.base import BaseLLMProvider


def _get_provider() -> BaseLLMProvider:
    provider = settings.llm_provider
    if provider == "claude":
        from src.llm.providers.claude import ClaudeProvider
        return ClaudeProvider()
    if provider == "openai":
        from src.llm.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if provider == "ollama":
        from src.llm.providers.ollama import OllamaProvider
        return OllamaProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")


class LLMEvaluator:
    def __init__(self):
        self._provider = _get_provider()

    async def evaluate(
        self,
        metrics: BacktestMetrics,
        strategy_name: str,
        strategy_description: str,
    ) -> tuple[str, str]:
        """Returns (evaluation_text, model_name)."""
        profit_factor_str = (
            f"{metrics.profit_factor:.2f}" if metrics.profit_factor is not None else "N/A (no losing trades)"
        )
        prompt = f"""You are an expert quantitative analyst. Evaluate the following trading strategy backtest results.

Strategy: {strategy_name}
Description: {strategy_description}

Backtest Results:
- Total Return: {metrics.total_return:.2%}
- Annualized Return: {metrics.annualized_return:.2%}
- Sharpe Ratio: {metrics.sharpe_ratio:.2f}
- Max Drawdown: {metrics.max_drawdown:.2%}
- Win Rate: {metrics.win_rate:.2%}
- Profit Factor: {profit_factor_str}
- Total Trades: {metrics.total_trades}
- Avg Hold Days: {metrics.avg_hold_days:.1f}

Please provide:
1. Overall assessment of the strategy's risk-adjusted performance
2. Notable strengths (if any)
3. Key weaknesses or risks
4. Specific improvement suggestions
5. Verdict: is this strategy worth trading live? (Yes / No / Needs Work)

Be concise and direct. Use bullet points."""
        evaluation = await self._provider.complete(prompt)
        model_name = self._provider.model_name
        return evaluation, model_name
