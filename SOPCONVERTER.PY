import os, io, re, json
from pathlib import Path
from docx import Document
from docx.shared import Inches
from PIL import Image

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeOutputOption

# Azure Vision 4.0 SDK
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures

# ---------- Config ----------
DOC_PATH = "input.pdf"                 # your source document (pdf/docx/pptx/etc.)
TEMPLATE_DOCX = "template.docx"        # docx with [[IMG:...]] placeholders
OUTPUT_DOCX = "output.docx"
PLACEHOLDER_MAP_JSON = "figure_map.json"  # {"cover":"1.1","chart-1":"2.3", ...}
IMG_DIR = Path("extracted_images")
IMG_DIR.mkdir(exist_ok=True)

# ---------- Clients ----------
di = DocumentIntelligenceClient(
    endpoint=os.environ["DOCUMENTINTELLIGENCE_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["DOCUMENTINTELLIGENCE_API_KEY"])
)
vision = ImageAnalysisClient(
    endpoint=os.environ["VISION_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["VISION_KEY"])
)

# ---------- 1) Analyze & fetch all figures ----------
with open(DOC_PATH, "rb") as f:
    poller = di.begin_analyze_document(
        "prebuilt-layout",
        body=f,
        output=[AnalyzeOutputOption.FIGURES]  # ask service to crop images for us
    )
result = poller.result()
operation_id = poller.details["operation_id"]  # needed to download figures

fig_index = {}  # figure_id -> local file path
tags_index = {} # figure_id -> list of tags

def extract_tags(result):
    # Preferred path (Image Analysis 4.0 Python SDK)
    vals = getattr(getattr(result, "tags", None), "values", None)
    if isinstance(vals, list):
        return [t.name for t in vals]
    # Fallback if you ever fed raw REST JSON (rare in this script)
    if isinstance(result, dict):
        maybe = result.get("tagsResult", {}).get("values") or result.get("tags", [])
        return [t.get("name") for t in maybe if isinstance(t, dict)]
    return []

def extract_caption(result):
    cap = getattr(result, "caption", None)
    if cap and getattr(cap, "text", None):
        return cap.text
    if isinstance(result, dict):
        return (result.get("captionResult") or {}).get("text")
    return None

if result.figures:
    for fig in result.figures:
        if not fig.id:
            continue
        # download cropped PNG for this figure
        stream = di.get_analyze_result_figure(
            model_id=result.model_id,
            result_id=operation_id,
            figure_id=fig.id
        )
        out_path = IMG_DIR / f"{fig.id}.png"
        with open(out_path, "wb") as w:
            for chunk in stream:
                w.write(chunk)
        fig_index[fig.id] = str(out_path)

        # ---------- 2) Tag each image with Vision 4.0 ----------
        with open(out_path, "rb") as img_f:
            ia = vision.analyze(
                image_data=img_f.read(),
                visual_features=[VisualFeatures.TAGS, VisualFeatures.CAPTION]  # caption optional
            )
        tags = extract_tags(ia)
        caption = extract_caption(ia)
        tags_index[fig.id] = {"tags": tags, "caption": caption}
else:
    print("No figures found in the document.")

# Save tags to a sidecar file if you want
with open("image_tags.json", "w", encoding="utf-8") as jf:
    json.dump(tags_index, jf, ensure_ascii=False, indent=2)

# ---------- 3) Rebuild a DOCX by replacing placeholders ----------
# Load your mapping of placeholder -> figureId (e.g., {"cover":"1.1", ...})
with open(PLACEHOLDER_MAP_JSON, "r", encoding="utf-8") as mf:
    placeholder_map = json.load(mf)

doc = Document(TEMPLATE_DOCX)
pattern = re.compile(r"\[\[IMG:([A-Za-z0-9_.\-]+)\]\]")  # [[IMG:tag]]

def replace_run_with_image(paragraph, run, img_path, max_width_in=6.0):
    # remove the placeholder text and insert image in its place
    text = run.text
    m = pattern.search(text)
    if not m: 
        return False
    before = text[:m.start()]
    after  = text[m.end():]

    run.text = before
    # insert the image after this run
    new_run = paragraph.add_run()
    # scale to a max width
    with Image.open(img_path) as im:
        width, height = im.size
        # basic scale-to-fit by width
        new_run.add_picture(img_path, width=Inches(min(max_width_in, width/96)))  # assume 96 DPI; tweak if needed
    if after:
        paragraph.add_run(after)
    return True

for para in doc.paragraphs:
    # scan all runs for placeholders
    for run in list(para.runs):
        m = pattern.search(run.text)
        if not m:
            continue
        tag = m.group(1)
        fig_id = placeholder_map.get(tag)
        if not fig_id:
            # leave text as-is if mapping isn't present
            continue
        img_path = fig_index.get(fig_id)
        if not img_path:
            continue
        replace_run_with_image(para, run, img_path)

doc.save(OUTPUT_DOCX)

print(f"Done. Wrote {OUTPUT_DOCX}.")
print("Tag metadata in image_tags.json (per figureId).")
