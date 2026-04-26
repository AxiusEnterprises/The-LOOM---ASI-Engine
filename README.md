# The LOOM — ASI Engine

A modular ASI (Artificial Super Intelligence) engine built around the LOOM orchestration framework.

## Repository Layout

```
The-LOOM---ASI-Engine/
├── compile_projects.py   # Packaging utility — zips all projects for upload
├── projects/             # Individual project modules
│   ├── loom_core/        # Central orchestration layer
│   └── asi_engine/       # Reasoning and inference module
└── output/               # Generated zip archives (gitignored)
```

## Compiling Projects for Upload

Run the packaging script to zip all projects under `projects/` and produce
upload-ready archives in `output/`:

```bash
python compile_projects.py
```

This creates:
- `output/<project_name>_<timestamp>.zip` — one archive per project
- `output/all_projects_<timestamp>.zip` — combined archive containing all individual zips
- `output/manifest_<timestamp>.json` — SHA-256 checksums and file inventory

### Options

```
--projects-dir DIR   Source directory for projects (default: ./projects)
--output-dir DIR     Destination for zip files (default: ./output)
--no-combined        Skip the combined all_projects zip
--list               List discovered projects without packaging
```

### Examples

```bash
# List what would be packaged
python compile_projects.py --list

# Package without the combined archive
python compile_projects.py --no-combined

# Use a custom source/output path
python compile_projects.py --projects-dir src/modules --output-dir dist
```

## Adding a New Project

Create a subdirectory under `projects/` with a `config.json`:

```json
{
  "name": "my_project",
  "version": "1.0.0",
  "description": "What this project does",
  "entry": "main.py",
  "dependencies": []
}
```

The packaging script will automatically discover and include it on the next run.
