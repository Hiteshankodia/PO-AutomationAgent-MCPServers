

"""Main application entry point for PO automation system with DB integration."""
import asyncio
import logging
from typing import Dict, Any
from dotenv import load_dotenv

from workflows.po_workflow import POWorkflow
from utils.helpers import format_currency
from config.azure_config import azure_config
from database.db_operations import DatabaseManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('po_automation.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class POAutomationApp:
    """Main application class for PO automation with DB support."""

    def __init__(self):
        self.workflow = None
        self.db_manager = None
        self.is_initialized = False

    async def initialize(self):
        """Initialize the application components."""
        try:
            logger.info("Initializing PO Automation System...")

            # Check Azure OpenAI configuration
            if not azure_config.is_configured:
                raise ValueError("Azure OpenAI configuration is incomplete")

            # Initialize database manager
            self.db_manager = DatabaseManager()

            # Initialize workflow
            self.workflow = POWorkflow()

            self.is_initialized = True
            logger.info("PO Automation System initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            raise

    async def process_purchase_order(self, po_request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single purchase order."""
        if not self.is_initialized:
            await self.initialize()

        logger.info(
            f"Processing PO {po_request.get('po_id', 'Unknown')} "
            f"for supplier {po_request.get('supplier_id', 'Unknown')}"
        )

        try:
            result = await self.workflow.process_po(po_request)

            # Log processing result
            self._log_processing_result(result)

            return result

        except Exception as e:
            logger.error(f"Error processing PO: {e}")
            return {
                "final_decision": "ERROR",
                "decision_reason": f"Processing error: {str(e)}",
                "po_id": po_request.get("po_id", "Unknown"),
                "processing_time": 0,
                "errors": [str(e)]
            }

    def _log_processing_result(self, result: Dict[str, Any]):
        """Log the processing result."""
        po_id = result.get("po_id", "Unknown")
        decision = result.get("final_decision", "Unknown")
        processing_time = result.get("processing_time", 0)

        logger.info(f"PO {po_id} processed in {processing_time:.2f}s - Decision: {decision}")

        # If payment plan exists, log a concise line for easy grepping
        plan = result.get("payment_plan")
        if not plan:
            logger.info("PaymentPlan | PO %s | skipped (decision=%s)", po_id, result.get("final_decision"))

        if plan:
            policy = plan.get("policy", {})
            amounts = plan.get("amounts", {})
            logger.info(
                "PaymentPlan | PO %s | Band=%s | Upfront%%=%.2f | Upfront=%s | Balance=%s",
                po_id,
                policy.get("band", "N/A"),
                policy.get("upfront_percent", 0.0),
                format_currency(amounts.get("upfront_amount", 0.0)),
                format_currency(amounts.get("balance_amount", 0.0)),
            )

        if result.get("errors"):
            for error in result["errors"]:
                logger.warning(f"PO {po_id} error: {error}")

    def _print_payment_plan(self, result: Dict[str, Any]):
        """Pretty print the payment plan (from payment_server.py) if present."""
        plan = result.get("payment_plan")
        if not plan:
            print("\nPayment Plan: —")
            return

        policy = plan.get("policy", {})
        totals = plan.get("totals", {})
        amounts = plan.get("amounts", {})
        risk = plan.get("risk", {})
        metrics = risk.get("metrics", {})

        print("\nPayment Plan")
        print("-" * 60)
        print(f"Risk Band:       {policy.get('band', 'N/A')} "
              f"(score {risk.get('risk_score', 0)})")
        print(f"Upfront:         {policy.get('upfront_percent', 0):.2f}% "
              f"= {format_currency(amounts.get('upfront_amount', 0.0))}")
        print(f"Balance:         {policy.get('balance_percent', 0):.2f}% "
              f"= {format_currency(amounts.get('balance_amount', 0.0))}")
        print(f"Milestone:       {policy.get('milestone', 'N/A')}")
        print(f"Total (INR):     {format_currency(totals.get('total_in_inr', 0.0))}")
        print(f"  • Lines:       {format_currency(totals.get('line_total', 0.0))}")
        print(f"  • Tax:         {format_currency(totals.get('tax_amount', 0.0))}")
        print(f"  • Freight:     {format_currency(totals.get('freight_amount', 0.0))}")
        print("Risk Metrics:")
        print(f"  • Fulfillment: {metrics.get('fulfillment_ratio', 0):.3f}")
        print(f"  • On-time:     {metrics.get('ontime_rate', 0):.3f}")
        print(f"  • Quality OK:  {metrics.get('quality_ok_rate', 0):.3f}")
        print(f"  • Inv Reject:  {metrics.get('invoice_rejection_rate', 0):.3f}")
        print(f"  • Pay Fail:    {metrics.get('payment_failure_rate', 0):.3f}")

    def print_processing_summary(self, result: Dict[str, Any]):
        """Print a formatted summary of the processing result."""
        print("\n" + "=" * 60)
        print("PURCHASE ORDER PROCESSING SUMMARY")
        print("=" * 60)

        po_request = result.get("po_request", {})

        print(f"PO ID: {result.get('po_id', 'N/A')}")
        print(f"Supplier: {po_request.get('supplier_id', 'N/A')}")
        print(f"Amount: {format_currency(po_request.get('amount', 0))}")
        print(f"Department: {po_request.get('department', 'N/A')}")
        print(f"Processing Time: {result.get('processing_time', 0):.2f} seconds")

        print(f"\nFINAL DECISION: {result.get('final_decision', 'N/A')}")
        print(f"REASON: {result.get('decision_reason', 'N/A')}")

        # Supplier validation
        supplier_val = result.get("supplier_validation", {})
        if supplier_val:
            print(f"\nSupplier Validation: "
                  f"{'✓ PASSED' if supplier_val.get('validation', {}).get('valid') else '✗ FAILED'}")
            if supplier_val.get("capacity"):
                capacity = supplier_val["capacity"]
                print(f"Capacity Check: {'✓ OK' if capacity.get('capacity_ok') else '✗ EXCEEDED'}")

        # Budget check
        budget_check = result.get("budget_check", {})
        if budget_check:
            print(f"Budget Check: {'✓ AVAILABLE' if budget_check.get('available') else '✗ INSUFFICIENT'}")
            if budget_check.get("amount_available") is not None:
                print(f"Available Budget: {format_currency(budget_check['amount_available'])}")

        # Approval status
        approval_status = result.get("approval_status", {})
        if approval_status:
            if approval_status.get("auto_approved"):
                print("Approval: ✓ AUTO-APPROVED")
            elif approval_status.get("approvers_required"):
                print(f"Approval: Pending from {', '.join(approval_status['approvers_required'])}")

        # >>> Payment plan (from payment_server.py)
        self._print_payment_plan(result)

        # Notifications
        notifications = result.get("notifications", [])
        if notifications:
            print(f"\nNotifications Sent: {len(notifications)}")

        # Errors
        errors = result.get("errors", [])
        if errors:
            print(f"\nErrors ({len(errors)}):")
            for error in errors:
                print(f"  - {error}")

        print("=" * 60)

    async def run_sample_scenarios(self):
        """Fetch POs from DB and run processing."""
        print("Starting PO Automation System - DB Mode")
        print("=" * 60)

        try:
            pos = self.db_manager.fetch_purchase_orders()
            if not pos:
                print("⚠ No purchase orders found in database.")
                return

            for i, po_request in enumerate(pos, 1):
                print(f"\nProcessing PO {i}/{len(pos)}")
                print("-" * 40)

                result = await self.process_purchase_order(po_request)
                self.print_processing_summary(result)

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error running sample scenarios: {e}")
            print(f"⚠ Error: {e}")

    async def close(self):
        """Clean up application resources."""
        if self.db_manager:
            self.db_manager.close()
        logger.info("PO Automation System closed")


async def main():
    """Main application entry point."""
    app = POAutomationApp()

    try:
        await app.initialize()
        await app.run_sample_scenarios()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())
