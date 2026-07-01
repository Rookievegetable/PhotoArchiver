"""
PhotoArchiver Bootstrap Script

Author : Xing Liu
Version: 1.0

功能：

✓ 创建项目目录
✓ 创建 __init__.py
✓ 创建基础配置文件
✓ 创建 README
✓ 创建 requirements
✓ 创建空日志目录
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# -----------------------------
# 目录
# -----------------------------

DIRECTORIES = [
    ".github/workflows",

    ".trae/context",
    ".trae/rules",
    ".trae/templates",
    ".trae/prompts",
    ".trae/checklists",

    ".ai/architecture",
    ".ai/business",
    ".ai/conventions",
    ".ai/decisions",
    ".ai/examples",
    ".ai/prompts",
    ".ai/rules",
    ".ai/templates",

    "config/settings",
    "config/logging",
    "config/themes",

    "docs",

    "requirements",

    "resources/icons",
    "resources/images",
    "resources/ui",
    "resources/fonts",
    "resources/styles",

    "scripts",

    "src/app",
    "src/application",
    "src/domain",
    "src/infrastructure",
    "src/presentation",
    "src/ai",
    "src/common",
    "src/plugins",
    "src/workers",

    "tests/unit",
    "tests/integration",
    "tests/resources",

    "models",

    "logs",

    "data",

    "tools",
]

# -----------------------------
# Python Package
# -----------------------------

PACKAGES = [
    "src",
    "src/app",
    "src/application",
    "src/domain",
    "src/infrastructure",
    "src/presentation",
    "src/ai",
    "src/common",
    "src/plugins",
    "src/workers",

    "tests",
    "tests/unit",
    "tests/integration",
]

# -----------------------------
# 文件模板
# -----------------------------

FILES = {
    "README.md": "# PhotoArchiver\n\n企业级照片智能归档系统\n",

    ".gitignore": """
.venv/
.idea/
.vscode/
__pycache__/
*.pyc
*.pyo
*.pyd

dist/
build/

logs/
data/

.env
""",

    ".editorconfig": """
root = true

[*]
charset = utf-8
indent_style = space
indent_size = 4
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
""",

    "requirements/base.txt": """PySide6
pandas
openpyxl
opencv-python
Pillow
insightface
onnxruntime
SQLAlchemy
alembic
loguru
watchdog
pydantic-settings
""",

    "requirements/dev.txt": """-r base.txt

black
ruff
isort
mypy
pytest
pytest-qt
pre-commit
""",

    "main.py": """from PySide6.QtWidgets import QApplication, QMainWindow
import sys

app = QApplication(sys.argv)

window = QMainWindow()
window.setWindowTitle("PhotoArchiver")
window.resize(1200, 800)
window.show()

sys.exit(app.exec())
""",

    "pyproject.toml": """
[tool.black]
line-length = 100

[tool.ruff]
line-length = 100

[tool.isort]
profile = "black"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.11"
"""
}

# -----------------------------
# 创建目录
# -----------------------------


def create_directories():
    for directory in DIRECTORIES:
        path = ROOT / directory
        path.mkdir(parents=True, exist_ok=True)
        print(f"📁 {directory}")


# -----------------------------
# 创建 __init__.py
# -----------------------------


def create_packages():
    for package in PACKAGES:
        init_file = ROOT / package / "__init__.py"

        if not init_file.exists():
            init_file.write_text(
                '"""Package"""\n',
                encoding="utf-8",
            )

        print(f"🐍 {package}")


# -----------------------------
# 创建文件
# -----------------------------


def create_files():
    for filename, content in FILES.items():
        file = ROOT / filename

        file.parent.mkdir(parents=True, exist_ok=True)

        if not file.exists():
            file.write_text(content.strip() + "\n", encoding="utf-8")

        print(f"📄 {filename}")


# -----------------------------
# main
# -----------------------------


def main():

    print("=" * 60)
    print("PhotoArchiver Bootstrap")
    print("=" * 60)

    create_directories()

    create_packages()

    create_files()

    print()
    print("Bootstrap Finished ✅")


if __name__ == "__main__":
    main()