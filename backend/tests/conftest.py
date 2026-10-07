import json
import sys
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from agents.tool_context import ToolContext

from app.agents.context import PresentationContext
from app.decks.builtin import builtin_deck

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

PDF_PAGES = [
    ("Quarterly Review", ["Revenue grew 12 percent", "Two new markets opened"]),
    ("Product Roadmap", ["Mobile app launch in spring", "API platform beta"]),
    ("Hiring Plan", ["Ten engineers", "Three designers"]),
]


def make_pdf(path: Path, pages: list[tuple[str, list[str]]] = PDF_PAGES) -> Path:
    doc = pymupdf.open()
    for title, bullets in pages:
        page = doc.new_page(width=960, height=540)
        page.insert_text((60, 90), title, fontsize=36)
        for i, b in enumerate(bullets):
            page.insert_text((80, 170 + i * 40), f"- {b}", fontsize=18)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "deck.pdf")


@pytest.fixture
def sample_pptx(tmp_path: Path) -> Path:
    from make_sample_pptx import build

    return build(tmp_path / "deck.pptx")


@pytest.fixture
def ctx() -> PresentationContext:
    return PresentationContext(deck=builtin_deck())


@pytest.fixture
def invoke():
    """Invoke a FunctionTool the way the SDK does, with a ToolContext around our context."""

    async def _invoke(tool: Any, context: PresentationContext, **kwargs: Any) -> str:
        args = json.dumps(kwargs)
        tool_ctx = ToolContext(
            context=context, tool_name=tool.name, tool_call_id="call_test", tool_arguments=args
        )
        return await tool.on_invoke_tool(tool_ctx, args)

    return _invoke
