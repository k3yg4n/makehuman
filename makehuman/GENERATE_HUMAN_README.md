# MakeHuman Headless Model Generator

## Overview

This script (`generate_human.py`) allows you to generate MakeHuman models with specific measurements without using the GUI. It's designed for automated workflows and batch processing.

## Requirements

- Python 3.12 (use the venv in the parent directory)
- MakeHuman dependencies (PyQt5, NumPy, etc.)
- A Unity-compatible rig file (.mhskel)

## Usage

All measurements are specified in **centimeters**. The script uses **iterative multi-constraint optimization** to achieve all target measurements simultaneously.

```bash
python3 generate_human.py \
    --height 169.0 \
    --upper-arm 29.0 \
    --lower-arm 25.0 \
    --upper-leg 38.5 \
    --lower-leg 48.0 \
    --rig-path "/Users/keeganliu/Documents/MakeHuman/v1py3/data/rigs/Unity_Rig/unity.mhskel" \
    --clothes "male_casualsuit01" \
    --output-dir "./output" \
    --mhm-dir "./tmp" \
    --tolerance 0.3
```

This will create:

- `./output/male_casualsuit01.fbx` - The FBX model file
- `./output/textures/` - Texture files for the model
- `./tmp/male_casualsuit01.mhm` - MakeHuman project file (optional)

### Parameters

**All Measurements (in centimeters):**

- `--height`: Total height in centimeters (100-220 cm)
- `--upper-arm`: Upper arm length in centimeters
- `--lower-arm`: Lower arm length in centimeters
- `--upper-leg`: Upper leg length in centimeters
- `--lower-leg`: Lower leg length in centimeters

**Clothing (Required):**

- `--clothes`: Name or path of clothes to add to the model. The output filename is derived from this.

**Pose:**

- `--pose`: Pose to apply (default: `tpose`). Options:
  - `tpose` - T-pose (default, recommended for Unity)
  - `none` - Rest pose
  - Path to a `.bvh` or `.mhp` pose file

**Output Options:**

- `--rig-path`: Path to the Unity rig file (.mhskel)
- `--output-dir`: Directory for the FBX output (required). Filename is `<clothes_name>.fbx`
- `--mhm-dir`: Directory for the MHM file (optional). Filename is `<clothes_name>.mhm`
- `--tolerance`: Acceptable error in cm for measurements (default: 0.5)

## Clothes

You can add clothes to your generated model using the `--clothes` parameter. This is now **required** as the output filename is derived from the clothes name.

### Available Built-in Clothes

| Category     | Options                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------ |
| Female suits | `female_elegantsuit01`, `female_casualsuit01`, `female_casualsuit02`, `female_sportsuit01` |
| Male suits   | `male_casualsuit01` through `male_casualsuit06`, `male_elegantsuit01`, `male_worksuit01`   |
| Shoes        | `shoes01` through `shoes06`                                                                |
| Accessories  | `fedora01`                                                                                 |

### Specifying Clothes

You can specify clothes in several ways:

1. **Just the name** (recommended):

   ```bash
   --clothes female_elegantsuit01
   ```

   Will automatically look in `data/clothes/<name>/<name>.mhclo`

2. **Full relative path**:

   ```bash
   --clothes data/clothes/male_casualsuit01/male_casualsuit01.mhclo
   ```

3. **Absolute path** (for custom clothes):
   ```bash
   --clothes /path/to/your/custom_outfit.mhclo
   ```

### Textures

When clothes are added, their textures are automatically exported to a `textures/` subfolder of the output directory:

```
output/
├── male_casualsuit01.fbx      # FBX file with material references
└── textures/
    ├── male_casualsuit01_diffuse.png   # Color/diffuse texture
    └── male_casualsuit01_normal.png    # Normal map
```

The FBX file references textures in the `textures/` subfolder. When importing into Unity:

- Place the `textures/` folder alongside the FBX file (this happens automatically)
- Unity should automatically find and apply the textures

### Face Hiding

The script automatically applies face hiding to prevent the body mesh from clipping through clothes. This replicates the "Hide faces under clothes" functionality from the MakeHuman GUI.

## How Exact Measurements Work

The script uses an **iterative multi-constraint optimization** algorithm:

1. **Adjust height modifier** to get close to target total height
2. **Adjust limb lengths** (upper arm, lower arm, upper leg, lower leg) individually
3. **Re-check all measurements** - limb adjustments may have changed total height
4. **Compensate using torso** if height drifted, or re-adjust height modifier
5. **Iterate** until all measurements are within tolerance or max iterations reached

This approach handles the interdependence between measurements:

- Changing leg length affects total height
- Changing height affects all limb proportions
- The algorithm iteratively converges on a solution that satisfies all constraints

### Example Output

```
============================================================
Configuring human with EXACT measurements:
  Target height: 175.0 cm
  Target upper arm: 30.5 cm
  Target lower arm: 25.0 cm
  Target upper leg: 45.0 cm
  Target lower leg: 40.0 cm
============================================================

--- Optimization iteration 1/10 ---
  Adjusting height...
  Adjusting limb lengths...

  Current measurements:
    ✓ height: 175.12 cm (target: 175.0, error: 0.12)
    ✓ upper_arm: 30.48 cm (target: 30.5, error: 0.02)
    ✓ lower_arm: 25.03 cm (target: 25.0, error: 0.03)
    ✓ upper_leg: 44.95 cm (target: 45.0, error: 0.05)
    ✓ lower_leg: 40.02 cm (target: 40.0, error: 0.02)

✓ All measurements within tolerance after 1 iterations!
```

## Important Notes

### Measurement Limitations

The measurement modifiers in MakeHuman are designed to **decrease** measurements from the default human model, not increase them. This means:

- If you specify measurements that are larger than the default model's dimensions, the script will use the closest possible value (usually the default).
- The iterative adjustment algorithm will attempt to match your target measurements, but may not converge if the targets are outside the modifier's range.

**Default measurements** (at height=0.8):

- Upper arm length: ~36 cm
- Lower arm length: ~29 cm
- Upper leg height: ~48 cm
- Lower leg height: ~65 cm

### Unity Rig

You need to provide your own Unity-compatible rig file. The script uses the default MakeHuman rig for vertex weights, but applies your specified rig for export.

To get a Unity rig:

1. Use the MakeHuman GUI to export a model with a Unity rig
2. Save the rig file (.mhskel) from the MakeHuman data directory
3. Use that rig file with this script

### FBX Export

The FBX export is configured with the following Unity-compatible settings:

- Binary FBX format
- Feet on ground
- Scale units: meters (0.1x scale from MakeHuman's decimeters)
- Y-up orientation with Z-forward
- Materials and textures included

**What's Exported:**

| Content             | Status         |
| ------------------- | -------------- |
| Human mesh          | ✓              |
| Skeleton/Rig        | ✓              |
| Clothes mesh        | ✓              |
| Material properties | ✓              |
| Diffuse textures    | ✓              |
| Normal maps         | ✓              |
| Other texture maps  | ✓ (if present) |
| Pose (T-pose)       | ✓              |

## Complete Example

```bash
# Using the venv Python
python3 generate_human.py \
    --height 175.0 \
    --upper-arm 32.0 \
    --lower-arm 26.0 \
    --upper-leg 44.0 \
    --lower-leg 50.0 \
    --rig-path "/path/to/Unity_Rig/unity.mhskel" \
    --clothes "male_casualsuit01" \
    --output-dir ./output \
    --mhm-dir ./tmp \
    --pose tpose \
    --tolerance 0.3
```

### Example Output

```
============================================================
MakeHuman Headless Model Generator
============================================================

Initializing MakeHuman...
Loading base mesh from data/3dobjs/base.obj
Creating human object...
Loading modeling modifiers...
Loading measurement modifiers...

============================================================
Configuring human with EXACT measurements:
  Target height: 175.0 cm
  Target upper arm: 32.0 cm
  Target lower arm: 26.0 cm
  Target upper leg: 44.0 cm
  Target lower leg: 50.0 cm
============================================================

--- Optimization iteration 1/10 ---
  Adjusting height...
  Adjusting limb lengths...

  Current measurements:
    ✓ height: 175.12 cm (target: 175.0, error: 0.12)
    ✓ upper_arm: 31.98 cm (target: 32.0, error: 0.02)
    ✓ lower_arm: 26.03 cm (target: 26.0, error: 0.03)
    ✓ upper_leg: 43.95 cm (target: 44.0, error: 0.05)
    ✓ lower_leg: 50.02 cm (target: 50.0, error: 0.02)

✓ All measurements within tolerance after 1 iterations!

Loading rig from /path/to/Unity_Rig/unity.mhskel...
  Loading default skeleton for vertex weights...
  Loading user skeleton...
Rig loaded and applied successfully!

Loading clothes...
  Loading clothes from data/clothes/male_casualsuit01/male_casualsuit01.mhclo...
  Clothes 'Male_casualsuit01' loaded successfully!
  Applying face hiding for clothes...
    Hiding 1234 vertices under 'Male_casualsuit01'
  Face hiding applied successfully!

Loading pose from data/poses/tpose.bvh...
  Pose 'tpose' loaded and applied successfully!

Saving MHM file to ./tmp/male_casualsuit01.mhm...
MHM file saved successfully: ./tmp/male_casualsuit01.mhm

Exporting to ./output/male_casualsuit01.fbx...
  Preparing materials for headless export...
  Preparing meshes and skeleton...
  Export complete! File saved to: ./output/male_casualsuit01.fbx

============================================================
Generation complete!
============================================================

Summary:
  Model configured: ✓
  Height: 175.0
  Rig applied: ✓
  Clothes loaded: ✓ (male_casualsuit01)
  Pose applied: ✓ (tpose)
  MHM file saved: ✓ (./tmp/male_casualsuit01.mhm)
  FBX export: ✓ (./output/male_casualsuit01.fbx)
```

## Output Files

After running the script, you'll have:

```
output/
├── male_casualsuit01.fbx      # Main FBX file for Unity import
└── textures/                  # Texture files
    ├── male_casualsuit01_diffuse.png
    └── male_casualsuit01_normal.png

tmp/
└── male_casualsuit01.mhm      # MakeHuman project file (if --mhm-dir used)
```

## Troubleshooting

### Script crashes with segfault (exit code 139)

- Make sure you're using the correct Python from the venv
- Check that all dependencies are installed: `pip install -r requirements.txt`

### "Modifier not found" warnings

- This is expected if the modifier names have changed
- Check the available modifiers by looking at `data/modifiers/measurement_modifiers.json`

### Measurements don't match targets

- Remember that modifiers can only decrease measurements
- Try adjusting the height parameter first
- Check the iteration output to see how close the algorithm got

### Clothes not loading

- Check that the clothes name matches exactly (case-sensitive)
- Verify the .mhclo file exists in `data/clothes/<name>/<name>.mhclo`
- For custom clothes, provide the full absolute path

### Textures not appearing in Unity

- Ensure the `textures/` folder is placed alongside the FBX file
- Check that Unity's material import settings are configured correctly
- Try re-importing the FBX with "Extract Materials" enabled
- **Set Model > Normals to "Calculate"** to fix white/splotchy textures

### Body clipping through clothes

- The script automatically applies face hiding
- If clipping still occurs, the clothes may not define `delete_verts` properly
- Try using a different clothes item

## Future Improvements

- Add support for multiple clothes items simultaneously
- Add more body parameters (weight, muscle, gender, etc.)
- Support for custom skin textures
- Hair and accessory support
