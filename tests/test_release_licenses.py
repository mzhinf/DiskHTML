"""最终发布包许可证识别和验证测试。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from unittest import TestCase


def _load_module() -> object:
    """直接加载独立发布辅助脚本，不依赖当前导入路径。"""

    root = Path(__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "release_licenses", root / "scripts" / "release_licenses.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseLicenseTests(TestCase):
    """保证许可证门禁保守且可独立复验。"""

    @classmethod
    def setUpClass(cls) -> None:
        """为所有隔离文件系统测试加载一次脚本。"""

        cls.module = _load_module()

    def test_native_runtime_definitions_keep_release_order(self) -> None:
        """声明式原生库规则必须保持许可证报告的既有顺序与来源字段。"""

        definitions = self.module._NATIVE_RUNTIME_COMPONENTS
        self.assertEqual(
            ["bzip2", "Expat", "libffi", "XZ Utils / liblzma", "mpdecimal", "zlib"],
            [definition.name for definition in definitions],
        )
        self.assertTrue(all(definition.patterns for definition in definitions))
        self.assertTrue(all(definition.source_name for definition in definitions))
        self.assertTrue(all(definition.output_name for definition in definitions))

    def test_missing_project_license_stops_generation_and_writes_audit(self) -> None:
        """构建不得臆造未由维护者提供的 DiskHTML 许可证。"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "DiskHTML"
            package.mkdir()
            (package / "DiskHTML.exe").write_bytes(b"placeholder")
            audit = root / "license-audit.json"

            with self.assertRaises(self.module.ReleaseLicenseError):
                self.module.build_license_bundle(package, root, audit)

            self.assertTrue(audit.is_file())
            self.assertFalse((package / "LICENSE.txt").exists())

    def test_tcl_tk_uses_license_from_final_package(self) -> None:
        """Tcl/Tk 必须优先使用最终包自带的 license.terms。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            internal = package / "_internal"
            license_file = internal / "_tk_data" / "license.terms"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Tcl/Tk license", encoding="utf-8")
            tcl_data = internal / "_tcl_data"
            tcl_data.mkdir()
            (tcl_data / "init.tcl").write_text(
                "package require -exact Tcl 8.6.12\\n", encoding="utf-8"
            )
            (internal / "_tkinter.pyd").write_bytes(b"placeholder")
            (internal / "tcl86t.dll").write_bytes(b"placeholder")

            components = self.module.discover_components(package)
            component = next(item for item in components if item.name == "Tcl/Tk Runtime")
            self.assertEqual("8.6.12", component.version)
            self.assertEqual(license_file, component.license_source)
            self.assertTrue(component.is_resolved)

    def test_residual_qt_runtime_blocks_release(self) -> None:
        """Tkinter 发布目录出现 Qt 文件时必须明确阻断。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            qt_file = package / "_internal" / "PySide6" / "Qt6Core.dll"
            qt_file.parent.mkdir(parents=True)
            qt_file.write_bytes(b"placeholder")

            components = self.module.discover_components(package)
            component = next(item for item in components if item.name == "Unexpected Qt Runtime")
            self.assertFalse(component.is_resolved)
            self.assertIn("必须清理", component.review_reason)

    def test_verifier_rejects_missing_notice_target(self) -> None:
        """每个 License File 引用都必须指向解压包内真实文件。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "licenses").mkdir()
            (package / "LICENSE.txt").write_text("project license", encoding="utf-8")
            (package / "THIRD-PARTY-NOTICES.txt").write_text(
                "License File:    licenses/missing.txt\n", encoding="utf-8"
            )

            with self.assertRaises(self.module.ReleaseLicenseError):
                self.module.verify_license_bundle(package)

    def test_verifier_accepts_matching_empty_component_inventory(self) -> None:
        """无第三方文件的测试包允许空声明与空 licenses 目录。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            (package / "licenses").mkdir()
            (package / "LICENSE.txt").write_text("project license", encoding="utf-8")
            (package / "THIRD-PARTY-NOTICES.txt").write_text(
                "THIRD-PARTY SOFTWARE NOTICES AND INFORMATION\n", encoding="utf-8"
            )

            self.module.verify_license_bundle(package)

    def test_verifier_rejects_unreferenced_license_file(self) -> None:
        """licenses 目录不得保留声明未引用的旧组件许可证。"""

        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            licenses = package / "licenses"
            licenses.mkdir()
            (licenses / "old-qt.txt").write_text("obsolete", encoding="utf-8")
            (package / "LICENSE.txt").write_text("project license", encoding="utf-8")
            (package / "THIRD-PARTY-NOTICES.txt").write_text(
                "THIRD-PARTY SOFTWARE NOTICES AND INFORMATION\n", encoding="utf-8"
            )

            with self.assertRaises(self.module.ReleaseLicenseError):
                self.module.verify_license_bundle(package)
