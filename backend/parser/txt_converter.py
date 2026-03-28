"""
Agentic GraphRAG - TXT to Markdown Converter + File Filter

Конвертирует .txt файлы в .md с базовой структурой.
Фильтрует мусорные файлы (бинари, кэши, логи сборки).
"""

import os
import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

# C/C++ код — парсится через Tree-sitter (жёсткие связи AST)
CPP_CODE_EXTENSIONS = {'.cpp', '.h', '.hpp', '.cc', '.c', '.cxx', '.hxx', '.inl'}

# Код на других языках — парсится как DOCUMENT (пока без AST)
OTHER_CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.rb',
    '.cs', '.swift', '.kt', '.scala', '.lua', '.r', '.m', '.mm',
    '.php', '.pl', '.pm', '.sh', '.bash', '.zsh', '.bat', '.ps1', '.cmd',
    '.sql', '.html', '.htm', '.css', '.scss', '.sass', '.less',
    '.xml', '.xsl', '.xslt', '.svg',  # SVG как код, не как картинка
}

# Структурированные данные и конфиги
DATA_EXTENSIONS = {
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
    '.env', '.properties', '.editorconfig',
    '.csv', '.tsv',
}

# Документация
DOC_EXTENSIONS = {
    '.md', '.markdown', '.txt', '.rst', '.adoc', '.asciidoc',
    '.tex', '.latex', '.org',
}

# Логи и прочий текст
LOG_EXTENSIONS = {'.log'}

# Файлы без расширения которые часто текстовые
KNOWN_TEXTFILES = {
    'Makefile', 'Dockerfile', 'Vagrantfile', 'Jenkinsfile', 'Procfile',
    'README', 'LICENSE', 'CHANGELOG', 'CONTRIBUTING', 'AUTHORS',
    'CMakeLists.txt', '.clang-format', '.clang-tidy',
    'requirements.txt', 'Pipfile', 'Gemfile', 'Cargo.toml',
    'package.json', 'tsconfig.json', 'docker-compose.yml',
}

# Все текстовые расширения (объединение)
ALL_TEXT_EXTENSIONS = (
    CPP_CODE_EXTENSIONS | OTHER_CODE_EXTENSIONS |
    DATA_EXTENSIONS | DOC_EXTENSIONS | LOG_EXTENSIONS
)

# Мусорные паттерны — пропускаем целиком
SKIP_DIRS = {
    '__pycache__', '.git', '.svn', '.hg', 'node_modules',
    '.vs', '.vscode', '.idea',
    'Debug', 'Release', 'x64', 'x86', '.cache',
    'bin', 'obj', 'dist', '.gradle', 'target',
}

SKIP_FILES = {
    '.gitignore', '.gitmodules', '.gitattributes',
    'Thumbs.db', '.DS_Store', 'desktop.ini',
}

# Бинарные / сгенерированные расширения
BINARY_EXTENSIONS = {
    # Compiled
    '.exe', '.dll', '.so', '.dylib', '.o', '.obj', '.a', '.lib',
    '.pdb', '.ilk', '.exp', '.pch', '.gch', '.pyc', '.class', '.wasm',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
    '.tiff', '.tif', '.psd', '.ai', '.eps', '.raw', '.cr2', '.nef',
    # Video
    '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v',
    '.mpg', '.mpeg', '.3gp', '.ts',
    # Audio
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus',
    # Archives
    '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', '.xz', '.zst',
    # Documents (binary)
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp',
    # Databases
    '.db', '.sqlite', '.sqlite3', '.mdb',
    # Fonts
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    # Other
    '.iso', '.dmg', '.apk', '.ipa', '.deb', '.rpm',
}


def should_skip_dir(dirname: str) -> bool:
    """Проверка что директорию нужно пропустить"""
    return dirname in SKIP_DIRS or dirname.startswith('.')


def should_skip_file(filename: str) -> bool:
    """Проверка что файл нужно пропустить"""
    if filename in SKIP_FILES:
        return True
    _, ext = os.path.splitext(filename)
    if ext.lower() in BINARY_EXTENSIONS:
        return True
    return False


def is_valid_text_file(filepath: str, max_size_mb: float = 5.0) -> bool:
    """Проверка что файл — валидный текстовый и не слишком большой"""
    try:
        size = os.path.getsize(filepath)
        if size == 0 or size > max_size_mb * 1024 * 1024:
            return False
        # Пробуем прочитать начало как текст
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            # Если больше 30% нечитаемых байт — бинарник
            non_text = sum(1 for b in chunk if b < 8 or (b > 13 and b < 32))
            if len(chunk) > 0 and non_text / len(chunk) > 0.3:
                return False
    except Exception:
        return False
    return True


def txt_to_markdown(filepath: str) -> str:
    """
    Конвертация .txt в Markdown с базовой структурой.

    Логика:
    - Первая непустая строка → # Заголовок
    - Строки CAPSLOCK → ## Подзаголовок
    - Строки начинающиеся с - или * → списки (оставляем как есть)
    - Всё остальное → параграфы
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.split('\n')
    result = []
    title_set = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            result.append('')
            continue

        # Первая непустая строка → заголовок
        if not title_set:
            result.append(f'# {stripped}')
            title_set = True
            continue

        # Строки полностью в CAPS (>5 символов) → подзаголовок
        if len(stripped) > 5 and stripped.upper() == stripped and stripped.isalpha():
            result.append(f'\n## {stripped.title()}')
            continue

        # Строки с разделителями (===, ---, ***) → горизонтальная линия
        if re.match(r'^[=\-*]{3,}$', stripped):
            result.append('---')
            continue

        result.append(stripped)

    return '\n'.join(result)


def scan_and_filter(root_dir: str) -> dict:
    """
    Сканирование директории с умной фильтрацией.

    Принцип: всё что текстовое — принимаем, бинарное — отсекаем.
    Даже неизвестные расширения проверяем на текстовость.

    Returns:
        {
            "cpp_files": [...],       # C++ → Tree-sitter AST
            "doc_files": [...],       # .md, .rst и т.д. → DOCUMENT
            "txt_files": [...],       # .txt → конвертируем в .md
            "other_text": [...],      # .py, .json, .yaml, .log и т.д. → DOCUMENT
            "skipped": [...],
            "stats": {total_scanned, accepted, filtered, by_category}
        }
    """
    cpp_files = []
    doc_files = []
    txt_files = []
    other_text = []
    skipped = []
    total = 0

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for filename in files:
            total += 1
            filepath = os.path.join(root, filename)

            if should_skip_file(filename):
                skipped.append(filepath)
                continue

            _, ext = os.path.splitext(filename)
            ext = ext.lower()

            # Бинарные — сразу отсекаем
            if ext in BINARY_EXTENSIONS:
                skipped.append(filepath)
                continue

            # Проверяем что файл реально текстовый и не слишком большой
            if not is_valid_text_file(filepath):
                skipped.append(filepath)
                continue

            # Классификация
            if ext in CPP_CODE_EXTENSIONS:
                cpp_files.append(filepath)
            elif ext == '.txt':
                txt_files.append(filepath)
            elif ext in DOC_EXTENSIONS:
                doc_files.append(filepath)
            elif ext in OTHER_CODE_EXTENSIONS | DATA_EXTENSIONS | LOG_EXTENSIONS:
                other_text.append(filepath)
            elif filename in KNOWN_TEXTFILES:
                other_text.append(filepath)
            elif ext == '' or ext not in BINARY_EXTENSIONS:
                # Неизвестное расширение — но прошло проверку is_valid_text_file
                # Значит это текст → принимаем как документ
                other_text.append(filepath)

    accepted = len(cpp_files) + len(doc_files) + len(txt_files) + len(other_text)
    return {
        "cpp_files": cpp_files,
        "code_files": cpp_files,  # backward compat
        "doc_files": doc_files,
        "txt_files": txt_files,
        "other_text": other_text,
        "skipped": skipped,
        "stats": {
            "total_scanned": total,
            "accepted": accepted,
            "filtered": len(skipped),
            "by_category": {
                "cpp": len(cpp_files),
                "docs": len(doc_files),
                "txt": len(txt_files),
                "other_text": len(other_text),
            }
        }
    }


def convert_txt_files(txt_files: List[str], output_dir: str = None, source_root: str = None) -> List[str]:
    """
    Конвертирует .txt файлы в .md.
    Возвращает пути к созданным .md файлам.

    Если output_dir указан — сохраняет структуру папок внутри него
    (избегает коллизий имён из разных поддиректорий).
    Если output_dir не указан — создаёт .md рядом с .txt.
    """
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    created = []
    for txt_path in txt_files:
        try:
            md_content = txt_to_markdown(txt_path)
            if output_dir:
                # Сохраняем структуру папок: /app/Project/src/foo.txt → /tmp/conv/src/foo.md
                if source_root:
                    rel = os.path.relpath(txt_path, source_root)
                else:
                    rel = os.path.basename(txt_path)
                md_rel = os.path.splitext(rel)[0] + '.md'
                md_path = os.path.join(output_dir, md_rel)
                os.makedirs(os.path.dirname(md_path), exist_ok=True)
            else:
                md_path = os.path.splitext(txt_path)[0] + '.md'

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            created.append(md_path)
            logger.info(f"Converted: {txt_path} → {md_path}")
        except Exception as e:
            logger.error(f"Failed to convert {txt_path}: {e}")

    return created
