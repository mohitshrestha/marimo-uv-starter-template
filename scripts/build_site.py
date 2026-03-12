"""
Build script for Marimo notebooks.

This script exports Marimo notebooks to HTML/WebAssembly format and generates
an index.html file that lists all the notebooks. It handles both regular notebooks
(from the notebooks/ directory) and apps (from the apps/ directory).

The script can be run from the command line with optional arguments:
    uv run .github/scripts/build_site.py [--output-dir OUTPUT_DIR]

The exported files will be placed in the specified output directory (default: _site).
"""

# Required dependencies (you can uncomment this and add it to your pyproject.toml)
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "jinja2==3.1.3",
#     "fire==0.7.0",
#     "loguru==0.7.0"
# ]
# ///

import subprocess
from pathlib import Path
from typing import List, Union

# Third-party libraries
import fire  # Used to handle command-line arguments
import jinja2  # Used for templating and rendering HTML
from loguru import logger  # Used for logging


def _export_html_wasm(notebook_path: Path, output_dir: Path, as_app: bool = False) -> bool:
    """
    Export a single Marimo notebook to HTML/WebAssembly format.

    This function uses the Marimo command-line tool to export a Python notebook (.py file)
    to HTML/WebAssembly. The notebook can be exported either as an "app" (in run mode with
    hidden code) or as a regular notebook (in edit mode, interactive).

    Args:
        notebook_path (Path): Path to the Marimo notebook (.py file) to export.
        output_dir (Path): Directory where the exported HTML file will be saved.
        as_app (bool, optional): Whether to export the notebook as an app (in run mode)
                                  or as a notebook (in edit mode). Defaults to False.

    Returns:
        bool: True if the export was successful, False otherwise.
    """
    # Convert the .py file extension to .html for the output file
    output_path: Path = notebook_path.with_suffix(".html")

    # Base command for exporting a notebook to HTML/WASM
    cmd: List[str] = ["uvx", "marimo", "export", "html-wasm", "--sandbox"]

    # If exporting as an app, hide the code and run it in app mode
    if as_app:
        logger.info(f"Exporting {notebook_path} to {output_path} as app")
        cmd.extend(["--mode", "run", "--no-show-code"])  # Apps run in "run" mode with hidden code
    else:
        logger.info(f"Exporting {notebook_path} to {output_path} as notebook")
        cmd.extend(["--mode", "edit"])  # Notebooks run in "edit" mode

    try:
        # Ensure the output directory exists before writing the exported HTML file
        output_file: Path = output_dir / notebook_path.with_suffix(".html")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Add the notebook path and output file path to the command
        cmd.extend([str(notebook_path), "-o", str(output_file)])

        # Run the Marimo export command
        logger.debug(f"Running command: {cmd}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Successfully exported {notebook_path}")
        return True
    except subprocess.CalledProcessError as e:
        # Log and handle errors during the export process
        logger.error(f"Error exporting {notebook_path}:")
        logger.error(f"Command output: {e.stderr}")
        return False
    except Exception as e:
        # Catch any unexpected errors and log them
        logger.error(f"Unexpected error exporting {notebook_path}: {e}")
        return False


def _generate_index(
    output_dir: Path,
    template_file: Path,
    notebooks_data: List[dict] | None = None,
    apps_data: List[dict] | None = None,
) -> None:
    """
    Generate the index.html file that lists all notebooks and apps.

    This function creates an HTML index page, rendering the provided data for notebooks
    and apps. It uses a Jinja2 template for the HTML structure and then writes the result
    to a new index.html file.

    Args:
        output_dir (Path): Directory where the generated index.html file will be saved.
        template_file (Path): Path to the template file used for rendering the index.
        notebooks_data (List[dict]): List of dictionaries containing data for notebooks.
        apps_data (List[dict]): List of dictionaries containing data for apps.

    Returns:
        None
    """
    logger.info("Generating index.html")

    # Create the full path for the index.html file in the output directory
    index_path: Path = output_dir / "index.html"

    # Ensure the output directory exists before generating the file
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Set up Jinja2 environment and load the provided template
        template_dir = template_file.parent
        template_name = template_file.name
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        template = env.get_template(template_name)

        # Render the HTML template with the data for notebooks and apps
        rendered_html = template.render(notebooks=notebooks_data, apps=apps_data)

        # Write the rendered HTML content to the index.html file
        with open(index_path, "w") as f:
            f.write(rendered_html)
        logger.info(f"Successfully generated index.html at {index_path}")

    except IOError as e:
        logger.error(f"Error generating index.html: {e}")
    except jinja2.exceptions.TemplateError as e:
        logger.error(f"Error rendering template: {e}")


def _export(folder: Path, output_dir: Path, as_app: bool = False) -> List[dict]:
    """
    Export all Marimo notebooks in a given folder to HTML/WebAssembly format.

    This function recursively finds all Python files in the specified folder and exports them
    using the _export_html_wasm function. It returns a list of dictionaries containing the
    exported notebook's display name and its HTML path.

    Args:
        folder (Path): Path to the folder containing Marimo notebooks.
        output_dir (Path): Directory where the exported HTML files will be saved.
        as_app (bool, optional): Whether to export as apps (run mode) or notebooks (edit mode).

    Returns:
        List[dict]: List of dictionaries with "display_name" and "html_path" for each notebook.
    """
    # Check if the folder exists before proceeding
    if not folder.exists():
        logger.warning(f"Directory not found: {folder}")
        return []

    # Find all Python files recursively in the folder
    notebooks = list(folder.rglob("*.py"))
    logger.debug(f"Found {len(notebooks)} Python files in {folder}")

    if not notebooks:
        logger.warning(f"No notebooks found in {folder}!")
        return []

    # Iterate over each notebook and export it using _export_html_wasm
    notebook_data = [
        {
            "display_name": (nb.stem.replace("_", " ").title()),
            "html_path": str(nb.with_suffix(".html")),
        }
        for nb in notebooks
        if _export_html_wasm(nb, output_dir, as_app=as_app)
    ]

    logger.info(
        f"Successfully exported {len(notebook_data)} out of {len(notebooks)} files from {folder}"
    )
    return notebook_data


def main(
    output_dir: Union[str, Path] = "_site",
    template: Union[str, Path] = "templates/tailwind.html.j2",
) -> None:
    """
    Main function to export Marimo notebooks.

    This function is responsible for the overall execution:
    1. Parses command-line arguments.
    2. Exports all Marimo notebooks from the specified folders (notebooks/ and apps/).
    3. Generates an index.html file that lists all the exported notebooks and apps.

    Command line arguments:
        --output-dir: Directory where the exported files will be saved (default: _site).
        --template: Path to the template file used to generate the index
        (default: templates/tailwind.html.j2).

    Returns:
        None
    """
    logger.info("Starting Marimo build process")

    # Convert output_dir explicitly to a Path object (fire doesn't automatically handle it)
    output_dir: Path = Path(output_dir)
    logger.info(f"Output directory: {output_dir}")

    # Ensure the output directory exists before proceeding
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert template to Path if provided
    template_file: Path = Path(template)
    logger.info(f"Using template file: {template_file}")

    # Export notebooks from the "contents/draft/" directory
    notebooks_data = _export(Path("contents/draft"), output_dir, as_app=False)

    # Export apps from the "contents/publish/" directory
    apps_data = _export(Path("contents/publish"), output_dir, as_app=True)

    # If no notebooks or apps were found, exit the process
    if not notebooks_data and not apps_data:
        logger.warning("No notebooks or apps found!")
        return

    # Generate the index.html file that lists all notebooks and apps
    _generate_index(
        output_dir=output_dir,
        notebooks_data=notebooks_data,
        apps_data=apps_data,
        template_file=template_file,
    )

    logger.info(f"Build completed successfully. Output directory: {output_dir}")


# Start the script execution by calling the main function when the script is run
if __name__ == "__main__":
    fire.Fire(main)
