"# aidocconverter" 

python -m venv myenv
. \myenv\Scripts\Activate
pip install azure-ai-documentintelligence azure-ai-vision-imageanalysis python-docx pillow
# optional for hi-DPI recrop:
pip install pymupdf

Required environment variables
 DOCUMENTINTELLIGENCE_ENDPOINT
 DOCUMENTINTELLIGENCE_API_KEY
 VISION_ENDPOINT
 VISION_KEY


1) Azure Document Intelligence (prebuilt-layout, FIGURES) to extract figures as PNGs.
2) Azure Vision Image Analysis 4.0 to tag/caption each figure.
3) Auto-map figures to placeholders (or use a provided figure_map.json).
4) Replace [[IMG:<tag>]] placeholders across body, tables, headers/footers in a DOCX template.
5) Optional hi-DPI recrop from original PDF for better tagging.


Extract figures from Azure Document Intelligence (Layout)

Tag each figure with Azure Vision Image Analysis 4.0 (robust to .values being a property or a method)

Backfill tags from Dense Captions and then from caption keywords if needed

Replace [[IMG:<tag>]] placeholders in body, tables, headers/footers of a DOCX

Uses figure_map.json if present; otherwise you can opt-in to auto-map (largest image → first placeholder, etc.)


 python sopv2.py
