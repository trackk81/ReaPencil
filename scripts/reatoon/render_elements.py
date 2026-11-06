"""Global persistent line render elements and portable output configuration."""
import builtins
import json
import math
import re
from pathlib import Path

FEATURES = ["outline", "open", "intersection", "hard", "material", "selected", "crease", "wireframe"]
DEFAULTS = dict(kind="line", active=True, visible_lines=True, hidden_lines=True,
                edge_types=FEATURES, lineset_ids=list(range(1, 9)), output_path_type="scene",
                output_path="", output_file_name="<Scene>", separate_folders=True, separator="_",
                output_element="color", z_min=100., z_max=300., max_velocity=50.,
                bg_color_enable=False, bg_color=[1., 1., 1.], file_type="eps")


def validate(values):
    result = dict(DEFAULTS)
    unknown = builtins.set(values) - builtins.set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown element fields: " + ", ".join(sorted(unknown)))
    result.update(values)
    enums = dict(kind=("line", "eps", "pld"), output_path_type=("scene", "custom"),
                 output_element=("color", "depth", "velocity"), separator=("_", "-", "."), file_type=("eps", "ai_eps"))
    for key, allowed in enums.items():
        if result[key] not in allowed:
            raise ValueError("Invalid render element " + key)
    for key in ("active", "visible_lines", "hidden_lines", "separate_folders", "bg_color_enable"):
        if not isinstance(result[key], bool):
            raise ValueError(key + " must be boolean")
    for key in ("z_min", "z_max", "max_velocity"):
        result[key] = float(result[key])
        if not math.isfinite(result[key]):
            raise ValueError(key + " must be finite")
    if result["z_max"] <= result["z_min"] or result["max_velocity"] <= 0:
        raise ValueError("Z Max must exceed Z Min; maximum velocity must be positive")
    if not builtins.set(result["edge_types"]) <= builtins.set(FEATURES):
        raise ValueError("Unknown edge type")
    if any(isinstance(i, bool) or not isinstance(i, int) or i not in range(1, 9) for i in result["lineset_ids"]):
        raise ValueError("Line Set IDs must be integers 1..8")
    rgb = result["bg_color"]
    if len(rgb) != 3 or any(not math.isfinite(float(v)) or not 0 <= float(v) <= 1 for v in rgb):
        raise ValueError("Background must contain three RGB values in [0,1]")
    for key in ("output_path", "output_file_name"):
        if not isinstance(result[key], str) or "\x00" in result[key]:
            raise ValueError("Invalid element output path")
    return result


def list_elements():
    from maya import cmds
    return sorted(cmds.ls(type="revToonRenderElement") or [])


def create(kind="line", name="revToonRenderElement"):
    from maya import cmds
    values = validate(dict(kind=kind))
    node = cmds.createNode("revToonRenderElement", name=name, skipSelect=True)
    set(node, values)
    return node


def get(node):
    from maya import cmds
    return validate(json.loads(cmds.getAttr(node + ".elementJson") or "{}"))


def set(node, values):
    from maya import cmds
    current = get(node)
    current.update(values)
    cmds.setAttr(node + ".elementJson", json.dumps(validate(current), sort_keys=True), type="string")


def delete(node):
    from maya import cmds
    if cmds.nodeType(node) != "revToonRenderElement":
        raise ValueError("Not a RevToon Render Element")
    cmds.delete(node)


def snapshot():
    return [dict(get(node), name=node) for node in list_elements()]


def accepts(element, visible, features, style):
    return (int(style.get("lineset_id", 1)) in element["lineset_ids"]
            and bool(builtins.set(features) & builtins.set(element["edge_types"]))
            and element["visible_lines" if visible else "hidden_lines"])


def output_path(element, prefix, scene_name=""):
    prefix = Path(prefix).resolve()
    base = element["output_file_name"].replace("<Scene>", scene_name or prefix.name)
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .") or prefix.name
    name = re.sub(r'[^\w.-]', "_", element["name"])
    folder = Path(element["output_path"]).expanduser() if element["output_path_type"] == "custom" and element["output_path"] else prefix.parent
    if element["separate_folders"]:
        folder /= name
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (base + element["separator"] + name + (".eps" if element["kind"] == "eps" else ".png"))
