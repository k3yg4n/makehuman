# MakeHuman Headless Model Generator

## Overview

This script (`generate_human.py`) allows you to generate MakeHuman models with specific measurements without using the GUI. It's designed for automated workflows and batch processing.

## Requirements

- Python 3.12 (use the venv in the parent directory)
- MakeHuman dependencies (PyQt5, NumPy, etc.)
- A Unity-compatible rig file (.mhskel)

## Usage

```bash
/path/to/venv/bin/python generate_human.py \
    --height 0.8 \
    --upper-arm 30.5 \
    --lower-arm 25.0 \
    --upper-leg 45.0 \
    --lower-leg 40.0 \
    --rig-path /path/to/unity.mhskel \
    --save-mhm /path/to/model.mhm \
    --output /path/to/output.fbx
```

### Parameters

- `--height`: Height as a value between 0 and 1 (proportional modifier)
- `--upper-arm`: Upper arm length in centimeters
- `--lower-arm`: Lower arm length in centimeters
- `--upper-leg`: Upper leg length in centimeters
- `--lower-leg`: Lower leg length in centimeters
- `--rig-path`: Path to the Unity rig file (.mhskel)
- `--output`: Output path for the FBX file
- `--save-mhm`: (Optional) Save the model as .mhm file for debugging or manual export

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
       --height 0.75 \
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
    --height 0.75 \
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

Configuring human with measurements:
  Height: 0.75 (0-1 scale)
  Upper arm: 32.0 cm
  Lower arm: 26.0 cm
  Upper leg: 44.0 cm
  Lower leg: 60.0 cm

Setting height...
Adjusting limb lengths...
  [Iterative adjustment output...]

Human configuration complete!

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
  Height: 0.75
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
