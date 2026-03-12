# /// script
# requires-python = ">=3.12"
# dependencies = ["jinja2", "fire", "loguru", "pyyaml", "tqdm"]
# ///

import ast
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import fire
import jinja2
import yaml
from loguru import logger
from tqdm import tqdm


class MarimoHubBuilder:
    """
    Automated Static Site Generator for Mohit Shrestha's Analytics Hub.
    Converts Marimo .py notebooks into WASM-powered HTML files.
    """

    def __init__(self, output_dir="_site", templates="templates", public="public", sandbox=True):
        """
        Initialize build paths and configurations.
        :param output_dir: Where the final website will be generated.
        :param templates: Folder containing gallery.html and partials.
        :param public: Folder for global CSS/Assets.
        """
        self.output_dir = Path(output_dir)
        self.template_dir = Path(templates)
        self.public_dir = Path(public)
        self.use_sandbox = sandbox

        # Initialize logging to a file for long-term maintenance
        logger.add("logs/build_{time}.log", rotation="1 week", level="DEBUG")

    def _extract_meta(self, path: Path):
        """
        Parses the docstring at the top of a .py file to find YAML metadata.
        Expected format:
        '''
        ---
        title: Project Name
        featured: true
        tags: [data, ai]
        ---
        '''
        """
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            doc = ast.get_docstring(tree) or ""

            # Default metadata if none is found
            meta = {
                "title": path.stem.replace("_", " ").title(),
                "description": "Interactive data solution by Mohit Shrestha.",
                "featured": False,
                "tags": [],
            }

            if "---" in doc:
                parts = doc.split("---")
                if len(parts) >= 3:
                    y_data = yaml.safe_load(parts[1])
                    if y_data:
                        meta.update(y_data)
            return meta
        except Exception as e:
            logger.error(f"Failed to parse metadata for {path.name}: {e}")
            return {"title": path.stem, "featured": False, "tags": []}

    def _convert_to_wasm(self, path: Path):
        """
        Worker function: Executes the marimo export command.
        Uses subprocess to run the CLI tool.
        """
        category = path.parent.name  # 'apps' or 'notebooks'
        mode = "run" if category.lower() == "apps" else "edit"

        target_dir = self.output_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{path.stem}.html"

        # Constructing the marimo export command
        cmd = [
            "uv",
            "run",
            "marimo",
            "export",
            "html-wasm",
            str(path),
            "-o",
            str(target_file),
            "--mode",
            mode,
        ]
        if self.use_sandbox:
            cmd.append("--sandbox")

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Exported {category}/{path.name}")
            return {
                "status": "success",
                "meta": self._extract_meta(path),
                "url": f"{category}/{target_file.name}",
                "category": category,
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"Error exporting {path.name}: {e.stderr}")
            return {"status": "error", "file": path.name}

    def build(self, input_path="contents/publish"):
        """
        Main orchestration logic.
        1. Cleans old files. 2. Copies CSS. 3. Runs WASM export. 4. Renders Index.
        """
        logger.info("🚀 Build started...")

        # Step 1: Clean Output
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir()

        # Step 2: Sync Public Assets
        if self.public_dir.exists():
            shutil.copytree(self.public_dir, self.output_dir, dirs_exist_ok=True)

        # Step 3: Find all notebooks
        files = list(Path(input_path).rglob("*.py"))
        if not files:
            logger.warning("No notebooks found!")
            return

        # Step 4: Process in parallel for speed
        results = []
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._convert_to_wasm, f): f for f in files}
            for fut in tqdm(as_completed(futures), total=len(files), desc="Building"):
                res = fut.result()
                if res["status"] == "success":
                    results.append(res)

        # Step 5: Render the Gallery Index
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.template_dir))
        items = sorted(
            results, key=lambda x: (not x["meta"].get("featured", False), x["meta"]["title"])
        )

        # Calculate counts for UI Badges
        counts = {
            "all": len(items),
            "apps": len([i for i in items if i["category"] == "apps"]),
            "notebooks": len([i for i in items if i["category"] == "notebooks"]),
        }

        template = env.get_template("gallery.html")
        with open(self.output_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(template.render(items=items, counts=counts))

        logger.success(f"Build finished! Site at {self.output_dir.absolute()}")


if __name__ == "__main__":
    # We point Fire directly to the 'build' method so 'uv run ...' works without arguments
    fire.Fire(MarimoHubBuilder().build)
