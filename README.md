## Project Setup

This readme shows how to setup a `uv` environment for running this project.

## Dependencies

This project requires Python 3.13+ and the following packages:
- numpy - Numerical computing
- scikit-learn - Machine learning library
- pandas - Data manipulation and analysis
- matplotlib - Plotting library
- jupyter - Jupyter notebook environment
- ipykernel - Jupyter kernel for Python
- ucimlrepo - UCI ML repository data access
- ruff - Code formatting and linting
- ty - CLI framework
- seaborn - Plotting tool

Please see `pyproject.toml` for the full list of dependencies.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd <repo-folder-name>
   ```

2. **Install dependencies using uv (recommended):**
   ```bash
   uv sync
   ```

   **Or using pip:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start Jupyter Lab:**
   ```bash
   uv run jupyter lab
   # or
   jupyter lab
   ```

4. **Open the notebook:**
   Navigate to `src/jupyter_template.ipynb` in the Jupyter Lab interface.

## How to Execute
**Run all cells in the notebook:**
- Open `src/jupyter_template.ipynb`
- Use "Run All Cells" from the Run menu, or
- Execute each cell sequentially using Shift+Enter


## Development Tools

- **Linting:** `uv run ruff check .`
- **Formatting:** `uv run ruff format .`
- **Auto-fix:** `uv run ruff check . --fix`