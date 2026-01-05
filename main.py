#!/usr/bin/env python3
"""Demo CLI para o Bazari Engine v1.0.0.

Uso:
    # Gerar apenas artefatos
    python main.py --project demo --input "Sistema de cadastro" --skip-build

    # Gerar com build
    python main.py --project demo --input "Sistema de cadastro"

    # Release mode (docker compose up + smoke tests)
    python main.py --project demo --input "Sistema de cadastro" --release

Demo FINAL:
    python main.py --project demo --input "Quero um sistema de cadastro de empresas com nome, cnpj e endereço" --release

O resultado será:
    - /home/bazari/generated/demo/
    - backend compiles
    - frontend compiles
    - docker-compose.yml exists
    - Smoke tests PASS
    - Sistema rodando

Regras absolutas:
    1. O motor nunca se auto-modifica (/home/bazari/engine/**)
    2. Templates nunca são alterados (/home/bazari/templates/**)
    3. Tudo que é gerado vai para /home/bazari/generated/
"""

import argparse
import sys
from pathlib import Path

from orchestrator.engine import Engine
from version import __version__, version_string
from release.release_report import ReleaseReportGenerator
from release.release_checklist import ReleaseChecklist
from release.diagnostic_report import DiagnosticReportGenerator


def parse_args() -> argparse.Namespace:
    """Parse argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description=f"Bazari Engine v{__version__} - Gerador de aplicações",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
    python main.py --project demo --input "Sistema de cadastro de empresas"
    python main.py --project crm --input "CRM com clientes e vendas" --title "Sistema CRM"
    python main.py --project demo --input "..." --skip-build
    python main.py --project demo --input "..." --release
        """,
    )

    parser.add_argument(
        "--project",
        required=True,
        help="Nome do projeto (ex: demo, crm, erp)",
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Descrição do sistema a ser gerado",
    )

    parser.add_argument(
        "--title",
        default=None,
        help="Título do sistema (opcional)",
    )

    parser.add_argument(
        "--store-root",
        default="/home/bazari/engine/demo_store",
        help="Diretório para armazenar artefatos (default: ./demo_store)",
    )

    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Pular fase de build (apenas gerar artefatos)",
    )

    parser.add_argument(
        "--release",
        action="store_true",
        help="Modo release: docker compose up + smoke tests",
    )

    parser.add_argument(
        "--clean-on-fail",
        action="store_true",
        help="Remove repo em caso de falha (padrão: preservar em _failed/)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Modo silencioso (não imprime resumo)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=version_string(),
    )

    return parser.parse_args()


def print_release_report(report: dict, quiet: bool = False) -> None:
    """Imprime o release report formatado."""
    if quiet:
        return

    print()
    print("=" * 60)
    print("RELEASE REPORT")
    print("=" * 60)
    print()

    status = "SUCCESS" if report["success"] else "FAILED"
    print(f"Status: {status}")
    print(f"Engine: Bazari Engine v{report['engine_version']}")
    print()

    print("System Summary:")
    metrics = report["metrics"]
    print(f"  - Requirements: {metrics['requirements_count']}")
    print(f"  - Entities: {metrics['entities_count']}")
    print(f"  - API Operations: {metrics['operations_count']}")
    print(f"  - Tasks: {metrics['tasks_count']}")
    print(f"  - Patches: {metrics['patch_count']}")
    print()

    print("Artifacts:")
    artifacts = report["artifacts"]
    print(f"  - SRS: v{artifacts['srs_version']}")
    print(f"  - IR: v{artifacts['ir_version']}")
    print(f"  - OpenAPI: v{artifacts['oas_version']}")
    print(f"  - RBAC: v{artifacts['rbac_version']}")
    print(f"  - PLAN: v{artifacts['plan_version']}")
    print()

    print("Build:")
    build = report["build"]
    print(f"  - Status: {'OK' if build['build_ok'] else 'FAILED'}")
    print(f"  - Fix Attempts: {build['fix_attempts']}")
    print(f"  - Fixes Applied: {build['fixes_applied']}")
    print()

    print("Release:")
    release = report["release"]
    print(f"  - Docker Compose: {'OK' if release['docker_compose_ok'] else 'FAILED'}")
    print(f"  - Services: {', '.join(release['services_running']) if release['services_running'] else 'None'}")
    print(f"  - Smoke Tests: {'OK' if release['smoke_ok'] else 'FAILED'} ({release['smoke_passed']}/{release['smoke_passed'] + release['smoke_failed']})")
    print()

    print("Paths:")
    print(f"  - Repository: {report['repo_path']}")
    print(f"  - Store: {report['store_path']}")
    print()

    print("Commands:")
    commands = report["commands"]
    print(f"  Start:   {commands['start']}")
    print(f"  Stop:    {commands['stop']}")
    print(f"  Logs:    {commands['logs']}")
    print(f"  Status:  {commands['status']}")
    print()

    if report["errors"]:
        print("Errors:")
        for error in report["errors"][:5]:
            print(f"  - {error}")
        print()

    print("=" * 60)


def main() -> int:
    """Ponto de entrada principal."""
    args = parse_args()

    # Criar Engine
    if not args.quiet:
        print(f"Bazari Engine v{__version__} - Gerando projeto: {args.project}")
        print(f"Store: {args.store_root}")
        print(f"Input: {args.input[:50]}...")
        print()

    engine = Engine(args.store_root)

    # Executar pipeline baseado no modo
    if args.release:
        # Modo release: docker compose up + smoke tests
        if not args.quiet:
            print("Modo RELEASE: docker compose up + smoke tests")
            print()
        result = engine.run_release(
            project=args.project,
            raw_input=args.input,
            title=args.title,
            enable_fix_loop=True,
        )
    elif args.skip_build:
        # Modo skip-build: apenas artefatos
        if not args.quiet:
            print("Modo skip-build: apenas artefatos serao gerados")
        result = engine.run_with_build(
            project=args.project,
            raw_input=args.input,
            title=args.title,
            skip_build=True,
        )
    else:
        # Modo build: gerar + compilar
        if not args.quiet:
            print("Executando pipeline completo com build...")
        result = engine.run_with_build(
            project=args.project,
            raw_input=args.input,
            title=args.title,
            skip_build=False,
        )

    # Mostrar resultado
    if not args.quiet:
        print()
        print(result.summary())

    # Mostrar info do blueprint
    if not args.quiet:
        print()
        blueprint_status = "GENERIC (FORCED)" if result.blueprint_forced_generic else result.blueprint_type.upper()
        print(f"Blueprint: {blueprint_status}")

    # Para modo release, gerar release report
    if args.release:
        # Executar checklist
        checklist = ReleaseChecklist(
            store_root=args.store_root,
            generated_root=engine.GENERATED_ROOT,
        )
        checklist_result = checklist.run(args.project, result.to_dict())

        # Gerar report
        report_generator = ReleaseReportGenerator(
            store_root=args.store_root,
            generated_root=engine.GENERATED_ROOT,
        )
        report_data = report_generator.generate_and_save(
            project=args.project,
            run_result=result.to_dict(),
            checklist_result=checklist_result.to_dict(),
        )

        # Imprimir release report
        print_release_report(report_data["report"], args.quiet)

        if not args.quiet:
            print(f"Release reports saved:")
            print(f"  - JSON: {report_data['files']['json']}")
            print(f"  - Markdown: {report_data['files']['markdown']}")

        # Gerar diagnostic report APENAS se falhou
        if not result.success:
            diagnostic_generator = DiagnosticReportGenerator(
                store_root=args.store_root,
                generated_root=engine.GENERATED_ROOT,
            )
            diagnostic_data = diagnostic_generator.generate_and_save(
                project=args.project,
                run_result=result.to_dict(),
            )
            if diagnostic_data and not args.quiet:
                print(f"  - Diagnostic: {diagnostic_data['markdown']}")

        if not args.quiet:
            print()

    # Verificar resultado final
    if result.success:
        if not args.quiet:
            print()
            print("Pipeline concluido com sucesso!")

            if result.repo_path:
                repo_path = Path(result.repo_path)

                print()
                print(f"Projeto gerado em: {result.repo_path}")

                # Verificar estrutura
                if (repo_path / "backend").exists():
                    print("  - backend/ existe")
                if (repo_path / "frontend").exists():
                    print("  - frontend/ existe")
                if (repo_path / "database").exists():
                    print("  - database/ existe")
                if (repo_path / "docker-compose.yml").exists():
                    print("  - docker-compose.yml existe")

                print()
                print("Estatisticas:")
                print(f"  - Artefatos: SRS v{result.srs_version}, IR v{result.ir_version}, OAS v{result.oas_version}, RBAC v{result.rbac_version}, PLAN v{result.plan_version}")
                print(f"  - Patches aplicados: {result.patch_count}")
                print(f"  - Build: {'OK' if result.build_ok else 'FAILED'}")
                print(f"  - Status final: {result.final_status}")

                # Mostrar info do release mode
                if result.release_mode:
                    print()
                    print("Release Mode:")
                    print(f"  - Docker Compose: {'OK' if result.docker_compose_ok else 'FAILED'}")
                    if result.services_running:
                        print(f"  - Services: {', '.join(result.services_running)}")
                    print(f"  - Smoke Tests: {'OK' if result.smoke_ok else 'FAILED'} ({result.smoke_passed}/{result.smoke_passed + result.smoke_failed})")

                # Mostrar info do Fix Loop se foi usado
                if result.fix_attempts > 0:
                    print()
                    print("Fix Loop:")
                    print(f"  - Tentativas: {result.fix_attempts}")
                    print(f"  - Fixes aplicados: {len(result.fixes_applied)}")
                    for fix in result.fixes_applied[:3]:
                        desc = fix.get('description', 'unknown fix')
                        print(f"    - {desc}")

            else:
                print("Artefatos gerados (sem build):")
                print(f"  - SRS: v{result.srs_version}")
                print(f"  - IR: v{result.ir_version}")
                print(f"  - OAS: v{result.oas_version}")
                print(f"  - RBAC: v{result.rbac_version}")
                print(f"  - PLAN: v{result.plan_version}")

        return 0

    else:
        if not args.quiet:
            print()
            print("Pipeline falhou!")

            if result.errors:
                print()
                print("Erros:")
                for error in result.errors:
                    print(f"  - {error}")

            if result.build_errors:
                print()
                print("Erros de build:")
                for error in result.build_errors[:5]:  # Limitar a 5 erros
                    print(f"  - {error}")
                if len(result.build_errors) > 5:
                    print(f"  ... e mais {len(result.build_errors) - 5} erros")

            if result.questions:
                print()
                print("Perguntas pendentes:")
                for q in result.questions:
                    print(f"  ? {q}")

            # Mostrar info do Fix Loop se foi usado
            if result.fix_attempts > 0:
                print()
                print("Fix Loop tentou corrigir:")
                print(f"  - Tentativas: {result.fix_attempts}")
                print(f"  - Fixes aplicados: {len(result.fixes_applied)}")
                if result.fix_loop_aborted_reason:
                    print(f"  - Razao do abort: {result.fix_loop_aborted_reason}")

            # Mostrar onde o repo foi preservado
            if result.failed_repo_path:
                print()
                print(f"Repo preservado em: {result.failed_repo_path}")

        # Se --clean-on-fail foi passado, remover o repo após salvar evidências
        if args.clean_on_fail and result.failed_repo_path:
            import shutil
            failed_path = Path(result.failed_repo_path)
            if failed_path.exists():
                if not args.quiet:
                    print(f"Removendo repo (--clean-on-fail): {failed_path}")
                shutil.rmtree(failed_path)

        return 1


if __name__ == "__main__":
    sys.exit(main())
