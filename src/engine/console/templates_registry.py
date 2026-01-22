"""Template registry for onboarding bundles.

Provides a fixed list of available bundle templates that can be used
to bootstrap new institutions.

Etapa 4.2: Onboarding + Templates
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BundleTemplate:
    """Template bundle for onboarding.

    Attributes:
        id: Unique identifier (e.g., "finance-pilot").
        name: Human-readable name.
        description: Description of what this template provides.
        departments: List of departments included in this bundle.
        path: Relative path from repository root to template bundle.
        seed_dsl_paths: Mapping of dept_id to relative path of seed DSL file.
        seed_dsl_version: Version of the IDL DSL used for seeds.
    """

    id: str
    name: str
    description: str
    departments: List[str]
    path: str
    seed_dsl_paths: Dict[str, str] = field(default_factory=dict)
    seed_dsl_version: str = "idl.v1.2.2"


# Fixed list of available templates
# Can be expanded to JSON/YAML in the future
AVAILABLE_TEMPLATES: List[BundleTemplate] = [
    BundleTemplate(
        id="finance-pilot",
        name="Finance Pilot",
        description=(
            "Single-department bundle for finance operations. "
            "Includes expense approval workflows, budget controls, "
            "and segregation of duties rules."
        ),
        departments=["finance"],
        path="bundles/finance-pilot",
        seed_dsl_paths={"finance": "seeds/finance.idl"},
        seed_dsl_version="idl.v1.2.2",
    ),
    BundleTemplate(
        id="multi-pilot",
        name="Multi-Department Pilot",
        description=(
            "Multi-department bundle with finance and support departments. "
            "Includes inter-department contracts and shared workflows."
        ),
        departments=["finance", "support"],
        path="bundles/multi-pilot",
        seed_dsl_paths={
            "finance": "seeds/finance.idl",
            "support": "seeds/support.idl",
        },
        seed_dsl_version="idl.v1.2.2",
    ),
]


def get_template(template_id: str) -> Optional[BundleTemplate]:
    """Get template by ID.

    Args:
        template_id: Template identifier.

    Returns:
        BundleTemplate if found, None otherwise.
    """
    for template in AVAILABLE_TEMPLATES:
        if template.id == template_id:
            return template
    return None


def list_templates() -> List[BundleTemplate]:
    """List all available templates.

    Returns:
        Copy of the templates list.
    """
    return AVAILABLE_TEMPLATES.copy()


def get_template_path(template_id: str) -> Optional[Path]:
    """Get absolute path to template bundle.

    Args:
        template_id: Template identifier.

    Returns:
        Absolute path to template bundle directory, or None if not found.
    """
    template = get_template(template_id)
    if not template:
        return None

    # Resolve relative to repository root (parent of src/engine)
    # The templates are in bundles/ at repo root
    engine_dir = Path(__file__).parent.parent  # src/engine
    src_dir = engine_dir.parent  # src
    repo_root = src_dir.parent  # repo root

    template_path = repo_root / template.path
    if template_path.exists():
        return template_path.resolve()

    return None


def get_repo_root() -> Path:
    """Get absolute path to repository root.

    Returns:
        Absolute path to repository root.
    """
    engine_dir = Path(__file__).parent.parent  # src/engine
    src_dir = engine_dir.parent  # src
    return src_dir.parent  # repo root


def get_seed_dsl_path(template_id: str, dept_id: str) -> Optional[Path]:
    """Get absolute path to seed DSL file for a department.

    Args:
        template_id: Template identifier.
        dept_id: Department identifier.

    Returns:
        Absolute path to seed DSL file, or None if not found.
    """
    template = get_template(template_id)
    if not template:
        return None

    seed_rel_path = template.seed_dsl_paths.get(dept_id)
    if not seed_rel_path:
        return None

    repo_root = get_repo_root()
    seed_path = repo_root / seed_rel_path
    if seed_path.exists():
        return seed_path.resolve()

    return None
