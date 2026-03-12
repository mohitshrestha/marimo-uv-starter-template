# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "jinja2==3.1.3",
#     "fire==0.7.0",
#     "loguru==0.7.0",
#     "pyyaml==6.0.1",
#     "tqdm==4.66.2",
# ]
# ///

import ast
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import fire
import jinja2
import yaml
from loguru import logger
from tqdm import tqdm


class MarimoSiteBuilder:
    """
    Automated Builder for Marimo Notebook Portfolios.

    Attributes:
        output_dir (Path): Where the final static files are written.
        template_path (Path): The Jinja2 template for the index page.
        public_dir (Path): Source of static assets (favicon, css, etc.).
    """

    def __init__(
        self,
        output_dir: str = "_site",
        template_path: str = "templates/gallery.html",
        public_dir: str = "public",
    ):
        self.output_dir = Path(output_dir)
        self.template_path = Path(template_path)
        self.public_dir = Path(public_dir)
        self.manifest: list[dict[str, Any]] = []

    def _copy_public_assets(self):
        """Moves contents of /public to the root of /_site."""
        if self.public_dir.exists():
            logger.info(f"🚚 Syncing assets from '{self.public_dir}'...")
            # Using dirs_exist_ok=True to allow merging with existing output
            shutil.copytree(self.public_dir, self.output_dir, dirs_exist_ok=True)

    def _extract_metadata(self, py_path: Path) -> dict[str, Any]:
        """
        Parses a notebook file to extract SEO and UI metadata.
        Priority: 1. YAML Frontmatter in Docstring, 2. Raw Docstring, 3. Filename.
        """
        try:
            with open(py_path, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            docstring = ast.get_docstring(tree) or ""
            meta = {
                "title": py_path.stem.replace("_", " ").title(),
                "description": "Interactive marimo notebook.",
                "tags": [],
                "thumbnail": "",
            }

            if "---" in docstring:
                parts = docstring.split("---")
                if len(parts) >= 3:
                    yaml_data = yaml.safe_load(parts[1])
                    if yaml_data:
                        meta.update(yaml_data)
            elif docstring:
                meta["description"] = docstring.split("\n")[0]

            return meta
        except Exception as e:
            logger.error(f"⚠️ Metadata parse error in {py_path.name}: {e}")
            return {"title": py_path.stem, "description": "Notebook", "tags": []}

    def _export_file(self, notebook_path: Path) -> dict[str, Any]:
        """
        Worker: Executes Marimo CLI to generate WASM-HTML.
        Returns a dict containing either success data or an error message.
        """
        # category = folder name (e.g., 'apps' or 'notebooks')
        category = notebook_path.parent.name

        # 'apps' get 'run' mode (app view), others get 'edit' mode (notebook view)
        mode = "run" if category.lower() == "apps" else "edit"

        target_folder = self.output_dir / category
        target_folder.mkdir(parents=True, exist_ok=True)

        output_filename = f"{notebook_path.stem}.html"
        output_path = target_folder / output_filename
        meta = self._extract_metadata(notebook_path)

        if meta.get("thumbnail"):
            thumb_src = notebook_path.parent / meta["thumbnail"]
            if thumb_src.exists():
                shutil.copy(thumb_src, target_folder / thumb_src.name)
                meta["thumbnail_url"] = f"{category}/{thumb_src.name}"

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
        ]
        if mode == "run":
            cmd.append("--no-show-code")

        try:
            # Run export and capture stderr for debugging
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return {
                "status": "success",
                "meta": meta,
                "url": f"{category}/{output_filename}",
                "category": category,
                "file_name": notebook_path.name,
            }
        except subprocess.CalledProcessError as e:
            return {"status": "error", "file_name": notebook_path.name, "message": e.stderr}

    def build(self, input_root: str = "contents/publish"):
        """
        Orchestrates the full site build process.
        Usage: uv run scripts/build_site.py build
        """
        input_path = Path(input_root)
        if not input_path.exists():
            logger.error(f"❌ Input path {input_root} not found!")
            return

        # 1. Prepare Directory Structure
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)

        # 2. Sync Static Files (Favicons, CSS, etc.)
        self._copy_public_assets()

        # 3. Discover Files
        all_files = list(input_path.rglob("*.py"))
        logger.info(f"📂 Found {len(all_files)} notebooks. Starting parallel build...")

        # 4. Process in Parallel with Centralized Logging
        results = []
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._export_file, f): f for f in all_files}

            # tqdm displays the progress bar in the main process
            for future in tqdm(as_completed(futures), total=len(all_files), desc="Exporting"):
                res = future.result()

                # We log in the main process so the user can see progress clearly
                if res["status"] == "success":
                    logger.success(f"✅ Exported: {res['category']}/{res['file_name']}")
                    results.append({**res["meta"], "url": res["url"], "category": res["category"]})
                else:
                    logger.error(f"❌ Failed: {res['file_name']} | Error: {res['message'][:200]}")

        self.manifest = results

        # 5. Final Step: Render the Hub UI
        if self.manifest:
            self._generate_index()
            logger.success(f"✨ Build Complete! Open {self.output_dir}/index.html")
        else:
            logger.error("🚫 No notebooks were successfully exported.")

    def _generate_index(self):
        """Uses Jinja2 to bake the manifest data into the HTML template."""
        try:
            env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_path.parent))
            template = env.get_template(self.template_path.name)

            # Sort the gallery: Categories first, then Titles
            sorted_items = sorted(self.manifest, key=lambda x: (x["category"], x["title"]))

            html = template.render(items=sorted_items)

            with open(self.output_dir / "index.html", "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            logger.error(f"💥 Index generation crashed: {e}")


if __name__ == "__main__":
    fire.Fire(MarimoSiteBuilder)
