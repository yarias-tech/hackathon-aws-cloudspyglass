"""Centralized service dependency instances for CloudSpyglass.

All route modules import their service dependencies from here to ensure
shared state across the application (e.g., a single CredentialManager
instance is used by both credentials and scan routes).
"""

from .services.credential_manager import CredentialManager
from .services.export_service import ExportService
from .services.filter_engine import FilterEngine
from .services.relationship_resolver import RelationshipResolver
from .services.scan_storage import ScanStorage
from .services.scanner import Scanner

# Shared singleton instances
credential_manager = CredentialManager()
scan_storage = ScanStorage()
filter_engine = FilterEngine()
export_service = ExportService()
scanner = Scanner(credential_manager)


def get_relationship_resolver(account_id: str) -> RelationshipResolver:
    """Create a RelationshipResolver for the given account.

    RelationshipResolver is stateful per-account (requires account_id at init),
    so we create a new instance each time rather than using a singleton.
    """
    return RelationshipResolver(account_id)
