#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Headless MakeHuman Model Generator

This script generates a human model with specific measurements without the GUI,
applies a Unity rig, and exports as FBX configured for Unity.

Usage:
    python generate_human.py \\
        --height 0.8 \\
        --upper-arm 30.5 \\
        --lower-arm 25.0 \\
        --upper-leg 45.0 \\
        --lower-leg 40.0 \\
        --rig-path /path/to/unity.mhskel \\
        --output /path/to/output.fbx
"""

import sys
import os
import argparse

# Disable GUI/OpenGL imports before loading MakeHuman modules
os.environ["MAKEHUMAN_NOGUI"] = "1"


# Set up MakeHuman paths before importing MH modules
def setup_makehuman_paths():
    """Initialize MakeHuman's Python path without GUI dependencies."""
    script_dir = os.path.dirname(os.path.realpath(__file__))
    sys.path.insert(0, script_dir)
    sys.path.insert(0, os.path.join(script_dir, "lib"))
    sys.path.insert(0, os.path.join(script_dir, "apps"))
    sys.path.insert(0, os.path.join(script_dir, "shared"))
    sys.path.insert(0, os.path.join(script_dir, "core"))
    sys.path.insert(0, os.path.join(script_dir, "plugins"))
    os.chdir(script_dir)


setup_makehuman_paths()


# Mock OpenGL modules to prevent import errors
class MockGL:
    """Mock OpenGL module to prevent import errors in headless mode."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


sys.modules["OpenGL"] = MockGL()
sys.modules["OpenGL.GL"] = MockGL()
sys.modules["OpenGL.GLU"] = MockGL()


# Mock Qt modules
class MockQt:
    """Mock Qt module to prevent import errors in headless mode."""

    def __getattr__(self, name):
        if name.startswith("Q"):
            return type(name, (), {})
        return lambda *args, **kwargs: None


sys.modules["PyQt5"] = MockQt()
sys.modules["PyQt5.QtCore"] = MockQt()
sys.modules["PyQt5.QtGui"] = MockQt()
sys.modules["PyQt5.QtWidgets"] = MockQt()

# Now import MakeHuman modules
import log as mhlog
import getpath
import module3d
import files3d
import material
import skeleton
import algos3d
import targets
import math
import numpy as np

# Import human and modifier classes
from human import Human
from humanmodifier import loadModifiers


class HeadlessApp:
    """Minimal app object to satisfy MakeHuman's global state requirements."""

    def __init__(self):
        self.selectedHuman = None
        self.loadHandlers = {}
        self.saveHandlers = []
        self.splash = None
        self.log_window = None
        self.statusBar = None
        self.modelCamera = None  # Required for saving .mhm files

    def progress(self, *args, **kwargs):
        """Progress callback that prints status."""
        if args:
            if len(args) > 1 and "text" in kwargs:
                print(f"  Progress: {kwargs['text']}")
            elif len(args) > 1:
                print(f"  Progress: {args[0]*100:.0f}%")

    def addLogMessage(self, message, level):
        pass


class Ruler:
    """
    Measurement ruler for calculating body part lengths.
    Based on makehuman/plugins/0_modeling_a_measurement.py
    """

    def __init__(self):
        self.Measures = {}
        self.Measures["measure/measure-upperarm-length-decr|incr"] = [8274, 10037]
        self.Measures["measure/measure-lowerarm-length-decr|incr"] = [10040, 10548]
        self.Measures["measure/measure-upperleg-height-decr|incr"] = [10970, 11230]
        self.Measures["measure/measure-lowerleg-height-decr|incr"] = [11225, 12820]

    def getMeasure(self, human, measurementname, mode):
        """Calculate the measurement in cm (metric mode)."""
        measure = 0
        vindex1 = self.Measures[measurementname][0]
        for vindex2 in self.Measures[measurementname]:
            vec = human.meshData.coord[vindex1] - human.meshData.coord[vindex2]
            measure += math.sqrt(vec.dot(vec))
            vindex1 = vindex2

        if mode == "metric":
            return 10.0 * measure
        else:
            return 10.0 * measure * 0.393700787


def init_logging():
    """Initialize MakeHuman logging system."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    mhlog.init()


def create_minimal_app():
    """Create minimal app object for headless operation."""
    from core import G

    G.app = HeadlessApp()

    # Create a minimal camera object for .mhm saving
    class MinimalCamera:
        def __init__(self):
            self.zoomFactor = 1.0
            self.translation = [0.0, 0.0, 0.0]

        def getRotation(self):
            return [0.0, 0.0, 0.0]

    G.app.modelCamera = MinimalCamera()

    return G.app


def load_base_mesh():
    """Load the base human mesh."""
    base_obj = getpath.getSysDataPath("3dobjs/base.obj")
    if not os.path.exists(base_obj):
        raise FileNotFoundError(f"Base mesh not found: {base_obj}")

    print(f"Loading base mesh from {base_obj}")
    mesh = files3d.loadMesh(base_obj, maxFaces=5)
    return mesh


def create_human(mesh):
    """Create and initialize a Human object."""
    print("Creating human object...")
    human = Human(mesh)

    # Load all modifiers
    modeling_modifiers = getpath.getSysDataPath("modifiers/modeling_modifiers.json")
    measurement_modifiers = getpath.getSysDataPath(
        "modifiers/measurement_modifiers.json"
    )

    print(f"Loading modeling modifiers from {modeling_modifiers}")
    loadModifiers(modeling_modifiers, human)

    print(f"Loading measurement modifiers from {measurement_modifiers}")
    loadModifiers(measurement_modifiers, human)

    # Apply default targets to get a valid mesh
    human.applyAllTargets()

    return human


def adjust_limb_to_target(
    human, modifier_name, measurement_name, target_cm, tolerance=0.5, max_iterations=20
):
    """
    Use binary search to find the modifier value that produces the target measurement.

    Args:
        human: The Human object
        modifier_name: Name of the modifier to adjust (e.g., 'measure/measure-upperarm-length')
        measurement_name: Name of the measurement (e.g., 'measure/measure-upperarm-length-decr|incr')
        target_cm: Target measurement in centimeters
        tolerance: Acceptable error in cm
        max_iterations: Maximum number of iterations

    Returns:
        The modifier value that achieves the target measurement
    """
    ruler = Ruler()

    try:
        modifier = human.getModifier(modifier_name)
    except KeyError:
        print(f"Warning: Modifier '{modifier_name}' not found. Skipping.")
        return None

    low, high = 0.0, 1.0
    best_value = 0.5
    best_error = float("inf")

    print(f"  Adjusting {modifier_name} to achieve {target_cm} cm...")

    for iteration in range(max_iterations):
        mid = (low + high) / 2.0
        modifier.setValue(mid)
        human.applyAllTargets()

        current_cm = ruler.getMeasure(human, measurement_name, "metric")
        error = abs(current_cm - target_cm)

        print(
            f"    Iteration {iteration + 1}: value={mid:.4f}, current={current_cm:.2f} cm, target={target_cm:.2f} cm, error={error:.2f} cm"
        )

        if error < best_error:
            best_error = error
            best_value = mid

        if error < tolerance:
            print(f"    Converged! Final value: {mid:.4f}")
            return mid

        if current_cm < target_cm:
            low = mid
        else:
            high = mid

    print(
        f"    Max iterations reached. Using best value: {best_value:.4f} (error: {best_error:.2f} cm)"
    )
    modifier.setValue(best_value)
    human.applyAllTargets()
    return best_value


def configure_human(
    human, height, upper_arm_cm, lower_arm_cm, upper_leg_cm, lower_leg_cm
):
    """
    Configure the human with specified measurements.

    Args:
        human: The Human object
        height: Height value (0-1)
        upper_arm_cm: Upper arm length in cm
        lower_arm_cm: Lower arm length in cm
        upper_leg_cm: Upper leg length in cm
        lower_leg_cm: Lower leg length in cm
    """
    print(f"\nConfiguring human with measurements:")
    print(f"  Height: {height} (0-1 scale)")
    print(f"  Upper arm: {upper_arm_cm} cm")
    print(f"  Lower arm: {lower_arm_cm} cm")
    print(f"  Upper leg: {upper_leg_cm} cm")
    print(f"  Lower leg: {lower_leg_cm} cm")

    # Set height using the proportional modifier
    print("\nSetting height...")
    human.setHeight(height, updateModifier=True)

    # Adjust limb lengths
    print("\nAdjusting limb lengths...")

    # Debug: Print available measurement modifiers
    print("  Available measurement modifiers:")
    for name in sorted(human.modifierNames):
        if name.startswith("measure/"):
            print(f"    - {name}")

    # Upper arm
    adjust_limb_to_target(
        human,
        "measure/measure-upperarm-length-decr|incr",
        "measure/measure-upperarm-length-decr|incr",
        upper_arm_cm,
    )

    # Lower arm
    adjust_limb_to_target(
        human,
        "measure/measure-lowerarm-length-decr|incr",
        "measure/measure-lowerarm-length-decr|incr",
        lower_arm_cm,
    )

    # Upper leg
    adjust_limb_to_target(
        human,
        "measure/measure-upperleg-height-decr|incr",
        "measure/measure-upperleg-height-decr|incr",
        upper_leg_cm,
    )

    # Lower leg
    adjust_limb_to_target(
        human,
        "measure/measure-lowerleg-height-decr|incr",
        "measure/measure-lowerleg-height-decr|incr",
        lower_leg_cm,
    )

    print("\nHuman configuration complete!")


def load_rig(human, rig_path):
    """Load and apply a rig to the human."""
    if not os.path.exists(rig_path):
        raise FileNotFoundError(f"Rig file not found: {rig_path}")

    print(f"\nLoading rig from {rig_path}...")
    rig = skeleton.load(rig_path, human.meshData)
    human.setSkeleton(rig)
    print("Rig loaded and applied successfully!")
    return rig


def save_mhm(human, mhm_path):
    """
    Save the human model as .mhm file for debugging or later use.

    Args:
        human: The Human object
        mhm_path: Path to save the .mhm file
    """
    print(f"\nSaving MHM file to {mhm_path}...")

    # Ensure output directory exists
    output_dir = os.path.dirname(mhm_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        human.save(mhm_path)
        print(f"MHM file saved successfully: {mhm_path}")
        print("You can load this file in MakeHuman GUI to verify or export manually.")
    except Exception as e:
        print(f"Warning: Failed to save MHM file: {e}")
        import traceback

        traceback.print_exc()


def export_fbx(human, output_path, verbose=True):
    """
    Export the human as FBX with Unity-compatible settings.

    Args:
        human: The Human object
        output_path: Path to save the FBX file
        verbose: Print detailed progress information

    Returns:
        True if export succeeded, False otherwise
    """
    if verbose:
        print(f"\nExporting to {output_path}...")
        print("  Note: FBX export in headless mode has limitations...")

    try:
        # The FBX plugin needs to be imported as a package to handle relative imports
        import importlib.util

        fbx_plugin_path = os.path.join(
            os.path.dirname(__file__), "plugins", "9_export_fbx"
        )

        # Add the plugins directory to path so the package can be imported
        plugins_path = os.path.join(os.path.dirname(__file__), "plugins")
        if plugins_path not in sys.path:
            sys.path.insert(0, plugins_path)

        if verbose:
            print("  Loading FBX export module...")

        # Import as a package to allow relative imports to work
        import importlib

        fbx_export = importlib.import_module("9_export_fbx.mh2fbx")

        if verbose:
            print("  FBX module loaded successfully")

        # Create export configuration
        class FbxConfig:
            def __init__(self):
                self.useRelPaths = False
                self.useMaterials = True
                self.binary = True
                self.yUpFaceZ = True
                self.yUpFaceX = False
                self.zUpFaceNegY = False
                self.zUpFaceX = False
                self.localY = True
                self.localX = False
                self.localG = False
                self.hiddenGeom = False
                self.feetOnGround = True
                self.scale = 0.1  # Convert to meters (MakeHuman uses decimeters)
                self.unit = "meter"
                self.human = None
                self._copiedFiles = {}

            def setHuman(self, human):
                self.human = human

            def setupTexFolder(self, filepath):
                self.outFolder = os.path.realpath(os.path.dirname(filepath))
                self.filename = os.path.basename(filepath)
                self.texFolder = os.path.join(self.outFolder, "textures")
                if not os.path.exists(self.texFolder):
                    os.makedirs(self.texFolder)

            def goodName(self, name):
                return name.replace(" ", "_").replace("-", "_").lower()

        config = FbxConfig()
        config.setHuman(human)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Export
        if verbose:
            print("  Preparing meshes and skeleton...")
        fbx_export.exportFbx(output_path, config)
        if verbose:
            print(f"  Export complete! File saved to: {output_path}")
        return True

    except Exception as e:
        if verbose:
            print(f"\n  Warning: FBX export failed: {e}")
            print(
                "  The model configuration is complete, but FBX export encountered an issue."
            )
            print("  The .mhm file (if saved) can be used to export via MakeHuman GUI.")
        return False


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a MakeHuman model with specific measurements and export as FBX.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python generate_human.py \\
        --height 0.8 \\
        --upper-arm 30.5 \\
        --lower-arm 25.0 \\
        --upper-leg 45.0 \\
        --lower-leg 40.0 \\
        --rig-path data/rigs/unity.mhskel \\
        --output output/human.fbx
        """,
    )

    parser.add_argument(
        "--height", type=float, required=True, help="Height as a value between 0 and 1"
    )
    parser.add_argument(
        "--upper-arm", type=float, required=True, help="Upper arm length in centimeters"
    )
    parser.add_argument(
        "--lower-arm", type=float, required=True, help="Lower arm length in centimeters"
    )
    parser.add_argument(
        "--upper-leg", type=float, required=True, help="Upper leg length in centimeters"
    )
    parser.add_argument(
        "--lower-leg", type=float, required=True, help="Lower leg length in centimeters"
    )
    parser.add_argument(
        "--rig-path",
        type=str,
        required=True,
        help="Path to the Unity rig file (.mhskel)",
    )
    parser.add_argument(
        "--output", type=str, required=True, help="Output path for the FBX file"
    )
    parser.add_argument(
        "--save-mhm",
        type=str,
        required=False,
        help="Optional: Save the model as .mhm file for debugging or manual export",
    )

    args = parser.parse_args()

    # Validate height
    if not 0.0 <= args.height <= 1.0:
        parser.error("Height must be between 0 and 1")

    # Validate measurements (reasonable ranges)
    if not 10.0 <= args.upper_arm <= 50.0:
        parser.error("Upper arm length should be between 10 and 50 cm")
    if not 10.0 <= args.lower_arm <= 50.0:
        parser.error("Lower arm length should be between 10 and 50 cm")
    if not 20.0 <= args.upper_leg <= 80.0:
        parser.error("Upper leg length should be between 20 and 80 cm")
    if not 20.0 <= args.lower_leg <= 80.0:
        parser.error("Lower leg length should be between 20 and 80 cm")

    return args


def main():
    """Main execution function."""
    print("=" * 60)
    print("MakeHuman Headless Model Generator")
    print("=" * 60)

    # Parse arguments
    args = parse_arguments()

    # Initialize
    print("\nInitializing MakeHuman...")
    init_logging()
    app = create_minimal_app()

    # Load base mesh
    mesh = load_base_mesh()

    # Create human
    human = create_human(mesh)
    app.selectedHuman = human

    # Configure measurements
    configure_human(
        human,
        args.height,
        args.upper_arm,
        args.lower_arm,
        args.upper_leg,
        args.lower_leg,
    )

    # Load rig
    load_rig(human, args.rig_path)

    # Save MHM file if requested (do this before FBX export for debugging)
    mhm_saved = False
    if args.save_mhm:
        save_mhm(human, args.save_mhm)
        mhm_saved = True

    # Export to FBX
    fbx_success = export_fbx(human, args.output)

    print("\n" + "=" * 60)
    print("Generation complete!")
    print("=" * 60)

    # Print summary
    print("\nSummary:")
    print(f"  Model configured: ✓")
    print(f"  Height: {args.height}")
    print(f"  Rig applied: ✓")
    if mhm_saved:
        print(f"  MHM file saved: ✓ ({args.save_mhm})")
    if fbx_success:
        print(f"  FBX export: ✓ ({args.output})")
    else:
        print(f"  FBX export: ✗ (failed - use .mhm file for manual export)")
        if not mhm_saved:
            print("\n  Recommendation: Run again with --save-mhm to save the model,")
            print("  then use MakeHuman GUI to load the .mhm and export to FBX.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
