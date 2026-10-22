#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de validación de sincronización de módulos MBA Consultings
Compara versiones en código vs servidores Odoo
"""

import json
import sys
from datetime import datetime
from typing import Dict, Tuple

# VERSIONES EN CÓDIGO (Fuente de verdad)
EXPECTED_VERSIONS = {
    "mba_pa_base": "18.0.1.0.2",
    "mba_pa_edi": "18.0.1.0.3",
    "mba_pa_products": "18.0.1.0.0",
    "mba_pa_sale": "18.0.1.0.11",
    "mba_pa_edi_hka": "18.0.1.0.5",
    "mba_pa_edi_digifact": "18.0.1.0.1",
    "mba_pa_pos": "18.0.1.0.3",
}

# VERSIONES EN SERVIDORES (Actualizar según Odoo UI)
SERVER_VERSIONS = {
    "odoo18demo.mbaconsultings.com": {
        "mba_pa_base": "18.0.1.0.2",
        "mba_pa_edi": "18.0.1.0.2",  # ⚠️ DESINCRONIZADO
        "mba_pa_products": "18.0.1.0.0",
        "mba_pa_sale": "18.0.1.0.11",
        "mba_pa_edi_hka": "18.0.1.0.5",
        "mba_pa_edi_digifact": None,
        "mba_pa_pos": None,
    },
    "demo-simplificati.mbaconsultings.com": {
        "mba_pa_base": "18.0.1.0.2",
        "mba_pa_edi": "18.0.1.0.3",
        "mba_pa_products": "18.0.1.0.0",
        "mba_pa_sale": "18.0.1.0.11",
        "mba_pa_edi_hka": "18.0.1.0.5",
        "mba_pa_edi_digifact": None,
        "mba_pa_pos": None,
    },
}


class SyncValidator:
    """Valida sincronización de versiones entre código y servidores"""

    def __init__(self):
        self.results = {}
        self.desync_count = 0
        self.sync_count = 0

    def validate_server(self, server_name: str, server_versions: Dict) -> Dict:
        """Valida un servidor específico"""
        print(f"\n{'='*70}")
        print(f"🔍 VALIDANDO: {server_name}")
        print(f"{'='*70}")

        server_result = {
            "server": server_name,
            "timestamp": datetime.now().isoformat(),
            "modules": {},
            "summary": {"sync": 0, "desync": 0, "missing": 0}
        }

        for module, expected_version in EXPECTED_VERSIONS.items():
            actual_version = server_versions.get(module)

            if actual_version is None:
                status = "MISSING"
                symbol = "⚫"
                color = ""
            elif actual_version == expected_version:
                status = "SYNC"
                symbol = "✅"
                self.sync_count += 1
                server_result["summary"]["sync"] += 1
                color = ""
            else:
                status = "DESYNC"
                symbol = "❌"
                self.desync_count += 1
                server_result["summary"]["desync"] += 1
                color = " 🔴 ACTUALIZAR"

            print(f"{symbol} {module:<30} Esperado: {expected_version:<15} | Actual: {str(actual_version):<15}{color}")

            server_result["modules"][module] = {
                "expected": expected_version,
                "actual": actual_version,
                "status": status
            }

            if status == "MISSING":
                server_result["summary"]["missing"] += 1

        return server_result

    def generate_report(self):
        """Genera reporte de validación"""
        print(f"\n\n{'='*70}")
        print("📊 REPORTE DE SINCRONIZACIÓN - mba-facturacion-panama")
        print(f"{'='*70}\n")

        all_results = {}

        for server_name, versions in SERVER_VERSIONS.items():
            result = self.validate_server(server_name, versions)
            all_results[server_name] = result

        # Resumen
        print(f"\n\n{'='*70}")
        print("📋 RESUMEN EJECUTIVO")
        print(f"{'='*70}\n")

        for server_name, result in all_results.items():
            summary = result["summary"]
            total = summary["sync"] + summary["desync"] + summary["missing"]

            if summary["desync"] == 0 and summary["missing"] == 0:
                status_icon = "✅"
                status_text = "SINCRONIZADO"
            else:
                status_icon = "⚠️"
                status_text = "DESINCRONIZADO"

            print(f"{status_icon} {server_name}")
            print(f"   Sincronizados: {summary['sync']}/{total}")
            print(f"   Desincronizados: {summary['desync']}")
            print(f"   No instalados: {summary['missing']}\n")

        # Recomendaciones
        print(f"{'='*70}")
        print("🎯 RECOMENDACIONES")
        print(f"{'='*70}\n")

        if self.desync_count > 0:
            print("🔴 ACCIÓN REQUERIDA:\n")
            for server_name, result in all_results.items():
                desync_modules = [
                    (m, v["expected"], v["actual"])
                    for m, v in result["modules"].items()
                    if v["status"] == "DESYNC"
                ]
                if desync_modules:
                    print(f"   {server_name}:")
                    for module, expected, actual in desync_modules:
                        print(f"      • {module}: actualizar de {actual} a {expected}")
                    print()
        else:
            print("✅ Todos los servidores están sincronizados.\n")

        # JSON para integración
        print(f"{'='*70}")
        print("📤 SALIDA JSON (para automatización)")
        print(f"{'='*70}\n")
        print(json.dumps(all_results, indent=2))

        return all_results


if __name__ == "__main__":
    validator = SyncValidator()
    validator.generate_report()

    # Exit code
    sys.exit(1 if validator.desync_count > 0 else 0)
