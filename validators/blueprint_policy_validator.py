"""Blueprint Policy Validator - Gates anti-invenção.

REGRA ABSOLUTA:
Blueprint só pode CONSUMIR, nunca PRODUZIR.

Gates de validação:
1. Não pode criar entidade fora do IR
2. Não pode criar endpoint fora do OAS
3. Não pode criar task fora do PLAN
4. Não pode alterar contratos (IR, OAS, RBAC)

Este validador verifica que o BlueprintResult não viola
nenhuma dessas regras após aplicação do blueprint.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple
from copy import deepcopy


@dataclass
class BlueprintPolicyReport:
    """Resultado da validação de política do blueprint.

    Attributes:
        ok: True se todas as políticas foram respeitadas
        violations: Lista de violações encontradas
        entities_created: Entidades que tentaram ser criadas (violação)
        endpoints_created: Endpoints que tentaram ser criados (violação)
        tasks_created: Tasks que tentaram ser criadas (violação)
        contracts_altered: Contratos que foram alterados (violação)
    """

    ok: bool
    violations: List[str] = field(default_factory=list)
    entities_created: List[str] = field(default_factory=list)
    endpoints_created: List[str] = field(default_factory=list)
    tasks_created: List[str] = field(default_factory=list)
    contracts_altered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "ok": self.ok,
            "violations": self.violations,
            "entities_created": self.entities_created,
            "endpoints_created": self.endpoints_created,
            "tasks_created": self.tasks_created,
            "contracts_altered": self.contracts_altered,
        }


class BlueprintPolicyValidator:
    """Validador de política anti-invenção para blueprints.

    REGRA: Blueprint só pode consumir, nunca produzir.

    Verifica que após aplicação do blueprint:
    1. Nenhuma entidade nova foi criada (não existe no IR original)
    2. Nenhum endpoint novo foi criado (não existe no OAS original)
    3. Nenhuma task nova foi criada (não existe no PLAN original)
    4. Nenhum contrato foi alterado (IR, OAS, RBAC devem ser idênticos)
    """

    def validate(
        self,
        original_ir: Dict[str, Any],
        original_oas: Dict[str, Any],
        original_rbac: Dict[str, Any],
        original_plan: Dict[str, Any],
        result_ir: Dict[str, Any],
        result_oas: Dict[str, Any],
        result_rbac: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> BlueprintPolicyReport:
        """Valida que o blueprint não violou políticas anti-invenção.

        Args:
            original_ir: IR antes do blueprint
            original_oas: OAS antes do blueprint
            original_rbac: RBAC antes do blueprint
            original_plan: PLAN antes do blueprint
            result_ir: IR após o blueprint
            result_oas: OAS após o blueprint
            result_rbac: RBAC após o blueprint
            result_plan: PLAN após o blueprint

        Returns:
            BlueprintPolicyReport com resultado da validação
        """
        violations: List[str] = []
        entities_created: List[str] = []
        endpoints_created: List[str] = []
        tasks_created: List[str] = []
        contracts_altered: List[str] = []

        # Gate 1: Verificar se entidades foram criadas
        entity_violations = self._check_entities_created(original_ir, result_ir)
        entities_created.extend(entity_violations)
        for entity in entity_violations:
            violations.append(f"Entity created outside IR: {entity}")

        # Gate 2: Verificar se endpoints foram criados
        endpoint_violations = self._check_endpoints_created(original_oas, result_oas)
        endpoints_created.extend(endpoint_violations)
        for endpoint in endpoint_violations:
            violations.append(f"Endpoint created outside OAS: {endpoint}")

        # Gate 3: Verificar se tasks foram criadas
        task_violations = self._check_tasks_created(original_plan, result_plan)
        tasks_created.extend(task_violations)
        for task in task_violations:
            violations.append(f"Task created outside PLAN: {task}")

        # Gate 4: Verificar se contratos foram alterados
        contract_violations = self._check_contracts_altered(
            original_ir, original_oas, original_rbac,
            result_ir, result_oas, result_rbac,
        )
        contracts_altered.extend(contract_violations)
        for contract in contract_violations:
            violations.append(f"Contract altered: {contract}")

        return BlueprintPolicyReport(
            ok=len(violations) == 0,
            violations=violations,
            entities_created=entities_created,
            endpoints_created=endpoints_created,
            tasks_created=tasks_created,
            contracts_altered=contracts_altered,
        )

    def validate_plan_only(
        self,
        original_plan: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> BlueprintPolicyReport:
        """Valida apenas o PLAN (para blueprints que só reordenam).

        Este método é mais leve e verifica apenas que:
        1. Nenhuma task nova foi criada
        2. Nenhuma task foi removida
        3. O conteúdo das tasks não foi alterado

        Args:
            original_plan: PLAN antes do blueprint
            result_plan: PLAN após o blueprint

        Returns:
            BlueprintPolicyReport com resultado da validação
        """
        violations: List[str] = []
        tasks_created: List[str] = []

        # Verificar tasks criadas
        task_violations = self._check_tasks_created(original_plan, result_plan)
        tasks_created.extend(task_violations)
        for task in task_violations:
            violations.append(f"Task created outside PLAN: {task}")

        # Verificar tasks removidas
        removed = self._check_tasks_removed(original_plan, result_plan)
        for task in removed:
            violations.append(f"Task removed from PLAN: {task}")

        # Verificar conteúdo alterado
        altered = self._check_tasks_content_altered(original_plan, result_plan)
        for task in altered:
            violations.append(f"Task content altered: {task}")

        return BlueprintPolicyReport(
            ok=len(violations) == 0,
            violations=violations,
            tasks_created=tasks_created,
        )

    def _check_entities_created(
        self,
        original_ir: Dict[str, Any],
        result_ir: Dict[str, Any],
    ) -> List[str]:
        """Verifica se novas entidades foram criadas.

        Args:
            original_ir: IR original
            result_ir: IR resultado

        Returns:
            Lista de entidades criadas indevidamente
        """
        original_entities = self._extract_entity_names(original_ir)
        result_entities = self._extract_entity_names(result_ir)

        # Entidades novas = existem no result mas não no original
        created = result_entities - original_entities
        return sorted(list(created))

    def _check_endpoints_created(
        self,
        original_oas: Dict[str, Any],
        result_oas: Dict[str, Any],
    ) -> List[str]:
        """Verifica se novos endpoints foram criados.

        Args:
            original_oas: OAS original
            result_oas: OAS resultado

        Returns:
            Lista de endpoints criados indevidamente
        """
        original_endpoints = self._extract_endpoints(original_oas)
        result_endpoints = self._extract_endpoints(result_oas)

        # Endpoints novos = existem no result mas não no original
        created = result_endpoints - original_endpoints
        return sorted(list(created))

    def _check_tasks_created(
        self,
        original_plan: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> List[str]:
        """Verifica se novas tasks foram criadas.

        Args:
            original_plan: PLAN original
            result_plan: PLAN resultado

        Returns:
            Lista de tasks criadas indevidamente
        """
        original_tasks = self._extract_task_ids(original_plan)
        result_tasks = self._extract_task_ids(result_plan)

        # Tasks novas = existem no result mas não no original
        created = result_tasks - original_tasks
        return sorted(list(created))

    def _check_tasks_removed(
        self,
        original_plan: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> List[str]:
        """Verifica se tasks foram removidas.

        Args:
            original_plan: PLAN original
            result_plan: PLAN resultado

        Returns:
            Lista de tasks removidas indevidamente
        """
        original_tasks = self._extract_task_ids(original_plan)
        result_tasks = self._extract_task_ids(result_plan)

        # Tasks removidas = existem no original mas não no result
        removed = original_tasks - result_tasks
        return sorted(list(removed))

    def _check_tasks_content_altered(
        self,
        original_plan: Dict[str, Any],
        result_plan: Dict[str, Any],
    ) -> List[str]:
        """Verifica se o conteúdo das tasks foi alterado.

        Args:
            original_plan: PLAN original
            result_plan: PLAN resultado

        Returns:
            Lista de tasks com conteúdo alterado
        """
        original_tasks = {t.get("id"): t for t in original_plan.get("tasks", [])}
        result_tasks = {t.get("id"): t for t in result_plan.get("tasks", [])}

        altered = []
        for task_id, original_task in original_tasks.items():
            result_task = result_tasks.get(task_id)
            if result_task is None:
                continue  # Task removida - já tratado em _check_tasks_removed

            if original_task != result_task:
                altered.append(task_id)

        return sorted(altered)

    def _check_contracts_altered(
        self,
        original_ir: Dict[str, Any],
        original_oas: Dict[str, Any],
        original_rbac: Dict[str, Any],
        result_ir: Dict[str, Any],
        result_oas: Dict[str, Any],
        result_rbac: Dict[str, Any],
    ) -> List[str]:
        """Verifica se contratos foram alterados.

        Contratos (IR, OAS, RBAC) devem ser IDÊNTICOS antes e depois.

        Args:
            original_ir: IR original
            original_oas: OAS original
            original_rbac: RBAC original
            result_ir: IR resultado
            result_oas: OAS resultado
            result_rbac: RBAC resultado

        Returns:
            Lista de contratos alterados
        """
        altered = []

        if not self._deep_equals(original_ir, result_ir):
            altered.append("IR")

        if not self._deep_equals(original_oas, result_oas):
            altered.append("OAS")

        if not self._deep_equals(original_rbac, result_rbac):
            altered.append("RBAC")

        return altered

    def _extract_entity_names(self, ir: Dict[str, Any]) -> Set[str]:
        """Extrai nomes de entidades do IR.

        Args:
            ir: Intermediate Representation

        Returns:
            Conjunto de nomes de entidades
        """
        entities = ir.get("domain", {}).get("entities", [])
        return {e.get("name", "") for e in entities if e.get("name")}

    def _extract_endpoints(self, oas: Dict[str, Any]) -> Set[str]:
        """Extrai endpoints do OAS.

        Formato: "METHOD /path"

        Args:
            oas: OpenAPI Specification

        Returns:
            Conjunto de endpoints
        """
        endpoints = set()
        paths = oas.get("paths", {})
        http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in path_item.keys():
                if method.lower() in http_methods:
                    endpoints.add(f"{method.upper()} {path}")

        return endpoints

    def _extract_task_ids(self, plan: Dict[str, Any]) -> Set[str]:
        """Extrai IDs de tasks do PLAN.

        Args:
            plan: PLAN

        Returns:
            Conjunto de IDs de tasks
        """
        tasks = plan.get("tasks", [])
        return {t.get("id", "") for t in tasks if t.get("id")}

    def _deep_equals(self, obj1: Any, obj2: Any) -> bool:
        """Compara dois objetos profundamente.

        Args:
            obj1: Primeiro objeto
            obj2: Segundo objeto

        Returns:
            True se são iguais
        """
        if type(obj1) != type(obj2):
            return False

        if isinstance(obj1, dict):
            if set(obj1.keys()) != set(obj2.keys()):
                return False
            return all(self._deep_equals(obj1[k], obj2[k]) for k in obj1.keys())

        if isinstance(obj1, (list, tuple)):
            if len(obj1) != len(obj2):
                return False
            return all(self._deep_equals(a, b) for a, b in zip(obj1, obj2))

        return obj1 == obj2


def validate_blueprint_policy(
    original_ir: Dict[str, Any],
    original_oas: Dict[str, Any],
    original_rbac: Dict[str, Any],
    original_plan: Dict[str, Any],
    result_ir: Dict[str, Any],
    result_oas: Dict[str, Any],
    result_rbac: Dict[str, Any],
    result_plan: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Função de conveniência para validar política do blueprint.

    Args:
        original_*: Artefatos antes do blueprint
        result_*: Artefatos após o blueprint

    Returns:
        Tupla (ok, violations)
    """
    validator = BlueprintPolicyValidator()
    report = validator.validate(
        original_ir, original_oas, original_rbac, original_plan,
        result_ir, result_oas, result_rbac, result_plan,
    )
    return (report.ok, report.violations)


def validate_blueprint_plan_only(
    original_plan: Dict[str, Any],
    result_plan: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Função de conveniência para validar apenas o PLAN.

    Args:
        original_plan: PLAN antes do blueprint
        result_plan: PLAN após o blueprint

    Returns:
        Tupla (ok, violations)
    """
    validator = BlueprintPolicyValidator()
    report = validator.validate_plan_only(original_plan, result_plan)
    return (report.ok, report.violations)
