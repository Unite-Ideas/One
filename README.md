# SketchUp Chair Fabric Randomizer

A starter extension is included at:

- `sketchup_extensions/chair_fabric_randomizer.rb`

## What it does

- Uses selected labeled chair parts (for example `BACK`) and then finds the same labels in every chair instance.
- Shows a color-picker dialog (2/3/4 colors) and builds tinted fabric variants from your picks.
- Applies one random palette material to matching target parts across chair instances.
- Keeps changes undoable in one SketchUp operation.

## Compatibility target

- Designed for SketchUp **2024, 2025, and 2026** (Ruby 3.x API usage only).

## Recommended modeling setup

To get reliable matching in nested models like `CHAIRS > SECTION > ROW > CHAIR > PART`:

1. Keep each chair as an instance copy (group copy or component instance), not exploded unique geometry.
2. Name repeated part containers consistently (e.g., `Back`, `Seat`, `Arm Left`, `Arm Right`).
3. Select containers (groups/components), not loose faces, when running the tool.
4. Paint sample fabric/texture on a representative chair part first; the tool colorizes that texture image with your picked colors.

## Install (manual)

1. Save `chair_fabric_randomizer.rb` in your SketchUp `Plugins` folder.
2. Restart SketchUp.
3. Run from **Extensions > Chair Fabric Randomizer**.

## Current limitations

- Matching is label-based (`name`/definition name). If labels are inconsistent between chairs, parts can be skipped.
- If many chair parts share identical unnamed structure, add names to improve match reliability.
- Very large models can take noticeable time because target instances are made unique and textured variants are generated before recoloring.
