"""Testes do PatchEngine para rewrite ratio slot-aware.

Regras verificadas:
- Arquivos com slots @engine:*:start/:end devem avaliar rewrite ratio apenas dentro dos slots.
- Arquivos sem slots mantêm o comportamento antigo (bloqueia >80%).
- Marcadores malformados (start sem end, end sem start, mismatch) devem falhar.
"""

import pytest

from patch_engine import PatchEngine, PatchSecurityError


@pytest.fixture
def engine(tmp_path):
    generated_root = tmp_path / "generated"
    (generated_root / "test_project").mkdir(parents=True, exist_ok=True)
    return PatchEngine("test_project", generated_root=str(generated_root))


def test_slotted_file_large_growth_allowed(engine):
    old_content = """import type { RouteObject } from 'react-router-dom';

// @engine:imports:start
// @engine:imports:end

export const routes: RouteObject[] = [
  // @engine:routes-array:start
  // @engine:routes-array:end
];
"""

    imports = "\n".join([f"import X{i} from './pages/x{i}/List';" for i in range(500)])
    routes = "\n".join([f"  {{ path: '/x{i}', element: <X{i} /> }}," for i in range(500)])

    new_content = f"""import type {{ RouteObject }} from 'react-router-dom';

// @engine:imports:start
{imports}
// @engine:imports:end

export const routes: RouteObject[] = [
  // @engine:routes-array:start
{routes}
  // @engine:routes-array:end
];
"""

    # Não deve falhar mesmo com crescimento enorme dentro dos slots.
    engine._check_rewrite_ratio(old_content, new_content, "frontend/src/routes.tsx")


def test_non_slotted_file_still_blocked(engine):
    old_content = "x" * 100
    new_content = "y" * 100
    with pytest.raises(PatchSecurityError, match="Rewrite ratio too high"):
        engine._check_rewrite_ratio(old_content, new_content, "plain.txt")


def test_missing_marker_fails(engine):
    old_content = """// @engine:imports:start
// @engine:imports:end
"""

    # End sem start
    new_content_1 = """// @engine:imports:end
"""
    with pytest.raises(PatchSecurityError, match="without start"):
        engine._check_rewrite_ratio(old_content, new_content_1, "slotted.tsx")

    # Start sem end
    new_content_2 = """// @engine:imports:start
content
"""
    with pytest.raises(PatchSecurityError, match="without end"):
        engine._check_rewrite_ratio(old_content, new_content_2, "slotted.tsx")
