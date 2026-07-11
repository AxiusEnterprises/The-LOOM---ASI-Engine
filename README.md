# The-LOOM---ASI-Engine
## Substrate Globe

An interactive WebGL globe (built with [cobe](https://cobe.vercel.app)) visualizing
weave nodes and the threads connecting them across the Loom substrate.

```bash
# Serve locally (any static server works)
python3 -m http.server 8000
# then open http://localhost:8000/web/globe/
```

Markers and arcs are bindable: each has an `id` that cobe exposes as CSS anchors
(`--cobe-{id}`, `--cobe-arc-{id}`) and visibility variables
(`--cobe-visible-{id}`), which drive the floating labels' position, opacity, and
blur as nodes rotate behind the globe. See `web/globe/index.html`.
