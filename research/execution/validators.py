"""Optional validation and diagnostics for fill simulations.

Provides non-blocking checks and warnings for execution results. Unlike BookValidator,
ExecutionValidator logs diagnostic information without rejecting events. This helps
identify anomalies in fill patterns, queue management, or trade flow.
"""

from dataclasses import dataclass

from research.execution.models import ExecutionResult, FillType


@dataclass
class ExecutionDiagnostic:
    """Diagnostic result from an execution validation check.

    Attributes:
        passed: True if check passed (expected result); False if anomaly detected.
        warning: Human-readable description of the result or warning.
        severity: 'info', 'warning', or 'error' (for future categorization).
    """

    passed: bool
    warning: str
    severity: str = "info"


class ExecutionValidator:
    """Non-blocking diagnostics for fill simulation results.

    Unlike BookValidator (which rejects invalid state), ExecutionValidator
    logs warnings and anomalies without blocking the replay or simulation.
    Useful for identifying:
    - Unexpected queue positions
    - Partial fills due to insufficient liquidity
    - Orders getting skipped in FIFO queue
    - Systematic misses at certain price levels
    """

    @staticmethod
    def validate_fill_quantity(result: ExecutionResult) -> ExecutionDiagnostic:
        """Check that fill quantity is consistent with order and trade sizes.

        Returns:
            ExecutionDiagnostic with pass/warning status.
        """
        if result.fill_type == FillType.NO_POSITION:
            return ExecutionDiagnostic(
                passed=True,
                warning="Order not in book or at wrong price; no fill expected.",
                severity="info",
            )

        if result.fill_type == FillType.POSITION_MISS:
            if result.fill_quantity != 0.0:
                return ExecutionDiagnostic(
                    passed=False,
                    warning=(
                        f"Position miss but fill_quantity={result.fill_quantity} > 0; "
                        "inconsistent result."
                    ),
                    severity="warning",
                )
            return ExecutionDiagnostic(
                passed=True,
                warning="Position miss; no fill expected.",
                severity="info",
            )

        if result.fill_type == FillType.PASSIVE_FILL:
            if result.fill_quantity <= 0.0:
                return ExecutionDiagnostic(
                    passed=False,
                    warning=f"Passive fill reported but fill_quantity={result.fill_quantity}; invalid.",
                    severity="error",
                )
            if result.fill_quantity > result.remaining_quantity + result.fill_quantity:
                return ExecutionDiagnostic(
                    passed=False,
                    warning=(
                        f"Fill quantity exceeds available: "
                        f"fill_qty={result.fill_quantity}, "
                        f"remaining after={result.remaining_quantity}."
                    ),
                    severity="error",
                )
            return ExecutionDiagnostic(
                passed=True,
                warning=f"Passive fill for {result.fill_quantity} shares.",
                severity="info",
            )

        return ExecutionDiagnostic(
            passed=False,
            warning=f"Unknown fill type: {result.fill_type}",
            severity="error",
        )

    @staticmethod
    def validate_queue_position(result: ExecutionResult) -> ExecutionDiagnostic:
        """Check queue position consistency with fill type.

        Returns:
            ExecutionDiagnostic with pass/warning status.
        """
        if result.fill_type == FillType.NO_POSITION:
            if result.queue_position is not None:
                return ExecutionDiagnostic(
                    passed=False,
                    warning="NO_POSITION but queue_position is not None; inconsistent.",
                    severity="warning",
                )
            return ExecutionDiagnostic(
                passed=True,
                warning="No position; queue_position correctly None.",
                severity="info",
            )

        if result.queue_position is None:
            return ExecutionDiagnostic(
                passed=False,
                warning=f"Fill type {result.fill_type.name} but queue_position is None; invalid.",
                severity="error",
            )

        if result.fill_type == FillType.PASSIVE_FILL and not result.queue_position.is_at_front:
            return ExecutionDiagnostic(
                passed=False,
                warning=(
                    f"Passive fill reported but order at position "
                    f"{result.queue_position.sequence_position} (not front); invalid."
                ),
                severity="error",
            )

        if result.fill_type == FillType.POSITION_MISS and result.queue_position.is_at_front:
            return ExecutionDiagnostic(
                passed=False,
                warning="Position miss reported but order is at front of queue; unexpected.",
                severity="warning",
            )

        return ExecutionDiagnostic(
            passed=True,
            warning=f"Queue position consistent with fill type.",
            severity="info",
        )

    @staticmethod
    def validate_remaining_quantity(result: ExecutionResult) -> ExecutionDiagnostic:
        """Check that remaining quantity is correct after fill.

        Returns:
            ExecutionDiagnostic with pass/warning status.
        """
        if result.fill_quantity < 0.0 or result.remaining_quantity < 0.0:
            return ExecutionDiagnostic(
                passed=False,
                warning=(
                    f"Negative quantities: fill_qty={result.fill_quantity}, "
                    f"remaining_qty={result.remaining_quantity}."
                ),
                severity="error",
            )

        return ExecutionDiagnostic(
            passed=True,
            warning=(
                f"Quantities valid: fill={result.fill_quantity}, "
                f"remaining={result.remaining_quantity}."
            ),
            severity="info",
        )

    @classmethod
    def validate_result(cls, result: ExecutionResult) -> list[ExecutionDiagnostic]:
        """Run all diagnostic checks on an ExecutionResult.

        Args:
            result: ExecutionResult to validate.

        Returns:
            List of ExecutionDiagnostic objects; all can be reviewed for warnings.
        """
        return [
            cls.validate_fill_quantity(result),
            cls.validate_queue_position(result),
            cls.validate_remaining_quantity(result),
        ]
