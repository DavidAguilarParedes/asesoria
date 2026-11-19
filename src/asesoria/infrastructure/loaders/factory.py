from asesoria.domain.models import DocType, SourceDoc
from asesoria.domain.ports import Loader
from asesoria.infrastructure.loaders.edgar_html import EdgarHtmlLoader
from asesoria.infrastructure.loaders.factsheet import FactSheetLoader
from asesoria.infrastructure.loaders.html_sections import HtmlSectionLoader
from asesoria.infrastructure.loaders.markdown import MarkdownLoader
from asesoria.infrastructure.loaders.pdf_sections import PROSPECTUS_HEADINGS, PdfSectionLoader


class LoaderFactory:
    @staticmethod
    def get(doc: SourceDoc) -> Loader:
        match doc.doc_type:
            case DocType.TEN_K:
                return EdgarHtmlLoader()
            case DocType.FACT_SHEET:
                return FactSheetLoader()
            case DocType.PROSPECTUS:
                return PdfSectionLoader(PROSPECTUS_HEADINGS)
            case DocType.POLICY:
                return MarkdownLoader()
            case DocType.GUIDE if doc.extension == ".html":
                return HtmlSectionLoader()
            case DocType.GUIDE:
                return PdfSectionLoader()
        raise ValueError(f"Tipo de documento no soportado: {doc.doc_type}")
