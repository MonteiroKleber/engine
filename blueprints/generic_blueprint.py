"""Blueprint Genérico - Organização estruturada de PLANs.

RESPONSABILIDADE:
- NÃO cria entidades
- NÃO cria endpoints
- NÃO cria tarefas novas
- NÃO altera IR/OAS/PLAN
- Apenas organiza e ordena o que já existe

O GenericBlueprint é um no-op estruturado:
- Recebe IR, OAS, RBAC, PLAN
- Retorna o PLAN original, possivelmente reordenado
- NUNCA expande ou adiciona tarefas
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from copy import deepcopy


@dataclass
class BlueprintResult:
    """Resultado da aplicação de um blueprint.

    Attributes:
        plan: O PLAN resultante (possivelmente reordenado)
        reordered: Se houve reordenação
        original_task_count: Número de tarefas no PLAN original
        final_task_count: Número de tarefas no PLAN final (deve ser igual)
        changes: Lista de alterações feitas (apenas reordenação)
    """

    plan: Dict[str, Any]
    reordered: bool = False
    original_task_count: int = 0
    final_task_count: int = 0
    changes: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Valida invariante: task count não pode mudar."""
        if self.original_task_count != self.final_task_count:
            raise ValueError(
                f"Blueprint violou invariante: task count mudou de "
                f"{self.original_task_count} para {self.final_task_count}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "plan": self.plan,
            "reordered": self.reordered,
            "original_task_count": self.original_task_count,
            "final_task_count": self.final_task_count,
            "changes": self.changes,
        }


class GenericBlueprint:
    """Blueprint genérico para organização de PLANs.

    Este blueprint é um no-op estruturado que:
    1. Recebe IR, OAS, RBAC e PLAN
    2. Valida que as entradas são consistentes
    3. Opcionalmente reordena tarefas por fase/prioridade
    4. Retorna o PLAN sem adicionar nenhuma tarefa nova

    REGRAS ABSOLUTAS:
    - NUNCA criar novas tarefas
    - NUNCA modificar conteúdo de tarefas existentes
    - NUNCA alterar IR, OAS ou RBAC
    - APENAS reordenar tarefas existentes

    Attributes:
        strict_mode: Se True, não faz nenhuma reordenação (pure no-op)
    """

    # Ordem padrão de fases
    DEFAULT_PHASE_ORDER = [
        "setup",
        "database",
        "backend",
        "frontend",
        "integration",
        "testing",
        "deployment",
    ]

    # Ordem padrão de prioridades
    PRIORITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def __init__(self, strict_mode: bool = False) -> None:
        """Inicializa o blueprint.

        Args:
            strict_mode: Se True, não faz nenhuma reordenação (pure no-op)
        """
        self.strict_mode = strict_mode

    def apply(
        self,
        ir: Dict[str, Any],
        oas: Dict[str, Any],
        rbac: Dict[str, Any],
        plan: Dict[str, Any],
    ) -> BlueprintResult:
        """Aplica o blueprint ao PLAN.

        Este método é um no-op estruturado:
        - Em strict_mode: retorna o PLAN exatamente como recebido
        - Caso contrário: pode reordenar tarefas por fase/prioridade

        INVARIANTES:
        - Número de tarefas não muda
        - Conteúdo das tarefas não muda
        - IR, OAS, RBAC não são modificados

        Args:
            ir: Intermediate Representation
            oas: OpenAPI Specification
            rbac: Role-Based Access Control
            plan: PLAN a ser processado

        Returns:
            BlueprintResult com o PLAN processado
        """
        # Fazer cópia profunda para não modificar original
        plan_copy = deepcopy(plan)

        # Contar tarefas originais
        original_tasks = self._extract_tasks(plan_copy)
        original_count = len(original_tasks)

        # Em strict_mode, retornar sem modificações
        if self.strict_mode:
            return BlueprintResult(
                plan=plan_copy,
                reordered=False,
                original_task_count=original_count,
                final_task_count=original_count,
                changes=[],
            )

        # Tentar reordenar por fase e prioridade
        reordered_plan, changes = self._reorder_tasks(plan_copy, ir, oas, rbac)

        # Contar tarefas finais
        final_tasks = self._extract_tasks(reordered_plan)
        final_count = len(final_tasks)

        # Validar invariante
        if original_count != final_count:
            raise ValueError(
                f"Blueprint violou invariante: task count mudou de "
                f"{original_count} para {final_count}"
            )

        return BlueprintResult(
            plan=reordered_plan,
            reordered=len(changes) > 0,
            original_task_count=original_count,
            final_task_count=final_count,
            changes=changes,
        )

    def _extract_tasks(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrai lista de tarefas do PLAN.

        Args:
            plan: PLAN a processar

        Returns:
            Lista de tarefas
        """
        return plan.get("tasks", [])

    def _reorder_tasks(
        self,
        plan: Dict[str, Any],
        ir: Dict[str, Any],
        oas: Dict[str, Any],
        rbac: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]:
        """Reordena tarefas por fase e prioridade.

        REGRAS:
        - NÃO adiciona tarefas
        - NÃO remove tarefas
        - NÃO modifica conteúdo de tarefas
        - APENAS reordena

        Args:
            plan: PLAN a processar
            ir: IR (para contexto, não modificado)
            oas: OAS (para contexto, não modificado)
            rbac: RBAC (para contexto, não modificado)

        Returns:
            Tupla (plan_reordenado, lista_de_mudanças)
        """
        tasks = plan.get("tasks", [])
        if not tasks:
            return plan, []

        # Criar cópia para reordenação
        original_order = [t.get("id", i) for i, t in enumerate(tasks)]

        # Ordenar por fase e prioridade
        sorted_tasks = sorted(
            tasks,
            key=lambda t: (
                self._get_phase_order(t),
                self._get_priority_order(t),
                t.get("id", ""),
            ),
        )

        # Verificar se houve mudança na ordem
        new_order = [t.get("id", i) for i, t in enumerate(sorted_tasks)]
        changes = []

        if original_order != new_order:
            changes.append(
                f"Reordered tasks by phase and priority: {len(tasks)} tasks"
            )

        # Atualizar plan com tarefas reordenadas
        plan["tasks"] = sorted_tasks

        return plan, changes

    def _get_phase_order(self, task: Dict[str, Any]) -> int:
        """Retorna ordem da fase para ordenação.

        Args:
            task: Tarefa a verificar

        Returns:
            Índice de ordenação da fase
        """
        phase = task.get("phase", "").lower()

        try:
            return self.DEFAULT_PHASE_ORDER.index(phase)
        except ValueError:
            # Fases desconhecidas vão para o final
            return len(self.DEFAULT_PHASE_ORDER)

    def _get_priority_order(self, task: Dict[str, Any]) -> int:
        """Retorna ordem da prioridade para ordenação.

        Args:
            task: Tarefa a verificar

        Returns:
            Índice de ordenação da prioridade
        """
        priority = task.get("priority", "medium").lower()
        return self.PRIORITY_ORDER.get(priority, 2)

    def validate_invariants(
        self,
        original_plan: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> bool:
        """Valida que invariantes foram mantidos.

        Invariantes:
        1. Número de tarefas não mudou
        2. IDs das tarefas são os mesmos
        3. Conteúdo das tarefas é o mesmo (apenas ordem diferente)

        Args:
            original_plan: PLAN original
            result_plan: PLAN resultante

        Returns:
            True se invariantes foram mantidos
        """
        original_tasks = self._extract_tasks(original_plan)
        result_tasks = self._extract_tasks(result_plan)

        # 1. Verificar contagem
        if len(original_tasks) != len(result_tasks):
            return False

        # 2. Verificar que IDs são os mesmos
        original_ids = {t.get("id") for t in original_tasks}
        result_ids = {t.get("id") for t in result_tasks}

        if original_ids != result_ids:
            return False

        # 3. Verificar que conteúdo é o mesmo
        original_by_id = {t.get("id"): t for t in original_tasks}
        result_by_id = {t.get("id"): t for t in result_tasks}

        for task_id, original_task in original_by_id.items():
            result_task = result_by_id.get(task_id)
            if result_task is None:
                return False

            # Comparar conteúdo (exceto ordem no dict)
            if original_task != result_task:
                return False

        return True


def apply_blueprint(
    ir: Dict[str, Any],
    oas: Dict[str, Any],
    rbac: Dict[str, Any],
    plan: Dict[str, Any],
    strict_mode: bool = False,
) -> BlueprintResult:
    """Função de conveniência para aplicar blueprint genérico.

    Args:
        ir: Intermediate Representation
        oas: OpenAPI Specification
        rbac: Role-Based Access Control
        plan: PLAN a ser processado
        strict_mode: Se True, não faz nenhuma reordenação

    Returns:
        BlueprintResult com o PLAN processado
    """
    blueprint = GenericBlueprint(strict_mode=strict_mode)
    return blueprint.apply(ir, oas, rbac, plan)
