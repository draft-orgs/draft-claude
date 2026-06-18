#!/usr/bin/env python3
import argparse
import html as html_lib
import io
import json
import math
import pathlib
import re
import urllib.parse
import urllib.request

import jsonschema
from PIL import Image
from playwright.sync_api import sync_playwright


# Collapse any FRAME whose only child is a FRAME without a style by lifting that child's own children into the parent and dropping the child.
def collapse(element):
    if element["type"] != "FRAME":
        return element
    element["children"] = [collapse(child) for child in element["children"]]
    while (
        len(element["children"]) == 1
        and element["children"][0]["type"] == "FRAME"
        and "style" not in element["children"][0]
    ):
        element["children"] = element["children"][0]["children"]
    return element


def _collect_frames(element, frames):
    # Walk every element and collect FRAME elements in traversal order.
    if element["type"] == "FRAME":
        frames.append(element)
    for child in element.get("children", []):
        _collect_frames(child, frames)


# Save a jpg screenshot of every frame and set its screenshot to that file name.
def _attach_figma_screenshots(tree, name, file_key, token, out_dir):
    # Collect all FRAME elements in traversal order.
    frames = []
    _collect_frames(tree, frames)

    # Batch-fetch the Figma images endpoint for every frame that has a nodeId.
    frames_with_id = [f for f in frames if "nodeId" in f]
    if frames_with_id:
        ids_joined = ",".join(f["nodeId"] for f in frames_with_id)
        img_query = urllib.parse.urlencode({"ids": ids_joined, "format": "jpg"})
        img_url = f"https://api.figma.com/v1/images/{file_key}?{img_query}"
        img_request = urllib.request.Request(img_url, headers={"X-Figma-Token": token})
        with urllib.request.urlopen(img_request) as img_response:
            img_data = json.loads(img_response.read())
        url_by_id = img_data["images"]

        # Download each image and assign the screenshot filename to the frame by index.
        for i, frame in enumerate(frames_with_id):
            node_id = frame["nodeId"]
            download_url = url_by_id[node_id]
            jpg_filename = f"{name}.frame.{i}.jpg"
            with urllib.request.urlopen(download_url) as dl:
                (out_dir / jpg_filename).write_bytes(dl.read())
            # Reorder keys: type, screenshot, style (if any), box, children.
            _set_frame_screenshot(frame, jpg_filename)

    # Remove the temporary nodeId field from every element so the schema validator does not reject it.
    _strip_node_ids(tree)


# Save a jpg screenshot of every frame and set its screenshot to that file name.
def _attach_html_screenshots(tree, name, page, out_dir):
    # Collect all FRAME elements in traversal order.
    frames = []
    _collect_frames(tree, frames)

    # Take one full-page screenshot to bytes.
    png_bytes = page.screenshot(full_page=True)

    # Open it as a PIL image.
    full_img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    # Crop each frame's region out of the full image and save as a jpg.
    for i, frame in enumerate(frames):
        box = frame["box"]
        x = box["x"]
        y = box["y"]
        # Compute the crop rectangle and clamp right/bottom to the image size.
        right  = min(x + box["width"],  full_img.width)
        bottom = min(y + box["height"], full_img.height)
        # Ensure left<right and top<bottom (a legitimate edge guard for zero-size or off-image boxes).
        right  = max(right,  x + 1)
        bottom = max(bottom, y + 1)
        crop = full_img.crop((x, y, right, bottom))
        jpg_filename = f"{name}.frame.{i}.jpg"
        crop.save(out_dir / jpg_filename)
        # Reorder keys: type, screenshot, style (if any), box, children.
        _set_frame_screenshot(frame, jpg_filename)

    # Remove the temporary nodeId field from every element (html mode does not use it but strip for safety).
    _strip_node_ids(tree)


def _set_frame_screenshot(frame, jpg_filename):
    # Reorder the frame dict keys: type, screenshot, style (if any), box, children.
    old = dict(frame)
    frame.clear()
    frame["type"] = old["type"]
    frame["screenshot"] = jpg_filename
    if "style" in old:
        frame["style"] = old["style"]
    frame["box"] = old["box"]
    frame["children"] = old["children"]


def _strip_node_ids(element):
    # Remove the temporary nodeId field from every element before schema validation.
    element.pop("nodeId", None)
    for child in element.get("children", []):
        _strip_node_ids(child)


# When emit-skeleton is given also render the design document tree into a skeleton written to the output folder as a name html file and a name css file, prefixing each element with an html comment in the form TYPE: box x,y,width,height then the element, rendering a FRAME as a div wrapping its rendered children, a TEXT as a p holding its content, a VECTOR as an img whose src is a deduplicated svg file written to the output folder, and an IMAGE as an img whose src is its content, emitting box only in the comment, all wrapped in a doctype html document with a head linking the css file and a body with margin zero.


def _num_token(value):
    # Turn a numeric value (int or float) into a class name token.
    # Negative numbers get an n prefix.  Decimal points stay as dots.
    # The CSS body keeps the original sign and adds px.
    if isinstance(value, float) and value == int(value):
        value = int(value)
    text = str(value)
    if text.startswith("-"):
        return "n" + text[1:]
    return text


def _color_token(rgba_string):
    # Parse rgba(r, g, b, a) and return a hex token.
    # Opaque (a==1) -> 6-digit rrggbb.  Partial alpha -> 8-digit rrggbbaa.
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([0-9.]+))?\s*\)", rgba_string)
    if not m:
        raise ValueError(f"Cannot parse color: {rgba_string!r}")
    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = float(m.group(4)) if m.group(4) is not None else 1.0
    if a == 1.0:
        return "%02x%02x%02x" % (r, g, b)
    aa = round(a * 255)
    return "%02x%02x%02x%02x" % (r, g, b, aa)


def _is_solid_color(value):
    # Return True when the background value is a single solid color (lone rgba(...) or #hex).
    value = value.strip()
    if re.fullmatch(r"rgba?\([^)]+\)", value):
        return True
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
        return True
    return False


def _selector(classname):
    # Build a CSS selector by escaping every dot in the class name with a backslash.
    return "." + classname.replace(".", r"\.")


def _expand_radius(radius_string):
    # Expand a CSS border-radius shorthand string into four corner values (TL, TR, BR, BL).
    # The string may be like "8px" or "4px 8px" etc.
    parts = radius_string.split()
    values = []
    for p in parts:
        p = p.rstrip("px") if p.endswith("px") else p
        values.append(float(p))
    if len(values) == 1:
        # One value: all four corners the same.
        tl = tr = br = bl = values[0]
    elif len(values) == 2:
        # Two values: TL+BR share first; TR+BL share second.
        tl, br = values[0], values[0]
        tr, bl = values[1], values[1]
    elif len(values) == 3:
        # Three values: TL first; TR+BL share second; BR third.
        tl = values[0]
        tr = bl = values[1]
        br = values[2]
    else:
        # Four values: TL TR BR BL.
        tl, tr, br, bl = values[0], values[1], values[2], values[3]
    return tl, tr, br, bl


def _parse_border_side(value):
    # Parse a border side string like "1px solid rgba(229, 231, 235, 1)" into (width_px, style, original_color).
    m = re.match(r"(\S+)\s+(\S+)\s+(.+)$", value.strip())
    if not m:
        raise ValueError(f"Cannot parse border side: {value!r}")
    width_part  = m.group(1)   # e.g. "1px"
    style_part  = m.group(2)   # e.g. "solid"
    color_part  = m.group(3)   # e.g. "rgba(229, 231, 235, 1)"
    width_num   = float(width_part.rstrip("px"))
    return width_num, style_part, color_part


def _style_to_classes(style, classes):
    # Give each element an atomic utility class for every style field it has, deduplicated across the document and defined once in the css file, following the class scheme in class-scheme.md, splitting each border side into a width a style and a color class and each border radius into four corner classes.
    # classes is a dict mapping classname -> css_declaration_body that accumulates across the whole document.
    # Returns (list_of_classnames, inline_style_string_or_None).
    element_classes = []
    inline_parts    = []

    for field, value in style.items():

        if field == "font-family":
            # ff-<primary-slug>: slug the first family only; body uses the full original string.
            primary = value.split(",")[0].strip().strip("\"'")
            slug    = re.sub(r"[^a-z0-9]+", "-", primary.lower()).strip("-")
            cn      = f"ff-{slug}"
            classes[cn] = f"font-family:{value}"
            element_classes.append(cn)

        elif field == "font-weight":
            cn = f"fw-{value}"
            classes[cn] = f"font-weight:{value}"
            element_classes.append(cn)

        elif field == "font-size":
            tok = _num_token(value)
            cn  = f"fs-{tok}"
            classes[cn] = f"font-size:{value}px"
            element_classes.append(cn)

        elif field == "text-align":
            cn = f"ta-{value}"
            classes[cn] = f"text-align:{value}"
            element_classes.append(cn)

        elif field == "letter-spacing":
            tok = _num_token(value)
            cn  = f"ls-{tok}"
            classes[cn] = f"letter-spacing:{value}px"
            element_classes.append(cn)

        elif field == "line-height":
            tok = _num_token(value)
            cn  = f"lh-{tok}"
            classes[cn] = f"line-height:{value}px"
            element_classes.append(cn)

        elif field in ("border-top", "border-right", "border-bottom", "border-left"):
            # Split each border side into a width a style and a color class.
            prefix_map = {
                "border-top":    ("bt", "border-top"),
                "border-right":  ("br", "border-right"),
                "border-bottom": ("bb", "border-bottom"),
                "border-left":   ("bl", "border-left"),
            }
            short, long = prefix_map[field]
            width_num, style_str, color_str = _parse_border_side(value)
            # Width class.
            w_tok = _num_token(width_num)
            cn_w  = f"{short}-{w_tok}"
            classes[cn_w] = f"{long}-width:{width_num:g}px"
            element_classes.append(cn_w)
            # Style class.
            cn_s  = f"{short}-{style_str}"
            classes[cn_s] = f"{long}-style:{style_str}"
            element_classes.append(cn_s)
            # Color class.
            hex_tok = _color_token(color_str)
            cn_c    = f"{short}-{hex_tok}"
            classes[cn_c] = f"{long}-color:{color_str}"
            element_classes.append(cn_c)

        elif field == "border-radius":
            # Split each border radius into four corner classes.
            tl, tr, br, bl = _expand_radius(value)
            corners = [
                ("rtl", "border-top-left-radius",     tl),
                ("rtr", "border-top-right-radius",     tr),
                ("rbr", "border-bottom-right-radius",  br),
                ("rbl", "border-bottom-left-radius",   bl),
            ]
            for prefix, prop, num in corners:
                tok = _num_token(num)
                cn  = f"{prefix}-{tok}"
                classes[cn] = f"{prop}:{num:g}px"
                element_classes.append(cn)

        elif field == "background":
            # When a background field is a single solid color give it a bg hex class otherwise put the background and any background blend mode inline on the element.
            if _is_solid_color(value):
                hex_tok = _color_token(value.strip())
                cn      = f"bg-{hex_tok}"
                classes[cn] = f"background:{value}"
                element_classes.append(cn)
            else:
                # Complex background goes inline.
                inline_parts.append(f"background:{value}")

        elif field == "background-blend-mode":
            # background-blend-mode is only emitted inline alongside a complex background.
            if isinstance(value, list):
                modes = ",".join(value)
            else:
                modes = value
            inline_parts.append(f"background-blend-mode:{modes}")

        elif field == "color":
            # When a color field is present give it a c hex class.
            hex_tok = _color_token(value.strip())
            cn      = f"c-{hex_tok}"
            classes[cn] = f"color:{value}"
            element_classes.append(cn)

        # box is never a style field in the design document; skip anything unrecognised silently would
        # mask errors per the fail-loud rule — so raise for any unknown field.
        else:
            raise ValueError(f"Unknown style field: {field!r}")

    inline_style = ";".join(inline_parts) if inline_parts else None
    return element_classes, inline_style


def _render_element(element, classes, svg_dedup, out_dir, name):
    # Build the html comment for this element: TYPE: box x,y,width,height.
    b = element["box"]
    comment = f"<!-- {element['type']}: box {b['x']},{b['y']},{b['width']},{b['height']} -->"

    # Give each element an atomic utility class for every style field it has, deduplicated across the document and defined once in the css file, following the class scheme in class-scheme.md, splitting each border side into a width a style and a color class and each border radius into four corner classes.
    element_classes, inline_style = _style_to_classes(element.get("style", {}), classes)

    class_attr  = f' class="{" ".join(element_classes)}"' if element_classes else ""
    style_attr  = f' style="{html_lib.escape(inline_style, quote=True)}"' if inline_style else ""

    if element["type"] == "FRAME":
        # Render a FRAME as a div wrapping its rendered children.
        child_parts = [_render_element(child, classes, svg_dedup, out_dir, name) for child in element.get("children", [])]
        inner = "".join(child_parts)
        return f"{comment}<div{class_attr}{style_attr}>{inner}</div>"

    if element["type"] == "TEXT":
        # Render a TEXT as a p holding its content (html-escaped).
        text = html_lib.escape(element["content"])
        return f"{comment}<p{class_attr}{style_attr}>{text}</p>"

    if element["type"] == "IMAGE":
        # An IMAGE renders as an img whose src is its content.
        return f'{comment}<img src="{element["content"]}">'

    # Render a VECTOR as an img whose src is a deduplicated svg file written to the output folder.
    if element["type"] != "VECTOR":
        raise ValueError(f"Unknown element type: {element['type']!r}")
    svg_content = element["content"]
    if svg_content not in svg_dedup:
        # First time seeing this svg content: assign it a filename based on the current dict size (0-based index).
        filename = f"{name}.vector.{len(svg_dedup)}.svg"
        svg_dedup[svg_content] = filename
        (out_dir / filename).write_text(svg_content)
    filename = svg_dedup[svg_content]
    return f'{comment}<img src="{filename}">'


def _write_skeleton(output, out_dir, name):
    # Give each element an atomic utility class for every style field it has, deduplicated across the document and defined once in the css file, following the class scheme in class-scheme.md, splitting each border side into a width a style and a color class and each border radius into four corner classes.
    # Accumulate all classname -> css_declaration_body mappings across the whole document.
    classes = {}

    # Accumulate all svg_content -> filename mappings for deduplicating svg files across the document.
    svg_dedup = {}

    # Render each top-level element under body so the body's first element child is the document frame.
    parts = [_render_element(child, classes, svg_dedup, out_dir, name) for child in output["children"]]
    body_inner = "".join(parts)

    # Emit the style rules in sorted order so the output is deterministic.
    style_lines = []
    for cn in sorted(classes):
        style_lines.append(f"{_selector(cn)}{{{classes[cn]}}}")
    css_text = "".join(style_lines)

    # Write the css file with the deduplicated class rules.
    (out_dir / f"{name}.css").write_text(css_text)

    # Write the html file with a head linking the css file and a body with margin zero.
    html_text = (
        f"<!DOCTYPE html><html><head><link rel=\"stylesheet\" href=\"{name}.css\"></head>"
        + '<body style="margin:0">'
        + body_inner
        + "</body></html>"
    )
    (out_dir / f"{name}.html").write_text(html_text)


def _fill_vector_svgs(element, base_dir):
    # When the element is an svg or an image whose source ends with svg make a VECTOR element with content set to the svg markup or the image source, then for an image source read the svg file relative to the html and set the content to its markup.
    if element["type"] == "VECTOR" and not element["content"].lstrip().startswith("<svg"):
        element["content"] = (base_dir / element["content"]).read_text()
    for child in element.get("children", []):
        _fill_vector_svgs(child, base_dir)


def main():
    parser = argparse.ArgumentParser(
        prog="extract.py",
        description="Extract a figma node or an html into a design document with an optional skeleton html",
        epilog=(
            "Examples:\n"
            "  python3 extract.py --figma-token your-figma-token --figma https://www.figma.com/design/your-file-key/Name?node-id=1-2 --out /path/to/dist --emit-skeleton\n"
            "  python3 extract.py --html /path/to/page.html --out /path/to/dist"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--figma",         type=str, help="The figma design url")
    parser.add_argument("--figma-token",   type=str, help="The figma personal access token")
    parser.add_argument("--html",          type=str, help="The path to the html file")
    parser.add_argument("--out",           type=str, required=True, help="The output folder for the design document")
    parser.add_argument("--emit-skeleton", action="store_true", help="Also write a skeleton html and css rendered from the design document tree")
    args = parser.parse_args()
    if args.html is not None and not re.match(r"^/", args.html):
        parser.error("--html must match ^/")
    if args.out is not None and not re.match(r"^/", args.out):
        parser.error("--out must match ^/")

    # Require exactly one source and error when both figma and html are given or when neither is given.
    if args.figma and args.html:
        parser.error("Provide either --figma or --html, not both.")
    if not args.figma and not args.html:
        parser.error("Provide exactly one of --figma or --html.")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.figma:
        # When figma is given parse the file key from the url path after design or file and the node id from the node-id query with a dash replaced by a colon.
        parsed_url = urllib.parse.urlparse(args.figma)
        path_parts = parsed_url.path.strip("/").split("/")
        file_key = ""
        for i, part in enumerate(path_parts):
            if part in ("design", "file") and i + 1 < len(path_parts):
                file_key = path_parts[i + 1]
                break
        query_params = urllib.parse.parse_qs(parsed_url.query)
        node_id_raw = query_params.get("node-id", [""])[0]
        node_id = node_id_raw.replace("-", ":")

        # Error when the parsed file key or the parsed node id is empty.
        if not file_key:
            parser.error("Could not parse file key from --figma url.")
        if not node_id:
            parser.error("Could not parse node id from --figma url node-id query param.")

        token = args.figma_token
        name = node_id.replace(":", "-")

        # When figma is given fetch the node json from the files nodes endpoint with the figma token in the X-Figma-Token header and read the subtree document.
        query = urllib.parse.urlencode({"ids": node_id})
        url = f"https://api.figma.com/v1/files/{file_key}/nodes?{query}"
        request = urllib.request.Request(url, headers={"X-Figma-Token": token})
        with urllib.request.urlopen(request) as response:
            data = json.loads(response.read())
        document = data["nodes"][node_id]["document"]

        # To resolve an image fill download it by mapping its imageRef through the file images endpoint then save it under the output directory and use that saved path in the url.
        images_map_cache = {}

        def download_image(imageRef):
            # Fetch the file images map once and cache it so multiple image fills do not refetch.
            if not images_map_cache:
                map_url = f"https://api.figma.com/v1/files/{file_key}/images"
                map_request = urllib.request.Request(map_url, headers={"X-Figma-Token": token})
                with urllib.request.urlopen(map_request) as map_response:
                    map_data = json.loads(map_response.read())
                images_map_cache.update(map_data["meta"]["images"])
            # Resolve the imageRef to a download url.
            image_url = images_map_cache[imageRef]
            # Download the image bytes and pick the file extension from the Content-Type header.
            with urllib.request.urlopen(image_url) as img_response:
                img_bytes = img_response.read()
                content_type = img_response.headers.get("Content-Type", "")
            ext_map = {
                "image/png":     ".png",
                "image/jpeg":    ".jpg",
                "image/svg+xml": ".svg",
                "image/gif":     ".gif",
            }
            ext = ext_map.get(content_type, ".png")
            # Save the bytes next to the output file and return the bare filename for use in url().
            filename = f"{imageRef}{ext}"
            (out_dir / filename).write_bytes(img_bytes)
            return filename

        def css_color(color, opacity=1):
            # Round r/g/b channels to 0-255 integers and combine opacity with the color alpha.
            r = round(color["r"] * 255)
            g = round(color["g"] * 255)
            b = round(color["b"] * 255)
            a = round(color["a"] * opacity, 2)
            if a == 1:
                return '#%02X%02X%02X' % (r, g, b)
            else:
                return 'rgba(%d, %d, %d, %s)' % (r, g, b, ('%.2f' % a))

        def build_frame_css(node):
            # When the node has a visible stroke set the div border per side from the side weight in px then solid then the first visible stroke color as a hex, taking each side weight from individualStrokeWeights or strokeWeight and keeping only sides above zero, and set border-radius from rectangleCornerRadii or cornerRadius in px.
            styles = {}
            visible_strokes = [s for s in node.get("strokes", []) if s.get("visible", True) is not False]
            if visible_strokes:
                color = visible_strokes[0]["color"]
                r = color["r"]
                g = color["g"]
                b = color["b"]
                a = color["a"]
                hex_color = '#%02X%02X%02X%02X' % (round(r * 255), round(g * 255), round(b * 255), round(a * 255))
                if "individualStrokeWeights" in node:
                    weights = node["individualStrokeWeights"]
                    top_weight    = weights["top"]
                    right_weight  = weights["right"]
                    bottom_weight = weights["bottom"]
                    left_weight   = weights["left"]
                else:
                    top_weight    = node["strokeWeight"]
                    right_weight  = node["strokeWeight"]
                    bottom_weight = node["strokeWeight"]
                    left_weight   = node["strokeWeight"]
                sides = [
                    (top_weight,    "border-top"),
                    (right_weight,  "border-right"),
                    (bottom_weight, "border-bottom"),
                    (left_weight,   "border-left"),
                ]
                for weight, css_key in sides:
                    if weight > 0:
                        styles[css_key] = f"{weight:g}px solid {hex_color}"
            if "rectangleCornerRadii" in node:
                radii = node["rectangleCornerRadii"]
                if any(rv > 0 for rv in radii):
                    styles["border-radius"] = " ".join(f"{rv:g}px" for rv in radii)
            elif "cornerRadius" in node and node["cornerRadius"] > 0:
                styles["border-radius"] = f'{node["cornerRadius"]:g}px'

            # When every fill of the node is a solid an image or an axis-aligned linear gradient set the div background from those fills in reverse order with a solid as a plain color or a single color gradient, an axis-aligned linear gradient as a linear gradient of its stops, and an image as a url scaled to cover, set background-blend-mode from the per layer blend modes, and download each image fill into the output folder.
            fills = node.get("fills", [])
            # Keep only visible fills (visible defaults to True when the key is absent).
            visible_fills = [f for f in fills if f.get("visible", True) is not False]

            def is_supported_fill(fill):
                # A SOLID fill is always supported.
                if fill["type"] == "SOLID":
                    return True
                # An IMAGE fill is always supported; it is rendered as a cover background.
                if fill["type"] == "IMAGE":
                    return True
                # A GRADIENT_LINEAR fill is supported when it is axis-aligned (horizontal or vertical).
                if fill["type"] == "GRADIENT_LINEAR":
                    h = fill["gradientHandlePositions"]
                    vertical   = abs(h[0]["x"] - h[1]["x"]) < 1e-6
                    horizontal = abs(h[0]["y"] - h[1]["y"]) < 1e-6
                    return vertical or horizontal
                return False

            # Gate: only build background when there is at least one visible fill and every visible fill is supported.
            if visible_fills and all(is_supported_fill(f) for f in visible_fills):
                bb = node["absoluteBoundingBox"]
                W  = bb["width"]
                H  = bb["height"]

                css_layers  = []
                blend_names = []

                # Build CSS layers in reversed fill order (Figma last fill = first CSS layer).
                for i, fill in enumerate(reversed(visible_fills)):
                    if fill["type"] == "SOLID":
                        c = css_color(fill["color"], fill.get("opacity", 1))
                        # The last CSS layer (i == len(visible_fills) - 1) becomes background-color, so emit a plain color.
                        if i == len(visible_fills) - 1:
                            layer = c
                        # Earlier layers must be a gradient, so wrap the solid color in a single-color linear gradient.
                        else:
                            layer = f"linear-gradient(0deg, {c} 0%, {c} 100%)"

                    elif fill["type"] == "GRADIENT_LINEAR":
                        # Compute the angle from the gradient handle positions.
                        h  = fill["gradientHandlePositions"]
                        dx = h[1]["x"] - h[0]["x"]
                        dy = h[1]["y"] - h[0]["y"]
                        angle = round(math.degrees(math.atan2(dx, -dy)) % 360)
                        # Project each color stop onto the gradient line to get its percentage.
                        th = math.radians(angle)
                        d  = (math.sin(th), -math.cos(th))
                        L  = abs(W * math.sin(th)) + abs(H * math.cos(th))
                        cx = W / 2
                        cy = H / 2
                        zx = cx - d[0] * L / 2
                        zy = cy - d[1] * L / 2
                        stop_strings = []
                        for s in fill["gradientStops"]:
                            Px  = (h[0]["x"] + s["position"] * (h[1]["x"] - h[0]["x"])) * W
                            Py  = (h[0]["y"] + s["position"] * (h[1]["y"] - h[0]["y"])) * H
                            pct = ((Px - zx) * d[0] + (Py - zy) * d[1]) / L * 100
                            stop_strings.append(f"{css_color(s['color'], fill.get('opacity', 1))} {('%g' % round(pct, 2))}%")
                        layer = f"linear-gradient({angle}deg, " + ", ".join(stop_strings) + ")"

                    else:
                        # IMAGE fill: render as a cover background, ignoring any crop transform.
                        # To resolve an image fill download it by mapping its imageRef through the file images endpoint then save it under the output directory and use that saved path in the url.
                        path  = download_image(fill["imageRef"])
                        layer = f"url({path}) center / cover no-repeat"

                    css_layers.append(layer)
                    bm = fill.get("blendMode", "NORMAL")
                    blend_names.append(bm.lower().replace("_", "-"))

                styles["background"] = ", ".join(css_layers)

                # Set background-blend-mode only when at least one layer is not normal.
                if any(bn != "normal" for bn in blend_names):
                    styles["background-blend-mode"] = ", ".join(blend_names)

            return styles

        def build_font_css(node):
            # For a text node set the div text to its characters and set font-family, font-weight, font-size in px, text-align, letter-spacing in px, and line-height in px from the node style and color from its single visible solid fill.
            figma_to_css = [
                ("fontFamily",          "font-family",    False),
                ("fontWeight",          "font-weight",    False),
                ("fontSize",            "font-size",      True),
                ("textAlignHorizontal", "text-align",     False),
                ("letterSpacing",       "letter-spacing", True),
                ("lineHeightPx",        "line-height",    True),
            ]
            style_source = node.get("style", {})
            parts = []
            for figma_key, css_key, use_px in figma_to_css:
                if figma_key in style_source:
                    val = style_source[figma_key]
                    if use_px:
                        parts.append(f"{css_key}: {val}px")
                    else:
                        parts.append(f"{css_key}: {val}")
            visible_fills = [f for f in node.get("fills", []) if f.get("visible", True) is not False]
            if len(visible_fills) == 1 and visible_fills[0]["type"] == "SOLID":
                fill = visible_fills[0]
                parts.append(f"color: {css_color(fill['color'], fill.get('opacity', 1))}")
            return "; ".join(parts)

        # When figma is given walk the node tree and build a nested html where each node is an absolute positioned div placed from its absoluteBoundingBox relative to its parent.
        def build_html_node(node, parent_x, parent_y):
            bb = node["absoluteBoundingBox"]
            left   = bb["x"] - parent_x
            top    = bb["y"] - parent_y
            width  = bb["width"]
            height = bb["height"]

            base_style = (
                f"position:absolute; "
                f"left:{left:g}px; top:{top:g}px; "
                f"width:{width:g}px; height:{height:g}px; "
                f"overflow:hidden"
            )

            # Add data-node-id to every div so the DOM walk can read the figma node id.
            node_id_attr = f' data-node-id="{node["id"]}"'

            # For a text node set the div text to its characters and set font-family, font-weight, font-size in px, text-align, letter-spacing in px, and line-height in px from the node style and color from its single visible solid fill.
            if "characters" in node and node["characters"]:
                font_css = build_font_css(node)
                style = base_style
                if font_css:
                    style = style + "; " + font_css
                text = html_lib.escape(node["characters"])
                return f'<div{node_id_attr} style="{style}">{text}</div>'

            # For a vector node fetch its svg through the images endpoint at format svg and inline that svg inside the div.
            if node["type"] == "VECTOR":
                node_id_local = node["id"]
                svg_q = urllib.parse.urlencode({"ids": node_id_local, "format": "svg"})
                svg_endpoint = f"https://api.figma.com/v1/images/{file_key}?{svg_q}"
                svg_req = urllib.request.Request(svg_endpoint, headers={"X-Figma-Token": token})
                with urllib.request.urlopen(svg_req) as svg_resp:
                    svg_data = json.loads(svg_resp.read())
                svg_url = svg_data["images"][node_id_local]
                with urllib.request.urlopen(svg_url) as svg_dl:
                    svg_markup = svg_dl.read().decode("utf-8")
                return f'<div{node_id_attr} style="{base_style}">{svg_markup}</div>'

            # For a node with no children and a visible image fill fetch the node through the images endpoint at format png and place that png file as the source of an image.
            has_visible_image = any(
                f.get("type") == "IMAGE" and f.get("visible", True) is not False
                for f in node.get("fills", [])
            )
            if not node.get("children") and has_visible_image:
                node_id_local = node["id"]
                png_q = urllib.parse.urlencode({"ids": node_id_local, "format": "png"})
                png_endpoint = f"https://api.figma.com/v1/images/{file_key}?{png_q}"
                png_req = urllib.request.Request(png_endpoint, headers={"X-Figma-Token": token})
                with urllib.request.urlopen(png_req) as png_resp:
                    png_data = json.loads(png_resp.read())
                png_url = png_data["images"][node_id_local]
                filename = re.sub(r"[^A-Za-z0-9_.-]", "-", node_id_local) + ".png"
                with urllib.request.urlopen(png_url) as png_dl:
                    (out_dir / filename).write_bytes(png_dl.read())
                return f'<img style="{base_style}" src="{filename}">'

            # Otherwise it is a frame: build css for borders, background, and recurse into children.
            frame_css_dict = build_frame_css(node)
            frame_css_parts = []
            for key, val in frame_css_dict.items():
                frame_css_parts.append(f"{key}: {val}")
            style = base_style
            if frame_css_parts:
                style = style + "; " + "; ".join(frame_css_parts)

            child_html_parts = []
            for child in node.get("children", []):
                # When figma is given skip a node whose visible is false or that is a mask and do not recurse into it so its children are dropped with it.
                if child.get("visible", True) is False or child.get("isMask", False):
                    continue
                child_html_parts.append(build_html_node(child, bb["x"], bb["y"]))
            children_html = "\n".join(child_html_parts)
            return f'<div{node_id_attr} style="{style}">{children_html}</div>'

        # Build the root div at left:0;top:0 and set the page body margin to 0.
        root_bb = document["absoluteBoundingBox"]
        root_html = build_html_node(document, root_bb["x"], root_bb["y"])
        html_string = (
            "<!DOCTYPE html><html><body style=\"margin:0\">"
            + root_html
            + "</body></html>"
        )

        # Load the html source into a chromium page at a fixed viewport width.
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1024})
            page.set_content(html_string, wait_until="networkidle")

            # Run the shared DOM walk using the shared root rule.
            tree = page.evaluate(_DOM_WALK_JS)

            # Collapse any FRAME whose only child is a FRAME without a style by lifting that child's own children into the parent and dropping the child.
            collapsed = collapse(tree)

            # Save a jpg screenshot of every frame and set its screenshot to that file name.
            _attach_figma_screenshots(collapsed, name, file_key, token, out_dir)

            browser.close()

    else:
        # When html is given read its body as the walk root.
        name = pathlib.Path(args.html).stem
        file_url = pathlib.Path(args.html).resolve().as_uri()

        # Load the html source into a chromium page at a fixed viewport width and read the single content root of its body or its body.
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1024})
            page.goto(file_url, wait_until="networkidle")

            # Run the shared DOM walk using the shared root rule.
            tree = page.evaluate(_DOM_WALK_JS)

            # Collapse any FRAME whose only child is a FRAME without a style by lifting that child's own children into the parent and dropping the child.
            collapsed = collapse(tree)

            # Save a jpg screenshot of every frame and set its screenshot to that file name.
            _attach_html_screenshots(collapsed, name, page, out_dir)

            browser.close()

        # When the element is an svg or an image whose source ends with svg make a VECTOR element with content set to the svg markup or the image source, then for an image source read the svg file relative to the html and set the content to its markup.
        base_dir = pathlib.Path(args.html).resolve().parent
        _fill_vector_svgs(collapsed, base_dir)

    # Write an object with a children array holding the transform of the body as a json in the output folder named from the source.
    output = {"children": [collapsed]}
    (out_dir / f"{name}.json").write_text(json.dumps(output, indent=2))

    # Validate the written object against element.schema.json in the references folder with a draft 2020-12 validator.
    schema_path = pathlib.Path(__file__).parent.parent / "references" / "element.schema.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.Draft202012Validator(schema).validate(output)

    # When emit-skeleton is given also render the design document tree into a skeleton written to the output folder as a name html file and a name css file, prefixing each element with an html comment in the form TYPE: box x,y,width,height then the element, rendering a FRAME as a div wrapping its rendered children, a TEXT as a p holding its content, a VECTOR as an img whose src is a deduplicated svg file written to the output folder, and an IMAGE as an img whose src is its content, emitting box only in the comment, all wrapped in a doctype html document with a head linking the css file and a body with margin zero.
    if args.emit_skeleton:
        _write_skeleton(output, out_dir, name)

    print(f"Wrote output to {out_dir / name}.json")


# Define a transform that turns an element into an element of the design document from its computed style and recurses into its children, ignoring script and style elements, reading every number as an integer normalizing a negative zero to zero and every color as rgba.
_DOM_WALK_JS = """
() => {
    // Parse a CSS color string like rgb(r, g, b) or rgba(r, g, b, a) into rgba(r, g, b, a) with integer channels.
    function toRgba(cssColor) {
        var m = cssColor.match(/rgba?\\(([^)]+)\\)/);
        if (!m) return cssColor;
        var parts = m[1].split(",").map(function(s) { return s.trim(); });
        var r = Math.round(parseFloat(parts[0]));
        var g = Math.round(parseFloat(parts[1]));
        var b = Math.round(parseFloat(parts[2]));
        var a = parts.length >= 4 ? parseFloat(parts[3]) : 1;
        return "rgba(" + r + ", " + g + ", " + b + ", " + a + ")";
    }

    // Normalize a negative zero to zero.
    function norm(n) { return Object.is(n, -0) ? 0 : n; }

    // Parse a CSS border side string like "Npx style color" and normalize the color part to rgba.
    function normalizeBorderSide(val) {
        if (!val || val === "0px" || val === "none") return "";
        // The browser serializes border as "Npx style rgba(...)" — reserialize the color portion.
        var m = val.match(/^(\\S+)\\s+(\\S+)\\s+(.+)$/);
        if (!m) return val;
        var widthPart = m[1];
        var stylePart = m[2];
        var colorPart = toRgba(m[3]);
        // Drop border sides where width is 0px.
        if (widthPart === "0px") return "";
        return widthPart + " " + stylePart + " " + colorPart;
    }

    // Parse a px value string like "16px" into an integer.
    function pxToInt(val) {
        return norm(Math.round(parseFloat(val)));
    }

    function transform(el) {
        // Set box to x, y, width, and height read from the element bounding rect on every element.
        var rect = el.getBoundingClientRect();
        var box = {
            x:      norm(Math.round(rect.x)),
            y:      norm(Math.round(rect.y)),
            width:  norm(Math.round(rect.width)),
            height: norm(Math.round(rect.height))
        };
        var tag = el.tagName.toLowerCase();

        // When the element is an svg or an image whose source ends with svg make a VECTOR element with content set to the svg markup or the image source, then for an image source read the svg file relative to the html and set the content to its markup.
        if (tag === "svg") {
            return { type: "VECTOR", content: el.outerHTML, box: box };
        }
        // When the element is an image whose source does not end with svg make an IMAGE element with content set to that source.
        if (tag === "img") {
            var src = el.getAttribute("src") || "";
            if (src.toLowerCase().endsWith(".svg")) {
                return { type: "VECTOR", content: src, box: box };
            }
            return { type: "IMAGE", content: src, box: box };
        }

        // When the element has no child elements and only text make a TEXT element with content set to that text and the computed font-family, font-weight, font-size, text-align, letter-spacing read as zero when normal, line-height, and color.
        if (el.children.length === 0 && el.textContent.trim() !== "") {
            var cs = getComputedStyle(el);
            var style = {};
            var ff = cs.getPropertyValue("font-family");
            if (ff !== "") style["font-family"] = ff;
            var fw = cs.getPropertyValue("font-weight");
            if (fw !== "") style["font-weight"] = norm(Math.round(parseFloat(fw)));
            var fsz = cs.getPropertyValue("font-size");
            if (fsz !== "") style["font-size"] = pxToInt(fsz);
            var ta = cs.getPropertyValue("text-align");
            if (ta !== "") style["text-align"] = ta;
            var ls = cs.getPropertyValue("letter-spacing");
            if (ls !== "") style["letter-spacing"] = (ls === "normal") ? 0 : pxToInt(ls);
            var lh = cs.getPropertyValue("line-height");
            if (lh !== "" && lh !== "normal") style["line-height"] = pxToInt(lh);
            var col = cs.getPropertyValue("color");
            if (col !== "") style["color"] = toRgba(col);
            return { type: "TEXT", content: el.textContent.trim(), style: style, box: box };
        }

        // Otherwise make a FRAME element with the computed border-top, border-right, border-bottom, border-left, border-radius, background, and background-blend-mode and children from the transform of each child element, splicing in the children of any element with a data-wrapper attribute in place of that element, reading the background as its color alone when there is no background image.
        var cs2 = getComputedStyle(el);
        var frameStyle = {};

        var bt = normalizeBorderSide(cs2.getPropertyValue("border-top"));
        if (bt !== "") frameStyle["border-top"] = bt;
        var br = normalizeBorderSide(cs2.getPropertyValue("border-right"));
        if (br !== "") frameStyle["border-right"] = br;
        var bb2 = normalizeBorderSide(cs2.getPropertyValue("border-bottom"));
        if (bb2 !== "") frameStyle["border-bottom"] = bb2;
        var bl = normalizeBorderSide(cs2.getPropertyValue("border-left"));
        if (bl !== "") frameStyle["border-left"] = bl;

        var brad = cs2.getPropertyValue("border-radius");
        if (brad !== "" && brad !== "0px") frameStyle["border-radius"] = brad;

        var bgImage = cs2.getPropertyValue("background-image");
        var bgColor = cs2.getPropertyValue("background-color");
        if (!(bgImage === "none" && bgColor === "rgba(0, 0, 0, 0)")) {
            if (bgImage === "none") {
                // No background image: store the color alone so the skeleton's solid-color detector can match it.
                frameStyle["background"] = toRgba(bgColor);
            } else {
                // Background image (gradient or url): read the full shorthand and basename any url().
                var bg = cs2.getPropertyValue("background");
                bg = bg.replace(/url\\((['"]?)([^'")]+)\\1\\)/g, function(_, q, u) {
                    var nameOnly = u.split("/").pop();
                    return 'url("' + nameOnly + '")';
                });
                frameStyle["background"] = bg;
            }
        }

        var bbm = cs2.getPropertyValue("background-blend-mode");
        if (bbm !== "") {
            var modes = bbm.split(", ");
            if (modes.some(function(m) { return m !== "normal"; })) frameStyle["background-blend-mode"] = modes;
        }

        var children = [];
        for (var k = 0; k < el.children.length; k++) {
            var childEl = el.children[k];
            var ctag = childEl.tagName.toLowerCase();
            if (ctag === "script" || ctag === "style") continue;
            if (childEl.getAttribute("data-wrapper") !== null) {
                var w = transform(childEl);            // a FRAME whose children are already flattened
                for (var j = 0; j < w.children.length; j++) children.push(w.children[j]);
            } else {
                children.push(transform(childEl));
            }
        }
        var node = { type: "FRAME" };
        // When the element has a data-node-id, read it into a temporary nodeId field so Python can batch-fetch screenshots.
        var nid = el.getAttribute("data-node-id");
        if (nid) node.nodeId = nid;
        if (Object.keys(frameStyle).length > 0) {
            node.style = frameStyle;
        }
        node.box = box;
        node.children = children;
        return node;
    }

    // Root at the single content element child of the body (ignoring script and style), otherwise the body itself.
    var roots = Array.prototype.filter.call(document.body.children, function (e) {
        var t = e.tagName.toLowerCase();
        return t !== "script" && t !== "style";
    });
    var root = roots.length === 1 ? roots[0] : document.body;
    return transform(root);
}
"""


if __name__ == "__main__":
    main()
