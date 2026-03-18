"""Semana 2 MVP: parser, validador y orquestador para tareas Storecheck."""

from .models import (
    BlockIR,
    ConditionEdge,
    ParseResult,
    TaskIR,
    ValidationIssue,
    ValidationResult,
)
from .parser_mvp import RuleBasedTaskParser
from .validator import TaskIRValidator
from .orchestrator import Semana2Orchestrator, OrchestratorResult
from .executor_h3 import (
    CallableScopeTypeBackend,
    NetworkCallEvidence,
    PlaybookExecutor,
    ScopeTypeBackend,
    ScopeTypePatternRunner,
)
from .evidence import EvidenceStore
from .mcp_backend import CallableMcpChromeBridge, McpChromeBridge, McpScopeTypeBackend
from .mcp_bridge_loader import load_mcp_bridge_from_env
from .mcp_bridge_runtime import EnvCallableMcpChromeBridge
from .mcp_callables_adapter import (
    evaluate_script,
    get_network_request,
    list_network_requests,
    set_mcp_client,
)

__all__ = [
    "BlockIR",
    "ConditionEdge",
    "ParseResult",
    "TaskIR",
    "ValidationIssue",
    "ValidationResult",
    "RuleBasedTaskParser",
    "TaskIRValidator",
    "Semana2Orchestrator",
    "OrchestratorResult",
    "CallableScopeTypeBackend",
    "NetworkCallEvidence",
    "PlaybookExecutor",
    "ScopeTypeBackend",
    "ScopeTypePatternRunner",
    "EvidenceStore",
    "McpChromeBridge",
    "CallableMcpChromeBridge",
    "McpScopeTypeBackend",
    "load_mcp_bridge_from_env",
    "EnvCallableMcpChromeBridge",
    "set_mcp_client",
    "evaluate_script",
    "list_network_requests",
    "get_network_request",
]
