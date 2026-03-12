# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "jinja2==3.1.3",
#     "fire==0.7.0",
#     "loguru==0.7.0",
#     "pyyaml==6.0.1",
# ]
# ///

import ast
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import fire
import jinja2
import yaml
from loguru import logger

# --- EMBEDDED JINJA2 TEMPLATE ---
GALLERY_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marimo Gallery</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    </style>
</head>
<body class="bg-slate-50 text-slate-900">
    <div class="max-w-7xl mx-auto px-6 py-12">
        <header class="mb-12 border-b border-slate-200 pb-8">
            <h1 class="text-5xl font-black tracking-tight italic text-slate-800">MARIMO <span class="text-blue-600">HUB</span></h1>
            <p class="text-slate-500 mt-2">Automated WebAssembly Notebook Gallery</p>
            <div class="mt-8">
                <input type="text" id="search" placeholder="Filter projects by title or category..." 
                    class="px-6 py-3 rounded-xl border border-slate-200 w-full max-w-lg shadow-sm outline-none focus:ring-2 focus:ring-blue-500 transition-all">
            </div>
        </header>

        <div id="grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {% for item in items %}
            <div class="project-card group bg-white rounded-2xl border border-slate-200 overflow-hidden hover:shadow-2xl hover:-translate-y-1 transition-all duration-300"
                 data-search="{{ item.title.lower() }} {{ item.category.lower() }}">
                
                <div class="aspect-video bg-slate-100 relative overflow-hidden">
                    {% if item.thumbnail_url %}
                    <img src="{{ item.thumbnail_url }}" class="object-cover w-full h-full group-hover:scale-105 transition-transform duration-500">
                    {% else %}
                    <div class="flex items-center justify-center h-full text-slate-300 font-bold text-xs uppercase tracking-widest">No Preview Available</div>
                    {% endif %}
                    <div class="absolute top-3 left-3">
                        <span class="bg-white/90 backdrop-blur-sm px-3 py-1 rounded-full text-[10px] font-bold shadow-sm border border-slate-100 uppercase">{{ item.category }}</span>
                    </div>
                </div>

                <div class="p-6">
                    <div class="flex flex-wrap gap-1 mb-3">
                        {% for tag in item.tags %}
                        <span class="text-[9px] font-bold uppercase px-2 py-0.5 bg-blue-50 text-blue-700 rounded-md border border-blue-100">{{ tag }}</span>
                        {% endfor %}
                    </div>
                    <h3 class="text-xl font-bold mb-2 group-hover:text-blue-600 transition-colors">{{ item.title }}</h3>
                    <p class="text-slate-500 text-sm mb-6 line-clamp-2 h-10">{{ item.description }}</p>
                    <a href="{{ item.url }}" class="flex items-center justify-center w-full bg-slate-900 text-white py-3 rounded-xl text-sm font-bold hover:bg-blue-600 transition-colors duration-300">
                        View Project
                    </a>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <script>
        document.getElementById('search').addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            document.querySelectorAll('.project-card').forEach(card => {
                const searchData = card.getAttribute('data-search');
                card.style.display = searchData.includes(term) ? 'block' : 'none';
            });
        });
    </script>
</body>
</html>
"""


class MarimoSiteBuilder:
    """
    Orchestrates the export of Marimo notebooks to a static site.
    """

    def __init__(self, output_dir: str = "_site"):
        self.output_dir = Path(output_dir)
        self.manifest: List[Dict] = []

    def _extract_metadata(self, py_path: Path) -> Dict:
        """Parses the notebook file for YAML frontmatter or docstrings."""
        try:
            with open(py_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception as e:
            logger.error(f"Failed to parse AST for {py_path}: {e}")
            return {"title": py_path.stem, "description": "", "tags": []}

        docstring = ast.get_docstring(tree) or ""
        meta = {
            "title": py_path.stem.replace("_", " ").title(),
            "description": "Interactive marimo notebook.",
            "tags": [],
            "thumbnail": "",
        }

        # YAML Frontmatter parsing
        if "---" in docstring:
            try:
                # Splits by --- and takes the content between the first two markers
                parts = docstring.split("---")
                if len(parts) >= 3:
                    yaml_data = yaml.safe_load(parts[1])
                    if yaml_data:
                        meta.update(yaml_data)
            except Exception as e:
                logger.warning(f"Metadata YAML error in {py_path.name}: {e}")
        elif docstring:
            meta["description"] = docstring.split("\n")[0]

        return meta

    def _export_file(self, notebook_path: Path) -> Optional[Dict]:
        """
        Worker function to export a single notebook.
        Designed to run in a separate process.
        """
        # Determine category based on the immediate parent folder under 'publish'
        # Path: contents/publish/[category]/notebook.py
        category = notebook_path.parent.name
        mode = "run" if category.lower() == "apps" else "edit"

        target_folder = self.output_dir / category
        target_folder.mkdir(parents=True, exist_ok=True)

        output_filename = f"{notebook_path.stem}.html"
        output_path = target_folder / output_filename

        meta = self._extract_metadata(notebook_path)

        # Handle Thumbnails (Check relative to the .py file)
        if meta.get("thumbnail"):
            thumb_src = notebook_path.parent / meta["thumbnail"]
            if thumb_src.exists():
                shutil.copy(thumb_src, target_folder / thumb_src.name)
                meta["thumbnail_url"] = f"{category}/{thumb_src.name}"
            else:
                logger.warning(f"Thumbnail defined but not found: {thumb_src}")

        # Marimo Export Command
        cmd = [
            "uvx",
            "marimo",
            "export",
            "html-wasm",
            str(notebook_path),
            "-o",
            str(output_path),
            "--mode",
            mode,
            "--sandbox",
        ]

        if mode == "run":
            cmd.append("--no-show-code")

        try:
            # We use check=True to raise an error if the export fails
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"Done: {category}/{notebook_path.name}")
            return {
                **meta,
                "url": f"{category}/{output_filename}",
                "category": category,
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"Marimo Export Failed [{notebook_path.name}]: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in worker [{notebook_path.name}]: {e}")
            return None

    def build(self, input_root: str = "contents/publish"):
        """
        Finds all notebooks, exports them in parallel, and builds the gallery.
        """
        logger.info(f"Starting build from root: {input_root}")
        input_path = Path(input_root)

        if not input_path.exists():
            logger.error(f"Source directory {input_root} does not exist.")
            return

        # 1. Clean and Prepare Output
        if self.output_dir.exists():
            logger.info(f"Cleaning existing output directory: {self.output_dir}")
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)

        # 2. Discover all .py files
        all_files = list(input_path.rglob("*.py"))
        logger.info(f"Discovered {len(all_files)} notebook(s) to process.")

        if not all_files:
            logger.warning("No .py files found in the source directory.")
            return

        # 3. Process in Parallel
        # Using as_completed allows us to log progress as each file finishes
        results = []
        logger.info(f"Exporting notebooks using {os.cpu_count()} workers...")

        with ProcessPoolExecutor() as executor:
            future_to_file = {executor.submit(self._export_file, f): f for f in all_files}

            for future in as_completed(future_to_file):
                res = future.result()
                if res:
                    results.append(res)

        # 4. Finalize
        self.manifest = results
        logger.info(f"Successfully exported {len(self.manifest)}/{len(all_files)} notebooks.")
        self._generate_index()

    def _generate_index(self):
        """Renders the final gallery HTML."""
        logger.info("Generating gallery index...")
        try:
            template = jinja2.Template(GALLERY_TEMPLATE)
            # Sort items by category, then title
            sorted_items = sorted(self.manifest, key=lambda x: (x["category"], x["title"]))

            html = template.render(items=sorted_items)

            output_file = self.output_dir / "index.html"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html)

            logger.success(f"Build complete! Hub is at: {output_file.absolute()}")
        except Exception as e:
            logger.error(f"Failed to generate index: {e}")


if __name__ == "__main__":
    # Fire makes 'build' a CLI command
    fire.Fire(MarimoSiteBuilder)
