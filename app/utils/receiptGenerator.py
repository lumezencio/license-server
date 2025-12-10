# [ Imports ]
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import locale
import logging

# IMPORTES ADICIONAIS PARA FORMATAÇÃO DE TEXTO PERFEITA
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet
# IMPORTANDO O ALINHAMENTO CENTRAL
from reportlab.lib.enums import TA_RIGHT, TA_JUSTIFY, TA_CENTER

# Configurar logging
logger = logging.getLogger(__name__)

try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except:
        pass

# ==========================================
# 🎨 CONFIGURAÇÕES DE DESIGN "FARAÔNICO" V4.3
# ==========================================
class ReceiptDesign:
    # Paleta de cores mantida: Autoridade e Luxo
    PRIMARY = '#000000'      # Preto (Textos)
    SECONDARY = '#B8860B'    # Ouro escuro (Linhas de luxo)
    ACCENT = '#1a237e'       # Azul profundo (Valor e Borda Interna)
    DARK = '#343a40'         # Cinza escuro
    LIGHT = '#ffffff'        # Branco
    GRAY = '#6c757d'         # Cinza
    BACKGROUND = '#FDFBF5'   # Fundo Marfim

    # Fontes clássicas (Serifadas para autoridade)
    FONT_BOLD = "Times-Bold"
    FONT_REGULAR = "Times-Roman"
    FONT_ITALIC = "Times-Italic"

    # Margens PROPORCIONAIS (Mantidas)
    MARGIN_LEFT = 3.0*cm
    MARGIN_RIGHT = 3.0*cm
    MARGIN_TOP = 2.8*cm
    MARGIN_BOTTOM = 2.8*cm

    # Espaçamentos PROPORCIONAIS (Mantidos)
    SPACE_XL = 2.0*cm
    SPACE_L = 1.5*cm
    SPACE_M = 1.0*cm
    SPACE_S = 0.6*cm
    SPACE_XS = 0.3*cm

# ==========================================
# 💎 FUNÇÕES DE DESENHO REFINADAS
# ==========================================

def draw_refined_line(c, y_pos):
    """Desenha uma linha dupla "refinada" (grossa e fina) para um acabamento de luxo."""
    largura = A4[0]
    c.setStrokeColor(HexColor(ReceiptDesign.SECONDARY))

    c.setLineWidth(2.0) # Linha Grossa
    c.line(ReceiptDesign.MARGIN_LEFT, y_pos, largura - ReceiptDesign.MARGIN_RIGHT, y_pos)

    y_pos_fina = y_pos - 0.08*cm # Linha Fina
    c.setLineWidth(0.5)
    c.line(ReceiptDesign.MARGIN_LEFT, y_pos_fina, largura - ReceiptDesign.MARGIN_RIGHT, y_pos_fina)

    return y_pos - 0.2*cm

def numero_por_extenso(valor: Decimal) -> str:
    """Converte número para extenso (Sem alterações)"""
    unidades = ["", "Um", "Dois", "Três", "Quatro", "Cinco", "Seis", "Sete", "Oito", "Nove"]
    dezenas = ["", "", "Vinte", "Trinta", "Quarenta", "Cinquenta", "Sessenta", "Setenta", "Oitenta", "Noventa"]
    especiais = ["Dez", "Onze", "Doze", "Treze", "Catorze", "Quinze", "Dezesseis", "Dezessete", "Dezoito", "Dezenove"]
    centenas = ["", "Cento", "Duzentos", "Trezentos", "Quatrocentos", "Quinhentos", "Seiscentos", "Setecentos", "Oitocentos", "Novecentos"]

    def converte_ate_999(n):
        if n == 0:
            return ""
        elif n < 10:
            return unidades[n]
        elif n < 20:
            return especiais[n - 10]
        elif n < 100:
            d, u = divmod(n, 10)
            if u == 0:
                return dezenas[d]
            return f"{dezenas[d]} e {unidades[u]}"
        else:
            c, resto = divmod(n, 100)
            if n == 100:
                return "Cem"
            if resto == 0:
                return centenas[c]
            return f"{centenas[c]} e {converte_ate_999(resto)}"

    valor_int = int(valor)
    centavos = int(round((valor - valor_int) * 100))

    if valor_int == 0 and centavos == 0:
        return "Zero Reais"

    parte_inteira = ""

    if valor_int >= 1000000:
        milhoes = valor_int // 1000000
        resto = valor_int % 1000000
        if milhoes == 1:
            parte_inteira = "Um Milhão"
        else:
            parte_inteira = f"{converte_ate_999(milhoes)} Milhões"
        if resto > 0:
            parte_inteira += f" e {converte_ate_999(resto)}"
    elif valor_int >= 1000:
        milhares = valor_int // 1000
        resto = valor_int % 1000
        if milhares == 1:
            parte_inteira = "Mil"
        else:
            parte_inteira = f"{converte_ate_999(milhares)} Mil"
        if resto > 0:
            parte_inteira += f" e {converte_ate_999(resto)}"
    else:
        parte_inteira = converte_ate_999(valor_int)

    if valor_int == 1:
        parte_inteira += " Real"
    elif valor_int > 1:
        parte_inteira += " Reais"
    elif valor_int == 0 and centavos > 0:
        parte_inteira = ""

    if centavos > 0:
        if centavos == 1:
            parte_centavos = "Um Centavo"
        else:
            parte_centavos = f"{converte_ate_999(centavos)} Centavos"
        if parte_inteira:
            return f"{parte_inteira} e {parte_centavos}"
        else:
            return parte_centavos

    return parte_inteira

def draw_watermark(c):
    """Marca d'água monumental (Sem alterações)"""
    try:
        c.saveState()
        c.translate(A4[0]/2, A4[1]/2)
        c.rotate(45)
        c.setFont(ReceiptDesign.FONT_BOLD, 110)
        c.setFillColor(HexColor('#e9ecef'))
        c.setFillAlpha(0.5)
        c.drawCentredString(0, 0, "RECIBO")
        c.restoreState()
    except Exception as e:
        logger.warning(f"Erro na marca d'água: {e}")

def draw_header(c, company_data, y_position, logo_path=None):
    """
    V4.1 (INTACTA): Logo maior, borda arredondada e
    texto da empresa PERFEITAMENTE CENTRALIZADO (na área direita).
    MODIFICADO: Recebe logo_path do tenant multi-tenant
    """
    largura = A4[0]

    initial_text_y = y_position

    logo_x = ReceiptDesign.MARGIN_LEFT
    logo_size = 2.5*cm # LOGO MAIOR

    # 1. LOGO COM BORDA COMPOSTA ARREDONDADA
    # Multi-tenant: usa logo_path do tenant se fornecido
    if logo_path:
        logo_file = Path(logo_path)
    else:
        logo_file = Path("static/company/logomarca.png")

    logo_box_width = logo_size + 1.0*cm # Mais espaço de "respiro"
    logo_box_height = logo_size + 1.0*cm
    logo_box_x = logo_x - 0.5*cm # Centraliza o logo na caixa
    logo_box_y = y_position - logo_box_height

    corner_radius = 0.4*cm

    c.setFillColor(HexColor(ReceiptDesign.BACKGROUND))
    c.roundRect(logo_box_x, logo_box_y, logo_box_width, logo_box_height, corner_radius, stroke=0, fill=1)

    c.setStrokeColor(HexColor(ReceiptDesign.SECONDARY))
    c.setLineWidth(2.5)
    c.roundRect(logo_box_x, logo_box_y, logo_box_width, logo_box_height, corner_radius, stroke=1, fill=0)

    inset_logo = 0.15*cm
    c.setStrokeColor(HexColor(ReceiptDesign.ACCENT))
    c.setLineWidth(1)
    c.roundRect(logo_box_x + inset_logo, logo_box_y + inset_logo,
           logo_box_width - (2*inset_logo), logo_box_height - (2*inset_logo),
           corner_radius - inset_logo/2, stroke=1, fill=0)

    if logo_file.exists():
        try:
            c.drawImage(str(logo_file), logo_x, logo_box_y + (logo_box_height - logo_size)/2,
                        width=logo_size, height=logo_size,
                        mask='auto', preserveAspectRatio=True)
            logger.info(f"Logo carregado com sucesso: {logo_file}")
        except Exception as e:
            logger.warning(f"Não foi possível desenhar o logo: {e}")
    else:
        logger.warning(f"Arquivo de logo não encontrado: {logo_file}")

    # 2. DADOS DA EMPRESA (CENTRALIZADOS USANDO PARAGRAPH)
    text_x_start = logo_box_x + logo_box_width + ReceiptDesign.SPACE_M
    text_width = (largura - ReceiptDesign.MARGIN_RIGHT) - text_x_start

    styles = getSampleStyleSheet()
    style = styles['Normal']
    style.alignment = TA_CENTER # ALINHAMENTO CENTRALIZADO
    style.fontName = ReceiptDesign.FONT_REGULAR
    style.textColor = HexColor(ReceiptDesign.PRIMARY)

    text_content = ""
    if company_data:
        empresa_nome = (company_data.get('legal_name') or company_data.get('trade_name', '')).upper()
        documento = company_data.get('document', '')

        text_content += f"<font name='{ReceiptDesign.FONT_BOLD}' size=14>{empresa_nome}</font><br/>"

        if documento:
            tipo_doc = 'CNPJ' if company_data.get('person_type') == 'PJ' else 'CPF'
            text_content += f"<font name='{ReceiptDesign.FONT_REGULAR}' size=10 color='{ReceiptDesign.DARK}'>{tipo_doc}: {documento}</font><br/>"

        endereco_parts = []
        if company_data.get('street'):
            endereco = company_data.get('street')
            if company_data.get('number'):
                endereco += f", {company_data.get('number')}"
            endereco_parts.append(endereco)

        if company_data.get('neighborhood'):
            endereco_parts.append(company_data.get('neighborhood'))

        if endereco_parts:
            endereco_text = " • ".join(endereco_parts)
            text_content += f"<font name='{ReceiptDesign.FONT_REGULAR}' size=9 color='{ReceiptDesign.GRAY}'>{endereco_text}</font>"

    p = Paragraph(text_content, style)

    w, h = p.wrap(text_width, 10*cm) # Calcula a altura

    # Alinha o *centro* do texto com o *centro* da caixa do logo (Alinhamento vertical)
    logo_box_center_y = logo_box_y + (logo_box_height / 2)
    text_y_draw = logo_box_center_y - (h / 2)
    p.drawOn(c, text_x_start, text_y_draw)

    # O Y final é o mais baixo entre o logo e o texto
    final_y_header_content = min(logo_box_y, text_y_draw)

    # 3. LINHA REFINADA (Dupla)
    current_y = draw_refined_line(c, final_y_header_content - ReceiptDesign.SPACE_M)

    return current_y - ReceiptDesign.SPACE_L

def draw_title(c, y_position):
    """Título CENTRALIZADO com LINHA REFINADA (Dupla) - INTACTO"""
    c.setFont(ReceiptDesign.FONT_BOLD, 26)
    c.setFillColor(HexColor(ReceiptDesign.PRIMARY))
    titulo = "RECIBO DE PAGAMENTO"
    c.drawCentredString(A4[0] / 2, y_position, titulo)

    # LINHA REFINADA (Dupla)
    line_y = y_position - 0.6*cm
    line_y = draw_refined_line(c, line_y)

    return line_y - ReceiptDesign.SPACE_M

def draw_payer_info(c, customer_data, y_position):
    """Informações do pagador (INTACTO)"""
    customer_name = customer_data.get('name', 'N/A').upper()
    customer_doc = customer_data.get('document', 'N/A')

    c.setFont(ReceiptDesign.FONT_REGULAR, 12)
    c.setFillColor(HexColor(ReceiptDesign.DARK))

    texto1 = f"Recebemos de {customer_name}, inscrito(a) no CPF/CNPJ sob o nº"
    c.drawString(ReceiptDesign.MARGIN_LEFT, y_position, texto1)
    y_position -= ReceiptDesign.SPACE_S

    c.setFont(ReceiptDesign.FONT_BOLD, 12)
    doc_width = c.stringWidth(customer_doc, ReceiptDesign.FONT_BOLD, 12)
    c.drawString(ReceiptDesign.MARGIN_LEFT, y_position, customer_doc)

    c.setFont(ReceiptDesign.FONT_REGULAR, 12)
    complemento = ", a importância descrita abaixo:"
    c.drawString(ReceiptDesign.MARGIN_LEFT + doc_width + 0.1*cm, y_position, complemento)

    return y_position - ReceiptDesign.SPACE_L

def draw_amount(c, amount, y_position):
    """Caixa de valor com BORDA COMPOSTA ARREDONDADA (INTACTO)"""
    largura = A4[0]
    container_height = 3.5*cm

    box_x = ReceiptDesign.MARGIN_LEFT
    box_y = y_position - container_height
    box_width = largura - ReceiptDesign.MARGIN_LEFT - ReceiptDesign.MARGIN_RIGHT

    corner_radius = 0.4*cm

    c.setFillColor(HexColor(ReceiptDesign.BACKGROUND))
    c.roundRect(box_x, box_y, box_width, container_height, corner_radius, stroke=0, fill=1)

    c.setStrokeColor(HexColor(ReceiptDesign.SECONDARY))
    c.setLineWidth(2.5)
    c.roundRect(box_x, box_y, box_width, container_height, corner_radius, stroke=1, fill=0)

    inset = 0.15*cm
    c.setStrokeColor(HexColor(ReceiptDesign.ACCENT))
    c.setLineWidth(1)
    c.roundRect(box_x + inset, box_y + inset,
           box_width - (2*inset), container_height - (2*inset),
           corner_radius - inset/2, stroke=1, fill=0)

    # Valor numérico
    valor_formatado = f"R$ {amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    c.setFont(ReceiptDesign.FONT_BOLD, 36)
    c.setFillColor(HexColor(ReceiptDesign.ACCENT))
    valor_width = c.stringWidth(valor_formatado, ReceiptDesign.FONT_BOLD, 36)
    valor_x = (largura - valor_width) / 2
    valor_y = y_position - 1.5*cm
    c.drawString(valor_x, valor_y, valor_formatado)

    # Valor por extenso
    valor_extenso = numero_por_extenso(Decimal(str(amount)))
    c.setFont(ReceiptDesign.FONT_ITALIC, 12)
    c.setFillColor(HexColor(ReceiptDesign.DARK))
    extenso_width = c.stringWidth(valor_extenso, ReceiptDesign.FONT_ITALIC, 12)
    extenso_x = (largura - extenso_width) / 2
    extenso_y = y_position - 2.8*cm
    c.drawString(extenso_x, extenso_y, f"({valor_extenso})")

    return y_position - (container_height + ReceiptDesign.SPACE_L)

def draw_payment_details(c, installment_data, y_position):
    """
    Detalhes do pagamento PERFEITAMENTE JUSTIFICADO (INTACTO)
    """
    installment_num = installment_data.get('installment_number', 1)
    total_installments = installment_data.get('total_installments', 1)
    description = installment_data.get('description', 'PAGAMENTO')
    payment_date = installment_data.get('payment_date') or installment_data.get('due_date')

    if isinstance(payment_date, str):
        payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))
    data_formatada = payment_date.strftime('%d/%m/%Y')

    max_width = A4[0] - ReceiptDesign.MARGIN_LEFT - ReceiptDesign.MARGIN_RIGHT

    full_text = (
        f"O referido valor é referente ao pagamento da parcela nº {installment_num} de um total de {total_installments}, "
        f"relativa a \"{description}\". O pagamento foi registrado em {data_formatada}, dando plena, geral e irrevogável "
        "quitação à referida parcela."
    )

    styles = getSampleStyleSheet()
    style = styles['Normal']
    style.fontName = ReceiptDesign.FONT_REGULAR
    style.fontSize = 12
    style.leading = 14 # Espaçamento entre linhas
    style.alignment = TA_JUSTIFY # ALINHAMENTO JUSTIFICADO
    style.textColor = HexColor(ReceiptDesign.DARK)

    p = Paragraph(full_text, style)

    w, h = p.wrap(max_width, 10*cm) # Calcula altura

    # Desenha o parágrafo na posição correta
    p.drawOn(c, ReceiptDesign.MARGIN_LEFT, y_position - h)

    return y_position - h - ReceiptDesign.SPACE_L

def draw_footer(c, company_data, y_position):
    """Rodapé com data e ASSINATURA REFINADA (INTACTO)"""
    largura = A4[0]
    centro_x = largura / 2

    # Data e local (Centralizado)
    cidade_empresa = company_data.get('city', 'Cidade') if company_data else 'Cidade'
    estado_empresa = company_data.get('state', 'UF') if company_data else 'UF'

    hoje = datetime.now()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
             'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
    mes_nome = meses[hoje.month - 1]
    data_extenso = f"{cidade_empresa} ({estado_empresa}), {hoje.day} de {mes_nome} de {hoje.year}."

    c.setFont(ReceiptDesign.FONT_REGULAR, 12)
    c.setFillColor(HexColor(ReceiptDesign.DARK))
    c.drawCentredString(centro_x, y_position, data_extenso)

    # Linha de assinatura REFINADA (Dupla)
    line_y = y_position - ReceiptDesign.SPACE_L
    old_margin_left = ReceiptDesign.MARGIN_LEFT
    old_margin_right = ReceiptDesign.MARGIN_RIGHT
    ReceiptDesign.MARGIN_LEFT = 5.5*cm
    ReceiptDesign.MARGIN_RIGHT = 5.5*cm

    line_y = draw_refined_line(c, line_y)

    ReceiptDesign.MARGIN_LEFT = old_margin_left
    ReceiptDesign.MARGIN_RIGHT = old_margin_right

    # Nome da empresa (Centralizado)
    current_y = line_y - ReceiptDesign.SPACE_S
    if company_data:
        responsavel = company_data.get('legal_name') or company_data.get('trade_name', 'Responsável')
    else:
        responsavel = "Responsável"

    c.setFont(ReceiptDesign.FONT_BOLD, 14)
    c.setFillColor(HexColor(ReceiptDesign.PRIMARY))
    c.drawCentredString(centro_x, current_y, responsavel.upper())

    # CNPJ (Centralizado)
    if company_data and company_data.get('document'):
        current_y -= (ReceiptDesign.SPACE_S * 0.8)
        documento = company_data.get('document', '')
        tipo_doc = 'CNPJ' if company_data.get('person_type') == 'PJ' else 'CPF'
        info_doc = f"{tipo_doc}: {documento}"
        c.setFont(ReceiptDesign.FONT_REGULAR, 10)
        c.setFillColor(HexColor(ReceiptDesign.GRAY))
        c.drawCentredString(centro_x, current_y, info_doc)

def draw_document_code(c, code):
    """Código único do documento no rodapé (INTACTO)"""
    c.setFont(ReceiptDesign.FONT_REGULAR, 8)
    c.setFillColor(HexColor(ReceiptDesign.GRAY))
    code_width = c.stringWidth(code, ReceiptDesign.FONT_REGULAR, 8)
    x_pos = (A4[0] - code_width) / 2
    y_pos = ReceiptDesign.MARGIN_BOTTOM / 2
    c.drawString(x_pos, y_pos, code)

# ==========================================
# 💎 FUNÇÃO MODIFICADA 💎
# ==========================================
def draw_legal_articles(c):
    """
    NOVA FUNÇÃO V4.3: Desenha os artigos 319 e 320 com
    destaque "faraônico" no número, como a imagem.
    """
    largura = A4[0]

    # Posição: Acima da posição do código do documento
    y_pos_doc_code = ReceiptDesign.MARGIN_BOTTOM / 2
    current_y = y_pos_doc_code + 2.0*cm # Posição inicial (mais alta)

    box_width = 1.8*cm
    box_height = 0.5*cm
    box_radius = 0.1*cm

    text_x_start = ReceiptDesign.MARGIN_LEFT + box_width + 0.3*cm
    text_width = (largura - ReceiptDesign.MARGIN_RIGHT) - text_x_start

    # Estilo do parágrafo do texto da lei
    styles = getSampleStyleSheet()
    style = styles['Normal']
    style.fontName = ReceiptDesign.FONT_ITALIC # Fonte Clássica Itálico
    style.fontSize = 7 # Pequeno e sutil
    style.alignment = TA_JUSTIFY # Justificado
    style.textColor = HexColor(ReceiptDesign.GRAY) # Cinza sutil
    style.leading = 9

    # --- ARTIGO 319 ---

    # 1. Caixa de destaque (Azul Accent)
    c.setFillColor(HexColor(ReceiptDesign.ACCENT))
    c.roundRect(ReceiptDesign.MARGIN_LEFT, current_y - box_height, box_width, box_height, box_radius, stroke=0, fill=1)

    # 2. Texto do Artigo (Branco, Negrito, Centralizado)
    c.setFillColor(HexColor(ReceiptDesign.LIGHT))
    c.setFont(ReceiptDesign.FONT_BOLD, 8)
    art_num_text = "Art. 319."
    text_width_art = c.stringWidth(art_num_text, ReceiptDesign.FONT_BOLD, 8)
    # Ajuste fino para centralizar o texto verticalmente na caixa
    text_y_art = current_y - (box_height / 2) - (c.stringWidth('A', ReceiptDesign.FONT_BOLD, 8) / 2) + 0.05*cm
    c.drawString(ReceiptDesign.MARGIN_LEFT + (box_width - text_width_art) / 2, text_y_art, art_num_text)

    # 3. Texto da Lei (em Parágrafo para quebrar linha)
    art_319_text = "O devedor que paga tem direito a quitação regular, e pode reter o pagamento, enquanto não lhe seja dada."
    p319 = Paragraph(art_319_text, style)
    w, h319 = p319.wrap(text_width, 10*cm)

    # Alinhar o parágrafo verticalmente (ao topo) com a caixa
    p319.drawOn(c, text_x_start, current_y - h319)

    # Mover cursor para baixo
    current_y -= max(box_height, h319) + 0.3*cm

    # --- ARTIGO 320 ---

    # 1. Caixa de destaque
    c.setFillColor(HexColor(ReceiptDesign.ACCENT))
    c.roundRect(ReceiptDesign.MARGIN_LEFT, current_y - box_height, box_width, box_height, box_radius, stroke=0, fill=1)

    # 2. Texto do Artigo
    c.setFillColor(HexColor(ReceiptDesign.LIGHT))
    c.setFont(ReceiptDesign.FONT_BOLD, 8)
    art_num_text = "Art. 320."
    text_width_art = c.stringWidth(art_num_text, ReceiptDesign.FONT_BOLD, 8)
    text_y_art = current_y - (box_height / 2) - (c.stringWidth('A', ReceiptDesign.FONT_BOLD, 8) / 2) + 0.05*cm
    c.drawString(ReceiptDesign.MARGIN_LEFT + (box_width - text_width_art) / 2, text_y_art, art_num_text)

    # 3. Texto da Lei
    art_320_text = "A quitação, que sempre poderá ser dada por instrumento particular, designará o valor e a espécie da dívida quitada, o nome do devedor, ou quem por este pagou, o tempo e o lugar do pagamento, com a assinatura do credor, ou do seu representante."
    p320 = Paragraph(art_320_text, style)
    w, h320 = p320.wrap(text_width, 10*cm)

    # Alinhar o parágrafo
    p320.drawOn(c, text_x_start, current_y - h320)

# ==========================================
# 🚀 FUNÇÃO PRINCIPAL (GERADOR)
# ==========================================

async def generate_receipt_pdf(installment_data: dict, customer_data: dict, company_data: dict = None, logo_path: str = None) -> bytes:
    """
    Gera PDF do recibo com design "FARAÔNICO E INVEJÁVEL" (V4.3)
    MODIFICADO: Recebe logo_path do tenant multi-tenant
    """

    from io import BytesIO
    buffer = BytesIO()

    c = canvas.Canvas(buffer, pagesize=A4)
    altura = A4[1]

    try:
        # 🎯 CONFIGURAÇÃO INICIAL
        y_pos = altura - ReceiptDesign.MARGIN_TOP

        # Gerando código similar ao do PDF original (REC20251115...)
        # Usarei a data e hora atuais
        doc_code = f"REC{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 1. MARCA D'ÁGUA (INTACTO)
        draw_watermark(c)

        # 2. CABEÇALHO (com logo do tenant)
        y_pos = draw_header(c, company_data, y_pos, logo_path=logo_path)

        # 3. TÍTULO (INTACTO)
        y_pos = draw_title(c, y_pos)

        # 4. INFORMAÇÕES DO PAGADOR (INTACTO)
        y_pos = draw_payer_info(c, customer_data, y_pos)

        # 5. CAIXA DE VALOR (INTACTO)
        amount = Decimal(str(installment_data.get('amount', 0)))
        y_pos = draw_amount(c, amount, y_pos)

        # 6. DETALHES DO PAGAMENTO (INTACTO)
        y_pos = draw_payment_details(c, installment_data, y_pos)

        # 7. RODAPÉ (INTACTO)
        draw_footer(c, company_data, y_position=y_pos)

        # 7.5. ARTIGOS LEGAIS (NOVO)
        draw_legal_articles(c) # <-- NOVA CHAMADA DE FUNÇÃO

        # 8. CÓDIGO DO DOCUMENTO (INTACTO)
        draw_document_code(c, doc_code)

        # ✅ FINALIZAR PDF
        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"✅ Recibo FARAÔNICO (V4.3) gerado - Valor: R$ {amount:.2f}")
        return pdf_bytes

    except Exception as e:
        logger.error(f"❌ Erro ao gerar PDF: {str(e)}")
        buffer.close()
        raise
