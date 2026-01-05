"""IDL Store - Persistencia e Contract Gate.

Este modulo implementa:
- Persistencia de documentos IDL em JSON e Markdown
- Contract Gate para validacao de integridade pos-save
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .idl_v1 import (
    IDL_SCHEMA_VERSION,
    HASHABLE_FIELDS,
    IDLDocument,
    IDLParser,
    compute_content_hash_sha256,
    extract_hashable_payload_from_canonical,
)


class IDLContractGateError(Exception):
    """Erro de Contract Gate - integridade comprometida."""
    pass


class IDLStore:
    """Store para documentos IDL com Contract Gate.

    Responsabilidades:
    - Salvar documentos IDL em JSON e Markdown
    - Validar integridade apos salvamento (Contract Gate)
    - Carregar e validar documentos existentes
    """

    def __init__(self, store_root: str):
        """Inicializa o store.

        Args:
            store_root: Diretorio raiz para armazenamento
        """
        self.store_root = Path(store_root)

    def save(
        self,
        document: IDLDocument,
        project: str,
        *,
        validate_gate: bool = True,
    ) -> Dict[str, str]:
        """Salva documento IDL e valida Contract Gate.

        Args:
            document: Documento IDL para salvar
            project: Nome do projeto (usado para nome do arquivo)
            validate_gate: Se True, valida Contract Gate apos salvar

        Returns:
            Dict com caminhos dos arquivos salvos:
            - json: caminho do arquivo JSON
            - markdown: caminho do arquivo Markdown

        Raises:
            IDLContractGateError: Se Contract Gate falhar
        """
        # Garante que diretorio existe
        idl_dir = self.store_root / "idl"
        idl_dir.mkdir(parents=True, exist_ok=True)

        # Gera timestamp para nome unico (com microsegundos para evitar colisoes)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base_name = f"{project}_{timestamp}"

        # Salva JSON
        json_path = idl_dir / f"{base_name}.json"
        json_content = document.to_json(indent=2)
        json_path.write_text(json_content, encoding='utf-8')

        # Salva Markdown
        md_path = idl_dir / f"{base_name}.md"
        md_content = document.to_markdown()
        md_path.write_text(md_content, encoding='utf-8')

        # Contract Gate
        if validate_gate:
            self._validate_contract_gate(json_path)

        return {
            "json": str(json_path),
            "markdown": str(md_path),
        }

    def load(self, json_path: str, *, validate_gate: bool = True) -> Dict[str, Any]:
        """Carrega documento IDL de JSON.

        Args:
            json_path: Caminho do arquivo JSON
            validate_gate: Se True, valida Contract Gate apos carregar

        Returns:
            Dicionario canonico do documento

        Raises:
            IDLContractGateError: Se Contract Gate falhar
            FileNotFoundError: Se arquivo nao existir
        """
        path = Path(json_path)

        with open(path, 'r', encoding='utf-8') as f:
            canonical = json.load(f)

        if validate_gate:
            self._validate_contract_gate_from_dict(canonical)

        return canonical

    def _validate_contract_gate(self, json_path: Path) -> None:
        """Valida Contract Gate lendo arquivo do disco.

        Recarrega o JSON e recalcula o hash para garantir integridade.

        Args:
            json_path: Caminho do arquivo JSON salvo

        Raises:
            IDLContractGateError: Se hash nao bater
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            loaded_canonical = json.load(f)

        self._validate_contract_gate_from_dict(loaded_canonical)

    def _validate_contract_gate_from_dict(self, canonical: Dict[str, Any]) -> None:
        """Valida Contract Gate a partir de dicionario canonico.

        Args:
            canonical: Dicionario canonico do documento

        Raises:
            IDLContractGateError: Se hash nao bater
        """
        # Extrai payload hashable
        hashable_payload = extract_hashable_payload_from_canonical(canonical)

        # Recalcula hash
        recalculated_hash = compute_content_hash_sha256(hashable_payload)

        # Compara com hash salvo
        saved_hash = canonical.get("content_hash_sha256", "")

        if recalculated_hash != saved_hash:
            raise IDLContractGateError(
                f"Contract Gate FAILED: hash mismatch. "
                f"Expected: {saved_hash}, "
                f"Recalculated: {recalculated_hash}"
            )

    def list_documents(self, project: Optional[str] = None) -> list:
        """Lista documentos IDL salvos.

        Args:
            project: Se fornecido, filtra por projeto

        Returns:
            Lista de caminhos de arquivos JSON
        """
        idl_dir = self.store_root / "idl"

        if not idl_dir.exists():
            return []

        pattern = f"{project}_*.json" if project else "*.json"
        return sorted([str(p) for p in idl_dir.glob(pattern)])

    def get_latest(self, project: str, *, validate_gate: bool = True) -> Optional[Dict[str, Any]]:
        """Retorna documento mais recente de um projeto.

        Args:
            project: Nome do projeto
            validate_gate: Se True, valida Contract Gate

        Returns:
            Dicionario canonico ou None se nao existir
        """
        docs = self.list_documents(project)

        if not docs:
            return None

        # Ultimo documento (ordenado por timestamp no nome)
        latest_path = docs[-1]

        return self.load(latest_path, validate_gate=validate_gate)

    def verify_all(self, project: Optional[str] = None) -> Dict[str, bool]:
        """Verifica integridade de todos documentos.

        Args:
            project: Se fornecido, filtra por projeto

        Returns:
            Dict com path -> True/False para cada documento
        """
        results = {}
        docs = self.list_documents(project)

        for doc_path in docs:
            try:
                self.load(doc_path, validate_gate=True)
                results[doc_path] = True
            except IDLContractGateError:
                results[doc_path] = False
            except Exception:
                results[doc_path] = False

        return results


def parse_and_save(
    source: str,
    project: str,
    store_root: str,
    *,
    contract_notes: Optional[str] = None,
) -> Dict[str, str]:
    """Funcao de conveniencia para parse + save.

    Args:
        source: Codigo fonte IDL
        project: Nome do projeto
        store_root: Diretorio raiz do store
        contract_notes: Notas opcionais (fora do hash)

    Returns:
        Dict com caminhos dos arquivos salvos
    """
    parser = IDLParser()
    document = parser.parse(source)

    if contract_notes:
        document.contract_notes = contract_notes

    store = IDLStore(store_root)
    return store.save(document, project)
