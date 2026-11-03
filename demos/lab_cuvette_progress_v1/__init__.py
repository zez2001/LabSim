"""Progress v1 diagnostic annotation; original scoring remains independent."""
from .config import EVALUATOR_VERSION, SCHEMA_VERSION, resolve_config
from .core import MILESTONES, STAGES, ProgressEvaluator

__all__ = ['ProgressEvaluator', 'resolve_config', 'STAGES', 'MILESTONES',
           'SCHEMA_VERSION', 'EVALUATOR_VERSION']
