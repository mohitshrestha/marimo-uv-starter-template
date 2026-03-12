# Template Documentation

## Overview

This directory contains Jinja2 templates used by the build script to generate HTML pages for the marimo WebAssembly + GitHub Pages project.  
Templates define the structure and appearance of the generated pages, particularly the index page that lists notebooks and apps.  

**Key Updates:**
- Supports **nested folders** and dynamically groups notebooks/apps by subfolder.
- Automatically organizes items into **categories** for better navigation.
- Optional **drafts handling** is supported if needed in the future.
- Works for Python scripts, notebooks, and marimo apps as long as they are in the proper folder structure.

## Template Requirements

### Basic Structure

A template should be a valid HTML file with Jinja2 syntax for dynamic content. The template must:

1. Have a `.html.j2` extension.
2. Include proper HTML structure (doctype, head, body).
3. Use responsive design principles for good display on various devices.

### Expected Variables

Templates now receive **grouped data** from the build script:

- `notebooks`: A **dictionary** where each key is a category (subfolder name) and value is a list of notebooks.
  - Each notebook has:
    - `display_name`: The formatted name of the notebook (e.g., "Linear Regression Tutorial").
    - `html_path`: The path to the HTML file for the notebook.

- `apps`: A **dictionary** where each key is a category (subfolder name) and value is a list of apps.
  - Each app has:
    - `display_name`: The formatted name of the app.
    - `html_path`: The path to the HTML file for the app.

**Example structure** passed to templates:

```python
notebooks = {
    "ml": [
        {"display_name": "Linear Regression", "html_path": "notebooks/ml/linear_regression.html"},
        {"display_name": "Decision Trees", "html_path": "notebooks/ml/decision_trees.html"}
    ],
    "data_viz": [
        {"display_name": "Matplotlib Basics", "html_path": "notebooks/data_viz/matplotlib_basics.html"}
    ]
}

apps = {
    "dashboards": [
        {"display_name": "Sales Dashboard", "html_path": "apps/dashboards/sales_dashboard.html"}
    ]
}
```

### Template Macros and Sections
Templates can use the provided `render_group` macro to render each category dynamically. Example usage:

```jinja
{% for category, items in notebooks.items() %}
    {{ render_group(category, items, 'notebook') }}
{% endfor %}

{% for category, items in apps.items() %}
    {{ render_group(category, items, 'app') }}
{% endfor %}
```

### Required Sections

A complete template should include:

1. **Notebook Groups**: Only displayed if `notebooks` is not empty. Can have multiple categories.
2. **App Groups**: Only displayed if `apps` is not empty. Can have multiple categories.
3. **Footer and Header**: Standard header/footer with links to marimo, GitHub, and documentation.

## Using Custom Templates

To use a custom template with the build script, use the `--template` parameter:

```bash
uv run .github/scripts/build.py --output-dir _site --template templates/your-custom-template.html.j2
```

## Example Templates

This repository includes:

1. `index.html.j2`: A classic template with plain CSS and a footer. Now supports categories.
2. `tailwind.html.j2`: A minimal template using Tailwind CSS with responsive design and dynamic grouping.

## Best Practices

1. **Folder Structure**: Organize notebooks and apps into subfolders for categories.
   - Example:
     ```
     notebooks/
       ml/
        data_viz/
      apps/
        dashboards/
     ```
3. **Styling**: 
   - Include CSS directly in the template using `<style>` tags for simplicity, or
   - Use Tailwind CSS via CDN for a utility-first approach without custom CSS
4. **Responsive Design**: Ensure good display on different devices.
5. **Conditional Sections**: Use `{% if %}` blocks to only display sections when items exist.
6. **Comments**: Include comments in templates to clarify sections and macros.
7. **Accessibility**: Use semantic HTML and proper ARIA attributes for accessibility