import os
import json
from dataclasses import dataclass
from typing import Dict, Any

# Mocking Strands Agents SDK and A2A Protocol components based on the standard Python tool-use pattern
# Replace these imports with `from strands import Agent, tool, A2A` when using the actual SDK package.

def tool(func):
    """Decorator to mark custom functions as executable tools for Strands agents."""
    func.__is_tool__ = True
    return func

@dataclass
class Agent:
    name: str
    role: str
    tools: list
    model: str = "anthropic.claude-3-sonnet-20240229-v1:0"  # AWS Bedrock default

    def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Core agent loop: routes input to tools or sub-agents dynamically."""
        print(f"[{self.name}] Processing workflow step...")
        
        # Execute tools assigned to this agent based on input
        context = input_data.copy()
        for t in self.tools:
            if callable(t):
                if t.__name__ == "parse_error_log" and "log_data" in context:
                    context["diagnostic_summary"] = t(context["log_data"])
                elif t.__name__ == "lookup_customer_profile" and "email" in context:
                    context["customer_info"] = t(context["email"])
                elif t.__name__ == "notify_slack_and_update_ticket" and "diagnostic_summary" in context:
                    context["delivery_status"] = t(
                        context.get("customer_info", {}).get("name", "Unknown"),
                        context["diagnostic_summary"]
                    )
        return context


class A2AProtocol:
    """Agent2Agent (A2A) communication protocol handler for sub-agent handoffs."""
    @staticmethod
    def delegate(target_agent: Agent, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[A2A Protocol] Delegating task to sub-agent: {target_agent.name}")
        return target_agent.run(task_payload)


# --- 1. Tools Definition (@tool decorators) ---

@tool
def lookup_customer_profile(email: str) -> Dict[str, Any]:
    """MCP Database tool simulator: fetches customer profile data."""
    # Simulates MCP Database server query
    database = {
        "alex@enterprise.com": {"name": "Alex Mercer", "tier": "Enterprise", "account_id": "ACC-9921"}
    }
    return database.get(email, {"name": "Valued Customer", "tier": "Standard", "account_id": "ACC-0000"})

@tool
def parse_error_log(log_data: str) -> str:
    """Diagnostic sub-agent tool: extracts root cause from unstructured error logs."""
    if "ConnectionRefusedError" in log_data or "500" in log_data:
        return "CRITICAL: Database connection pool exhausted on cluster-east-2."
    return "WARNING: Unhandled exception detected in request payload."

@tool
def notify_slack_and_update_ticket(customer_name: str, issue_details: str) -> str:
    """External service tool: updates ticket status and notifies engineering team."""
    message = f"Ticket Updated for {customer_name}. Root Cause: {issue_details}"
    print(f"[Slack #eng-alerts] {message}")
    return "Notification Sent & Ticket Updated"


# --- 2. Multi-Agent Setup (A2A Architecture) ---

# Diagnostic Sub-Agent (Lite model / Fast micro-task)
diagnostic_agent = Agent(
    name="DiagnosticParserAgent",
    role="Parse error logs and analyze system diagnostics",
    tools=[parse_error_log],
    model="ollama/llama3"
)

# Primary Support Orchestration Agent (Bedrock Claude model)
main_agent = Agent(
    name="OpsPulseMainAgent",
    role="Orchestrate support workflows, query customer info, and communicate results",
    tools=[lookup_customer_profile, notify_slack_and_update_ticket],
    model="anthropic.claude-3-sonnet-20240229-v1:0"
)


# --- 3. End-to-End Workflow Execution ---

def run_opspulse_pipeline(incoming_event: Dict[str, Any]):
    print("=== Starting OpsPulse Workflow Execution ===")
    
    # Step 1: Extract unstructured incoming email and attachment
    sender_email = incoming_event["sender"]
    raw_log = incoming_event["attachment_content"]
    
    # Step 2: Main agent looks up customer details via MCP tool
    context = main_agent.run({"email": sender_email})
    
    # Step 3: Main agent delegates log parsing to Diagnostic Sub-Agent via A2A Protocol
    diagnostic_input = {"log_data": raw_log}
    diagnostic_output = A2AProtocol.delegate(diagnostic_agent, diagnostic_input)
    
    # Merge sub-agent results back into primary workflow context
    context.update(diagnostic_output)
    
    # Step 4: Final execution - Resolution, ticket update, and Slack alert
    final_result = main_agent.run(context)
    
    print("\n=== Workflow Completed Successfully ===")
    print(f"Customer: {final_result['customer_info']['name']}")
    print(f"Diagnosis: {final_result['diagnostic_summary']}")
    print(f"Status: {final_result['delivery_status']}")


if __name__ == "__main__":
    # Simulated Trigger: Unstructured support email with error log
    sample_incoming_email = {
        "sender": "alex@enterprise.com",
        "subject": "Help! Production server is dropping requests",
        "attachment_content": "2026-09-07 14:22:01 ERROR ConnectionRefusedError: [Errno 111] Could not connect to DB host at 10.0.4.12:5432"
    }
    
    run_opspulse_pipeline(sample_incoming_email)