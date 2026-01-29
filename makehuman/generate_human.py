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
import numpy as np

import log as mhlog
import getpath
import module3d
import files3d
import material
import skeleton
import algos3d
import targets
import proxy
import bvh
import animation
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


def configure_human_exact(
    human,
    height_cm,
    upper_arm_cm,
    lower_arm_cm,
    upper_leg_cm,
    lower_leg_cm,
    tolerance=0.5,
    max_outer_iterations=10,
):
    """
    Configure the human with EXACT measurements including total height in cm.

    This uses an iterative multi-constraint optimization approach:
    1. Adjust height modifier to approximate target height
    2. Adjust individual limb lengths
    3. Re-check total height and iterate until all constraints are satisfied

    Args:
        human: The Human object
        height_cm: Exact total height in centimeters
        upper_arm_cm: Upper arm length in cm
        lower_arm_cm: Lower arm length in cm
        upper_leg_cm: Upper leg length in cm
        lower_leg_cm: Lower leg length in cm
        tolerance: Acceptable error in cm for each measurement
        max_outer_iterations: Maximum optimization iterations

    Returns:
        dict with final measurements and errors
    """
    ruler = Ruler()

    print(f"\n{'='*60}")
    print("Configuring human with EXACT measurements:")
    print(f"  Target height: {height_cm} cm")
    print(f"  Target upper arm: {upper_arm_cm} cm")
    print(f"  Target lower arm: {lower_arm_cm} cm")
    print(f"  Target upper leg: {upper_leg_cm} cm")
    print(f"  Target lower leg: {lower_leg_cm} cm")
    print(f"{'='*60}")

    # Define all measurements we want to control
    measurements = {
        "height": {
            "target": height_cm,
            "get_current": lambda h: h.getHeightCm(),
            "modifier": "macrodetails-height/Height",
        },
        "upper_arm": {
            "target": upper_arm_cm,
            "get_current": lambda h: ruler.getMeasure(
                h, "measure/measure-upperarm-length-decr|incr", "metric"
            ),
            "modifier": "measure/measure-upperarm-length-decr|incr",
        },
        "lower_arm": {
            "target": lower_arm_cm,
            "get_current": lambda h: ruler.getMeasure(
                h, "measure/measure-lowerarm-length-decr|incr", "metric"
            ),
            "modifier": "measure/measure-lowerarm-length-decr|incr",
        },
        "upper_leg": {
            "target": upper_leg_cm,
            "get_current": lambda h: ruler.getMeasure(
                h, "measure/measure-upperleg-height-decr|incr", "metric"
            ),
            "modifier": "measure/measure-upperleg-height-decr|incr",
        },
        "lower_leg": {
            "target": lower_leg_cm,
            "get_current": lambda h: ruler.getMeasure(
                h, "measure/measure-lowerleg-height-decr|incr", "metric"
            ),
            "modifier": "measure/measure-lowerleg-height-decr|incr",
        },
    }

    def get_all_errors():
        """Calculate current errors for all measurements."""
        errors = {}
        for name, m in measurements.items():
            current = m["get_current"](human)
            errors[name] = {
                "current": current,
                "target": m["target"],
                "error": abs(current - m["target"]),
            }
        return errors

    def all_within_tolerance(errors):
        """Check if all measurements are within tolerance."""
        return all(e["error"] < tolerance for e in errors.values())

    def adjust_height_to_target(target_cm, inner_tolerance=0.3, inner_max_iter=15):
        """Binary search to find height modifier value for target height in cm."""
        low, high = 0.0, 1.0
        best_value = 0.5
        best_error = float("inf")

        for _ in range(inner_max_iter):
            mid = (low + high) / 2.0
            human.setHeight(mid, updateModifier=True)

            current_cm = human.getHeightCm()
            error = abs(current_cm - target_cm)

            if error < best_error:
                best_error = error
                best_value = mid

            if error < inner_tolerance:
                return mid

            if current_cm < target_cm:
                low = mid
            else:
                high = mid

        human.setHeight(best_value, updateModifier=True)
        return best_value

    def adjust_limb_quietly(
        modifier_name, measurement_name, target_cm, inner_max_iter=15
    ):
        """Adjust a limb measurement without verbose output."""
        try:
            modifier = human.getModifier(modifier_name)
        except KeyError:
            return None

        low, high = -1.0, 1.0
        if modifier.getMin() >= 0:
            low = 0.0

        best_value = 0.0
        best_error = float("inf")

        for _ in range(inner_max_iter):
            mid = (low + high) / 2.0
            modifier.setValue(mid)
            human.applyAllTargets()

            current_cm = ruler.getMeasure(human, measurement_name, "metric")
            error = abs(current_cm - target_cm)

            if error < best_error:
                best_error = error
                best_value = mid

            if error < tolerance * 0.5:  # Use tighter tolerance for inner loop
                return mid

            if current_cm < target_cm:
                low = mid
            else:
                high = mid

        modifier.setValue(best_value)
        human.applyAllTargets()
        return best_value

    # Main optimization loop
    for outer_iter in range(max_outer_iterations):
        print(
            f"\n--- Optimization iteration {outer_iter + 1}/{max_outer_iterations} ---"
        )

        # Step 1: Adjust height first
        print("  Adjusting height...")
        adjust_height_to_target(height_cm)

        # Step 2: Adjust limb lengths
        print("  Adjusting limb lengths...")
        adjust_limb_quietly(
            "measure/measure-upperarm-length-decr|incr",
            "measure/measure-upperarm-length-decr|incr",
            upper_arm_cm,
        )
        adjust_limb_quietly(
            "measure/measure-lowerarm-length-decr|incr",
            "measure/measure-lowerarm-length-decr|incr",
            lower_arm_cm,
        )
        adjust_limb_quietly(
            "measure/measure-upperleg-height-decr|incr",
            "measure/measure-upperleg-height-decr|incr",
            upper_leg_cm,
        )
        adjust_limb_quietly(
            "measure/measure-lowerleg-height-decr|incr",
            "measure/measure-lowerleg-height-decr|incr",
            lower_leg_cm,
        )

        # Step 3: Check all errors
        errors = get_all_errors()

        print("\n  Current measurements:")
        for name, e in errors.items():
            status = "✓" if e["error"] < tolerance else "✗"
            print(
                f"    {status} {name}: {e['current']:.2f} cm (target: {e['target']:.2f}, error: {e['error']:.2f})"
            )

        if all_within_tolerance(errors):
            print(
                f"\n✓ All measurements within tolerance after {outer_iter + 1} iterations!"
            )
            break

        # Step 4: Height may have changed due to limb adjustments - compensate
        # Calculate how much height we need to add/remove via torso/neck adjustments
        height_error = errors["height"]["error"]
        if height_error >= tolerance:
            print(f"\n  Height drifted - re-adjusting...")
            # Try to compensate using torso height if available
            try:
                torso_modifier = human.getModifier("torso/torso-scale-vert-decr|incr")
                current_height = human.getHeightCm()
                height_diff = height_cm - current_height

                # Estimate torso adjustment needed (rough approximation)
                if abs(height_diff) > tolerance:
                    # Adjust torso to compensate
                    current_torso = torso_modifier.getValue()
                    # Small adjustment in the direction needed
                    adjustment = 0.1 if height_diff > 0 else -0.1
                    new_torso = max(-1.0, min(1.0, current_torso + adjustment))
                    torso_modifier.setValue(new_torso)
                    human.applyAllTargets()
            except KeyError:
                # No torso modifier available, will rely on height re-adjustment
                pass
    else:
        print(f"\n⚠ Max iterations reached. Some measurements may not be exact.")

    # Final report
    final_errors = get_all_errors()
    print(f"\n{'='*60}")
    print("FINAL MEASUREMENTS:")
    print(f"{'='*60}")
    total_error = 0
    for name, e in final_errors.items():
        status = "✓" if e["error"] < tolerance else "✗"
        print(
            f"  {status} {name}: {e['current']:.2f} cm (target: {e['target']:.2f}, error: {e['error']:.2f})"
        )
        total_error += e["error"]
    print(f"\n  Total error: {total_error:.2f} cm")
    print(f"{'='*60}")

    return final_errors


def load_rig(human, rig_path):
    """Load and apply a rig to the human."""
    if not os.path.exists(rig_path):
        raise FileNotFoundError(f"Rig file not found: {rig_path}")

    print(f"\nLoading rig from {rig_path}...")

    # First, load the default skeleton as the base skeleton
    # This is required because the default skeleton has the vertex weights defined
    # Other skeletons (like Unity rig) remap their weights from this reference
    default_skel_path = getpath.getSysDataPath("rigs/default.mhskel")
    print(f"  Loading default skeleton for vertex weights from {default_skel_path}...")
    base_skel = skeleton.load(default_skel_path, human.meshData)
    human.setBaseSkeleton(base_skel)

    # Now load the user-specified rig (e.g., Unity rig) as the export skeleton
    print(f"  Loading user skeleton from {rig_path}...")
    user_rig = skeleton.load(rig_path, human.meshData)
    human.setSkeleton(user_rig)

    print("Rig loaded and applied successfully!")
    return user_rig


def load_clothes(human, clothes_path):
    """
    Load and apply clothes to the human model.

    Args:
        human: The Human object
        clothes_path: Path to the .mhclo file. Can be:
                      - Just a name (e.g., 'female_elegantsuit01') - will look in data/clothes/
                      - A relative path (e.g., 'data/clothes/female_elegantsuit01/female_elegantsuit01.mhclo')
                      - An absolute path to a .mhclo file

    Returns:
        The loaded proxy object, or None if loading failed
    """
    original_path = clothes_path

    # Resolve the clothes path
    if not os.path.isabs(clothes_path):
        # If it's just a name (no path separators and no .mhclo extension)
        if os.sep not in clothes_path and "/" not in clothes_path:
            if not clothes_path.endswith(".mhclo"):
                # Try: data/clothes/<name>/<name>.mhclo
                clothes_path = getpath.getSysDataPath(
                    f"clothes/{clothes_path}/{clothes_path}.mhclo"
                )

        # If still not found and doesn't end with .mhclo, try adding extension
        if not os.path.exists(clothes_path) and not clothes_path.endswith(".mhclo"):
            clothes_path = clothes_path + ".mhclo"

        # If still not absolute, try getSysDataPath
        if not os.path.isabs(clothes_path) and not os.path.exists(clothes_path):
            clothes_path = getpath.getSysDataPath(clothes_path)

    if not os.path.exists(clothes_path):
        print(f"  Warning: Clothes file not found: {original_path}")
        print(f"           Tried: {clothes_path}")
        return None

    print(f"  Loading clothes from {clothes_path}...")

    try:
        # Load the proxy (clothes)
        pxy = proxy.loadProxy(human, clothes_path, type="Clothes")
        if pxy is None:
            print(f"  Warning: Failed to load clothes proxy from {clothes_path}")
            return None

        # Load the mesh and create the object
        mesh, obj = pxy.loadMeshAndObject(human)
        if not mesh:
            print(f"  Warning: Failed to load clothes mesh")
            return None

        # Name the mesh/object according to the clothing item filename
        # item_name = os.path.splitext(os.path.basename(clothes_path))[0]
        # if hasattr(mesh, "name"):
        #     mesh.name = f"{item_name}Mesh"
        # if hasattr(pxy, "name"):
        #     pxy.name = item_name

        # IMPORTANT: Adapt the proxy mesh to the human's current shape
        # This fits the clothes to the human's modified dimensions
        # The GUI does this in adaptProxyToHuman() after loading
        seed_mesh = obj.getSeedMesh()
        pxy.update(seed_mesh, fit_to_posed=False)  # Fit to rest pose shape
        seed_mesh.update()

        # Add the clothes to the human
        human.addClothesProxy(pxy)

        print(f"  Clothes '{pxy.name}' loaded successfully!")
        return pxy

    except Exception as e:
        print(f"  Warning: Failed to load clothes: {e}")
        import traceback

        traceback.print_exc()
        return None


def apply_face_hiding(human):
    """
    Apply face masking to hide body vertices under clothes.
    This prevents the body from clipping through clothing.

    This replicates the "Hide faces under clothes" functionality from the GUI.
    """
    clothes_proxies = human.clothesProxies
    if not clothes_proxies:
        return

    print("  Applying face hiding for clothes...")

    # Create a vertex mask - start with all vertices visible
    vertsMask = np.ones(human.meshData.getVertexCount(), dtype=bool)

    # Sort clothes by z_depth (render order)
    sorted_proxies = sorted(
        clothes_proxies.values(), key=lambda p: p.z_depth, reverse=True
    )

    for pxy in sorted_proxies:
        # Check if this proxy defines vertices to delete (hide)
        if pxy.deleteVerts is not None and len(pxy.deleteVerts) > 0:
            # Get the vertices that should be hidden
            verts_to_hide = np.argwhere(pxy.deleteVerts)[..., 0]
            vertsMask[verts_to_hide] = False
            print(f"    Hiding {len(verts_to_hide)} vertices under '{pxy.name}'")

    # Apply the mask to the human mesh
    human.changeVertexMask(vertsMask)
    print("  Face hiding applied successfully!")


def load_pose(human, pose_path):
    """
    Load and apply a pose (BVH or MHP file) to the human.

    Args:
        human: The Human object with skeleton attached.
        pose_path: Path to the pose file (e.g., tpose.bvh).

    Returns:
        The loaded animation object, or None if loading failed.
    """
    if not os.path.exists(pose_path):
        print(f"  Warning: Pose file not found: {pose_path}")
        return None

    print(f"\nLoading pose from {pose_path}...")

    try:
        ext = os.path.splitext(pose_path)[1].lower()

        if ext == ".bvh":
            # Load BVH file
            bvh_file = bvh.load(pose_path, convertFromZUp="auto")

            # Create animation track from BVH
            base_skel = human.getBaseSkeleton()
            if base_skel is None:
                print("  Warning: No base skeleton set, cannot load pose.")
                return None

            anim = bvh_file.createAnimationTrack(base_skel)

            # Auto-scale the animation to match the human's proportions
            # Compare using the upper leg bone
            compare_bone = "upperleg01.L"
            if compare_bone in bvh_file.joints and base_skel.getBone(compare_bone):
                import numpy.linalg as la

                bvh_joint = bvh_file.joints[compare_bone]
                bvh_bone_length = la.norm(
                    bvh_joint.children[0].position - bvh_joint.position
                )

                bone = base_skel.getBone(compare_bone)
                scale_factor = float(bone.length) / bvh_bone_length

                # Get root translation and scale it
                if "root" in bvh_file.joints:
                    posedata = anim.getAtFramePos(0, noBake=True)
                    root_bone_idx = 0
                    bvh_root_translation = posedata[root_bone_idx, :3, 3].copy()
                    trans = scale_factor * bvh_root_translation
                    posedata[root_bone_idx, :3, 3] = trans
                    anim.resetBaked()

        elif ext == ".mhp":
            # Load MHP file
            base_skel = human.getBaseSkeleton()
            if base_skel is None:
                print("  Warning: No base skeleton set, cannot load pose.")
                return None

            anim = animation.loadPoseFromMhpFile(pose_path, base_skel)
        else:
            print(f"  Warning: Unknown pose file format: {ext}")
            return None

        if anim is None:
            print("  Warning: Failed to create animation from pose file.")
            return None

        # Apply the pose to the human
        human.addAnimation(anim)
        human.setActiveAnimation(anim.name)
        human.setToFrame(0, update=False)
        human.setPosed(True)

        print(f"  Pose '{anim.name}' loaded and applied successfully!")
        return anim

    except Exception as e:
        print(f"  Warning: Failed to load pose: {e}")
        import traceback

        traceback.print_exc()
        return None


def save_mhm(human, mhm_path, skeleton_path=None, clothes_proxies=None, pose_path=None):
    """
    Save the human model as .mhm file for debugging or later use.

    Args:
        human: The Human object
        mhm_path: Path to save the .mhm file
        skeleton_path: Path to the skeleton file (for MHM compatibility)
        clothes_proxies: List of clothes proxy objects
        pose_path: Path to the pose file (e.g., tpose.bvh)
    """
    print(f"\nSaving MHM file to {mhm_path}...")

    # Ensure output directory exists
    output_dir = os.path.dirname(mhm_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        human.save(mhm_path)

        # Append skeleton, clothes, and pose info that plugins would normally add
        # These are not included by human.save() in headless mode
        with open(mhm_path, "a") as f:
            # Add skeleton reference
            if skeleton_path:
                # Get relative path for better portability
                skel_name = os.path.basename(skeleton_path)
                skel_dir = os.path.basename(os.path.dirname(skeleton_path))
                relative_skel = f"{skel_dir}/{skel_name}" if skel_dir else skel_name
                f.write(f"skeleton {relative_skel}\n")

            # Add clothes references (format: clothes <name> <uuid>)
            if clothes_proxies:
                for pxy in clothes_proxies:
                    f.write(f"clothes {pxy.name} {pxy.getUuid()}\n")

            # Add pose reference
            if pose_path:
                # Get relative path for better portability
                pose_name = os.path.basename(pose_path)
                f.write(f"pose {pose_name}\n")

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
                self.useMaterials = True  # Enable materials/textures export
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
                self.scale = 1.0  # Keep original scale in decimeters
                self.unit = "decimeter"
                self.human = None
                self._copiedFiles = {}

            def setHuman(self, human):
                self.human = human

            @property
            def meshOrientation(self):
                if self.yUpFaceZ:
                    return "yUpFaceZ"
                if self.yUpFaceX:
                    return "yUpFaceX"
                if self.zUpFaceNegY:
                    return "zUpFaceNegY"
                if self.zUpFaceX:
                    return "zUpFaceX"
                return "yUpFaceZ"

            @property
            def localBoneAxis(self):
                if self.localY:
                    return "y"
                if self.localX:
                    return "x"
                if self.localG:
                    return "g"
                return "y"

            @property
            def offset(self):
                if self.feetOnGround and self.human:
                    yOffset = -self.scale * self.human.getJointPosition("ground")[1]
                    return np.asarray([0.0, yOffset, 0.0], dtype=np.float32)
                else:
                    return np.zeros(3, dtype=np.float32)

            def setupTexFolder(self, filepath):
                self.outFolder = os.path.realpath(os.path.dirname(filepath))
                self.filename = os.path.basename(filepath)
                self.texFolder = os.path.join(self.outFolder, "textures")
                if not os.path.exists(self.texFolder):
                    os.makedirs(self.texFolder)

            def goodName(self, name):
                return name.replace(" ", "_").replace("-", "_").lower()

            def copyTextureToNewLocation(self, filepath):
                """Copy a texture file to the export textures folder."""
                import shutil

                if not filepath:
                    return filepath

                if filepath in self._copiedFiles:
                    return self._copiedFiles[filepath]

                # Get the destination path
                basename = os.path.basename(filepath)
                dest_path = os.path.join(self.texFolder, basename)

                # Copy the file if it exists and isn't already there
                if os.path.isfile(filepath) and not os.path.exists(dest_path):
                    try:
                        shutil.copy2(filepath, dest_path)
                    except Exception as e:
                        print(f"  Warning: Could not copy texture {filepath}: {e}")
                        return filepath

                self._copiedFiles[filepath] = dest_path
                return dest_path

        config = FbxConfig()
        config.setHuman(human)

        # Disable autoBlendSkin on all materials to avoid Qt image processing
        # This is necessary for headless mode
        if verbose:
            print("  Preparing materials for headless export...")
        for obj in human.getObjects():
            if hasattr(obj, "material") and obj.material:
                obj.material._autoBlendSkin = False
        for pxy in human.getProxies():
            if hasattr(pxy, "material") and pxy.material:
                pxy.material._autoBlendSkin = False

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
            import traceback

            print(f"\n  Warning: FBX export failed: {e}")
            print("  Full traceback:")
            traceback.print_exc()
            print(
                "\n  The model configuration is complete, but FBX export encountered an issue."
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
        --height 175.0 \\
        --upper-arm 30.5 \\
        --lower-arm 25.0 \\
        --upper-leg 45.0 \\
        --lower-leg 40.0 \\
        --rig-path /path/to/unity.mhskel \\
        --clothes male_casualsuit01 \\
        --output-dir ./output \\
        --mhm-dir ./tmp

    This will create:
        ./output/male_casualsuit01.fbx
        ./output/textures/...
        ./tmp/male_casualsuit01.mhm

Available clothes (in data/clothes/):
    female_elegantsuit01, female_casualsuit01, female_casualsuit02, female_sportsuit01
    male_casualsuit01-06, male_elegantsuit01, male_worksuit01
    shoes01-06, fedora01
        """,
    )

    parser.add_argument(
        "--height",
        type=float,
        required=True,
        help="Height in centimeters (uses iterative optimization)",
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
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for the FBX file (filename will be based on clothes name)",
    )
    parser.add_argument(
        "--mhm-dir",
        type=str,
        required=False,
        help="Optional: Directory to save the .mhm file (filename will be based on clothes name)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.5,
        help="Acceptable error tolerance in cm for exact measurements (default: 0.5)",
    )
    parser.add_argument(
        "--clothes-dir",
        type=str,
        required=True,
        help="Directory containing .mhclo clothing files to add to the model. All .mhclo files in this directory will be applied.",
    )
    parser.add_argument(
        "--pose",
        type=str,
        default="tpose",
        help="Pose to apply: 'tpose' for T-pose (default), 'none' for rest pose, or path to .bvh/.mhp file",
    )

    args = parser.parse_args()

    # Validate height
    if not 100.0 <= args.height <= 220.0:
        parser.error("Height should be between 100 and 220 cm")

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

    # Configure measurements with exact values using iterative optimization
    configure_human_exact(
        human,
        args.height,
        args.upper_arm,
        args.lower_arm,
        args.upper_leg,
        args.lower_leg,
        tolerance=args.tolerance,
    )

    # Load rig
    load_rig(human, args.rig_path)

    # Load clothes from directory of clothing item subdirectories
    clothes_loaded = False
    loaded_clothes_proxies = []
    import os

    clothes_dir = args.clothes_dir
    if not os.path.isdir(clothes_dir):
        raise FileNotFoundError(f"Clothes directory not found: {clothes_dir}")
    clothes_subdirs = [
        os.path.join(clothes_dir, d)
        for d in sorted(os.listdir(clothes_dir))
        if os.path.isdir(os.path.join(clothes_dir, d))
    ]
    if not clothes_subdirs:
        print(f"No clothing subdirectories found in: {clothes_dir}")
    else:
        print(f"\nLoading clothes from subdirectories in: {clothes_dir}")
        for subdir in clothes_subdirs:
            # Find the .mhclo file in each subdir
            mhclo_files = [f for f in os.listdir(subdir) if f.endswith(".mhclo")]
            if not mhclo_files:
                print(f"  No .mhclo file found in: {subdir}")
                continue
            clothes_path = os.path.join(subdir, mhclo_files[0])
            print(f"  Applying clothes: {os.path.basename(subdir)} ({mhclo_files[0]})")
            pxy = load_clothes(human, clothes_path)
            if pxy:
                loaded_clothes_proxies.append(pxy)
                clothes_loaded = True
        if loaded_clothes_proxies:
            # Apply face hiding to prevent body clipping through clothes
            # apply_face_hiding(human)
            pass

    # Load pose (default is T-pose)
    pose_loaded = False
    pose_path_used = None
    if args.pose and args.pose.lower() != "none":
        if args.pose.lower() == "tpose":
            # Use the built-in T-pose file
            pose_path_used = getpath.getSysDataPath("poses/tpose.bvh")
        else:
            # User-specified pose file
            pose_path_used = args.pose
            if not os.path.exists(pose_path_used):
                # Try to find it in the poses directory
                alt_path = getpath.getSysDataPath(f"poses/{pose_path_used}")
                if os.path.exists(alt_path):
                    pose_path_used = alt_path

        anim = load_pose(human, pose_path_used)
        pose_loaded = anim is not None

    # Use a fixed output basename for all clothed avatars
    output_basename = "clothed_avatar"

    # Ensure output directories exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    fbx_output_path = os.path.join(args.output_dir, f"{output_basename}.fbx")
    mhm_output_path = None
    if args.mhm_dir:
        if not os.path.exists(args.mhm_dir):
            os.makedirs(args.mhm_dir)
        mhm_output_path = os.path.join(args.mhm_dir, f"{output_basename}.mhm")

    # Save MHM file if requested (do this before FBX export for debugging)
    mhm_saved = False
    if mhm_output_path:
        save_mhm(
            human,
            mhm_output_path,
            skeleton_path=args.rig_path,
            clothes_proxies=loaded_clothes_proxies if loaded_clothes_proxies else None,
            pose_path=pose_path_used if pose_loaded else None,
        )
        mhm_saved = True

    # Export to FBX
    fbx_success = export_fbx(human, fbx_output_path)

    print("\n" + "=" * 60)
    print("Generation complete!")
    print("=" * 60)

    # Print summary
    print("\nSummary:")
    print(f"  Model configured: ✓")
    print(f"  Height: {args.height}")
    print(f"  Rig applied: ✓")
    if args.clothes_dir:
        if clothes_loaded:
            print(f"  Clothes loaded from directory: ✓ ({args.clothes_dir})")
        else:
            print(f"  Clothes loaded from directory: ✗ (failed)")
    if args.pose and args.pose.lower() != "none":
        if pose_loaded:
            print(f"  Pose applied: ✓ ({args.pose})")
        else:
            print(f"  Pose applied: ✗ (failed)")
    else:
        print(f"  Pose: rest pose (no pose applied)")
    if mhm_saved:
        print(f"  MHM file saved: ✓ ({mhm_output_path})")
    if fbx_success:
        print(f"  FBX export: ✓ ({fbx_output_path})")
    else:
        print(f"  FBX export: ✗ (failed - use .mhm file for manual export)")
        if not mhm_saved:
            print("\n  Recommendation: Run again with --mhm-dir to save the model,")
            print("  then use MakeHuman GUI to load the .mhm and export to FBX.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
