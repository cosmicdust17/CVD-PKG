"""Read-only PDF inventory and verifiable physical-page text. No KG extraction."""
import argparse
from pathlib import Path
from .core import file_identity, write

def audit(pdf, out):
    from pypdf import PdfReader
    pdf, out = Path(pdf).resolve(), Path(out)
    doc_id, sha = file_identity(pdf)
    reader = PdfReader(pdf)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF: no password was provided')
    pages = [{'page': i + 1, 'text': page.extract_text() or ''} for i, page in enumerate(reader.pages)]
    record = {'document_id': doc_id, 'sha256': sha, 'name': pdf.name, 'path': str(pdf),
              'page_count': len(pages), 'page_numbering': 'physical_pdf_1_based',
              'page_text_characters': [len(p['text']) for p in pages],
              'status': 'local_pdf_read_only; not RAGFlow parsing or knowledge extraction'}
    write(out / 'document.json', record)
    write(out / 'pages.json', pages)
    print(f'{pdf.name}: {len(pages)} pages, {sum(len(p["text"]) for p in pages)} text characters; {doc_id}')
    return record

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--out', default='data/pdf-audit')
    args = parser.parse_args()
    source = Path(args.input)
    files = sorted(source.rglob('*.pdf')) if source.is_dir() else [source]
    records = []
    for pdf in files:
        doc_id, _ = file_identity(pdf)
        records.append(audit(pdf, Path(args.out) / doc_id))
    write(Path(args.out) / 'inventory.json', records)

if __name__ == '__main__':
    main()
