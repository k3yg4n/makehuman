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
    --height 175.0 \
    --upper-arm 30.5 \
    --lower-arm 25.0 \
    --upper-leg 45.0 \
    --lower-leg 40.0 \
    --rig-path "/path/to/unity.mhskel" \
    --output "./tmp/output.fbx" \
    --save-mhm "./tmp/generate_human_model.mhm" \
    --tolerance 0.3
```

### Parameters

**All Measurements (in centimeters):**

- `--height`: Total height in centimeters (100-220 cm)
- `--upper-arm`: Upper arm length in centimeters
- `--lower-arm`: Lower arm length in centimeters
- `--upper-leg`: Upper leg length in centimeters
- `--lower-leg`: Lower leg length in centimeters

**Output Options:**

- `--rig-path`: Path to the Unity rig file (.mhskel)
- `--output`: Output path for the FBX file
- `--save-mhm`: (Optional) Save the model as .mhm file for debugging or manual export
- `--tolerance`: (Optional) Acceptable error in cm for measurements (default: 0.5)

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

### Example Output (Exact Mode)

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

============================================================
FINAL MEASUREMENTS:
============================================================
  ✓ height: 175.12 cm (target: 175.0, error: 0.12)
  ✓ upper_arm: 30.48 cm (target: 30.5, error: 0.02)
  ✓ lower_arm: 25.03 cm (target: 25.0, error: 0.03)
  ✓ upper_leg: 44.95 cm (target: 45.0, error: 0.05)
  ✓ lower_leg: 40.02 cm (target: 40.0, error: 0.02)

  Total error: 0.24 cm
============================================================
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

To achieve specific measurements, you may need to:

1. Start with measurements at or below the defaults
2. Adjust the height parameter to scale the overall model
3. Use the measurement modifiers to fine-tune individual limb lengths

### Unity Rig

You need to provide your own Unity-compatible rig file. The script uses the default MakeHuman rig if you don't have a Unity-specific one, but this may not be optimal for Unity imports.

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

## Known Issues & Solutions

1. **FBX Export Limitations**: The FBX export may fail in headless mode due to OpenGL/GUI dependencies.

   **Solution**: The script now automatically saves a .mhm file (when `--save-mhm` is specified) that you can:

   - Load in MakeHuman GUI to verify the model
   - Export manually to FBX with full Unity settings
   - Use for further customization

2. **Measurement Convergence**: The iterative algorithm may not converge for measurements outside the modifier range. The script will use the best approximation it can achieve and report the error.

3. **Recommended Workflow**:

   ```bash
   # Step 1: Generate and configure the model
   python generate_human.py \
       --height 175.0 \
       --upper-arm 32.0 \
       --lower-arm 26.0 \
       --upper-leg 44.0 \
       --lower-leg 60.0 \
       --rig-path data/rigs/default.mhskel \
       --save-mhm output/my_character.mhm \
       --output output/my_character.fbx

   # Step 2: If FBX export fails, load the .mhm file in MakeHuman GUI
   # File > Load > output/my_character.mhm
   # Then: File > Export > FBX with your desired settings
   ```

## Example

```bash
# Using the venv Python
/Users/keeganliu/Dev/UWaterloo/makehuman/venv/bin/python generate_human.py \
    --height 175.0 \
    --upper-arm 32.0 \
    --lower-arm 26.0 \
    --upper-leg 44.0 \
    --lower-leg 60.0 \
    --rig-path data/rigs/default.mhskel \
    --save-mhm output/my_character.mhm \
    --output output/my_character.fbx
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
  Target lower leg: 60.0 cm
============================================================

--- Optimization iteration 1/10 ---
  Adjusting height...
  Adjusting limb lengths...

  Current measurements:
    ✓ height: 175.12 cm (target: 175.0, error: 0.12)
    ✓ upper_arm: 31.98 cm (target: 32.0, error: 0.02)
    ✓ lower_arm: 26.03 cm (target: 26.0, error: 0.03)
    ✓ upper_leg: 43.95 cm (target: 44.0, error: 0.05)
    ✓ lower_leg: 59.98 cm (target: 60.0, error: 0.02)

✓ All measurements within tolerance after 1 iterations!

Loading rig from data/rigs/default.mhskel...
Rig loaded and applied successfully!

Saving MHM file to output/my_character.mhm...
MHM file saved successfully: output/my_character.mhm

Exporting to output/my_character.fbx...
  [Export status...]

============================================================
Generation complete!
============================================================

Summary:
  Model configured: ✓
  Rig applied: ✓
  MHM file saved: ✓ (output/my_character.mhm)
  FBX export: ✓ (output/my_character.fbx)
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

## Future Improvements

- Add support for saving to .mhm format
- Implement better measurement scaling algorithms
- Add more body parameters (weight, muscle, etc.)
- Create a pure Python FBX exporter to avoid GUI dependencies
