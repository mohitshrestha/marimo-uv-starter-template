# /// script
# requires-python = ">=3.12"
# dependencies = ["jinja2", "fire", "loguru", "pyyaml", "tqdm"]
# ///

import ast
import datetime
import os
import shutil
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from xml.sax.saxutils import escape

import fire
import yaml
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from tqdm import tqdm


class MarimoHubBuilder:
    def __init__(self, output=None, content=None, templates="templates", base_url=None):
        # 1. Load from pyproject.toml
        project_config = {}
        pyproject_path = Path("pyproject.toml")
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                project_config = data.get("tool", {}).get("marimo_hub", {})

        # 2. Resolve Paths & URL
        self.output_path = Path(output or project_config.get("output_dir", "_site")).resolve()
        self.content_path = Path(
            content or project_config.get("content_dir", "contents/publish")
        ).resolve()
        self.template_path = Path(templates).resolve()

        final_url = base_url or project_config.get("base_url") or "https://mohitshrestha.com.np"
        self.base_url = final_url.rstrip("/")

        # 3. Logging Setup
        logger.remove()
        log_format = (
            "<blue>{time:HH:mm:ss}</blue> | <level>{level: <8}</level> | <cyan>{message}</cyan>"
        )
        logger.add(sys.stderr, level="INFO", format=log_format)
        logger.info(f"🌐 Build URL: {self.base_url}")

    def _get_full_url(self, relative_path):
        return f"{self.base_url}/{relative_path.lstrip('/')}"

    def _parse_metadata(self, file_path):
        """Parses notebook docstrings for YAML metadata."""
        meta = {
            "title": file_path.stem.replace("_", " ").title(),
            "description": "Interactive data visualization.",
            "featured": False,
            "date": datetime.date.today().isoformat(),
            "tags": ["Analysis"],
            "thumbnail": "/public/default-og.png",  # Fallback image
        }
        try:
            with open(file_path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
                doc = ast.get_docstring(tree) or ""
                if "---" in doc:
                    parts = doc.split("---")
                    if len(parts) > 1:
                        parsed = yaml.safe_load(parts[1])
                        if parsed:
                            meta.update(parsed)
        except Exception as e:
            logger.warning(f"⚠️ Metadata error in {file_path.name}: {e}")
        return meta

    def _inject_og_metadata(self, item):
        """Injects SEO and Social Image tags into generated HTML."""
        html_path = (self.output_path / item["url"].replace("/", os.sep)).resolve()
        meta = item["meta"]
        full_url = self._get_full_url(item["url"])
        image_url = self._get_full_url(meta.get("thumbnail"))

        tags = f"""
        <link rel="icon" href="/public/favicon.ico">
        <meta property="og:type" content="website">
        <meta property="og:url" content="{full_url}">
        <meta property="og:title" content="{escape(meta.get("title", "Project"))}">
        <meta property="og:description" content="{escape(meta.get("description", ""))}">
        <meta property="og:image" content="{image_url}">
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:image" content="{image_url}">
        """

        for _ in range(20):
            if not html_path.exists():
                time.sleep(0.3)
                continue
            try:
                with open(html_path, "r+", encoding="utf-8") as f:
                    content = f.read()
                    if "</head>" in content:
                        updated = content.replace("</head>", f"{tags}\n</head>")
                        f.seek(0)
                        f.write(updated)
                        f.truncate()
                        logger.info(f"🧬 Injected SEO/Social metadata into {item['filename']}")
                        return True
                    else:
                        logger.error(f"❌ Could not find </head> in {item['filename']}")
                        return False
            except (PermissionError, OSError) as e:  # Fixed Syntax: Added parentheses
                logger.warning(f"⚠️ Error occurred while updating {item['filename']}: {e}")
                time.sleep(0.3)
        return False

    def _generate_rss(self, results):
        """Generates RSS 2.0 feed with XSL stylesheet."""
        logger.info("📡 Generating RSS feed...")
        rss_items = []
        sorted_results = sorted(results, key=lambda x: x["meta"].get("date", ""), reverse=True)
        for item in sorted_results:
            meta = item["meta"]
            link = self._get_full_url(item["url"])
            pub_date = datetime.datetime.fromisoformat(
                meta.get("date", datetime.date.today().isoformat())
            ).strftime("%a, %d %b %Y 00:00:00 +0000")
            rss_items.append(
                f"<item><title>{escape(meta.get('title'))}</title><link>{link}</link><guid>{link}</guid><pubDate>{pub_date}</pubDate><description>{escape(meta.get('description'))}</description></item>"
            )

        # Added the xml-stylesheet line pointing to the public folder
        rss_content = (
            f'<?xml version="1.0" encoding="UTF-8" ?>'
            f'<?xml-stylesheet type="text/xsl" href="/public/rss-style.xsl"?>'
            f'<rss version="2.0"><channel>'
            f"<title>Mohit Shrestha - Marimo Gallery</title>"
            f"<link>{self.base_url}</link>"
            f"<description>Interactive Data Apps</description>"
            f"{''.join(rss_items)}</channel></rss>"
        )
        (self.output_path / "rss.xml").write_text(rss_content, encoding="utf-8")

    def _convert_notebook(self, file_path):
        """Runs the Marimo WASM export process."""
        category = file_path.parent.name
        rel_output = f"{category}/{file_path.stem}.html"
        full_output = self.output_path / rel_output
        full_output.parent.mkdir(parents=True, exist_ok=True)
        mode = "run" if category == "apps" else "edit"
        cmd = [
            "uv",
            "run",
            "marimo",
            "export",
            "html-wasm",
            str(file_path),
            "-o",
            str(full_output),
            "--mode",
            mode,
            "--sandbox",
        ]
        try:
            start = time.time()
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            duration = time.time() - start
            logger.info(f"✨ Converted {file_path.name} in {duration:.2f}s")
            return {
                "status": "success",
                "url": rel_output,
                "category": category,
                "meta": self._parse_metadata(file_path),
                "filename": file_path.name,
            }
        except Exception as e:
            return {"status": "error", "file": file_path.name, "error": str(e)}

    def build(self):
        """Main build pipeline."""
        start_time = time.time()
        if self.output_path.exists():
            shutil.rmtree(self.output_path)
        self.output_path.mkdir(parents=True)

        # This copies your public/rss-style.xsl into _site/public/rss-style.xsl
        if Path("public").exists():
            shutil.copytree("public", self.output_path / "public")

        files = list(self.content_path.rglob("*.py"))
        results = []
        with ProcessPoolExecutor() as executor:
            futures = [executor.submit(self._convert_notebook, f) for f in files]
            for f in tqdm(as_completed(futures), total=len(files), desc="Building"):
                res = f.result()
                if res["status"] == "success":
                    results.append(res)
                    self._inject_og_metadata(res)
                else:
                    logger.error(f"❌ Failed: {res.get('file')}")

        if results:
            self._generate_rss(results)
            env = Environment(loader=FileSystemLoader(self.template_path))
            template = env.get_template("gallery.html")
            counts = {
                "all": len(results),
                "apps": len([r for r in results if r["category"] == "apps"]),
                "notebooks": len([r for r in results if r["category"] == "notebooks"]),
            }
            items = sorted(
                results,
                key=lambda x: (not x["meta"].get("featured", False), x["meta"].get("title", "")),
            )
            (self.output_path / "index.html").write_text(
                template.render(
                    items=items, counts=counts, base_url=self.base_url, now=datetime.datetime.now()
                ),
                encoding="utf-8",
            )

        logger.success(f"✅ Build finished in {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    fire.Fire(MarimoHubBuilder)
