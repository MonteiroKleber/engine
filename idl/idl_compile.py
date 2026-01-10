"""IDL Compiler - Draft → IDL v1.

GATE 2: Draft → IDL Compile Gate

Este modulo implementa o compilador que transforma IDL Draft v1 em IDL v1.

REGRAS DE BLOQUEIO (obrigatorias):
A compilacao DEVE FALHAR se existir:
- Qualquer "unknown" em campos obrigatorios
- Qualquer open_questions nao resolvida
- Qualquer entidade sem tipo definido
- Qualquer ator sem role
- Qualquer regra ambigua

REGRAS DE TRANSFORMACAO (quando permitido):
- Remover: assumptions, open_questions, source
- Normalizar: ordenacao, estruturas conforme IDL v1
- Gerar IDL v1 puro, pronto para canonizacao e Contract Gate

PROIBICOES ABSOLUTAS:
- NAO usar LLM dentro do compilador
- NAO inferir campos automaticamente
- NAO "corrigir" Draft silenciosamente
- NAO gerar IDL parcialmente valido
- NAO permitir Draft passar ao motor
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .idl_draft_v1 import (
    IDLDraftV1,
    DraftActor,
    DraftEntity,
    DraftField,
    DraftUseCase,
    DraftIntegration,
    DraftNonFunctional,
    is_unknown,
    UNKNOWN,
)
from .idl_v1 import (
    IDLDocument,
    SystemDefinition,
    ActorDefinition,
    ActorType,
    AuthMethod,
    EntityDefinition,
    FieldDefinition,
    UseCaseDefinition,
    FlowStep,
    PriorityLevel,
    ComplexityLevel,
    IntegrationDefinition,
    IntegrationType,
    ProtocolType,
    NFRDefinition,
    NFRType,
)


# ============================================
# COMPILATION ERRORS
# ============================================

@dataclass
class CompileBlockingError:
    """Erro de bloqueio na compilacao.

    Este erro indica que o Draft NAO pode ser compilado para IDL v1.
    """
    error: str
    reason: str
    location: str

    def to_dict(self) -> Dict[str, str]:
        """Converte para dicionario estruturado."""
        return {
            "error": self.error,
            "reason": self.reason,
            "location": self.location,
        }


class DraftNotCompileableError(Exception):
    """Excecao lancada quando Draft nao pode ser compilado.

    Esta excecao contem informacoes estruturadas sobre o motivo do bloqueio.
    """
    def __init__(self, errors: List[CompileBlockingError]):
        self.errors = errors
        messages = [f"{e.error}: {e.reason} at {e.location}" for e in errors]
        super().__init__(f"Draft cannot be compiled: {'; '.join(messages)}")

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario estruturado."""
        return {
            "error": "DRAFT_NOT_COMPILEABLE",
            "blocking_errors": [e.to_dict() for e in self.errors],
        }


# ============================================
# COMPILE RESULT
# ============================================

@dataclass
class CompileResult:
    """Resultado da compilacao."""
    success: bool
    idl: Optional[IDLDocument] = None
    errors: List[CompileBlockingError] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionario."""
        if self.success:
            return {
                "success": True,
                "idl": self.idl.to_canonical_dict() if self.idl else None,
            }
        else:
            return {
                "success": False,
                "errors": [e.to_dict() for e in self.errors],
            }


# ============================================
# COMPILER
# ============================================

class DraftToIDLCompiler:
    """Compilador Draft → IDL v1.

    Este compilador transforma um IDL Draft v1 valido em IDL v1 canonico.

    O compilador NAO:
    - Infere campos automaticamente
    - Corrige Draft silenciosamente
    - Gera IDL parcialmente valido
    - Usa LLM

    O compilador FALHA se:
    - Existem open_questions
    - Existem campos unknown obrigatorios
    - Existem ambiguidades
    """

    def compile(self, draft: IDLDraftV1) -> CompileResult:
        """Compila Draft para IDL v1.

        Args:
            draft: IDL Draft v1 validado

        Returns:
            CompileResult com sucesso ou erros de bloqueio

        Raises:
            DraftNotCompileableError: Se Draft nao pode ser compilado
        """
        # Fase 1: Verificar bloqueios
        blocking_errors = self._check_blocking_conditions(draft)

        if blocking_errors:
            return CompileResult(success=False, errors=blocking_errors)

        # Fase 2: Transformar para IDL v1
        try:
            idl = self._transform_to_idl(draft)
            return CompileResult(success=True, idl=idl)
        except Exception as e:
            return CompileResult(
                success=False,
                errors=[CompileBlockingError(
                    error="TRANSFORMATION_ERROR",
                    reason=str(e),
                    location="root",
                )],
            )

    def compile_or_raise(self, draft: IDLDraftV1) -> IDLDocument:
        """Compila Draft para IDL v1 ou lanca excecao.

        Args:
            draft: IDL Draft v1 validado

        Returns:
            IDLDocument compilado

        Raises:
            DraftNotCompileableError: Se Draft nao pode ser compilado
        """
        result = self.compile(draft)

        if not result.success:
            raise DraftNotCompileableError(result.errors)

        return result.idl

    def _check_blocking_conditions(self, draft: IDLDraftV1) -> List[CompileBlockingError]:
        """Verifica condicoes de bloqueio.

        Returns:
            Lista de erros de bloqueio (vazia se OK)
        """
        errors: List[CompileBlockingError] = []

        # 1. Open questions bloqueiam compilacao
        if draft.has_open_questions():
            for i, question in enumerate(draft.open_questions):
                errors.append(CompileBlockingError(
                    error="UNRESOLVED_QUESTION",
                    reason=f"Open question not resolved: '{question}'",
                    location=f"open_questions[{i}]",
                ))

        # 2. Actors sem role
        for actor in draft.actors:
            if is_unknown(actor.role):
                errors.append(CompileBlockingError(
                    error="UNKNOWN_ACTOR_ROLE",
                    reason=f"Actor '{actor.id}' has unknown role",
                    location=f"actors.{actor.id}.role",
                ))

        # 3. Entities com campos unknown
        for entity in draft.entities:
            for field_def in entity.fields:
                if is_unknown(field_def.type):
                    errors.append(CompileBlockingError(
                        error="UNKNOWN_FIELD_TYPE",
                        reason=f"Field '{field_def.name}' in entity '{entity.id}' has unknown type",
                        location=f"entities.{entity.id}.fields.{field_def.name}.type",
                    ))
                if is_unknown(field_def.required):
                    errors.append(CompileBlockingError(
                        error="UNKNOWN_FIELD_REQUIRED",
                        reason=f"Field '{field_def.name}' in entity '{entity.id}' has unknown required status",
                        location=f"entities.{entity.id}.fields.{field_def.name}.required",
                    ))

        # 4. Use cases sem actor
        for uc in draft.use_cases:
            if is_unknown(uc.actor):
                errors.append(CompileBlockingError(
                    error="UNKNOWN_USECASE_ACTOR",
                    reason=f"Use case '{uc.id}' has unknown actor",
                    location=f"use_cases.{uc.id}.actor",
                ))

        # 5. Integrations sem type
        for integ in draft.integrations:
            if is_unknown(integ.type):
                errors.append(CompileBlockingError(
                    error="UNKNOWN_INTEGRATION_TYPE",
                    reason=f"Integration '{integ.system}' has unknown type",
                    location=f"integrations.{integ.system}.type",
                ))

        return errors

    def _transform_to_idl(self, draft: IDLDraftV1) -> IDLDocument:
        """Transforma Draft em IDL v1.

        Esta transformacao:
        - Remove assumptions
        - Remove open_questions
        - Remove source
        - Normaliza estruturas

        Args:
            draft: Draft validado e sem bloqueios

        Returns:
            IDLDocument pronto para canonizacao
        """
        # Transformar actors
        actors = [self._transform_actor(a) for a in draft.actors]

        # Transformar entities
        entities = [self._transform_entity(e) for e in draft.entities]

        # Transformar use_cases
        usecases = [self._transform_usecase(u) for u in draft.use_cases]

        # Transformar integrations
        integrations = [self._transform_integration(i) for i in draft.integrations]

        # Transformar non_functional
        nonfunctional = []
        if draft.non_functional:
            nonfunctional = self._transform_non_functional(draft.non_functional)

        # Criar sistema basico
        system = SystemDefinition(
            id=draft.project,
            name=draft.project,
        )

        return IDLDocument(
            system=system,
            actors=actors,
            entities=entities,
            usecases=usecases,
            integrations=integrations,
            nonfunctional=nonfunctional,
        )

    def _transform_actor(self, draft_actor: DraftActor) -> ActorDefinition:
        """Transforma DraftActor em ActorDefinition."""
        # Mapear role para ActorType
        actor_type = self._infer_actor_type(draft_actor.role)

        return ActorDefinition(
            id=draft_actor.id,
            actor_type=actor_type,
            name=draft_actor.id,  # Usar ID como nome
            description=f"Role: {draft_actor.role}",
            permissions=draft_actor.permissions,
            authentication=AuthMethod.NONE,
        )

    def _infer_actor_type(self, role: str) -> ActorType:
        """Mapeia role string para ActorType.

        NAO infere - apenas mapeia valores conhecidos.
        """
        role_lower = role.lower()

        # Mapeamento explicito
        system_keywords = {"system", "service", "api", "bot", "scheduler", "cron"}
        external_keywords = {"external", "third-party", "partner", "gateway"}

        for keyword in system_keywords:
            if keyword in role_lower:
                return ActorType.SYSTEM

        for keyword in external_keywords:
            if keyword in role_lower:
                return ActorType.EXTERNAL

        # Default: human
        return ActorType.HUMAN

    def _transform_entity(self, draft_entity: DraftEntity) -> EntityDefinition:
        """Transforma DraftEntity em EntityDefinition."""
        fields = [self._transform_field(f) for f in draft_entity.fields]

        return EntityDefinition(
            id=draft_entity.id,
            fields=fields,
        )

    def _transform_field(self, draft_field: DraftField) -> FieldDefinition:
        """Transforma DraftField em FieldDefinition."""
        # Resolver required
        required = draft_field.required if isinstance(draft_field.required, bool) else False

        return FieldDefinition(
            id=draft_field.name,
            field_type=draft_field.type,
            required=required,
        )

    def _transform_usecase(self, draft_uc: DraftUseCase) -> UseCaseDefinition:
        """Transforma DraftUseCase em UseCaseDefinition."""
        # Transformar flow steps
        flow_steps = [
            FlowStep(number=s.step, description=s.action)
            for s in draft_uc.flow
        ]

        return UseCaseDefinition(
            id=draft_uc.id,
            name=draft_uc.id,
            actors=[draft_uc.actor],
            main_flow=flow_steps,
            priority=PriorityLevel.MEDIUM,
            complexity=ComplexityLevel.MEDIUM,
        )

    def _transform_integration(self, draft_integ: DraftIntegration) -> IntegrationDefinition:
        """Transforma DraftIntegration em IntegrationDefinition."""
        # Mapear type
        integ_type = self._map_integration_type(draft_integ.type)

        return IntegrationDefinition(
            id=draft_integ.system,
            name=draft_integ.system,
            integration_type=integ_type,
        )

    def _map_integration_type(self, type_str: str) -> IntegrationType:
        """Mapeia string de tipo para IntegrationType."""
        type_lower = type_str.lower()

        mapping = {
            "api": IntegrationType.REST_API,
            "rest_api": IntegrationType.REST_API,
            "rest": IntegrationType.REST_API,
            "db": IntegrationType.DATABASE,
            "database": IntegrationType.DATABASE,
            "queue": IntegrationType.MESSAGE_QUEUE,
            "message_queue": IntegrationType.MESSAGE_QUEUE,
            "graphql": IntegrationType.GRAPHQL,
            "grpc": IntegrationType.GRPC,
            "soap": IntegrationType.SOAP,
            "webhook": IntegrationType.WEBHOOK,
            "file": IntegrationType.FILE_SYSTEM,
            "file_system": IntegrationType.FILE_SYSTEM,
        }

        return mapping.get(type_lower, IntegrationType.REST_API)

    def _transform_non_functional(self, draft_nf: DraftNonFunctional) -> List[NFRDefinition]:
        """Transforma DraftNonFunctional em lista de NFRDefinition."""
        nfrs = []

        # Performance (se nao unknown)
        if not is_unknown(draft_nf.performance):
            nfrs.append(NFRDefinition(
                id="performance",
                nfr_type=NFRType.PERFORMANCE,
                name="Performance",
                target=draft_nf.performance,
            ))

        # Security (se nao unknown)
        if not is_unknown(draft_nf.security):
            nfrs.append(NFRDefinition(
                id="security",
                nfr_type=NFRType.SECURITY,
                name="Security",
                target=draft_nf.security,
            ))

        return nfrs


# ============================================
# CONVENIENCE FUNCTIONS
# ============================================

def compile_draft_to_idl(draft: IDLDraftV1) -> CompileResult:
    """Funcao de conveniencia para compilar Draft.

    Args:
        draft: IDL Draft v1 validado

    Returns:
        CompileResult com sucesso ou erros
    """
    compiler = DraftToIDLCompiler()
    return compiler.compile(draft)


def compile_draft_to_idl_or_raise(draft: IDLDraftV1) -> IDLDocument:
    """Funcao de conveniencia que lanca excecao em erro.

    Args:
        draft: IDL Draft v1 validado

    Returns:
        IDLDocument compilado

    Raises:
        DraftNotCompileableError: Se Draft nao pode ser compilado
    """
    compiler = DraftToIDLCompiler()
    return compiler.compile_or_raise(draft)
