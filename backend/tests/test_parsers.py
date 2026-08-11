from pathlib import Path

from app.document_parser import DocumentParser


def test_all_demo_formats_are_parsed() -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "generated"
    expected = {
        "product_S4-1000.pdf": "S4-1000",
        "quality_guide_S4-1000.docx": "十件一箱",
        "supplier_cost_001.xlsx": "Unit Cost",
        "inquiry_001.eml": "询价",
    }
    parser = DocumentParser()
    for filename, needle in expected.items():
        text = "\n".join(block.content for block in parser.parse(root / filename))
        assert needle in text
