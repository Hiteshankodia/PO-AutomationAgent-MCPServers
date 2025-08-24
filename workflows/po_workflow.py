
"""Purchase Order workflow implementation using LangGraph."""
import asyncio
import time
import json
from typing import Dict, Any
from datetime import datetime

from langgraph.graph import StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from workflows.workflow_state import POWorkflowState
from utils.azure_llm import llm_manager
from utils.helpers import generate_po_id, validate_po_request, format_currency
import logging

logger = logging.getLogger(__name__)

class POWorkflow:
    """Purchase Order processing workflow using LangGraph and MCP servers."""
    
    def __init__(self):
        """Initialize the PO workflow."""
        self.mcp_config = {
            "supplier": {
                "command": "python",
                "args": ["mcp_servers/supplier_server.py"],
                "transport": "stdio"
            },
            "budget": {
                "command": "python", 
                "args": ["mcp_servers/budget_server.py"],
                "transport": "stdio"
            },
            "approval": {
                "command": "python",
                "args": ["mcp_servers/approval_server.py"],
                "transport": "stdio"
            },
            "notification": {
                "command": "python",
                "args": ["mcp_servers/notification_server.py"],
                "transport": "stdio"
            },
            "payment": {
                "command": "python",
                "args": ["mcp_servers/payment_server.py"],
                "transport": "stdio"
            }
        }
        # Create MCP client directly - NO CONTEXT MANAGER
        self.mcp_client = MultiServerMCPClient(self.mcp_config)
        self.workflow = None
        logger.info("PO workflow initialized with MCP client")
    
    def _handle_tool_response(self, response, tool_name: str):
        """Handle different types of responses from MCP tools."""
        if isinstance(response, str):
            try:
                import json
                parsed_response = json.loads(response)
                logger.debug(f"{tool_name} string response parsed successfully")
                return parsed_response
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"{tool_name} returned unparseable string response: {response}")
                return {"error": True, "message": response}
        elif isinstance(response, dict):
            return response
        elif isinstance(response, list) and len(response) > 0:
            first = response[0]
            return first if isinstance(first, dict) else {"error": True, "message": str(response)}
        else:
            logger.warning(f"{tool_name} returned unexpected response type: {type(response)}")
            return {"error": True, "message": f"Unexpected response type: {type(response)}"}
    
    async def get_tools_safe(self, server_name: str):
        """Get tools from MCP server with proper handling of list vs dict responses."""
        try:
            tools = await self.mcp_client.get_tools(server_name=server_name)
            logger.debug(f"Raw tools from {server_name}: {type(tools)}")
            if isinstance(tools, list):
                if len(tools) > 0:
                    tool_dict = {}
                    for tool in tools:
                        if hasattr(tool, 'name'):
                            tool_dict[tool.name] = tool
                        elif hasattr(tool, '__name__'):
                            tool_dict[tool.__name__] = tool
                    return tool_dict if tool_dict else tools[0]
                else:
                    logger.warning(f"Empty tools list from {server_name}")
                    return {}
            elif isinstance(tools, dict):
                return tools
            else:
                logger.warning(f"Unexpected tools type from {server_name}: {type(tools)}")
                return tools
        except Exception as e:
            logger.error(f"Error getting tools from {server_name}: {e}")
            return {}
    
    async def validate_po_request(self, state: POWorkflowState) -> POWorkflowState:
        """Initial validation of PO request."""
        start_time = time.time()
        logger.info(f"Starting PO validation for request: {state['po_request'].get('supplier_id', 'Unknown')}")
        try:
            po_request = state["po_request"]
            if not state.get("po_id"):
                state["po_id"] = generate_po_id()
                po_request["po_id"] = state["po_id"]
            is_valid, validation_message = validate_po_request(po_request)
            if not is_valid:
                state["final_decision"] = "REJECTED"
                state["decision_reason"] = f"Validation failed: {validation_message}"
                state["errors"].append(validation_message)
                logger.warning(f"PO validation failed: {validation_message}")
                return state
            try:
                llm = llm_manager.llm
                analysis_prompt = f"""
                Analyze this Purchase Order request briefly:
                
                PO ID: {state['po_id']}
                Supplier: {po_request.get('supplier_id')}
                Amount: {format_currency(po_request.get('amount', 0))}
                Department: {po_request.get('department')}
                
                Provide a brief analysis in 1-2 sentences.
                """
                analysis_response = await llm.ainvoke([HumanMessage(content=analysis_prompt)])
                state["messages"].append(
                    AIMessage(content=f"AI Analysis: {analysis_response.content}")
                )
            except Exception as llm_error:
                logger.warning(f"LLM analysis failed (continuing without): {llm_error}")
            state["messages"].append(
                SystemMessage(content=f"PO {state['po_id']} validated successfully. Amount: {format_currency(po_request['amount'])}")
            )
            logger.info(f"PO validation completed for {state['po_id']}")
        except Exception as e:
            error_msg = f"Error during PO validation: {str(e)}"
            state["errors"].append(error_msg)
            state["final_decision"] = "ERROR"
            state["decision_reason"] = error_msg
            logger.error(error_msg)
        finally:
            state["processing_time"] = time.time() - start_time
        return state
    
    async def check_supplier(self, state: POWorkflowState) -> POWorkflowState:
        """Validate supplier using MCP server."""
        logger.info(f"Checking supplier for PO {state['po_id']}")
        try:
            supplier_tools = await self.get_tools_safe("supplier")
            supplier_id = state["po_request"]["supplier_id"]
            order_amount = state["po_request"]["amount"]
            validate_tool = supplier_tools.get("validate_supplier")
            capacity_tool = supplier_tools.get("check_supplier_capacity")
            if not validate_tool or not capacity_tool:
                raise Exception(f"Required supplier tools not found. Available: {list(supplier_tools.keys()) if isinstance(supplier_tools, dict) else supplier_tools}")
            raw_supplier_result = await validate_tool.ainvoke({"supplier_id": supplier_id})
            raw_capacity_result = await capacity_tool.ainvoke({"supplier_id": supplier_id, "order_value": order_amount})
            supplier_result = self._handle_tool_response(raw_supplier_result, "validate_supplier")
            capacity_result = self._handle_tool_response(raw_capacity_result, "check_supplier_capacity")
            state["supplier_validation"] = {
                "validation": supplier_result,
                "capacity": capacity_result,
                "checked_at": datetime.now().isoformat()
            }
            if supplier_result.get("error", False):
                state["final_decision"] = "REJECTED"
                state["decision_reason"] = f"Supplier validation error: {supplier_result.get('message', 'Unknown error')}"
                return state
            if capacity_result.get("error", False):
                state["final_decision"] = "REJECTED"
                state["decision_reason"] = f"Supplier capacity check error: {capacity_result.get('message', 'Unknown error')}"
                return state
            is_valid = supplier_result.get("valid", False)
            capacity_ok = capacity_result.get("capacity_ok", False)
            if not is_valid or not capacity_ok:
                reasons = []
                if not is_valid:
                    reasons.append(supplier_result.get("message", "Supplier validation failed"))
                if not capacity_ok:
                    max_cap = capacity_result.get("max_capacity", 0)
                    reasons.append(f"Order exceeds capacity: {format_currency(order_amount)} > {format_currency(max_cap)}")
                state["final_decision"] = "REJECTED"
                state["decision_reason"] = f"Supplier validation failed: {'; '.join(reasons)}"
                return state
            state["messages"].append(SystemMessage(content=f"Supplier {supplier_id} validated successfully"))
            logger.info(f"Supplier validation passed for {state['po_id']}")
        except Exception as e:
            error_msg = f"Error during supplier validation: {str(e)}"
            state["errors"].append(error_msg)
            state["final_decision"] = "ERROR"
            state["decision_reason"] = error_msg
            logger.error(error_msg)
        return state
    
    async def verify_budget(self, state: POWorkflowState) -> POWorkflowState:
        """Check budget availability using MCP server."""
        logger.info(f"Verifying budget for PO {state['po_id']}")
        try:
            budget_tools = await self.get_tools_safe("budget")
            department_id = state["po_request"]["department"]
            amount = state["po_request"]["amount"]
            check_tool = budget_tools.get("check_budget_availability")
            reserve_tool = budget_tools.get("reserve_budget")
            if not check_tool:
                raise Exception(f"Budget check tool not found. Available: {list(budget_tools.keys()) if isinstance(budget_tools, dict) else budget_tools}")
            raw_budget_result = await check_tool.ainvoke({"department_id": department_id, "amount": amount})
            budget_result = self._handle_tool_response(raw_budget_result, "check_budget_availability")
            if budget_result.get("error", False):
                state["final_decision"] = "ERROR"
                state["decision_reason"] = f"Budget check error: {budget_result.get('message', 'Unknown error')}"
                return state
            state["budget_check"] = {**budget_result, "checked_at": datetime.now().isoformat()}
            is_available = budget_result.get("available", False)
            available_amount = budget_result.get("amount_available", 0)
            if not is_available:
                state["final_decision"] = "REJECTED"
                state["decision_reason"] = f"Insufficient budget: requested {format_currency(amount)}, available {format_currency(available_amount)}"
                return state
            if reserve_tool:
                raw_reserve_result = await reserve_tool.ainvoke({
                    "department_id": department_id,
                    "amount": amount,
                    "po_id": state["po_id"]
                })
                reserve_result = self._handle_tool_response(raw_reserve_result, "reserve_budget")
                if not reserve_result.get("error", False) and reserve_result.get("reserved", False):
                    state["budget_check"]["reservation"] = reserve_result
                    state["messages"].append(SystemMessage(content=f"Budget reserved: {format_currency(amount)}"))
        except Exception as e:
            error_msg = f"Error during budget verification: {str(e)}"
            state["errors"].append(error_msg)
            state["final_decision"] = "ERROR"
            state["decision_reason"] = error_msg
            logger.error(error_msg)
        return state
    
    async def process_approval(self, state: POWorkflowState) -> POWorkflowState:
        """Handle approval process using MCP server."""
        logger.info(f"Processing approval for PO {state['po_id']}")
        try:
            approval_tools = await self.get_tools_safe("approval")
            amount = state["po_request"]["amount"]
            department = state["po_request"]["department"]
            get_approvers_tool = approval_tools.get("get_required_approvers")
            send_request_tool = approval_tools.get("send_approval_request")
            if not get_approvers_tool:
                raise Exception(f"Get approvers tool not found. Available: {list(approval_tools.keys()) if isinstance(approval_tools, dict) else approval_tools}")
            raw_approvers_result = await get_approvers_tool.ainvoke({"amount": amount, "department": department})
            approvers_result = self._handle_tool_response(raw_approvers_result, "get_required_approvers")
            if approvers_result.get("error", False):
                state["final_decision"] = "ERROR"
                state["decision_reason"] = f"Approval check error: {approvers_result.get('message', 'Unknown error')}"
                return state
            state["approval_status"] = {**approvers_result, "processed_at": datetime.now().isoformat()}
            auto_approve = approvers_result.get("auto_approve", False)
            threshold = approvers_result.get("threshold", 0)
            if auto_approve:
                state["final_decision"] = "APPROVED"
                state["decision_reason"] = f"Auto-approved: amount {format_currency(amount)} below threshold {format_currency(threshold)}"
                state["approval_status"]["auto_approved"] = True
                logger.info(f"PO {state['po_id']} auto-approved")
                return state
            if send_request_tool:
                approvers_required = approvers_result.get("approvers_required", [])
                raw_approval_request = await send_request_tool.ainvoke({
                    "po_id": state["po_id"],
                    "approvers": approvers_required,
                    "po_details": state["po_request"]
                })
                approval_request = self._handle_tool_response(raw_approval_request, "send_approval_request")
                state["approval_status"]["request_details"] = approval_request
                state["final_decision"] = "PENDING_APPROVAL"
                state["decision_reason"] = f"Awaiting approval from: {', '.join(approvers_required)}"
                state["messages"].append(SystemMessage(content=f"Approval requests sent to: {', '.join(approvers_required)}"))
            else:
                state["final_decision"] = "PENDING_APPROVAL"
                state["decision_reason"] = "Manual approval required"
        except Exception as e:
            error_msg = f"Error during approval processing: {str(e)}"
            state["errors"].append(error_msg)
            state["final_decision"] = "ERROR"
            state["decision_reason"] = error_msg
            logger.error(error_msg)
        return state
    
    async def send_notifications(self, state: POWorkflowState) -> POWorkflowState:
        """Send notifications based on PO status."""
        logger.info(f"Sending notifications for PO {state['po_id']}")
        try:
            notification_tools = await self.get_tools_safe("notification")
            po_request = state["po_request"]
            decision = state["final_decision"]
            notifications = []
            email_tool = notification_tools.get("send_email_notification")
            slack_tool = notification_tools.get("send_slack_notification")
            if email_tool:
                requester_email = po_request.get("requested_by", "requester@company.com")
                raw_email_result = await email_tool.ainvoke({
                    "recipient": requester_email,
                    "subject": f"PO {state['po_id']} - {decision}",
                    "body": f"PO Status: {decision}\nAmount: {format_currency(po_request['amount'])}\nReason: {state['decision_reason']}",
                    "po_id": state["po_id"]
                })
                email_result = self._handle_tool_response(raw_email_result, "send_email_notification")
                notifications.append(email_result)
            if slack_tool:
                raw_slack_result = await slack_tool.ainvoke({
                    "channel": "#procurement",
                    "message": f"PO {state['po_id']} ({format_currency(po_request['amount'])}) - {decision}",
                    "po_id": state["po_id"]
                })
                slack_result = self._handle_tool_response(raw_slack_result, "send_slack_notification")
                notifications.append(slack_result)
            state["notifications"] = notifications
            state["messages"].append(SystemMessage(content=f"Notifications sent for PO {state['po_id']}"))
            logger.info(f"Notifications sent for {state['po_id']}")
        except Exception as e:
            error_msg = f"Error sending notifications: {str(e)}"
            state["errors"].append(error_msg)
            logger.error(error_msg)
        return state
    
    def should_continue(self, state: POWorkflowState) -> str:
        logger.debug(f"should_continue called for PO {state.get('po_id')}")
        logger.debug(f"  supplier_validation: {bool(state.get('supplier_validation'))}")
        logger.debug(f"  budget_check: {bool(state.get('budget_check'))}")
        logger.debug(f"  approval_status: {bool(state.get('approval_status'))}")
        logger.debug(f"  payment_plan: {bool(state.get('payment_plan'))}")
        logger.debug(f"  payment_attempted: {bool(state.get('payment_attempted'))}")
        logger.debug(f"  final_decision: {state.get('final_decision')}")
        logger.debug(f"  notifications: {bool(state.get('notifications'))}")

        if not state.get("supplier_validation"):
            return "check_supplier"
        if not state.get("budget_check"):
            return "verify_budget"
        if not state.get("approval_status"):
            return "process_approval"

        # Always compute payment once before notifications, even if final_decision is set
        if not state.get("payment_plan") and not state.get("payment_attempted"):
            logger.debug("Routing to: calculate_payment (pre-notification pass)")
            return "calculate_payment"

        if state.get("final_decision") and not state.get("notifications"):
            return "send_notifications"

        return "END"



    
    def _build_workflow(self):
        """Build the LangGraph workflow."""
        workflow = StateGraph(POWorkflowState)
        
        # Add nodes
        workflow.add_node("validate_request", self.validate_po_request)
        workflow.add_node("check_supplier", self.check_supplier)
        workflow.add_node("verify_budget", self.verify_budget)
        workflow.add_node("calculate_payment", self.calculate_payment)
        workflow.add_node("process_approval", self.process_approval)
        workflow.add_node("send_notifications", self.send_notifications)
        
        # Set entry point
        workflow.set_entry_point("validate_request")
        
        # Add conditional edges with ALL possible mappings
        workflow.add_conditional_edges(
            "validate_request",
            self.should_continue,
            {
                "check_supplier": "check_supplier",
                "calculate_payment": "calculate_payment",
                "send_notifications": "send_notifications",
                "END": "__end__"
            }
        )
        workflow.add_conditional_edges(
            "check_supplier", 
            self.should_continue,
            {
                "verify_budget": "verify_budget",
                "calculate_payment": "calculate_payment",
                "send_notifications": "send_notifications",
                "END": "__end__"
            }
        )
        workflow.add_conditional_edges(
            "verify_budget",
            self.should_continue,
            {
                "process_approval": "process_approval",
                "calculate_payment": "calculate_payment",
                "send_notifications": "send_notifications",
                "END": "__end__"
            }
        )
        workflow.add_conditional_edges(
            "process_approval",
            self.should_continue,
            {
                "calculate_payment": "calculate_payment",
                "send_notifications": "send_notifications",
                "END": "__end__"
            }
        )
        workflow.add_conditional_edges(
            "calculate_payment",
            self.should_continue,
            {
                "send_notifications": "send_notifications",
                "END": "__end__"
            }
        )
        workflow.add_conditional_edges(
            "send_notifications",
            self.should_continue,
            {
                "END": "__end__"
            }
        )
        
        self.workflow = workflow.compile()
        logger.info("PO workflow built successfully")
        
    async def process_po(self, po_request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a purchase order through the complete workflow."""
        start_time = time.time()
        logger.info(f"Starting PO processing for supplier: {po_request.get('supplier_id', 'Unknown')}")
        if self.workflow is None:
            self._build_workflow()
        initial_state = {
            "messages": [HumanMessage(content=f"Process PO for ${po_request.get('amount', 0):,.2f}")],
            "po_request": po_request,
            "po_id": "",
            "supplier_validation": {},
            "budget_check": {},
            "approval_status": {},
            "notifications": [],
            "final_decision": "",
            "decision_reason": "",
            "processing_time": 0.0,
            "errors": [],
            "payment_attempted": False
        }
        try:
            result = await self.workflow.ainvoke(initial_state)
            result["processing_time"] = time.time() - start_time
            logger.info(f"PO processing completed for {result.get('po_id', 'Unknown')} in {result['processing_time']:.2f}s")
            return result
        except Exception as e:
            error_msg = f"Workflow execution failed: {str(e)}"
            logger.error(error_msg)
            logger.exception("Full traceback:")
            return {
                **initial_state,
                "final_decision": "ERROR",
                "decision_reason": error_msg,
                "processing_time": time.time() - start_time,
                "errors": [error_msg]
            }
    
    async def test_mcp_connections(self):
        """Test all MCP server connections for debugging."""
        servers = ["supplier", "budget", "approval", "notification", "payment"]
        for server_name in servers:
            try:
                logger.info(f"Testing connection to {server_name} server...")
                tools = await self.get_tools_safe(server_name)
                logger.info(f"✅ {server_name} server connected. Tools type: {type(tools)}")
                if isinstance(tools, dict):
                    logger.info(f"Available tools: {list(tools.keys())}")
                elif isinstance(tools, list):
                    logger.info(f"Tools list length: {len(tools)}")
                else:
                    logger.info(f"Tools content: {tools}")
            except Exception as e:
                logger.error(f"❌ {server_name} server failed: {e}")
                return False
        return True


        # inside class POWorkflow
    async def calculate_payment(self, state: POWorkflowState) -> POWorkflowState:
        """Derive payment plan from PO totals and supplier risk policy."""
        logger.info(f"Calculating payment plan for PO {state['po_id']}")
        try:
            payment_tools = await self.get_tools_safe("payment")
            plan_tool = payment_tools.get("recommend_payment_plan")
            if not plan_tool:
                raise Exception(
                    f"Payment tool 'recommend_payment_plan' not found. "
                    f"Available: {list(payment_tools.keys()) if isinstance(payment_tools, dict) else payment_tools}"
                )

            po_id_for_calc = state.get("po_id") or state["po_request"].get("po_id")
            if not po_id_for_calc:
                raise Exception("po_id missing for payment calculation")

            supplier_id = state["po_request"].get("supplier_id")
            if not supplier_id:
                raise Exception("supplier_id missing for payment calculation")

            # IMPORTANT: pass the request-style PO (e.g., 'PO-2025...') PLUS supplier_id.
            # The payment_server will map it to the static DB ids {SUP001:1, SUP002:2, SUP003:3, SUP999:4}.
            raw_plan = await plan_tool.ainvoke({
                "po_id": po_id_for_calc,           # do NOT cast to int
                "supplier_id": supplier_id
            })
            plan = self._handle_tool_response(raw_plan, "recommend_payment_plan")

            if plan.get("error"):
                state["final_decision"] = "ERROR"
                state["decision_reason"] = f"Payment plan error: {plan.get('message')}"
                state["errors"].append(state["decision_reason"])
                return state

            state["payment_plan"] = plan

            up_pct = plan["policy"]["upfront_percent"]
            up_amt = plan["amounts"]["upfront_amount"]
            bal_amt = plan["amounts"]["balance_amount"]
            band = plan["policy"]["band"]
            state["messages"].append(
                SystemMessage(
                    content=f"Payment plan: {up_pct:.2f}% upfront ({format_currency(up_amt)}), "
                            f"balance {format_currency(bal_amt)} [{band} risk]"
                )
            )
            logger.info(f"Payment plan computed for PO {state['po_id']}")
        except Exception as e:
            msg = f"Error during payment calculation: {e}"
            logger.error(msg)
            state["errors"].append(msg)
            state["final_decision"] = "ERROR"
            state["decision_reason"] = msg
        finally:
            state["payment_attempted"] = True
        return state

