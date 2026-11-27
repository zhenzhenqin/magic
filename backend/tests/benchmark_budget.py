"""Local Phase 4.2 budget estimates based on the retained Qwen ledger."""

from dataclasses import dataclass
from decimal import Decimal
from sqlite3 import Connection

FLASH_INPUT_LIMIT = 262_144  # Use the entire published context as an upper bound for input.
FLASH_TIERS = (32_768, 131_072, FLASH_INPUT_LIMIT)


class BudgetPause(ValueError):
    pass


@dataclass(frozen=True)
class PriceTier:
    max_input: int
    input_price: Decimal
    output_price: Decimal

    @classmethod
    def parse(cls, text: str):
        limit, input_price, output_price = text.split(":")
        prices = Decimal(input_price), Decimal(output_price)
        if any(not price.is_finite() or price <= 0 for price in prices):
            raise ValueError("Use the positive on-demand rates before any credits or discounts")
        return cls(int(limit), *prices)

    def estimate(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (input_tokens * self.input_price + output_tokens * self.output_price) / 1_000_000


@dataclass(frozen=True)
class LedgerEstimate:
    attempts: int
    amount: Decimal


@dataclass(frozen=True)
class LiveBudget:
    authorized_attempts: int
    approved_amount: Decimal
    currency: str
    price_reference: str
    tiers: tuple[PriceTier, ...]
    endpoint_fingerprint: str
    model: str
    max_output: int

    def __post_init__(self):
        if tuple(tier.max_input for tier in self.tiers) != FLASH_TIERS:
            raise BudgetPause("Qwen3-VL-Flash 的地区价目必须覆盖 32K、128K 和 256K 三档")

    @property
    def next_call_upper_bound(self) -> Decimal:
        return max(tier.estimate(tier.max_input, self.max_output) for tier in self.tiers)

    def estimate_attempt(self, record) -> Decimal:
        input_tokens, output_tokens = record["input_tokens"], record["output_tokens"]
        if (not record["usage_known"] or type(input_tokens) is not int or type(output_tokens) is not int
                or input_tokens < 0 or output_tokens < 0):
            raise BudgetPause("历史调用 Token 用量未知，先核对用量和账单")
        for tier in self.tiers:
            if input_tokens <= tier.max_input:
                return tier.estimate(input_tokens, output_tokens)
        raise BudgetPause("历史调用超出现有价格档位，先核对适用价目")

    def ledger_estimate(self, ledger: Connection) -> LedgerEstimate:
        # A single SQLite read snapshot includes all Qwen jobs, regardless of account, client, or UTC date.
        rows = ledger.execute("""
            SELECT b.spent, u.id AS attempt_id, u.model, u.status, u.usage_known,
                   u.input_tokens, u.output_tokens, j.processing_fingerprint,
                   EXISTS(SELECT 1 FROM ai_jobs WHERE provider = 'qwen' AND status IN ('pending', 'running')) AS active
            FROM ai_call_budgets b
            LEFT JOIN ai_usage_logs u ON u.provider = b.provider AND u.status != 'not_sent'
            LEFT JOIN ai_jobs j ON j.id = u.job_id
            WHERE b.provider = 'qwen'
        """).fetchall()
        if not rows:
            raise BudgetPause("原联调账本缺少 Qwen 累计记录")
        if rows[0]["active"] or any(row["status"] in ("reserved", "dispatching", "unknown") for row in rows):
            raise BudgetPause("仍有未结清的调用或任务，先核对发送状态")
        attempts = [row for row in rows if row["attempt_id"] is not None]
        spent = rows[0]["spent"]
        if spent != len(attempts):
            raise BudgetPause("累计次数与留存用量明细不一致，先核对账本")
        amount = Decimal(0)
        for row in attempts:
            if (row["status"] not in ("succeeded", "failed") or row["model"] != self.model
                    or row["processing_fingerprint"] != self.endpoint_fingerprint):
                raise BudgetPause("历史调用的模型、计费状态或地域端点无法按当前价目核对")
            amount += self.estimate_attempt(row)
        return LedgerEstimate(spent, amount)

    def require_next(self, estimate: LedgerEstimate, cumulative_limit: int):
        if estimate.attempts >= min(self.authorized_attempts, cumulative_limit):
            raise BudgetPause("累计调用次数已达到授权上限")
        if estimate.amount + self.next_call_upper_bound > self.approved_amount:
            raise BudgetPause("累计估算加下一次调用的保守上界超出授权金额")

    def safe_launch_limit(self, estimate: LedgerEstimate, cumulative_limit: int) -> int:
        self.require_next(estimate, cumulative_limit)
        per_call = self.next_call_upper_bound
        limit = min(self.authorized_attempts, cumulative_limit)
        if (limit - estimate.attempts) * per_call <= self.approved_amount - estimate.amount:
            return limit
        # The running browser and CLI share this existing Worker cap even if requests overlap.
        remaining = int((self.approved_amount - estimate.amount) // per_call)
        return estimate.attempts + remaining
