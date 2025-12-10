"""
Gerador de Nota Promissória em PDF
Documento legal conforme Lei Uniforme de Genebra (Decreto nº 57.663/1966)
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)

logger = logging.getLogger(__name__)


def format_currency(value) -> str:
    """Formata valor para moeda brasileira"""
    if value is None:
        return "R$ 0,00"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_currency_extenso(value) -> str:
    """Converte valor numérico para extenso em português"""
    if value is None or value == 0:
        return "zero reais"

    value = float(value)

    unidades = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
                "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis",
                "dezessete", "dezoito", "dezenove"]
    dezenas = ["", "", "vinte", "trinta", "quarenta", "cinquenta",
               "sessenta", "setenta", "oitenta", "noventa"]
    centenas = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos",
                "seiscentos", "setecentos", "oitocentos", "novecentos"]

    def extenso_centena(n):
        if n == 0:
            return ""
        if n == 100:
            return "cem"

        c = n // 100
        d = (n % 100) // 10
        u = n % 10

        resultado = []
        if c > 0:
            resultado.append(centenas[c])

        if d == 1:
            resultado.append(unidades[10 + u])
        else:
            if d > 1:
                resultado.append(dezenas[d])
            if u > 0:
                resultado.append(unidades[u])

        return " e ".join([r for r in resultado if r])

    inteiro = int(value)
    centavos = int(round((value - inteiro) * 100))

    resultado = []

    if inteiro >= 1000000:
        milhoes = inteiro // 1000000
        inteiro = inteiro % 1000000
        if milhoes == 1:
            resultado.append("um milhão")
        else:
            resultado.append(f"{extenso_centena(milhoes)} milhões")

    if inteiro >= 1000:
        milhares = inteiro // 1000
        inteiro = inteiro % 1000
        if milhares == 1:
            resultado.append("mil")
        else:
            resultado.append(f"{extenso_centena(milhares)} mil")

    if inteiro > 0:
        resultado.append(extenso_centena(inteiro))

    if len(resultado) == 0:
        texto_reais = "zero reais"
    else:
        texto = " e ".join([r for r in resultado if r])
        if int(value) == 1:
            texto_reais = f"{texto} real"
        else:
            texto_reais = f"{texto} reais"

    if centavos > 0:
        if centavos == 1:
            texto_centavos = f"{extenso_centena(centavos)} centavo"
        else:
            texto_centavos = f"{extenso_centena(centavos)} centavos"
        return f"{texto_reais} e {texto_centavos}"

    return texto_reais


def format_date_extenso(d: date) -> str:
    """Formata data por extenso"""
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


def format_cpf_cnpj(doc: str) -> str:
    """Formata CPF ou CNPJ"""
    if not doc:
        return ""
    doc = ''.join(filter(str.isdigit, doc))
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    elif len(doc) == 14:
        return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
    return doc


class PromissoryPDF:
    """
    Gerador de Nota Promissória em PDF - Layout otimizado para 1 página A4
    Conforme Lei Uniforme de Genebra (Decreto nº 57.663/1966)
    """

    def __init__(self, company_data: dict, customer_data: dict, total_value: float, due_date: date, doc_number: str):
        self.company = company_data
        self.customer = customer_data
        self.total_value = total_value
        self.due_date = due_date
        self.doc_number = doc_number
        self.buffer = BytesIO()

    def generate(self) -> BytesIO:
        """Gera o PDF da promissória - Layout otimizado para caber em 1 folha A4"""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=1*cm,
            bottomMargin=1*cm
        )

        elements = []

        # Cores do documento
        AZUL_ESCURO = colors.HexColor('#1a365d')
        AZUL_MEDIO = colors.HexColor('#2c5282')
        CINZA = colors.HexColor('#4a5568')
        CINZA_CLARO = colors.HexColor('#718096')

        # ===== ESTILOS COMPACTOS =====
        title_style = ParagraphStyle(
            'TitleStyle',
            fontSize=18,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            spaceAfter=1*mm,
            textColor=AZUL_ESCURO,
            leading=20
        )

        subtitle_style = ParagraphStyle(
            'SubtitleStyle',
            fontSize=8,
            fontName='Helvetica',
            alignment=TA_CENTER,
            spaceAfter=3*mm,
            textColor=CINZA_CLARO
        )

        section_title_style = ParagraphStyle(
            'SectionTitleStyle',
            fontSize=9,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT,
            spaceBefore=3*mm,
            spaceAfter=1*mm,
            textColor=AZUL_MEDIO
        )

        body_style = ParagraphStyle(
            'BodyStyle',
            fontSize=10,
            fontName='Helvetica',
            alignment=TA_JUSTIFY,
            spaceBefore=2*mm,
            spaceAfter=2*mm,
            leading=13,
            firstLineIndent=8*mm
        )

        info_style = ParagraphStyle(
            'InfoStyle',
            fontSize=9,
            fontName='Helvetica',
            alignment=TA_LEFT,
            leading=12,
            textColor=CINZA
        )

        clause_style = ParagraphStyle(
            'ClauseStyle',
            fontSize=8,
            fontName='Helvetica',
            alignment=TA_JUSTIFY,
            spaceBefore=1*mm,
            spaceAfter=1*mm,
            leading=11,
            leftIndent=3*mm,
            textColor=CINZA
        )

        footer_style = ParagraphStyle(
            'FooterStyle',
            fontSize=7,
            fontName='Helvetica',
            alignment=TA_JUSTIFY,
            textColor=CINZA_CLARO,
            leading=9,
            spaceBefore=1*mm
        )

        # Preparar dados
        valor_extenso = format_currency_extenso(self.total_value)
        due_date_str = self.due_date.strftime('%d/%m/%Y') if self.due_date else '___/___/______'
        city_emitente = self.company.get('city', 'Local')
        state_emitente = self.company.get('state', '')
        local_pagamento = f"{city_emitente}/{state_emitente}" if state_emitente else city_emitente
        data_emissao = format_date_extenso(date.today())
        customer_name = self.customer.get('name', 'DEVEDOR')
        customer_doc = format_cpf_cnpj(self.customer.get('document', ''))
        customer_address = self.customer.get('address', '')
        customer_city = self.customer.get('city', '')
        customer_state = self.customer.get('state', '')
        company_name = self.company.get('legal_name') or self.company.get('trade_name', 'CREDOR')
        company_doc = format_cpf_cnpj(self.company.get('document', ''))
        company_address = self.company.get('address', '')

        # ═══════════════════════════════════════════════════════════
        # CABEÇALHO COMPACTO
        # ═══════════════════════════════════════════════════════════
        elements.append(Paragraph("NOTA PROMISSÓRIA", title_style))
        elements.append(Paragraph(
            "Título de Crédito — Lei Uniforme de Genebra (Decreto nº 57.663/1966)",
            subtitle_style
        ))

        # Linha decorativa simples
        elements.append(HRFlowable(width="100%", thickness=1.5, color=AZUL_MEDIO, spaceBefore=0, spaceAfter=4*mm))

        # ═══════════════════════════════════════════════════════════
        # QUADRO DE IDENTIFICAÇÃO - COMPACTO
        # ═══════════════════════════════════════════════════════════
        info_data = [
            [
                Paragraph("<b>Nº DO TÍTULO</b>", ParagraphStyle('', fontSize=8, alignment=TA_CENTER, textColor=CINZA)),
                Paragraph("<b>VENCIMENTO</b>", ParagraphStyle('', fontSize=8, alignment=TA_CENTER, textColor=CINZA)),
                Paragraph("<b>VALOR (R$)</b>", ParagraphStyle('', fontSize=8, alignment=TA_CENTER, textColor=CINZA)),
            ],
            [
                Paragraph(f"<b>{self.doc_number or 'S/N'}</b>", ParagraphStyle('', fontSize=11, fontName='Helvetica-Bold', alignment=TA_CENTER)),
                Paragraph(f"<b>{due_date_str}</b>", ParagraphStyle('', fontSize=11, fontName='Helvetica-Bold', alignment=TA_CENTER)),
                Paragraph(f"<font color='#c53030'><b>{format_currency(self.total_value)}</b></font>",
                         ParagraphStyle('', fontSize=12, fontName='Helvetica-Bold', alignment=TA_CENTER)),
            ],
        ]

        info_table = Table(info_data, colWidths=[5.5*cm, 5.5*cm, 7*cm])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f0f4f8')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.white),
            ('BOX', (0, 0), (-1, -1), 1, AZUL_MEDIO),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 2*mm))

        # Valor por extenso compacto
        extenso_box = Table([[
            Paragraph(f"<b>POR EXTENSO:</b> {valor_extenso.upper()}",
                     ParagraphStyle('', fontSize=9, fontName='Helvetica', alignment=TA_CENTER))
        ]], colWidths=[18*cm])
        extenso_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#f59e0b')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(extenso_box)
        elements.append(Spacer(1, 4*mm))

        # ═══════════════════════════════════════════════════════════
        # TEXTO PRINCIPAL - MAIS COMPACTO
        # ═══════════════════════════════════════════════════════════
        texto_promissoria = f"""No dia <b>{due_date_str}</b>, pagarei por esta única via de <b>NOTA PROMISSÓRIA</b>, à <b>{company_name}</b>, inscrita no CNPJ/CPF sob nº <b>{company_doc}</b>, {f'com sede em {company_address},' if company_address else ''} ou à sua ordem, a quantia de <b>{format_currency(self.total_value)}</b> ({valor_extenso.upper()}), em moeda corrente nacional, pagável na praça de <b>{local_pagamento}</b>."""

        elements.append(Paragraph(texto_promissoria, body_style))

        # ═══════════════════════════════════════════════════════════
        # CLÁUSULA DE MORA - COMPACTA
        # ═══════════════════════════════════════════════════════════
        elements.append(Paragraph("CLÁUSULA DE MORA", section_title_style))

        mora_text = """Em caso de inadimplemento, o débito será acrescido de: <b>(i)</b> Juros de mora de <b>1% ao mês</b>, <i>pro rata die</i>; <b>(ii)</b> Correção monetária pelo <b>INPC-E (IBGE)</b>; <b>(iii)</b> Multa de <b>2%</b> (art. 52, §1º, CDC); <b>(iv)</b> Honorários advocatícios de <b>10%</b> em caso de cobrança judicial/extrajudicial."""

        elements.append(Paragraph(mora_text, clause_style))

        # ═══════════════════════════════════════════════════════════
        # DADOS DAS PARTES - LADO A LADO COMPACTO
        # ═══════════════════════════════════════════════════════════
        elements.append(Paragraph("IDENTIFICAÇÃO DAS PARTES", section_title_style))

        info_parte_style = ParagraphStyle('', fontSize=8, fontName='Helvetica', leading=11, textColor=CINZA)

        # Emitente (Devedor) e Beneficiário (Credor) lado a lado
        emitente_text = f"""<b>EMITENTE / DEVEDOR</b><br/>
        <b>Nome:</b> {customer_name}<br/>
        <b>CPF/CNPJ:</b> {customer_doc or 'Não informado'}<br/>
        <b>Endereço:</b> {customer_address or 'Não informado'}<br/>
        <b>Cidade/UF:</b> {f'{customer_city}/{customer_state}' if customer_city else 'Não informado'}"""

        beneficiario_text = f"""<b>BENEFICIÁRIO / CREDOR</b><br/>
        <b>Razão Social:</b> {company_name}<br/>
        <b>CNPJ:</b> {company_doc}<br/>
        <b>Endereço:</b> {company_address or 'Não informado'}"""

        partes_table = Table([
            [Paragraph(emitente_text, info_parte_style), Paragraph(beneficiario_text, info_parte_style)]
        ], colWidths=[9*cm, 9*cm])
        partes_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('BOX', (0, 0), (0, 0), 0.5, colors.HexColor('#e2e8f0')),
            ('BOX', (1, 0), (1, 0), 0.5, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(partes_table)
        elements.append(Spacer(1, 6*mm))

        # ═══════════════════════════════════════════════════════════
        # LOCAL, DATA E ASSINATURA - COMPACTO
        # ═══════════════════════════════════════════════════════════
        elements.append(Paragraph(
            f"<b>{local_pagamento}</b>, {data_emissao}.",
            ParagraphStyle('DateStyle', fontSize=10, alignment=TA_RIGHT, fontName='Helvetica')
        ))
        elements.append(Spacer(1, 10*mm))

        # Área de assinatura compacta
        sig_table = Table([
            [Paragraph("_" * 45, ParagraphStyle('', fontSize=9, alignment=TA_CENTER))],
            [Paragraph(f"<b>{customer_name}</b>", ParagraphStyle('', fontSize=9, alignment=TA_CENTER, fontName='Helvetica-Bold'))],
            [Paragraph(f"CPF/CNPJ: {customer_doc} — <b>EMITENTE/DEVEDOR</b>", ParagraphStyle('', fontSize=8, alignment=TA_CENTER, textColor=CINZA))],
        ], colWidths=[10*cm])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))

        sig_container = Table([[sig_table]], colWidths=[18*cm])
        sig_container.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        elements.append(sig_container)
        elements.append(Spacer(1, 8*mm))

        # ═══════════════════════════════════════════════════════════
        # FUNDAMENTAÇÃO LEGAL - RODAPÉ COMPACTO
        # ═══════════════════════════════════════════════════════════
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0'), spaceBefore=0, spaceAfter=2*mm))

        notas_legais = """<b>FUNDAMENTAÇÃO LEGAL:</b> Lei Uniforme de Genebra (Dec. nº 57.663/66) · Código Civil (Lei nº 10.406/02), Arts. 887-926 · Lei de Protesto (Lei nº 9.492/97) · CDC (Lei nº 8.078/90), Art. 52, §1º · Art. 406 CC c/c Art. 161, §1º CTN. <i>Este documento constitui <b>TÍTULO EXECUTIVO EXTRAJUDICIAL</b> nos termos do Art. 784, I, do CPC (Lei nº 13.105/15).</i>"""

        elements.append(Paragraph(notas_legais, footer_style))

        # Construir documento
        doc.build(elements)
        self.buffer.seek(0)
        return self.buffer


async def generate_promissory_pdf(company_data: dict, customer_data: dict, total_value: float, due_date, doc_number: str) -> bytes:
    """
    Função auxiliar para gerar PDF da nota promissória
    Retorna os bytes do PDF
    """
    try:
        # Converter due_date para date se necessário
        if isinstance(due_date, str):
            due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00')).date()
        elif isinstance(due_date, datetime):
            due_date = due_date.date()

        pdf_generator = PromissoryPDF(
            company_data,
            customer_data,
            total_value,
            due_date,
            doc_number
        )
        pdf_buffer = pdf_generator.generate()
        return pdf_buffer.getvalue()

    except Exception as e:
        logger.error(f"❌ Erro ao gerar promissória: {str(e)}")
        raise
