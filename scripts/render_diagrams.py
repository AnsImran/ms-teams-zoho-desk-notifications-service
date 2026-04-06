"""Render Mermaid diagrams from README.md into PNG images.

Uses the mermaid.ink public API to convert Mermaid code blocks into PNG files.
No local Node.js or mermaid-cli required.

Usage (from repo root):
  uv run python scripts/render_diagrams.py

Output: docs/diagrams/*.png
"""  # Module-level docstring explaining purpose and usage.

import base64                   # Encode Mermaid text for the API URL.
import re                       # Extract Mermaid code blocks from markdown.
import os                       # Create output directories.
import requests                 # Download rendered PNG images.
from pathlib import Path        # Build file paths cleanly.


REPO_ROOT   = Path(__file__).resolve().parents[1]                                # Repository root directory.
README_PATH = REPO_ROOT / "README.md"                                            # Path to the README file.
OUTPUT_DIR  = REPO_ROOT / "docs" / "diagrams"                                    # Where to save the PNG files.

DIAGRAM_NAMES = [                                                                # Friendly names for each diagram in order of appearance.
    "architecture",
    "polling_cycle",
    "search_query",
    "pending_summary",
]


def extract_mermaid_blocks(markdown_text: str) -> list[str]:                     # Pull all mermaid code blocks from markdown.
    """Extract all ```mermaid ... ``` code blocks from markdown text."""         # Docstring in plain words.
    pattern = r"```mermaid\s*\n(.*?)```"                                         # Regex to match mermaid fenced blocks.
    return re.findall(pattern, markdown_text, re.DOTALL)                          # Return list of mermaid source strings.


def render_to_png(mermaid_code: str, output_path: Path) -> None:                 # Convert one diagram to a PNG file.
    """Render a Mermaid diagram to PNG using the mermaid.ink public API."""      # Docstring in plain words.
    encoded = base64.urlsafe_b64encode(mermaid_code.encode("utf-8")).decode("ascii")  # Base64-encode the diagram text.
    url     = f"https://mermaid.ink/img/{encoded}?type=png&bgColor=white"             # Build the mermaid.ink render URL.
    print(f"  Downloading {output_path.name} ...")                                    # Log progress.
    response = requests.get(url, timeout=60)                                          # Download the rendered image.
    response.raise_for_status()                                                       # Fail loudly on HTTP error.
    output_path.write_bytes(response.content)                                         # Save the PNG file.
    print(f"  Saved {output_path} ({len(response.content)} bytes)")                   # Log success.


def main():                                                                      # Script entry point.
    """Extract Mermaid blocks from README.md and render each to PNG."""          # Docstring in plain words.
    readme_text = README_PATH.read_text(encoding="utf-8")                        # Read the full README.
    blocks      = extract_mermaid_blocks(readme_text)                            # Extract all mermaid code blocks.

    if not blocks:                                                               # If no diagrams found...
        print("No mermaid blocks found in README.md.")                           # Tell the user.
        return                                                                   # Nothing to do.

    print(f"Found {len(blocks)} mermaid diagram(s) in README.md.")               # Log count.
    os.makedirs(OUTPUT_DIR, exist_ok=True)                                       # Create output directory if needed.

    for i, block in enumerate(blocks):                                           # Walk each diagram.
        name        = DIAGRAM_NAMES[i] if i < len(DIAGRAM_NAMES) else f"diagram_{i + 1}"  # Pick a friendly name.
        output_path = OUTPUT_DIR / f"{name}.png"                                          # Build output file path.
        try:                                                                              # Wrap in try so one failure does not stop the rest.
            render_to_png(block, output_path)                                             # Render and save the PNG.
        except Exception as error:                                                        # Catch any rendering errors.
            print(f"  FAILED to render {name}: {error}")                                  # Log the failure.

    print()                                                                      # Blank line for readability.
    print(f"Done. PNGs saved to {OUTPUT_DIR}/")                                  # Final summary.


if __name__ == "__main__":  # Allow running via `python scripts/render_diagrams.py`.
    main()                  # Run the rendering flow.
