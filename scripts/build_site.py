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
    def __init__(
        self,
        output_dir: str = "_site",
        template_path: str = "templates/gallery.html",
        public_dir: str = "public",
        sandbox: bool = True,  # Toggle for environment isolation
    ):
        self.output_dir = Path(output_dir)
        self.template_path = Path(template_path)
        self.public_dir = Path(public_dir)
        self.use_sandbox = sandbox
        self.manifest: list[dict[str, Any]] = []

    def _copy_public_assets(self):
        """Syncs the 'public' folder (CSS, icons) to the site root."""
        if self.public_dir.exists():
            logger.info(f"🚚 Syncing assets from '{self.public_dir}'...")
            shutil.copytree(self.public_dir, self.output_dir, dirs_exist_ok=True)

    def _extract_metadata(self, py_path: Path) -> dict[str, Any]:
        """Parses YAML frontmatter for 'featured', 'tags', and 'description'."""
        try:
            with open(py_path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            docstring = ast.get_docstring(tree) or ""
            meta = {
                "title": py_path.stem.replace("_", " ").title(),
                "description": "Interactive marimo notebook.",
                "tags": [],
                "thumbnail": "",
                "featured": False,
            }
            if "---" in docstring:
                parts = docstring.split("---")
                if len(parts) >= 3:
                    yaml_data = yaml.safe_load(parts[1])
                    if yaml_data:
                        meta.update(yaml_data)
            return meta
        except Exception as e:
            logger.warning(f"⚠️ Meta-parse failed for {py_path.name}: {e}")
            return {"title": py_path.stem, "description": "", "tags": [], "featured": False}

    def _export_file(self, notebook_path: Path) -> dict[str, Any]:
        """Worker function to convert .py to WASM-HTML."""
        category = notebook_path.parent.name
        mode = "run" if category.lower() == "apps" else "edit"
        target_folder = self.output_dir / category
        target_folder.mkdir(parents=True, exist_ok=True)

        output_path = target_folder / f"{notebook_path.stem}.html"
        meta = self._extract_metadata(notebook_path)

        # Base Command using 'uv run' for stability
        cmd = [
            "uv",
            "run",
            "marimo",
            "export",
            "html-wasm",
            str(notebook_path),
            "-o",
            str(output_path),
            "--mode",
            mode,
        ]

        if self.use_sandbox:
            cmd.append("--sandbox")
        if mode == "run":
            cmd.append("--no-show-code")

        try:
            # Capture output for better error reporting
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {
                "status": "success",
                "meta": meta,
                "category": category,
                "url": f"{category}/{output_path.name}",
                "file_name": notebook_path.name,
            }
        except subprocess.CalledProcessError as e:
            return {"status": "error", "file_name": notebook_path.name, "msg": e.stderr}

    def build(self, input_root: str = "contents/publish"):
        """Execution entry point."""
        input_path = Path(input_root)
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True)
        self._copy_public_assets()

        all_files = list(input_path.rglob("*.py"))
        logger.info(f"🏗️ Starting Build | Sandbox: {self.use_sandbox} | Files: {len(all_files)}")

        results = []
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._export_file, f): f for f in all_files}
            for future in tqdm(as_completed(futures), total=len(all_files), desc="Exporting"):
                res = future.result()
                if res["status"] == "success":
                    logger.success(f"✅ {res['category']}/{res['file_name']}")
                    results.append({**res["meta"], "url": res["url"], "category": res["category"]})
                else:
                    logger.error(f"❌ {res['file_name']} failed. (Try --sandbox=False to debug)")
                    logger.debug(f"Error detail: {res['msg']}")

        self.manifest = results
        if self.manifest:
            self._generate_index()

    def _generate_index(self):
        """Bakes the search gallery using Jinja2."""
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_path.parent))
        template = env.get_template(self.template_path.name)
        # Sort: Featured first, then alphabetical
        sorted_items = sorted(
            self.manifest, key=lambda x: (not x.get("featured", False), x["title"])
        )

        with open(self.output_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(template.render(items=sorted_items))
        logger.success(f"🌐 Site live at: {self.output_dir.absolute()}/index.html")


if __name__ == "__main__":
    fire.Fire(MarimoSiteBuilder)
