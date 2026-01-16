"""
AST-based Smart Chunker for Code RAG
=====================================
Uses tree-sitter to parse code into semantic units (functions, classes, methods).
Preserves parent context and extracts rich metadata.

Performance target: Process 500 files in < 30 seconds
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any
import logging

# tree-sitter imports (install: pip install tree-sitter tree-sitter-python tree-sitter-javascript)
try:
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    from tree_sitter import Language, Parser, Node
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    Parser = None
    Node = None

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """A semantic code chunk with rich metadata."""

    # Identity
    id: str                          # SHA256 hash for deduplication

    # Location
    file_path: str                   # Relative path from project root
    start_line: int                  # 1-indexed line number
    end_line: int                    # 1-indexed line number

    # Content
    chunk_type: str                  # "function", "class", "method", "module", "block"
    name: str                        # Function/class name or "module" for top-level
    text: str                        # Actual code content
    summary: Optional[str] = None    # LLM-generated summary (filled later)

    # Parent context
    parent_class: Optional[str] = None    # For methods: parent class name
    parent_context: Optional[str] = None  # Signature of parent (class definition)

    # Metadata
    imports: List[str] = field(default_factory=list)       # Import statements
    decorators: List[str] = field(default_factory=list)    # @decorators
    dependencies: List[str] = field(default_factory=list)  # Called functions/classes
    docstring: Optional[str] = None                        # Existing docstring
    signature: Optional[str] = None                        # Function signature

    # Embeddings (filled during indexing)
    dense_vector: Optional[List[float]] = None
    sparse_tokens: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict:
        """Serialize for JSON storage."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "text": self.text,
            "summary": self.summary,
            "parent_class": self.parent_class,
            "parent_context": self.parent_context,
            "imports": self.imports,
            "decorators": self.decorators,
            "dependencies": self.dependencies,
            "docstring": self.docstring,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CodeChunk":
        """Deserialize from JSON."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            chunk_type=data["chunk_type"],
            name=data["name"],
            text=data["text"],
            summary=data.get("summary"),
            parent_class=data.get("parent_class"),
            parent_context=data.get("parent_context"),
            imports=data.get("imports", []),
            decorators=data.get("decorators", []),
            dependencies=data.get("dependencies", []),
            docstring=data.get("docstring"),
            signature=data.get("signature"),
        )


class ASTChunker:
    """
    Smart code chunker using AST parsing.

    Strategy:
    1. Parse file with tree-sitter
    2. Extract top-level: functions, classes, module docstring
    3. For classes: extract methods with class context attached
    4. Preserve import statements for each chunk
    5. Extract dependencies (function calls, class instantiations)
    """

    # Node types to extract as chunks (tree-sitter grammar dependent)
    PYTHON_CHUNK_TYPES = {
        "function_definition": "function",
        "class_definition": "class",
        "decorated_definition": "decorated",  # Handle @decorators
    }

    JS_CHUNK_TYPES = {
        "function_declaration": "function",
        "class_declaration": "class",
        "arrow_function": "function",
        "method_definition": "method",
        "export_statement": "export",
    }

    # Maximum chunk size (characters) - split if exceeded
    MAX_CHUNK_SIZE = 3000

    # Minimum chunk size - merge small adjacent chunks
    MIN_CHUNK_SIZE = 100

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._parsers: Dict[str, Parser] = {}
        self._setup_parsers()

    def _setup_parsers(self):
        """Initialize tree-sitter parsers for each language."""
        if not TREE_SITTER_AVAILABLE:
            logger.warning("tree-sitter not installed. Falling back to regex chunking.")
            return

        # Python parser
        try:
            py_lang = Language(tspython.language())
            py_parser = Parser(py_lang)
            self._parsers["python"] = py_parser
        except Exception as e:
            logger.warning(f"Failed to init Python parser: {e}")

        # JavaScript/TypeScript parser
        try:
            js_lang = Language(tsjavascript.language())
            js_parser = Parser(js_lang)
            self._parsers["javascript"] = js_parser
            self._parsers["typescript"] = js_parser  # Basic TS support
        except Exception as e:
            logger.warning(f"Failed to init JS parser: {e}")

    def chunk_file(self, file_path: Path) -> List[CodeChunk]:
        """
        Parse a file and extract semantic chunks.

        Returns list of CodeChunk objects with full metadata.
        """
        relative_path = str(file_path.relative_to(self.project_root))

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []

        # Determine language
        lang = self._detect_language(file_path)

        if lang in self._parsers and TREE_SITTER_AVAILABLE:
            chunks = self._chunk_with_ast(content, relative_path, lang)
        else:
            chunks = self._chunk_with_regex(content, relative_path, lang)

        # Extract file-level imports
        imports = self._extract_imports(content, lang)
        for chunk in chunks:
            chunk.imports = imports

        return chunks

    def _detect_language(self, path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".mjs": "javascript",
            ".cjs": "javascript",
        }
        return ext_map.get(path.suffix.lower(), "unknown")

    def _chunk_with_ast(
        self,
        content: str,
        file_path: str,
        lang: str
    ) -> List[CodeChunk]:
        """Use tree-sitter AST to extract semantic chunks."""
        parser = self._parsers[lang]
        tree = parser.parse(bytes(content, "utf-8"))
        root = tree.root_node

        chunks: List[CodeChunk] = []
        lines = content.split("\n")

        # Get chunk types for this language
        chunk_types = (
            self.PYTHON_CHUNK_TYPES if lang == "python"
            else self.JS_CHUNK_TYPES
        )

        def extract_chunks(node: Node, parent_class: Optional[str] = None):
            """Recursively extract chunks from AST."""

            if node.type in chunk_types:
                chunk = self._node_to_chunk(
                    node, content, lines, file_path,
                    chunk_types[node.type], parent_class
                )
                if chunk:
                    chunks.append(chunk)

                    # For classes, recurse into methods
                    if node.type in ("class_definition", "class_declaration"):
                        class_name = self._get_node_name(node, lang)
                        class_signature = self._get_class_signature(node, content)
                        for child in node.children:
                            if child.type in ("block", "class_body"):
                                for method_node in child.children:
                                    if method_node.type in ("function_definition", "method_definition"):
                                        method_chunk = self._node_to_chunk(
                                            method_node, content, lines, file_path,
                                            "method", class_name
                                        )
                                        if method_chunk:
                                            method_chunk.parent_context = class_signature
                                            chunks.append(method_chunk)
                        return  # Don't recurse further for class children

            # Recurse into children
            for child in node.children:
                extract_chunks(child, parent_class)

        extract_chunks(root)

        # Add module-level chunk if file has significant top-level code
        module_chunk = self._extract_module_chunk(root, content, lines, file_path, chunks)
        if module_chunk:
            chunks.insert(0, module_chunk)

        return chunks

    def _node_to_chunk(
        self,
        node: Node,
        content: str,
        lines: List[str],
        file_path: str,
        chunk_type: str,
        parent_class: Optional[str] = None
    ) -> Optional[CodeChunk]:
        """Convert AST node to CodeChunk."""

        start_line = node.start_point[0] + 1  # 1-indexed
        end_line = node.end_point[0] + 1

        # Extract text
        text = content[node.start_byte:node.end_byte]

        # Skip tiny chunks
        if len(text.strip()) < self.MIN_CHUNK_SIZE:
            return None

        # Handle oversized chunks - split into sub-chunks
        if len(text) > self.MAX_CHUNK_SIZE:
            # For now, truncate with marker. Could implement sub-splitting later.
            text = text[:self.MAX_CHUNK_SIZE] + "\n# ... [truncated]"

        # Extract name
        name = self._get_node_name(node, "python")  # Works for most langs
        if not name:
            name = f"anonymous_{chunk_type}_{start_line}"

        # Extract decorators
        decorators = self._extract_decorators(node, content)

        # Extract docstring
        docstring = self._extract_docstring(node, content)

        # Extract signature
        signature = self._extract_signature(node, content)

        # Extract dependencies (function calls)
        dependencies = self._extract_dependencies(node, content)

        # Generate chunk ID
        chunk_id = hashlib.sha256(
            f"{file_path}:{start_line}:{end_line}:{name}".encode()
        ).hexdigest()[:16]

        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            chunk_type=chunk_type,
            name=name,
            text=text,
            parent_class=parent_class,
            decorators=decorators,
            docstring=docstring,
            signature=signature,
            dependencies=dependencies,
        )

    def _get_node_name(self, node: Node, lang: str) -> Optional[str]:
        """Extract function/class name from AST node."""
        for child in node.children:
            if child.type == "identifier" or child.type == "name":
                return child.text.decode("utf-8")
        return None

    def _get_class_signature(self, node: Node, content: str) -> str:
        """Extract class signature (first line with inheritance)."""
        start = node.start_byte
        # Find end of first line
        end = content.find("\n", start)
        if end == -1:
            end = start + 100
        return content[start:end].strip()

    def _extract_decorators(self, node: Node, content: str) -> List[str]:
        """Extract @decorator annotations."""
        decorators = []

        # Check if parent is decorated_definition
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    decorators.append(content[child.start_byte:child.end_byte])

        # Also check direct children (for some grammars)
        for child in node.children:
            if child.type == "decorator":
                decorators.append(content[child.start_byte:child.end_byte])

        return decorators

    def _extract_docstring(self, node: Node, content: str) -> Optional[str]:
        """Extract docstring from function/class body."""
        for child in node.children:
            if child.type in ("block", "class_body", "statement_block"):
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        for expr in stmt.children:
                            if expr.type == "string":
                                text = content[expr.start_byte:expr.end_byte]
                                # Remove quotes
                                if text.startswith('"""') or text.startswith("'''"):
                                    return text[3:-3].strip()
                                elif text.startswith('"') or text.startswith("'"):
                                    return text[1:-1].strip()
                        break  # Only first statement can be docstring
                break
        return None

    def _extract_signature(self, node: Node, content: str) -> Optional[str]:
        """Extract function signature (def line)."""
        start = node.start_byte
        # Find the colon that ends the signature
        colon_pos = content.find(":", start)
        if colon_pos != -1 and colon_pos < node.end_byte:
            sig = content[start:colon_pos + 1].strip()
            # Remove decorators from signature
            if sig.startswith("@"):
                lines = sig.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("def ") or line.strip().startswith("class "):
                        sig = "\n".join(lines[i:])
                        break
            return sig
        return None

    def _extract_dependencies(self, node: Node, content: str) -> List[str]:
        """Extract function/class calls within the chunk."""
        deps = set()

        def find_calls(n: Node):
            if n.type == "call":
                # Get the function being called
                for child in n.children:
                    if child.type in ("identifier", "attribute"):
                        call_text = content[child.start_byte:child.end_byte]
                        deps.add(call_text)
                        break
            for child in n.children:
                find_calls(child)

        find_calls(node)
        return list(deps)[:20]  # Limit to top 20

    def _extract_imports(self, content: str, lang: str) -> List[str]:
        """Extract all import statements from file."""
        imports = []

        if lang == "python":
            # Match import and from...import statements
            import_pattern = r'^(?:from\s+[\w.]+\s+)?import\s+.+$'
            for match in re.finditer(import_pattern, content, re.MULTILINE):
                imports.append(match.group().strip())

        elif lang in ("javascript", "typescript"):
            # Match import statements
            import_pattern = r'^import\s+.+$'
            for match in re.finditer(import_pattern, content, re.MULTILINE):
                imports.append(match.group().strip())
            # Match require statements
            require_pattern = r"(?:const|let|var)\s+\w+\s*=\s*require\(['\"][\w./]+['\"]\)"
            for match in re.finditer(require_pattern, content):
                imports.append(match.group().strip())

        return imports[:30]  # Limit to 30 imports

    def _extract_module_chunk(
        self,
        root: Node,
        content: str,
        lines: List[str],
        file_path: str,
        existing_chunks: List[CodeChunk]
    ) -> Optional[CodeChunk]:
        """
        Extract module-level code (globals, constants, module docstring).
        Only if there's significant code outside functions/classes.
        """
        # Collect byte ranges covered by existing chunks
        covered_ranges = set()
        for chunk in existing_chunks:
            for line in range(chunk.start_line, chunk.end_line + 1):
                covered_ranges.add(line)

        # Collect uncovered lines
        module_lines = []
        for i, line in enumerate(lines, 1):
            if i not in covered_ranges and line.strip():
                # Skip import lines (already captured in metadata)
                if not line.strip().startswith(("import ", "from ")):
                    module_lines.append((i, line))

        if len(module_lines) < 3:  # Not enough module-level code
            return None

        # Build module chunk text
        text_parts = []
        for line_num, line in module_lines[:50]:  # Limit to first 50 lines
            text_parts.append(f"# L{line_num}: {line}")

        text = "\n".join(text_parts)

        chunk_id = hashlib.sha256(
            f"{file_path}:module:0".encode()
        ).hexdigest()[:16]

        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            start_line=1,
            end_line=len(lines),
            chunk_type="module",
            name="module",
            text=text,
            docstring=self._extract_module_docstring(content),
        )

    def _extract_module_docstring(self, content: str) -> Optional[str]:
        """Extract module-level docstring (first string in file)."""
        stripped = content.lstrip()
        if stripped.startswith('"""'):
            end = stripped.find('"""', 3)
            if end != -1:
                return stripped[3:end].strip()
        elif stripped.startswith("'''"):
            end = stripped.find("'''", 3)
            if end != -1:
                return stripped[3:end].strip()
        return None

    def _chunk_with_regex(
        self,
        content: str,
        file_path: str,
        lang: str
    ) -> List[CodeChunk]:
        """
        Fallback: Use regex to extract functions/classes when tree-sitter unavailable.
        Less accurate but works without dependencies.
        """
        chunks = []
        lines = content.split("\n")

        if lang == "python":
            # Pattern for Python functions and classes
            pattern = r'^((?:@[\w.]+(?:\([^)]*\))?\s*\n)*)((?:async\s+)?def\s+(\w+)|class\s+(\w+))'

            for match in re.finditer(pattern, content, re.MULTILINE):
                start_pos = match.start()
                start_line = content[:start_pos].count("\n") + 1

                decorators_text = match.group(1)
                name = match.group(3) or match.group(4)
                chunk_type = "function" if match.group(3) else "class"

                # Find the end of this block (next unindented line or EOF)
                end_line = self._find_block_end(lines, start_line - 1, lang)

                text = "\n".join(lines[start_line - 1:end_line])

                if len(text.strip()) >= self.MIN_CHUNK_SIZE:
                    chunk_id = hashlib.sha256(
                        f"{file_path}:{start_line}:{end_line}:{name}".encode()
                    ).hexdigest()[:16]

                    chunks.append(CodeChunk(
                        id=chunk_id,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        name=name,
                        text=text,
                        decorators=[d.strip() for d in decorators_text.strip().split("\n") if d.strip()],
                    ))

        elif lang in ("javascript", "typescript"):
            # Pattern for JS functions and classes
            patterns = [
                (r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', "function"),
                (r'(?:export\s+)?class\s+(\w+)', "class"),
                (r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>', "function"),
            ]

            for pattern, chunk_type in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    start_pos = match.start()
                    start_line = content[:start_pos].count("\n") + 1
                    name = match.group(1)

                    end_line = self._find_block_end_js(lines, start_line - 1)
                    text = "\n".join(lines[start_line - 1:end_line])

                    if len(text.strip()) >= self.MIN_CHUNK_SIZE:
                        chunk_id = hashlib.sha256(
                            f"{file_path}:{start_line}:{end_line}:{name}".encode()
                        ).hexdigest()[:16]

                        chunks.append(CodeChunk(
                            id=chunk_id,
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                            chunk_type=chunk_type,
                            name=name,
                            text=text,
                        ))

        return chunks

    def _find_block_end(self, lines: List[str], start_idx: int, lang: str) -> int:
        """Find end of indented block (Python)."""
        if start_idx >= len(lines):
            return len(lines)

        # Get base indentation
        base_line = lines[start_idx]
        base_indent = len(base_line) - len(base_line.lstrip())

        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip():  # Empty line
                continue

            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent and line.strip():
                # Found line at same or lower indentation
                return i

        return len(lines)

    def _find_block_end_js(self, lines: List[str], start_idx: int) -> int:
        """Find end of block by matching braces (JS/TS)."""
        brace_count = 0
        started = False

        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    started = True
                elif char == "}":
                    brace_count -= 1

            if started and brace_count == 0:
                return i + 1

        return len(lines)


# Utility function for batch processing
def chunk_codebase(
    project_root: Path,
    file_patterns: List[str] = None,
    exclude_patterns: List[str] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> List[CodeChunk]:
    """
    Chunk entire codebase with progress tracking.

    Args:
        project_root: Root directory of the project
        file_patterns: Glob patterns to include (default: common code files)
        exclude_patterns: Glob patterns to exclude
        progress_callback: Called with (current_file, processed, total)

    Returns:
        List of all CodeChunks
    """
    if file_patterns is None:
        file_patterns = ["**/*.py", "**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx"]

    if exclude_patterns is None:
        exclude_patterns = [
            "**/node_modules/**", "**/.git/**", "**/venv/**",
            "**/__pycache__/**", "**/dist/**", "**/build/**",
            "**/.cache/**", "**/.*/**"
        ]

    chunker = ASTChunker(project_root)
    all_chunks: List[CodeChunk] = []

    # Collect files
    files = []
    for pattern in file_patterns:
        for path in project_root.glob(pattern):
            if path.is_file():
                # Check exclusions
                excluded = False
                for exc in exclude_patterns:
                    if path.match(exc):
                        excluded = True
                        break
                if not excluded:
                    files.append(path)

    # Process files
    total = len(files)
    for i, file_path in enumerate(files):
        if progress_callback:
            progress_callback(str(file_path), i + 1, total)

        try:
            chunks = chunker.chunk_file(file_path)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.error(f"Failed to chunk {file_path}: {e}")

    return all_chunks
