import io
from docx import Document


def resume_to_docx(resume_text: str) -> bytes:
    """
    Converts the tailored resume text into a .docx file in memory.
    Lines in ALL CAPS are treated as section headers and bolded.
    Returns the raw bytes of the .docx file.
    """
    document = Document()

    for line in resume_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            document.add_paragraph("")
            continue

        is_header = stripped.isupper() and len(stripped) > 1
        paragraph = document.add_paragraph()
        run = paragraph.add_run(stripped)
        if is_header:
            run.bold = True

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
