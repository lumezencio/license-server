"""
Servico de Emissao de NF-e (Nota Fiscal Eletronica)

Este modulo implementa a comunicacao com os web services da SEFAZ
para emissao, consulta, cancelamento e inutilizacao de NF-e.

Utiliza as bibliotecas:
- lxml: Manipulacao de XML
- signxml: Assinatura digital XML
- zeep: Cliente SOAP para web services
- cryptography: Manipulacao de certificados digitais

Documentacao SEFAZ: https://www.nfe.fazenda.gov.br/portal/principal.aspx
"""

import logging
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.fernet import Fernet
from signxml import XMLSigner, XMLVerifier
from signxml.algorithms import SignatureMethod, DigestAlgorithm
import zeep
from zeep.transports import Transport
from zeep.wsse.signature import Signature
import asyncpg
import uuid

logger = logging.getLogger(__name__)

# =====================================================
# URLS DOS WEB SERVICES SEFAZ POR UF
# =====================================================

# URLs de Homologacao (testes)
SEFAZ_URLS_HOMOLOGACAO = {
    # Autorizadores proprios
    'AM': {
        'NfeAutorizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeAutorizacao4',
        'NfeRetAutorizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeConsulta4',
        'NfeStatusServico': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeStatusServico4',
        'RecepcaoEvento': 'https://homnfe.sefaz.am.gov.br/services2/services/RecepcaoEvento4',
        'NfeInutilizacao': 'https://homnfe.sefaz.am.gov.br/services2/services/NfeInutilizacao4',
    },
    'BA': {
        'NfeAutorizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeAutorizacao4/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeRetAutorizacao4/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeConsultaProtocolo4/NFeConsultaProtocolo4.asmx',
        'NfeStatusServico': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeStatusServico4/NFeStatusServico4.asmx',
        'RecepcaoEvento': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
        'NfeInutilizacao': 'https://hnfe.sefaz.ba.gov.br/webservices/NFeInutilizacao4/NFeInutilizacao4.asmx',
    },
    'GO': {
        'NfeAutorizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://homolog.sefaz.go.gov.br/nfe/services/NFeInutilizacao4',
    },
    'MG': {
        'NfeAutorizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsulta4',
        'NfeStatusServico': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4',
    },
    'MS': {
        'NfeAutorizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeStatusServico4',
        'RecepcaoEvento': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://hom.nfe.sefaz.ms.gov.br/ws/NFeInutilizacao4',
    },
    'MT': {
        'NfeAutorizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeAutorizacao4',
        'NfeRetAutorizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta4',
        'NfeStatusServico': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeStatusServico4',
        'RecepcaoEvento': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/RecepcaoEvento4',
        'NfeInutilizacao': 'https://homologacao.sefaz.mt.gov.br/nfews/v2/services/NfeInutilizacao4',
    },
    'PE': {
        'NfeAutorizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeStatusServico4',
        'RecepcaoEvento': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://nfehomolog.sefaz.pe.gov.br/nfe-service/services/NFeInutilizacao4',
    },
    'PR': {
        'NfeAutorizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeAutorizacao4',
        'NfeRetAutorizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRetAutorizacao4',
        'NfeConsultaProtocolo': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeConsultaProtocolo4',
        'NfeStatusServico': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeStatusServico4',
        'RecepcaoEvento': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeRecepcaoEvento4',
        'NfeInutilizacao': 'https://homologacao.nfe.sefa.pr.gov.br/nfe/NFeInutilizacao4',
    },
    'RS': {
        'NfeAutorizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'NfeStatusServico': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'RecepcaoEvento': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'NfeInutilizacao': 'https://nfe-homologacao.sefazrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx',
    },
    'SP': {
        'NfeAutorizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx',
        'NfeRetAutorizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferetautorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx',
        'NfeStatusServico': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx',
        'RecepcaoEvento': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx',
        'NfeInutilizacao': 'https://homologacao.nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx',
    },
    # SVRS - Estados que usam SEFAZ Virtual RS
    'SVRS': {
        'NfeAutorizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx',
        'NfeRetAutorizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeRetAutorizacao/NFeRetAutorizacao4.asmx',
        'NfeConsultaProtocolo': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx',
        'NfeStatusServico': 'https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx',
        'RecepcaoEvento': 'https://nfe-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx',
        'NfeInutilizacao': 'https://nfe-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx',
    },
}

# Estados que usam SVRS (SEFAZ Virtual RS)
UF_SVRS = ['AC', 'AL', 'AP', 'DF', 'ES', 'PB', 'PI', 'RJ', 'RN', 'RO', 'RR', 'SC', 'SE', 'TO']

# Codigo UF IBGE
CODIGO_UF = {
    'AC': '12', 'AL': '27', 'AP': '16', 'AM': '13', 'BA': '29', 'CE': '23',
    'DF': '53', 'ES': '32', 'GO': '52', 'MA': '21', 'MT': '51', 'MS': '50',
    'MG': '31', 'PA': '15', 'PB': '25', 'PR': '41', 'PE': '26', 'PI': '22',
    'RJ': '33', 'RN': '24', 'RS': '43', 'RO': '11', 'RR': '14', 'SC': '42',
    'SP': '35', 'SE': '28', 'TO': '17'
}

# Namespace da NF-e 4.0
NFE_NAMESPACE = 'http://www.portalfiscal.inf.br/nfe'
NSMAP = {None: NFE_NAMESPACE}


class NFeService:
    """Servico para emissao e gerenciamento de NF-e"""

    def __init__(self, secret_key: str):
        """
        Inicializa o servico de NF-e.

        Args:
            secret_key: Chave secreta para descriptografar senha do certificado
        """
        self.secret_key = secret_key
        self._certificate = None
        self._private_key = None

    def _decrypt_password(self, encrypted_password: str) -> str:
        """Descriptografa a senha do certificado"""
        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret_key.encode()).digest())
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_password.encode()).decode()

    def load_certificate(self, cert_data: bytes, encrypted_password: str) -> Tuple[Any, Any]:
        """
        Carrega o certificado digital A1.

        Args:
            cert_data: Bytes do arquivo .pfx
            encrypted_password: Senha criptografada

        Returns:
            Tupla (private_key, certificate)
        """
        password = self._decrypt_password(encrypted_password)
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            cert_data, password.encode(), default_backend()
        )
        self._private_key = private_key
        self._certificate = certificate
        return private_key, certificate

    def get_sefaz_url(self, uf: str, servico: str, ambiente: int = 2) -> str:
        """
        Retorna a URL do web service SEFAZ para o estado e servico.

        Args:
            uf: Sigla do estado (ex: 'SP', 'RJ')
            servico: Nome do servico (ex: 'NfeAutorizacao', 'NfeStatusServico')
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            URL do web service
        """
        # Por enquanto so temos URLs de homologacao
        if ambiente == 1:
            # TODO: Adicionar URLs de producao
            raise NotImplementedError("URLs de producao ainda nao implementadas")

        # Verifica se UF usa SVRS
        if uf in UF_SVRS:
            urls = SEFAZ_URLS_HOMOLOGACAO.get('SVRS', {})
        else:
            urls = SEFAZ_URLS_HOMOLOGACAO.get(uf, SEFAZ_URLS_HOMOLOGACAO.get('SVRS', {}))

        return urls.get(servico, '')

    def gerar_chave_acesso(
        self,
        uf: str,
        data_emissao: datetime,
        cnpj: str,
        modelo: int,
        serie: int,
        numero: int,
        tipo_emissao: int = 1,
        codigo_numerico: str = None
    ) -> str:
        """
        Gera a chave de acesso da NF-e (44 digitos).

        Formato: cUF + AAMM + CNPJ + mod + serie + nNF + tpEmis + cNF + cDV

        Args:
            uf: Sigla do estado
            data_emissao: Data de emissao
            cnpj: CNPJ do emitente (apenas numeros)
            modelo: Modelo (55=NF-e, 65=NFC-e)
            serie: Serie da nota
            numero: Numero da nota
            tipo_emissao: Tipo de emissao (1=Normal, 9=Contingencia)
            codigo_numerico: Codigo numerico aleatorio (8 digitos)

        Returns:
            Chave de acesso com 44 digitos
        """
        cuf = CODIGO_UF.get(uf, '35')  # Default SP
        aamm = data_emissao.strftime('%y%m')
        cnpj_limpo = cnpj.replace('.', '').replace('/', '').replace('-', '').zfill(14)
        mod = str(modelo).zfill(2)
        ser = str(serie).zfill(3)
        nnf = str(numero).zfill(9)
        tpemis = str(tipo_emissao)

        if codigo_numerico is None:
            import random
            codigo_numerico = str(random.randint(10000000, 99999999))

        cnf = codigo_numerico.zfill(8)

        # Chave sem digito verificador
        chave_sem_dv = f"{cuf}{aamm}{cnpj_limpo}{mod}{ser}{nnf}{tpemis}{cnf}"

        # Calcula digito verificador (modulo 11)
        dv = self._calcular_dv_mod11(chave_sem_dv)

        return f"{chave_sem_dv}{dv}"

    def _calcular_dv_mod11(self, chave: str) -> str:
        """Calcula digito verificador modulo 11"""
        peso = 2
        soma = 0

        for digito in reversed(chave):
            soma += int(digito) * peso
            peso += 1
            if peso > 9:
                peso = 2

        resto = soma % 11
        dv = 11 - resto

        if dv >= 10:
            return '0'
        return str(dv)

    def gerar_xml_nfe(
        self,
        dados_nfe: Dict[str, Any],
        dados_emitente: Dict[str, Any],
        dados_destinatario: Dict[str, Any],
        itens: list,
        chave_acesso: str
    ) -> str:
        """
        Gera o XML da NF-e no formato exigido pela SEFAZ.

        Args:
            dados_nfe: Dados gerais da NF-e (numero, serie, data, etc)
            dados_emitente: Dados do emitente (empresa)
            dados_destinatario: Dados do destinatario (cliente)
            itens: Lista de itens da nota
            chave_acesso: Chave de acesso gerada

        Returns:
            XML da NF-e como string
        """
        # Cria elemento raiz
        nfe = etree.Element('{%s}NFe' % NFE_NAMESPACE, nsmap=NSMAP)

        # infNFe - Informacoes da NF-e
        infNFe = etree.SubElement(nfe, '{%s}infNFe' % NFE_NAMESPACE)
        infNFe.set('versao', '4.00')
        infNFe.set('Id', f'NFe{chave_acesso}')

        # ide - Identificacao da NF-e
        ide = etree.SubElement(infNFe, '{%s}ide' % NFE_NAMESPACE)
        etree.SubElement(ide, '{%s}cUF' % NFE_NAMESPACE).text = dados_nfe['cUF']
        etree.SubElement(ide, '{%s}cNF' % NFE_NAMESPACE).text = dados_nfe['cNF']
        etree.SubElement(ide, '{%s}natOp' % NFE_NAMESPACE).text = dados_nfe.get('natOp', 'VENDA')
        etree.SubElement(ide, '{%s}mod' % NFE_NAMESPACE).text = str(dados_nfe.get('mod', 55))
        etree.SubElement(ide, '{%s}serie' % NFE_NAMESPACE).text = str(dados_nfe['serie'])
        etree.SubElement(ide, '{%s}nNF' % NFE_NAMESPACE).text = str(dados_nfe['nNF'])
        etree.SubElement(ide, '{%s}dhEmi' % NFE_NAMESPACE).text = dados_nfe['dhEmi']
        etree.SubElement(ide, '{%s}tpNF' % NFE_NAMESPACE).text = '1'  # 1=Saida
        etree.SubElement(ide, '{%s}idDest' % NFE_NAMESPACE).text = dados_nfe.get('idDest', '1')
        etree.SubElement(ide, '{%s}cMunFG' % NFE_NAMESPACE).text = dados_nfe['cMunFG']
        etree.SubElement(ide, '{%s}tpImp' % NFE_NAMESPACE).text = '1'  # DANFE retrato
        etree.SubElement(ide, '{%s}tpEmis' % NFE_NAMESPACE).text = str(dados_nfe.get('tpEmis', 1))
        etree.SubElement(ide, '{%s}cDV' % NFE_NAMESPACE).text = chave_acesso[-1]
        etree.SubElement(ide, '{%s}tpAmb' % NFE_NAMESPACE).text = str(dados_nfe['tpAmb'])
        etree.SubElement(ide, '{%s}finNFe' % NFE_NAMESPACE).text = '1'  # NF-e normal
        etree.SubElement(ide, '{%s}indFinal' % NFE_NAMESPACE).text = '1'  # Consumidor final
        etree.SubElement(ide, '{%s}indPres' % NFE_NAMESPACE).text = '1'  # Presencial
        etree.SubElement(ide, '{%s}procEmi' % NFE_NAMESPACE).text = '0'  # Emissao propria
        etree.SubElement(ide, '{%s}verProc' % NFE_NAMESPACE).text = 'Enterprise System 1.0'

        # emit - Emitente
        emit = etree.SubElement(infNFe, '{%s}emit' % NFE_NAMESPACE)
        etree.SubElement(emit, '{%s}CNPJ' % NFE_NAMESPACE).text = dados_emitente['CNPJ']
        etree.SubElement(emit, '{%s}xNome' % NFE_NAMESPACE).text = dados_emitente['xNome'][:60]

        if dados_emitente.get('xFant'):
            etree.SubElement(emit, '{%s}xFant' % NFE_NAMESPACE).text = dados_emitente['xFant'][:60]

        # Endereco do emitente
        enderEmit = etree.SubElement(emit, '{%s}enderEmit' % NFE_NAMESPACE)
        etree.SubElement(enderEmit, '{%s}xLgr' % NFE_NAMESPACE).text = dados_emitente.get('xLgr', '')[:60]
        etree.SubElement(enderEmit, '{%s}nro' % NFE_NAMESPACE).text = dados_emitente.get('nro', 'S/N')[:60]
        if dados_emitente.get('xCpl'):
            etree.SubElement(enderEmit, '{%s}xCpl' % NFE_NAMESPACE).text = dados_emitente['xCpl'][:60]
        etree.SubElement(enderEmit, '{%s}xBairro' % NFE_NAMESPACE).text = dados_emitente.get('xBairro', '')[:60]
        etree.SubElement(enderEmit, '{%s}cMun' % NFE_NAMESPACE).text = dados_emitente.get('cMun', '')
        etree.SubElement(enderEmit, '{%s}xMun' % NFE_NAMESPACE).text = dados_emitente.get('xMun', '')[:60]
        etree.SubElement(enderEmit, '{%s}UF' % NFE_NAMESPACE).text = dados_emitente.get('UF', '')
        etree.SubElement(enderEmit, '{%s}CEP' % NFE_NAMESPACE).text = dados_emitente.get('CEP', '').replace('-', '')
        etree.SubElement(enderEmit, '{%s}cPais' % NFE_NAMESPACE).text = '1058'  # Brasil
        etree.SubElement(enderEmit, '{%s}xPais' % NFE_NAMESPACE).text = 'BRASIL'

        if dados_emitente.get('fone'):
            etree.SubElement(enderEmit, '{%s}fone' % NFE_NAMESPACE).text = dados_emitente['fone'].replace('(', '').replace(')', '').replace('-', '').replace(' ', '')

        etree.SubElement(emit, '{%s}IE' % NFE_NAMESPACE).text = dados_emitente.get('IE', 'ISENTO')
        etree.SubElement(emit, '{%s}CRT' % NFE_NAMESPACE).text = str(dados_emitente.get('CRT', 1))  # Simples Nacional

        # dest - Destinatario
        dest = etree.SubElement(infNFe, '{%s}dest' % NFE_NAMESPACE)

        cpf_cnpj = dados_destinatario.get('CPF') or dados_destinatario.get('CNPJ', '')
        cpf_cnpj_limpo = cpf_cnpj.replace('.', '').replace('/', '').replace('-', '')

        if len(cpf_cnpj_limpo) == 11:
            etree.SubElement(dest, '{%s}CPF' % NFE_NAMESPACE).text = cpf_cnpj_limpo
        elif len(cpf_cnpj_limpo) == 14:
            etree.SubElement(dest, '{%s}CNPJ' % NFE_NAMESPACE).text = cpf_cnpj_limpo

        etree.SubElement(dest, '{%s}xNome' % NFE_NAMESPACE).text = dados_destinatario.get('xNome', 'CONSUMIDOR')[:60]

        # Endereco do destinatario
        if dados_destinatario.get('xLgr'):
            enderDest = etree.SubElement(dest, '{%s}enderDest' % NFE_NAMESPACE)
            etree.SubElement(enderDest, '{%s}xLgr' % NFE_NAMESPACE).text = dados_destinatario.get('xLgr', '')[:60]
            etree.SubElement(enderDest, '{%s}nro' % NFE_NAMESPACE).text = dados_destinatario.get('nro', 'S/N')[:60]
            if dados_destinatario.get('xCpl'):
                etree.SubElement(enderDest, '{%s}xCpl' % NFE_NAMESPACE).text = dados_destinatario['xCpl'][:60]
            etree.SubElement(enderDest, '{%s}xBairro' % NFE_NAMESPACE).text = dados_destinatario.get('xBairro', '')[:60]
            etree.SubElement(enderDest, '{%s}cMun' % NFE_NAMESPACE).text = dados_destinatario.get('cMun', '')
            etree.SubElement(enderDest, '{%s}xMun' % NFE_NAMESPACE).text = dados_destinatario.get('xMun', '')[:60]
            etree.SubElement(enderDest, '{%s}UF' % NFE_NAMESPACE).text = dados_destinatario.get('UF', '')
            etree.SubElement(enderDest, '{%s}CEP' % NFE_NAMESPACE).text = dados_destinatario.get('CEP', '').replace('-', '')
            etree.SubElement(enderDest, '{%s}cPais' % NFE_NAMESPACE).text = '1058'
            etree.SubElement(enderDest, '{%s}xPais' % NFE_NAMESPACE).text = 'BRASIL'

        etree.SubElement(dest, '{%s}indIEDest' % NFE_NAMESPACE).text = '9'  # Nao contribuinte

        # det - Detalhes dos produtos
        for i, item in enumerate(itens, start=1):
            det = etree.SubElement(infNFe, '{%s}det' % NFE_NAMESPACE)
            det.set('nItem', str(i))

            # Produto
            prod = etree.SubElement(det, '{%s}prod' % NFE_NAMESPACE)
            etree.SubElement(prod, '{%s}cProd' % NFE_NAMESPACE).text = item.get('cProd', str(i))[:60]
            etree.SubElement(prod, '{%s}cEAN' % NFE_NAMESPACE).text = item.get('cEAN', 'SEM GTIN')
            etree.SubElement(prod, '{%s}xProd' % NFE_NAMESPACE).text = item.get('xProd', 'PRODUTO')[:120]
            etree.SubElement(prod, '{%s}NCM' % NFE_NAMESPACE).text = item.get('NCM', '00000000')
            etree.SubElement(prod, '{%s}CFOP' % NFE_NAMESPACE).text = item.get('CFOP', '5102')
            etree.SubElement(prod, '{%s}uCom' % NFE_NAMESPACE).text = item.get('uCom', 'UN')[:6]
            etree.SubElement(prod, '{%s}qCom' % NFE_NAMESPACE).text = f"{float(item.get('qCom', 1)):.4f}"
            etree.SubElement(prod, '{%s}vUnCom' % NFE_NAMESPACE).text = f"{float(item.get('vUnCom', 0)):.10f}"
            etree.SubElement(prod, '{%s}vProd' % NFE_NAMESPACE).text = f"{float(item.get('vProd', 0)):.2f}"
            etree.SubElement(prod, '{%s}cEANTrib' % NFE_NAMESPACE).text = item.get('cEANTrib', 'SEM GTIN')
            etree.SubElement(prod, '{%s}uTrib' % NFE_NAMESPACE).text = item.get('uTrib', item.get('uCom', 'UN'))[:6]
            etree.SubElement(prod, '{%s}qTrib' % NFE_NAMESPACE).text = f"{float(item.get('qTrib', item.get('qCom', 1))):.4f}"
            etree.SubElement(prod, '{%s}vUnTrib' % NFE_NAMESPACE).text = f"{float(item.get('vUnTrib', item.get('vUnCom', 0))):.10f}"
            etree.SubElement(prod, '{%s}indTot' % NFE_NAMESPACE).text = '1'  # Compoe total

            # Imposto
            imposto = etree.SubElement(det, '{%s}imposto' % NFE_NAMESPACE)

            # ICMS
            icms = etree.SubElement(imposto, '{%s}ICMS' % NFE_NAMESPACE)
            icms_sn = etree.SubElement(icms, '{%s}ICMSSN102' % NFE_NAMESPACE)  # Simples Nacional
            etree.SubElement(icms_sn, '{%s}orig' % NFE_NAMESPACE).text = item.get('orig', '0')
            etree.SubElement(icms_sn, '{%s}CSOSN' % NFE_NAMESPACE).text = item.get('CSOSN', '102')

            # PIS
            pis = etree.SubElement(imposto, '{%s}PIS' % NFE_NAMESPACE)
            pis_nt = etree.SubElement(pis, '{%s}PISOutr' % NFE_NAMESPACE)
            etree.SubElement(pis_nt, '{%s}CST' % NFE_NAMESPACE).text = item.get('CST_PIS', '99')
            etree.SubElement(pis_nt, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(pis_nt, '{%s}pPIS' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(pis_nt, '{%s}vPIS' % NFE_NAMESPACE).text = '0.00'

            # COFINS
            cofins = etree.SubElement(imposto, '{%s}COFINS' % NFE_NAMESPACE)
            cofins_nt = etree.SubElement(cofins, '{%s}COFINSOutr' % NFE_NAMESPACE)
            etree.SubElement(cofins_nt, '{%s}CST' % NFE_NAMESPACE).text = item.get('CST_COFINS', '99')
            etree.SubElement(cofins_nt, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(cofins_nt, '{%s}pCOFINS' % NFE_NAMESPACE).text = '0.00'
            etree.SubElement(cofins_nt, '{%s}vCOFINS' % NFE_NAMESPACE).text = '0.00'

        # total - Totais da NF-e
        total = etree.SubElement(infNFe, '{%s}total' % NFE_NAMESPACE)
        icms_tot = etree.SubElement(total, '{%s}ICMSTot' % NFE_NAMESPACE)
        etree.SubElement(icms_tot, '{%s}vBC' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSDeson' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPUFDest' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSUFDest' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vICMSUFRemet' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCP' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vBCST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPST' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vFCPSTRet' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vProd' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vProd', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vFrete' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vFrete', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vSeg' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vDesc' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vDesc', 0)):.2f}"
        etree.SubElement(icms_tot, '{%s}vII' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vIPI' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vIPIDevol' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vPIS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vCOFINS' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vOutro' % NFE_NAMESPACE).text = '0.00'
        etree.SubElement(icms_tot, '{%s}vNF' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vNF', 0)):.2f}"

        # transp - Transporte
        transp = etree.SubElement(infNFe, '{%s}transp' % NFE_NAMESPACE)
        etree.SubElement(transp, '{%s}modFrete' % NFE_NAMESPACE).text = '9'  # Sem frete

        # pag - Pagamento
        pag = etree.SubElement(infNFe, '{%s}pag' % NFE_NAMESPACE)
        det_pag = etree.SubElement(pag, '{%s}detPag' % NFE_NAMESPACE)
        etree.SubElement(det_pag, '{%s}tPag' % NFE_NAMESPACE).text = dados_nfe.get('tPag', '01')  # Dinheiro
        etree.SubElement(det_pag, '{%s}vPag' % NFE_NAMESPACE).text = f"{float(dados_nfe.get('vNF', 0)):.2f}"

        # infAdic - Informacoes adicionais
        if dados_nfe.get('infCpl'):
            inf_adic = etree.SubElement(infNFe, '{%s}infAdic' % NFE_NAMESPACE)
            etree.SubElement(inf_adic, '{%s}infCpl' % NFE_NAMESPACE).text = dados_nfe['infCpl'][:5000]

        return etree.tostring(nfe, encoding='unicode', pretty_print=True)

    def assinar_xml(self, xml_str: str) -> str:
        """
        Assina digitalmente o XML da NF-e.

        Args:
            xml_str: XML da NF-e como string

        Returns:
            XML assinado como string
        """
        if not self._private_key or not self._certificate:
            raise ValueError("Certificado digital nao carregado")

        # Parse XML
        xml_doc = etree.fromstring(xml_str.encode('utf-8'))

        # Encontra elemento a ser assinado (infNFe)
        infNFe = xml_doc.find('.//{%s}infNFe' % NFE_NAMESPACE)
        if infNFe is None:
            raise ValueError("Elemento infNFe nao encontrado no XML")

        # Configura assinatura
        signer = XMLSigner(
            method=SignatureMethod.RSA_SHA1,
            digest_algorithm=DigestAlgorithm.SHA1,
            c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315',
            signature_algorithm='http://www.w3.org/2000/09/xmldsig#rsa-sha1'
        )

        # Assina
        signed_xml = signer.sign(
            xml_doc,
            key=self._private_key,
            cert=self._certificate,
            reference_uri=f"#{infNFe.get('Id')}"
        )

        return etree.tostring(signed_xml, encoding='unicode', pretty_print=True)

    async def consultar_status_servico(self, uf: str, ambiente: int = 2) -> Dict[str, Any]:
        """
        Consulta status do servico SEFAZ.

        Args:
            uf: Sigla do estado
            ambiente: 1=Producao, 2=Homologacao

        Returns:
            Dicionario com status do servico
        """
        url = self.get_sefaz_url(uf, 'NfeStatusServico', ambiente)

        if not url:
            return {
                'cStat': '999',
                'xMotivo': f'URL do servico nao encontrada para UF {uf}',
                'status': 'ERROR'
            }

        try:
            # Cria XML de consulta
            cons_stat = etree.Element('{%s}consStatServ' % NFE_NAMESPACE, nsmap=NSMAP)
            cons_stat.set('versao', '4.00')
            etree.SubElement(cons_stat, '{%s}tpAmb' % NFE_NAMESPACE).text = str(ambiente)
            etree.SubElement(cons_stat, '{%s}cUF' % NFE_NAMESPACE).text = CODIGO_UF.get(uf, '35')
            etree.SubElement(cons_stat, '{%s}xServ' % NFE_NAMESPACE).text = 'STATUS'

            xml_str = etree.tostring(cons_stat, encoding='unicode')

            # TODO: Implementar chamada SOAP com zeep
            # Por enquanto retorna simulacao
            return {
                'cStat': '107',
                'xMotivo': 'Servico em Operacao',
                'status': 'OK',
                'url': url
            }

        except Exception as e:
            logger.error(f"Erro ao consultar status SEFAZ: {e}")
            return {
                'cStat': '999',
                'xMotivo': str(e),
                'status': 'ERROR'
            }


# =====================================================
# FUNCOES AUXILIARES PARA USO NO GATEWAY
# =====================================================

async def processar_emissao_nfe(
    conn: asyncpg.Connection,
    nfe_id: str,
    service: NFeService
) -> Dict[str, Any]:
    """
    Processa a emissao de uma NF-e pendente.

    Args:
        conn: Conexao com banco do tenant
        nfe_id: ID da emissao
        service: Instancia do NFeService

    Returns:
        Resultado do processamento
    """
    try:
        # Busca dados da emissao
        nfe = await conn.fetchrow(
            "SELECT * FROM nfe_emissions WHERE id = $1",
            nfe_id
        )

        if not nfe:
            return {'success': False, 'error': 'Emissao nao encontrada'}

        if nfe['status'] != 'PENDING':
            return {'success': False, 'error': f'Status invalido: {nfe["status"]}'}

        # Busca configuracoes fiscais
        fiscal = await conn.fetchrow(
            "SELECT * FROM fiscal_settings WHERE is_active = TRUE LIMIT 1"
        )

        if not fiscal or not fiscal['is_configured']:
            return {'success': False, 'error': 'Configuracoes fiscais nao encontradas'}

        # Busca dados da venda
        sale = await conn.fetchrow(
            "SELECT * FROM sales WHERE id = $1",
            nfe['sale_id']
        )

        if not sale:
            return {'success': False, 'error': 'Venda nao encontrada'}

        # Busca itens da venda
        items = await conn.fetch(
            "SELECT * FROM sale_items WHERE sale_id = $1",
            sale['id']
        )

        # Busca dados do cliente
        customer = await conn.fetchrow(
            "SELECT * FROM customers WHERE id = $1",
            sale['customer_id']
        )

        # Busca dados da empresa
        company = await conn.fetchrow("SELECT * FROM companies LIMIT 1")

        if not company:
            return {'success': False, 'error': 'Dados da empresa nao cadastrados'}

        # Carrega certificado
        service.load_certificate(
            fiscal['certificate_file'],
            fiscal['certificate_password_encrypted']
        )

        # Gera chave de acesso
        data_emissao = datetime.now(timezone.utc)
        chave_acesso = service.gerar_chave_acesso(
            uf=fiscal['uf'],
            data_emissao=data_emissao,
            cnpj=company['document'],
            modelo=nfe['modelo'],
            serie=nfe['serie'],
            numero=nfe['numero_nfe'],
            tipo_emissao=1
        )

        # Prepara dados para geracao do XML
        dados_nfe = {
            'cUF': CODIGO_UF.get(fiscal['uf'], '35'),
            'cNF': chave_acesso[35:43],
            'natOp': 'VENDA DE MERCADORIA',
            'mod': nfe['modelo'],
            'serie': nfe['serie'],
            'nNF': nfe['numero_nfe'],
            'dhEmi': data_emissao.strftime('%Y-%m-%dT%H:%M:%S-03:00'),
            'tpAmb': fiscal['ambiente'],
            'cMunFG': fiscal['codigo_municipio'] or '3550308',
            'tpEmis': 1,
            'vProd': float(sale['subtotal'] or 0),
            'vDesc': float(sale['discount_amount'] or 0),
            'vFrete': float(sale['shipping_amount'] or 0),
            'vNF': float(sale['total_amount'] or 0),
            'tPag': '01',  # Dinheiro
        }

        dados_emitente = {
            'CNPJ': (company['document'] or '').replace('.', '').replace('/', '').replace('-', ''),
            'xNome': company['legal_name'] or company['trade_name'] or '',
            'xFant': company['trade_name'] or '',
            'xLgr': company['street'] or '',
            'nro': company['number'] or 'S/N',
            'xCpl': company['complement'] or '',
            'xBairro': company['neighborhood'] or '',
            'cMun': fiscal['codigo_municipio'] or '3550308',
            'xMun': company['city'] or '',
            'UF': company['state'] or fiscal['uf'],
            'CEP': (company['zip_code'] or '').replace('-', ''),
            'fone': company['phone'] or '',
            'IE': company['state_registration'] or 'ISENTO',
            'CRT': fiscal['regime_tributario'] or 1,
        }

        dados_destinatario = {}
        if customer:
            cpf_cnpj = (customer['cpf_cnpj'] or '').replace('.', '').replace('/', '').replace('-', '')
            if len(cpf_cnpj) == 11:
                dados_destinatario['CPF'] = cpf_cnpj
            else:
                dados_destinatario['CNPJ'] = cpf_cnpj

            nome = customer['company_name'] or customer['trade_name'] or \
                   f"{customer['first_name'] or ''} {customer['last_name'] or ''}".strip() or 'CONSUMIDOR'
            dados_destinatario['xNome'] = nome
            dados_destinatario['xLgr'] = customer['address'] or ''
            dados_destinatario['nro'] = customer['address_number'] or 'S/N'
            dados_destinatario['xCpl'] = customer['address_complement'] or ''
            dados_destinatario['xBairro'] = customer['neighborhood'] or ''
            dados_destinatario['xMun'] = customer['city'] or ''
            dados_destinatario['UF'] = customer['state'] or ''
            dados_destinatario['CEP'] = (customer['zip_code'] or '').replace('-', '')

        # Prepara itens
        itens_nfe = []
        for item in items:
            itens_nfe.append({
                'cProd': item['product_code'] or str(item['id'])[:60],
                'xProd': item['product_name'] or 'PRODUTO',
                'NCM': item['ncm_code'] or '00000000',
                'CFOP': item['cfop'] or '5102',
                'uCom': item['unit'] or 'UN',
                'qCom': float(item['quantity'] or 1),
                'vUnCom': float(item['unit_price'] or 0),
                'vProd': float(item['total_amount'] or 0),
            })

        # Gera XML
        xml_nfe = service.gerar_xml_nfe(
            dados_nfe=dados_nfe,
            dados_emitente=dados_emitente,
            dados_destinatario=dados_destinatario,
            itens=itens_nfe,
            chave_acesso=chave_acesso
        )

        # Assina XML
        xml_assinado = service.assinar_xml(xml_nfe)

        # Atualiza registro com XML e chave de acesso
        await conn.execute("""
            UPDATE nfe_emissions SET
                chave_acesso = $1,
                xml_nfe = $2,
                tentativas_envio = tentativas_envio + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """, chave_acesso, xml_assinado, nfe_id)

        # TODO: Enviar para SEFAZ via web service
        # Por enquanto, simula autorizacao em homologacao
        if fiscal['ambiente'] == 2:  # Homologacao
            protocolo = f"HOM{datetime.now().strftime('%Y%m%d%H%M%S')}"

            await conn.execute("""
                UPDATE nfe_emissions SET
                    status = 'AUTHORIZED',
                    protocolo_autorizacao = $1,
                    data_autorizacao = CURRENT_TIMESTAMP,
                    codigo_retorno = '100',
                    motivo_retorno = 'Autorizado o uso da NF-e (HOMOLOGACAO)',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """, protocolo, nfe_id)

            return {
                'success': True,
                'chave_acesso': chave_acesso,
                'protocolo': protocolo,
                'status': 'AUTHORIZED',
                'message': 'NF-e autorizada em homologacao'
            }
        else:
            # Em producao, precisaria enviar para SEFAZ
            return {
                'success': False,
                'error': 'Emissao em producao requer implementacao completa do web service'
            }

    except Exception as e:
        logger.error(f"Erro ao processar emissao NF-e: {e}")
        import traceback
        traceback.print_exc()

        # Atualiza com erro
        await conn.execute("""
            UPDATE nfe_emissions SET
                status = 'ERROR',
                ultimo_erro = $1,
                tentativas_envio = tentativas_envio + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
        """, str(e), nfe_id)

        return {
            'success': False,
            'error': str(e)
        }
